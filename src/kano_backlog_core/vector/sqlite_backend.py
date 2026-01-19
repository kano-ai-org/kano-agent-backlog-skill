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
    ):
        self._base_path = Path(path)
        self._collection = collection
        self._embedding_space_id = (embedding_space_id or "").strip() or None
        self._conn: Optional[sqlite3.Connection] = None
        self._dims: Optional[int] = None
        self._metric: Optional[str] = None
        self._db_path: Optional[Path] = None

    def _resolve_db_path(self) -> Path:
        if self._embedding_space_id:
            digest = hashlib.sha256(self._embedding_space_id.encode("utf-8")).hexdigest()[:12]
            # If base_path is a directory, place per-space db inside.
            if self._base_path.suffix:
                base_dir = self._base_path.parent
            else:
                base_dir = self._base_path
            return base_dir / f"{self._collection}.{digest}.sqlite3"

        # Fallback: treat base_path as a file when it has a suffix, otherwise default name.
        if self._base_path.suffix:
            return self._base_path
        return self._base_path / f"{self._collection}.sqlite3"

    def _ensure_connection(self) -> None:
        if self._conn is not None:
            return

        db_path = self._resolve_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path

        self._conn = sqlite3.connect(str(db_path), timeout=10.0)

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

    def upsert(self, chunk: VectorChunk) -> None:
        self._ensure_connection()
        assert self._conn is not None

        if chunk.vector is None:
            raise ValueError("chunk.vector must not be None")
        if self._dims is not None and len(chunk.vector) != self._dims:
            raise ValueError(
                f"Vector dims mismatch: expected={self._dims} got={len(chunk.vector)}"
            )

        vector_json = json.dumps(chunk.vector, separators=(",", ":"), ensure_ascii=True)
        metadata_json = json.dumps(chunk.metadata or {}, sort_keys=True, separators=(",", ":"))

        self._conn.execute(
            f"""
            INSERT OR REPLACE INTO {self._collection}_chunks
            (chunk_id, text, metadata_json, vector_json)
            VALUES (?, ?, ?, ?)
            """,
            (chunk.chunk_id, chunk.text, metadata_json, vector_json),
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
        cursor = self._conn.execute(
            f"""
            SELECT chunk_id, text, metadata_json, vector_json
            FROM {self._collection}_chunks
            """
        )

        results: List[VectorQueryResult] = []
        for chunk_id, text, metadata_json, vector_json in cursor:
            try:
                stored_vector = json.loads(vector_json)
            except (json.JSONDecodeError, TypeError):
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
        self._dims = int(dims) if dims is not None else self._dims
        self._metric = metric or self._metric

