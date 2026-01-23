"""Enhanced error handling for tokenizer adapters.

This module provides comprehensive error handling classes and utilities for
tokenizer adapter operations, including graceful degradation, clear error
messages, and recovery strategies.
"""

import logging
from typing import Any, Dict, List, Optional, Type, Union

logger = logging.getLogger(__name__)


class TokenizerError(Exception):
    """Base exception for tokenizer-related errors."""
    
    def __init__(self, message: str, adapter_name: Optional[str] = None, 
                 model_name: Optional[str] = None, recovery_suggestions: Optional[List[str]] = None):
        super().__init__(message)
        self.adapter_name = adapter_name
        self.model_name = model_name
        self.recovery_suggestions = recovery_suggestions or []
    
    def get_detailed_message(self) -> str:
        """Get detailed error message with context and recovery suggestions."""
        parts = [str(self)]
        
        if self.adapter_name:
            parts.append(f"Adapter: {self.adapter_name}")
        
        if self.model_name:
            parts.append(f"Model: {self.model_name}")
        
        if self.recovery_suggestions:
            parts.append("Recovery suggestions:")
            for i, suggestion in enumerate(self.recovery_suggestions, 1):
                parts.append(f"  {i}. {suggestion}")
        
        return "\n".join(parts)


class AdapterNotAvailableError(TokenizerError):
    """Raised when a requested tokenizer adapter cannot be created."""
    
    def __init__(self, adapter_name: str, reason: str, model_name: Optional[str] = None):
        recovery_suggestions = self._get_recovery_suggestions(adapter_name, reason)
        super().__init__(
            f"Tokenizer adapter '{adapter_name}' is not available: {reason}",
            adapter_name=adapter_name,
            model_name=model_name,
            recovery_suggestions=recovery_suggestions
        )
        self.reason = reason
    
    def _get_recovery_suggestions(self, adapter_name: str, reason: str) -> List[str]:
        """Generate recovery suggestions based on adapter and error reason."""
        suggestions = []
        
        if "tiktoken" in adapter_name.lower():
            if "import" in reason.lower() or "module" in reason.lower():
                suggestions.extend([
                    "Install tiktoken: pip install tiktoken",
                    "Use 'heuristic' adapter as fallback",
                    "Set KANO_TOKENIZER_ADAPTER=heuristic environment variable"
                ])
            else:
                suggestions.extend([
                    "Check tiktoken installation: python -c 'import tiktoken'",
                    "Try updating tiktoken: pip install --upgrade tiktoken",
                    "Use 'heuristic' adapter as fallback"
                ])
        
        elif "huggingface" in adapter_name.lower():
            if "import" in reason.lower() or "module" in reason.lower():
                suggestions.extend([
                    "Install transformers: pip install transformers",
                    "For sentence-transformers models: pip install sentence-transformers",
                    "Use 'heuristic' adapter as fallback",
                    "Set KANO_TOKENIZER_ADAPTER=heuristic environment variable"
                ])
            else:
                suggestions.extend([
                    "Check transformers installation: python -c 'import transformers'",
                    "Try updating transformers: pip install --upgrade transformers",
                    "Verify model name format (e.g., 'bert-base-uncased')",
                    "Use 'heuristic' adapter as fallback"
                ])
        
        elif "heuristic" in adapter_name.lower():
            suggestions.extend([
                "Heuristic adapter should always be available",
                "Check for configuration errors",
                "Verify model_name parameter is not empty"
            ])
        
        else:
            suggestions.extend([
                "Check adapter name spelling",
                "Use 'auto' for automatic adapter selection",
                "Available adapters: heuristic, tiktoken, huggingface"
            ])
        
        return suggestions


