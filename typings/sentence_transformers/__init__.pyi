from __future__ import annotations

from typing import Any, Sequence


class SentenceTransformer:
    max_seq_length: int

    def __init__(self, model_name: str, **kwargs: Any) -> None: ...

    def encode(
        self,
        sentences: Sequence[str],
        batch_size: int = 32,
        show_progress_bar: bool = False,
        normalize_embeddings: bool = False,
        **kwargs: Any,
    ) -> Any: ...

    def get_sentence_embedding_dimension(self) -> int: ...
