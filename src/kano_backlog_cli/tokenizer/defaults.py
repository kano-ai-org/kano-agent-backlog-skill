from __future__ import annotations

from typing import Dict

# Simplistic map of model prefixes/names to context window sizes.
# These defaults are conservative estimates.
MODEL_BUDGETS: Dict[str, int] = {
    "gpt-4": 8192,  # Base model often 8k
    "gpt-4-32k": 32768,
    "gpt-4-turbo": 128000,
    "gpt-4o": 128000,
    "gpt-3.5": 4096,  # turbo often 4k or 16k
    "gpt-3.5-turbo": 4096,
    "gpt-3.5-turbo-16k": 16385,
    "claude": 100000,  # Claude 2 is 100k
    "claude-2": 100000,
    "claude-3": 200000, # Claude 3 is 200k
    "default": 4096,   # Safe fallback
}


def get_model_budget(model_name: str | None) -> int:
    """
    Resolve the token budget for a given model name.
    Matches by exact key, then prefix, then falls back to default.
    """
    if not model_name:
        return MODEL_BUDGETS["default"]

    name = model_name.lower().strip()
    
    # Exact match
    if name in MODEL_BUDGETS:
        return MODEL_BUDGETS[name]
    
    # Prefix match (longest match wins)
    best_match_len = 0
    best_budget = MODEL_BUDGETS["default"]
    
    for key, budget in MODEL_BUDGETS.items():
        if key == "default":
            continue
        if name.startswith(key):
            if len(key) > best_match_len:
                best_match_len = len(key)
                best_budget = budget
                
    return best_budget
