"""SQLite vector backend.

Local-first and dependency-minimal:
- Stores vectors and metadata in plain SQLite tables.
- Attempts to load sqlite-vec (vec0) if available, but correctness does not depend on it.

Notes:
- This backend is keyed by a single embedding space (dims + metric). If the on-disk
  schema indicates a mismatch, it fails fast.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import hashlib
import json
import sqlite3
import struct
from datetime import datetime

from .adapter import VectorBackendAdapter
from .types import VectorChunk, VectorQueryResult


class SQLiteVectorBackend(VectorBackendAdapter):
    """Vector backend using SQLite (optional sqlite-vec extension)."""

    def __init__(
        self,
        path: str,
        collection: str = "backlog",
        *,
        embedding_space_id: Optional[str] = None,
        storage_format: str = "binary",
    ):
        self._base_path = Path(path)
        self._collection = collection
        self._embedding_space_id = (embedding_space_id or "").strip() or None
        self._storage_format = storage_format if storage_format in ("binary", "json") else "binary"
        self._conn: Optional[sqlite3.Connection] = None
        self._dims: Optional[int] = None
        self._metric: Optional[str] = None
        self._db_path: Optional[Path] = None

    def _resolve_db_path(self) -> Path:
        if self._base_path.suffix:
            return self._base_path
            
        if self._embedding_space_id:
            components = {}
            for segment in self._embedding_space_id.split('|'):
                if ':' in segment:
                    key, value = segment.split(':', 1)
                    components[key] = value
            
            corpus = components.get('corpus', 'unknown')
            
            emb_parts = components.get('emb', '').split(':')
            if len(emb_parts) >= 3:
                emb_type = emb_parts[0]
                emb_dim = emb_parts[-1]
                emb_short = f"{emb_type}-{emb_dim}"
            else:
                emb_short = "unknown"
            
            digest = hashlib.sha256(self._embedding_space_id.encode("utf-8")).hexdigest()[:8]
            
            if self._base_path.suffix:
                base_dir = self._base_path.parent
            else:
                base_dir = self._base_path
            return base_dir / f"vectors.{corpus}.{emb_short}.{digest}.db"

        if self._base_path.suffix:
            return self._base_path
        return self._base_path / f"vectors.{self._collection}.db"

    def _write_metadata_file(self) -> None:
        """Write human-readable metadata file next to the SQLite database."""
        if not self._db_path or not self._embedding_space_id:
            return
        
        metadata_path = self._db_path.with_suffix('.meta')
        
        # Parse embedding_space_id to extract components
        parts = {}
        if self._embedding_space_id:
            for segment in self._embedding_space_id.split('|'):
                if ':' in segment:
                    key, *values = segment.split(':')
                    parts[key] = ':'.join(values)
        
        metadata = {
            "database": self._db_path.name,
            "collection": self._collection,
            "embedding_space_id": self._embedding_space_id,
            "hash": self._db_path.stem.split('.')[-1] if '.' in self._db_path.stem else None,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "config": {
                "dimensions": self._dims,
                "metric": self._metric,
                "storage_format": self._storage_format,
            },
            "components": parts,
        }
        
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
            f.write('\n')

    def _ensure_connection(self) -> None:
        if self._conn is not None:
            return

        db_path = self._resolve_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path

        self._conn = sqlite3.connect(str(db_path), timeout=10.0)
        # Some environments block SQLite rollback journal file operations (e.g., atomic renames),
        # which can surface as "disk I/O error" even when the directory is writable.
        # For derived caches, prefer in-memory journaling to keep the pipeline usable.
        try:
            self._conn.execute("PRAGMA journal_mode=MEMORY")
            self._conn.execute("PRAGMA synchronous=OFF")
            self._conn.execute("PRAGMA temp_store=MEMORY")
        except sqlite3.OperationalError:
            pass

        # Attempt to load vec extension (optional)
        try:
            self._conn.enable_load_extension(True)
            for ext_name in ["vec0", "vec", "sqlite-vec"]:
                try:
                    self._conn.load_extension(ext_name)
                    break
                except sqlite3.OperationalError:
                    continue
        except (sqlite3.OperationalError, AttributeError):
            pass

    def _validate_metric(self, metric: str) -> str:
        m = metric.strip().lower()
        if m not in {"cosine", "l2", "ip"}:
            raise ValueError(f"Unsupported metric: {metric}")
        return m

    def _write_meta(self, key: str, value: str) -> None:
        assert self._conn is not None
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (key, value),
        )

    def _read_meta(self, key: str) -> Optional[str]:
        assert self._conn is not None
        cur = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,))
        row = cur.fetchone()
        return row[0] if row else None

    def prepare(self, schema: Dict[str, Any], dims: int, metric: str = "cosine") -> None:
        self._ensure_connection()
        assert self._conn is not None

        if dims <= 0:
            raise ValueError("dims must be positive")

        metric_norm = self._validate_metric(metric)

        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )

        # Fail fast if existing DB has incompatible dims/metric.
        existing_dims = self._read_meta("dims")
        existing_metric = self._read_meta("metric")
        if existing_dims is not None and int(existing_dims) != dims:
            raise ValueError(
                f"Vector DB dims mismatch: db={existing_dims} config={dims} (path={self._db_path})"
            )
        if existing_metric is not None and existing_metric != metric_norm:
            raise ValueError(
                f"Vector DB metric mismatch: db={existing_metric} config={metric_norm} (path={self._db_path})"
            )

        self._dims = dims
        self._metric = metric_norm

        self._write_meta("dims", str(dims))
        self._write_meta("metric", metric_norm)
        self._write_meta("storage_format", self._storage_format)
        if self._embedding_space_id:
            self._write_meta("embedding_space_id", self._embedding_space_id)
        self._write_meta("schema_version", "1")

        self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self._collection}_chunks (
                chunk_id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                vector_json TEXT NOT NULL
            )
            """
        )

        # Optional vec0 virtual table creation (ignored if extension missing)
        try:
            self._conn.execute(
                f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS {self._collection}_vec
                USING vec0(
                    chunk_id TEXT PRIMARY KEY,
                    embedding FLOAT[{dims}]
                    distance_metric={metric_norm}
                )
                """
            )
        except sqlite3.OperationalError:
            pass

        self._conn.commit()
        
        self._write_metadata_file()

    def upsert(self, chunk: VectorChunk) -> None:
        self._ensure_connection()
        assert self._conn is not None

        if chunk.vector is None:
            raise ValueError("chunk.vector must not be None")
        if self._dims is not None and len(chunk.vector) != self._dims:
            raise ValueError(
                f"Vector dims mismatch: expected={self._dims} got={len(chunk.vector)}"
            )

        if self._storage_format == "binary":
            vector_data = struct.pack(f'{len(chunk.vector)}f', *chunk.vector)
        else:
            vector_data = json.dumps(chunk.vector, separators=(",", ":"), ensure_ascii=True)
        
        metadata_json = json.dumps(chunk.metadata or {}, sort_keys=True, separators=(",", ":"))

        self._conn.execute(
            f"""
            INSERT OR REPLACE INTO {self._collection}_chunks
            (chunk_id, text, metadata_json, vector_json)
            VALUES (?, ?, ?, ?)
            """,
            (chunk.chunk_id, chunk.text, metadata_json, vector_data),
        )

        # Optional: sync vec0 table if present
        try:
            vec_data = json.dumps(chunk.vector, separators=(",", ":")).encode("utf-8")
            self._conn.execute(
                f"INSERT OR REPLACE INTO {self._collection}_vec (chunk_id, embedding) VALUES (?, ?)",
                (chunk.chunk_id, vec_data),
            )
        except sqlite3.OperationalError:
            pass

    def list_chunk_ids(self) -> List[str]:
        """Return all chunk_ids currently stored in this collection."""
        self._ensure_connection()
        assert self._conn is not None
        cursor = self._conn.execute(
            f"SELECT chunk_id FROM {self._collection}_chunks"
        )
        return [str(r[0]) for r in cursor.fetchall()]

    def prune_to_chunk_ids(self, keep_chunk_ids: List[str]) -> None:
        """Delete rows not present in keep_chunk_ids.

        Intended for keeping the vector DB in sync with a canonical chunk contract.
        """
        self._ensure_connection()
        assert self._conn is not None

        cur = self._conn.cursor()
        cur.execute("CREATE TEMP TABLE IF NOT EXISTS tmp_keep (chunk_id TEXT PRIMARY KEY)")
        cur.execute("DELETE FROM tmp_keep")

        if not keep_chunk_ids:
            cur.execute(f"DELETE FROM {self._collection}_chunks")
            try:
                cur.execute(f"DELETE FROM {self._collection}_vec")
            except sqlite3.OperationalError:
                pass
            self._conn.commit()
            return

        BATCH = 500
        for i in range(0, len(keep_chunk_ids), BATCH):
            batch = keep_chunk_ids[i : i + BATCH]
            cur.executemany(
                "INSERT OR IGNORE INTO tmp_keep(chunk_id) VALUES (?)",
                [(str(cid),) for cid in batch],
            )

        cur.execute(
            f"DELETE FROM {self._collection}_chunks WHERE chunk_id NOT IN (SELECT chunk_id FROM tmp_keep)"
        )
        try:
            cur.execute(
                f"DELETE FROM {self._collection}_vec WHERE chunk_id NOT IN (SELECT chunk_id FROM tmp_keep)"
            )
        except sqlite3.OperationalError:
            pass

        self._conn.commit()

    def delete(self, chunk_id: str) -> None:
        self._ensure_connection()
        assert self._conn is not None

        self._conn.execute(
            f"DELETE FROM {self._collection}_chunks WHERE chunk_id = ?", (chunk_id,)
        )
        try:
            self._conn.execute(
                f"DELETE FROM {self._collection}_vec WHERE chunk_id = ?", (chunk_id,)
            )
        except sqlite3.OperationalError:
            pass

    def query(
        self, vector: List[float], k: int = 10, filters: Dict[str, Any] | None = None
    ) -> List[VectorQueryResult]:
        self._ensure_connection()
        assert self._conn is not None

        if self._dims is not None and len(vector) != self._dims:
            raise ValueError(
                f"Query vector dims mismatch: expected={self._dims} got={len(vector)}"
            )

        # MVP: brute-force scan for correctness. (vec0, if present, can be used later.)
        #
        # Supported filters (SQLite backend only):
        # - filters={"chunk_ids": ["...", ...]} limits the scan to a candidate set.
        chunk_ids = None
        if filters and isinstance(filters, dict):
            chunk_ids = filters.get("chunk_ids")

        base_sql = (
            f"SELECT chunk_id, text, metadata_json, vector_json FROM {self._collection}_chunks"
        )

        cursor = None
        chunk_id_set = None
        if chunk_ids is not None:
            chunk_ids_list = [str(x) for x in list(chunk_ids)]
            if not chunk_ids_list:
                return []

            # SQLite has a variable limit (commonly 999). For large candidate sets,
            # fall back to filtering in Python.
            if len(chunk_ids_list) <= 900:
                placeholders = ",".join(["?"] * len(chunk_ids_list))
                sql = f"{base_sql} WHERE chunk_id IN ({placeholders})"
                cursor = self._conn.execute(sql, tuple(chunk_ids_list))
            else:
                chunk_id_set = set(chunk_ids_list)
                cursor = self._conn.execute(base_sql)
        else:
            cursor = self._conn.execute(base_sql)

        results: List[VectorQueryResult] = []
        for chunk_id, text, metadata_json, vector_data in cursor:
            if chunk_id_set is not None and str(chunk_id) not in chunk_id_set:
                continue
            try:
                if isinstance(vector_data, bytes):
                    stored_vector = list(struct.unpack(f'{len(vector_data)//4}f', vector_data))
                else:
                    stored_vector = json.loads(vector_data)
            except (json.JSONDecodeError, TypeError, struct.error):
                continue

            score = self._score(vector, stored_vector)

            try:
                metadata = json.loads(metadata_json) if metadata_json else {}
            except json.JSONDecodeError:
                metadata = {}

            results.append(
                VectorQueryResult(chunk_id=chunk_id, score=score, metadata=metadata, text=text)
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k]

    def _score(self, vec1: List[float], vec2: List[float]) -> float:
        if len(vec1) != len(vec2):
            return float("-inf")

        metric = self._metric or "cosine"
        if metric == "cosine":
            return self._cosine_similarity(vec1, vec2)
        if metric == "ip":
            return self._dot(vec1, vec2)
        if metric == "l2":
            # negative distance so that higher score is better
            return -self._l2_distance(vec1, vec2)

        return self._cosine_similarity(vec1, vec2)

    @staticmethod
    def _dot(vec1: List[float], vec2: List[float]) -> float:
        return sum(a * b for a, b in zip(vec1, vec2))

    @staticmethod
    def _l2_distance(vec1: List[float], vec2: List[float]) -> float:
        return sum((a - b) ** 2 for a, b in zip(vec1, vec2)) ** 0.5

    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        dot = sum(a * b for a, b in zip(vec1, vec2))
        mag1 = sum(a * a for a in vec1) ** 0.5
        mag2 = sum(b * b for b in vec2) ** 0.5
        if mag1 == 0 or mag2 == 0:
            return 0.0
        return dot / (mag1 * mag2)

    def persist(self) -> None:
        if self._conn:
            self._conn.commit()

    def load(self) -> None:
        self._ensure_connection()
        assert self._conn is not None

        # Load dims/metric if present.
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        dims = self._read_meta("dims")
        metric = self._read_meta("metric")
        storage_format = self._read_meta("storage_format")
        self._dims = int(dims) if dims is not None else self._dims
        self._metric = metric or self._metric
        if storage_format:
            self._storage_format = storage_format
        
        self._write_metadata_file()

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the vector index."""
        self._ensure_connection()
        assert self._conn is not None

        # Ensure meta table exists
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )

        # Check if chunks table exists
        cursor = self._conn.execute(
            f"""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='{self._collection}_chunks'
            """
        )
        table_exists = cursor.fetchone() is not None

        if not table_exists:
            return {
                "chunks_count": 0,
                "dims": self._dims,
                "metric": self._metric,
                "embedding_space_id": self._embedding_space_id,
                "table_exists": False,
            }

        # Get chunk count
        cursor = self._conn.execute(f"SELECT COUNT(*) FROM {self._collection}_chunks")
        chunks_count = cursor.fetchone()[0]

        # Get metadata
        dims = self._read_meta("dims")
        metric = self._read_meta("metric")
        embedding_space_id = self._read_meta("embedding_space_id")
        schema_version = self._read_meta("schema_version")

        return {
            "chunks_count": chunks_count,
            "dims": int(dims) if dims else self._dims,
            "metric": metric or self._metric,
            "embedding_space_id": embedding_space_id or self._embedding_space_id,
            "schema_version": schema_version,
            "table_exists": True,
            "db_path": str(self._db_path) if self._db_path else None,
        }