class DependencyMissingError(TokenizerError):
    """Raised when required dependencies are missing."""
    
    def __init__(self, dependency: str, adapter_name: str, model_name: Optional[str] = None):
        recovery_suggestions = self._get_installation_instructions(dependency, adapter_name)
        super().__init__(
            f"Required dependency '{dependency}' is missing for {adapter_name} adapter",
            adapter_name=adapter_name,
            model_name=model_name,
            recovery_suggestions=recovery_suggestions
        )
        self.dependency = dependency
    
    def _get_installation_instructions(self, dependency: str, adapter_name: str) -> List[str]:
        """Get specific installation instructions for the missing dependency."""
        instructions = []
        
        if dependency == "tiktoken":
            instructions.extend([
                "Install tiktoken: pip install tiktoken",
                "For conda users: conda install -c conda-forge tiktoken",
                "Verify installation: python -c 'import tiktoken; print(tiktoken.__version__)'"
            ])
        
        elif dependency == "transformers":
            instructions.extend([
                "Install transformers: pip install transformers",
                "For sentence-transformers: pip install sentence-transformers",
                "For conda users: conda install -c huggingface transformers",
                "Verify installation: python -c 'import transformers; print(transformers.__version__)'"
            ])
        
        else:
            instructions.extend([
                f"Install {dependency}: pip install {dependency}",
                f"Check PyPI for {dependency} installation instructions"
            ])
        
        # Add fallback suggestions
        instructions.extend([
            f"Alternative: Use 'heuristic' adapter (no dependencies required)",
            f"Set environment variable: KANO_TOKENIZER_ADAPTER=heuristic"
        ])
        
        return instructions


class TokenizationFailedError(TokenizerError):
    """Raised when tokenization operation fails."""
    
    def __init__(self, adapter_name: str, model_name: str, text_preview: str, 
                 original_error: Exception):
        recovery_suggestions = self._get_recovery_suggestions(adapter_name, original_error)
        super().__init__(
            f"Tokenization failed with {adapter_name} adapter for model {model_name}: {original_error}",
            adapter_name=adapter_name,
            model_name=model_name,
            recovery_suggestions=recovery_suggestions
        )
        self.text_preview = text_preview[:100] + "..." if len(text_preview) > 100 else text_preview
        self.original_error = original_error
    
    def _get_recovery_suggestions(self, adapter_name: str, original_error: Exception) -> List[str]:
        """Generate recovery suggestions based on the tokenization failure."""
        suggestions = []
        error_str = str(original_error).lower()
        
        if "encoding" in error_str or "decode" in error_str:
            suggestions.extend([
                "Check text encoding (ensure UTF-8)",
                "Remove or escape special characters",
                "Try preprocessing text with unicodedata.normalize('NFC', text)"
            ])
        
        elif "token" in error_str and "limit" in error_str:
            suggestions.extend([
                "Text may exceed model token limits",
                "Try chunking text into smaller pieces",
                "Use a model with higher token limits"
            ])
        
        elif "model" in error_str or "not found" in error_str:
            suggestions.extend([
                "Verify model name is correct",
                "Check if model is available in the tokenizer library",
                "Try a different model name"
            ])
        
        # Always suggest fallback
        suggestions.extend([
            f"Try fallback adapter: use 'auto' for automatic selection",
            f"Use 'heuristic' adapter for approximate token counting"
        ])
        
        return suggestions


class ConfigurationError(TokenizerError):
    """Raised when tokenizer configuration is invalid."""
    
    def __init__(self, config_key: str, config_value: Any, reason: str):
        recovery_suggestions = self._get_config_suggestions(config_key, config_value, reason)
        super().__init__(
            f"Invalid configuration for '{config_key}': {reason}",
            recovery_suggestions=recovery_suggestions
        )
        self.config_key = config_key
        self.config_value = config_value
        self.reason = reason
    
    def _get_config_suggestions(self, config_key: str, config_value: Any, reason: str) -> List[str]:
        """Generate configuration-specific recovery suggestions."""
        suggestions = []
        
        if config_key == "adapter":
            suggestions.extend([
                "Valid adapters: 'heuristic', 'tiktoken', 'huggingface', 'auto'",
                "Use 'auto' for automatic adapter selection",
                "Check spelling and case sensitivity"
            ])
        
        elif config_key == "model":
            suggestions.extend([
                "Ensure model name is not empty",
                "Use valid model identifiers (e.g., 'text-embedding-3-small')",
                "Check model name format for the selected adapter"
            ])
        
        elif config_key == "max_tokens":
            suggestions.extend([
                "max_tokens must be a positive integer",
                "Typical values: 512, 1024, 2048, 4096, 8192",
                "Leave unset to use model defaults"
            ])
        
        elif config_key == "fallback_chain":
            suggestions.extend([
                "Fallback chain must be a non-empty list",
                "Valid adapters: ['tiktoken', 'huggingface', 'heuristic']",
                "Order matters: first available adapter will be used"
            ])
        
        elif "chars_per_token" in config_key:
            suggestions.extend([
                "chars_per_token must be a positive number",
                "Typical values: 3.0-5.0 for English text",
                "Lower values = more tokens, higher values = fewer tokens"
            ])
        
        else:
            suggestions.extend([
                f"Check documentation for '{config_key}' parameter",
                "Verify configuration file syntax",
                "Use default values if unsure"
            ])
        
        return suggestions


