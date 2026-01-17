"""OpenAI embedding adapter implementation."""

from typing import List, Optional
import time

from ..adapter import EmbeddingAdapter
from ..types import EmbeddingResult, EmbeddingTelemetry

class OpenAIEmbeddingAdapter(EmbeddingAdapter):
    """Embedding adapter for OpenAI models."""
    
    def __init__(self, model_name: str = "text-embedding-3-small", api_key: Optional[str] = None):
        super().__init__(model_name)
        self._api_key = api_key
        self._client = None
        self._dimension = 1536 if "small" in model_name else 3072
        
    def _ensure_client(self):
        if self._client is not None:
            return
            
        try:
            import openai
        except ImportError:
            raise ImportError("openai package required for OpenAI embeddings. Install with: pip install openai")
        
        if self._api_key:
            self._client = openai.OpenAI(api_key=self._api_key)
        else:
            # Will use OPENAI_API_KEY environment variable
            self._client = openai.OpenAI()
    
    def embed_batch(self, texts: List[str]) -> List[EmbeddingResult]:
        self._ensure_client()
        
        t0 = time.perf_counter()
        
        try:
            response = self._client.embeddings.create(
                model=self.model_name,
                input=texts
            )
        except Exception as e:
            raise RuntimeError(f"OpenAI embedding failed: {e}")
        
        duration_ms = (time.perf_counter() - t0) * 1000
        
        results = []
        for i, embedding_data in enumerate(response.data):
            # OpenAI doesn't provide token counts in embedding response
            # We estimate based on text length
            token_count = len(texts[i]) // 4
            
            telemetry = EmbeddingTelemetry(
                provider_id="openai",
                model_name=self.model_name,
                token_count=token_count,
                dimension=len(embedding_data.embedding),
                duration_ms=duration_ms / len(texts),
                trimmed=False
            )
            
            results.append(EmbeddingResult(
                vector=embedding_data.embedding,
                telemetry=telemetry
            ))
        
        return results