class FallbackChainExhaustedError(TokenizerError):
    """Raised when all adapters in the fallback chain fail."""
    
    def __init__(self, attempted_adapters: List[str], errors: List[str], model_name: str):
        recovery_suggestions = self._get_recovery_suggestions(attempted_adapters, errors)
        super().__init__(
            f"All tokenizer adapters failed for model '{model_name}'. "
            f"Attempted: {', '.join(attempted_adapters)}",
            model_name=model_name,
            recovery_suggestions=recovery_suggestions
        )
        self.attempted_adapters = attempted_adapters
        self.errors = errors
    
    def _get_recovery_suggestions(self, attempted_adapters: List[str], errors: List[str]) -> List[str]:
        """Generate recovery suggestions when all adapters fail."""
        suggestions = []
        
        # Analyze errors to provide specific guidance
        has_import_error = any("import" in error.lower() or "module" in error.lower() for error in errors)
        has_config_error = any("config" in error.lower() or "invalid" in error.lower() for error in errors)
        
        if has_import_error:
            suggestions.extend([
                "Install missing dependencies:",
                "  - For tiktoken: pip install tiktoken",
                "  - For transformers: pip install transformers",
                "Check Python environment and package installations"
            ])
        
        if has_config_error:
            suggestions.extend([
                "Check tokenizer configuration:",
                "  - Verify model name format",
                "  - Check adapter-specific settings",
                "  - Validate configuration file syntax"
            ])
        
        # General recovery suggestions
        suggestions.extend([
            "Try with minimal configuration:",
            "  - Use 'heuristic' adapter (no dependencies)",
            "  - Set KANO_TOKENIZER_ADAPTER=heuristic",
            "Check system requirements and Python version",
            "Review error details above for specific issues"
        ])
        
        return suggestions


class ErrorRecoveryManager:
    """Manages error recovery strategies for tokenizer operations."""
    
    def __init__(self):
        self.recovery_attempts: Dict[str, int] = {}
        self.max_recovery_attempts = 3
        self.degradation_history: Dict[str, List[Dict[str, Any]]] = {}

    def clear_cache(self) -> None:
        """Clear internal recovery/degradation caches."""
        self.recovery_attempts.clear()
        self.degradation_history.clear()
    
    def should_attempt_recovery(self, error_key: str) -> bool:
        """Check if recovery should be attempted for this error."""
        attempts = self.recovery_attempts.get(error_key, 0)
        return attempts < self.max_recovery_attempts
    
    def record_recovery_attempt(self, error_key: str) -> None:
        """Record a recovery attempt for tracking."""
        self.recovery_attempts[error_key] = self.recovery_attempts.get(error_key, 0) + 1
    
    def reset_recovery_attempts(self, error_key: str) -> None:
        """Reset recovery attempts for successful operations."""
        self.recovery_attempts.pop(error_key, None)
    
    def suggest_fallback_adapter(self, failed_adapter: str, available_adapters: List[str]) -> Optional[str]:
        """Suggest the best fallback adapter based on the failed adapter and history.
        
        Args:
            failed_adapter: Name of the adapter that failed
            available_adapters: List of available fallback adapters
            
        Returns:
            Recommended fallback adapter name, or None if no suitable fallback
        """
        # Define fallback preferences based on adapter characteristics
        fallback_preferences = {
            "tiktoken": ["huggingface", "heuristic"],  # Exact -> Exact -> Approximate
            "huggingface": ["tiktoken", "heuristic"],  # Exact -> Exact -> Approximate
            "heuristic": [],  # Heuristic is the final fallback
        }
        
        preferences = fallback_preferences.get(failed_adapter, ["heuristic"])
        
        # Check degradation history to avoid problematic adapters
        problematic_adapters = self._get_problematic_adapters(failed_adapter)
        
        for preferred in preferences:
            if preferred in available_adapters and preferred not in problematic_adapters:
                return preferred
        
        # If no preferences available or all are problematic, return first available
        for adapter in available_adapters:
            if adapter not in problematic_adapters:
                return adapter
        
        # If all adapters are problematic, return the least problematic
        if available_adapters:
            return min(available_adapters, key=lambda a: len(self.degradation_history.get(a, [])))
        
        return None
    
    def _get_problematic_adapters(self, context_adapter: str) -> List[str]:
        """Get list of adapters that have had recent failures.
        
        Args:
            context_adapter: The adapter that's currently failing (for context)
            
        Returns:
            List of adapter names that should be avoided
        """
        import time
        current_time = time.time()
        recent_threshold = 300  # 5 minutes
        
        problematic = []
        
        for adapter_name, history in self.degradation_history.items():
            # Count recent failures
            recent_failures = [
                event for event in history 
                if current_time - event.get("timestamp", 0) < recent_threshold
            ]
            
            # If more than 2 recent failures, consider problematic
            if len(recent_failures) > 2:
                problematic.append(adapter_name)
        
        return problematic
    
    def record_degradation_event(self, failed_adapter: str, fallback_adapter: str, 
                                model_name: str, error: Exception) -> None:
        """Record a degradation event for analysis and future fallback decisions.
        
        Args:
            failed_adapter: Name of the adapter that failed
            fallback_adapter: Name of the adapter used as fallback
            model_name: Model name involved in the failure
            error: The original error that caused the degradation
        """
        import time
        
        event = {
            "timestamp": time.time(),
            "failed_adapter": failed_adapter,
            "fallback_adapter": fallback_adapter,
            "model_name": model_name,
            "error_type": type(error).__name__,
            "error_message": str(error)[:200]  # Truncate long messages
        }
        
        # Record in degradation history
        if failed_adapter not in self.degradation_history:
            self.degradation_history[failed_adapter] = []
        
        self.degradation_history[failed_adapter].append(event)
        
        # Keep only recent history (last 10 events per adapter)
        self.degradation_history[failed_adapter] = self.degradation_history[failed_adapter][-10:]
    
    def get_recovery_statistics(self) -> Dict[str, Any]:
        """Get statistics about recovery attempts and degradation events.
        
        Returns:
            Dictionary with recovery statistics
        """
        import time
        current_time = time.time()
        recent_threshold = 3600  # 1 hour
        
        stats = {
            "total_recovery_attempts": sum(self.recovery_attempts.values()),
            "active_recovery_keys": len(self.recovery_attempts),
            "total_degradation_events": sum(len(history) for history in self.degradation_history.values()),
            "recent_degradation_events": 0,
            "most_problematic_adapter": None,
            "degradation_by_adapter": {}
        }
        
        # Count recent degradation events
        recent_events = 0
        adapter_recent_counts = {}
        
        for adapter_name, history in self.degradation_history.items():
            recent_adapter_events = [
                event for event in history 
                if current_time - event.get("timestamp", 0) < recent_threshold
            ]
            recent_events += len(recent_adapter_events)
            adapter_recent_counts[adapter_name] = len(recent_adapter_events)
            
            stats["degradation_by_adapter"][adapter_name] = {
                "total_events": len(history),
                "recent_events": len(recent_adapter_events)
            }
        
        stats["recent_degradation_events"] = recent_events
        
        # Find most problematic adapter
        if adapter_recent_counts:
            stats["most_problematic_adapter"] = max(
                adapter_recent_counts.items(), 
                key=lambda x: x[1]
            )[0]
        
        return stats
    
    def create_recovery_context(self, error: Exception, adapter_name: str, 
                              model_name: str) -> Dict[str, Any]:
        """Create context information for error recovery."""
        import time
        
        context = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "adapter_name": adapter_name,
            "model_name": model_name,
            "timestamp": time.time(),
            "recovery_attempts": self.recovery_attempts.get(f"{adapter_name}:{model_name}", 0),
            "degradation_history": self.degradation_history.get(adapter_name, [])[-3:]  # Last 3 events
        }
        
        return context
    
    def suggest_recovery_strategy(self, error: Exception, adapter_name: str, 
                                model_name: str) -> Dict[str, Any]:
        """Suggest a recovery strategy based on error type and history.
        
        Args:
            error: The error that occurred
            adapter_name: Name of the failing adapter
            model_name: Model name involved
            
        Returns:
            Dictionary with recovery strategy recommendations
        """
        strategy = {
            "recommended_action": "fallback",
            "fallback_adapter": None,
            "user_message": None,
            "technical_details": None,
            "retry_recommended": False
        }
        
        error_str = str(error).lower()
        error_type = type(error).__name__
        
        # Dependency missing errors
        if isinstance(error, ImportError) or "import" in error_str or "module" in error_str:
            if "tiktoken" in error_str:
                strategy.update({
                    "recommended_action": "install_dependency",
                    "fallback_adapter": "huggingface",
                    "user_message": "TikToken library not installed. Install with: pip install tiktoken",
                    "technical_details": "TikToken provides exact tokenization for OpenAI models",
                    "retry_recommended": True
                })
            elif "transformers" in error_str:
                strategy.update({
                    "recommended_action": "install_dependency", 
                    "fallback_adapter": "tiktoken",
                    "user_message": "Transformers library not installed. Install with: pip install transformers",
                    "technical_details": "Transformers provides exact tokenization for HuggingFace models",
                    "retry_recommended": True
                })
        
        # Configuration errors
        elif "config" in error_str or error_type in ["ValueError", "ConfigurationError"]:
            strategy.update({
                "recommended_action": "fix_configuration",
                "fallback_adapter": "heuristic",
                "user_message": "Configuration error detected. Check model name and adapter settings.",
                "technical_details": f"Error: {str(error)[:100]}",
                "retry_recommended": True
            })
        
        # Network or model loading errors
        elif "network" in error_str or "timeout" in error_str or "connection" in error_str:
            strategy.update({
                "recommended_action": "retry_with_fallback",
                "fallback_adapter": "heuristic",
                "user_message": "Network error loading model. Using offline fallback.",
                "technical_details": "Model loading failed due to network issues",
                "retry_recommended": True
            })
        
        # Generic fallback strategy
        else:
            strategy.update({
                "fallback_adapter": "heuristic",
                "user_message": f"Adapter {adapter_name} failed. Using approximate tokenization.",
                "technical_details": f"Error type: {error_type}",
                "retry_recommended": False
            })
        
        return strategy


def wrap_adapter_error(error: Exception, adapter_name: str, model_name: str, 
                      operation: str = "creation") -> TokenizerError:
    """Wrap generic exceptions in appropriate TokenizerError subclasses."""
    if isinstance(error, TokenizerError):
        return error
    
    error_str = str(error).lower()
    
    # Import/dependency errors
    if isinstance(error, ImportError) or "import" in error_str or "module" in error_str:
        if "tiktoken" in error_str:
            return DependencyMissingError("tiktoken", adapter_name, model_name)
        elif "transformers" in error_str:
            return DependencyMissingError("transformers", adapter_name, model_name)
        else:
            return DependencyMissingError("unknown", adapter_name, model_name)
    
    # Configuration errors
    if isinstance(error, (ValueError, TypeError)) and ("config" in error_str or "invalid" in error_str):
        return ConfigurationError("unknown", None, str(error))
    
    # Tokenization errors
    if operation == "tokenization":
        return TokenizationFailedError(adapter_name, model_name, "", error)
    
    # Generic adapter errors
    return AdapterNotAvailableError(adapter_name, str(error), model_name)


def log_error_with_context(error: TokenizerError, context: Optional[Dict[str, Any]] = None) -> None:
    """Log error with full context and recovery suggestions."""
    logger.error(f"Tokenizer error: {error}")
    
    if context:
        logger.error(f"Context: {context}")
    
    if error.recovery_suggestions:
        logger.info("Recovery suggestions:")
        for i, suggestion in enumerate(error.recovery_suggestions, 1):
            logger.info(f"  {i}. {suggestion}")


def create_user_friendly_error_message(error: TokenizerError) -> str:
    """Create a user-friendly error message with actionable guidance."""
    message_parts = [
        "❌ Tokenizer Error",
        f"   {error}",
        ""
    ]
    
    if error.adapter_name:
        message_parts.append(f"📍 Adapter: {error.adapter_name}")
    
    if error.model_name:
        message_parts.append(f"🤖 Model: {error.model_name}")
    
    if error.recovery_suggestions:
        message_parts.extend([
            "",
            "💡 How to fix this:",
        ])
        for i, suggestion in enumerate(error.recovery_suggestions, 1):
            message_parts.append(f"   {i}. {suggestion}")
    
    message_parts.extend([
        "",
        "ℹ️  For more help, check the tokenizer documentation or use 'heuristic' adapter as fallback."
    ])
    
    return "\n".join(message_parts)
