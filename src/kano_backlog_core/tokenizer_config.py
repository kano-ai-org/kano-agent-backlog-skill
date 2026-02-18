"""Comprehensive configuration system for tokenizer adapters.

This module provides TOML-based configuration with environment variable overrides,
validation, and migration support for tokenizer adapter settings.

Features:
- TOML configuration file support with fallback to JSON
- Environment variable overrides for runtime configuration
- Configuration validation with sensible defaults
- Migration from existing configuration formats
- Integration with existing tokenizer registry system
"""

import logging
import math
import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .errors import ConfigError

# Conditional TOML import: stdlib tomllib (3.11+) or fallback tomli (<3.11)
try:
    import tomllib  # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore

logger = logging.getLogger(__name__)

# Environment variable prefixes for tokenizer configuration
ENV_PREFIX = "KANO_TOKENIZER_"
ENV_ADAPTER_PREFIX = f"{ENV_PREFIX}ADAPTER"
ENV_MODEL_PREFIX = f"{ENV_PREFIX}MODEL"
ENV_MAX_TOKENS_PREFIX = f"{ENV_PREFIX}MAX_TOKENS"

# Default configuration values
DEFAULT_CONFIG = {
    "adapter": "auto",
    "model": "text-embedding-3-small",
    "max_tokens": None,
    "fallback_chain": ["tiktoken", "huggingface", "heuristic"],
    "options": {},
    "cache": {
        "enabled": True,
        "max_size": 1000,
        "ttl_seconds": None
    }
}

# Adapter-specific default configurations
ADAPTER_DEFAULTS = {
    "heuristic": {
        "chars_per_token": 4.0
    },
    "tiktoken": {
        "encoding": None  # Auto-detect based on model
    },
    "huggingface": {
        "use_fast": True,
        "trust_remote_code": False
    }
}


@dataclass
class TokenizerConfig:
    """Comprehensive tokenizer configuration with validation and defaults."""
    
    adapter: str = "auto"
    model: str = "text-embedding-3-small"
    max_tokens: Optional[int] = None
    fallback_chain: List[str] = field(default_factory=lambda: ["tiktoken", "huggingface", "heuristic"])
    options: Dict[str, Any] = field(default_factory=dict)
    
    # Cache configuration
    cache: Dict[str, Any] = field(default_factory=lambda: DEFAULT_CONFIG["cache"].copy())
    
    # Adapter-specific configurations
    heuristic: Dict[str, Any] = field(default_factory=lambda: ADAPTER_DEFAULTS["heuristic"].copy())
    tiktoken: Dict[str, Any] = field(default_factory=lambda: ADAPTER_DEFAULTS["tiktoken"].copy())
    huggingface: Dict[str, Any] = field(default_factory=lambda: ADAPTER_DEFAULTS["huggingface"].copy())
    
    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        # Merge with defaults to ensure all required keys are present
        self.heuristic = {**ADAPTER_DEFAULTS["heuristic"], **self.heuristic}
        self.tiktoken = {**ADAPTER_DEFAULTS["tiktoken"], **self.tiktoken}
        self.huggingface = {**ADAPTER_DEFAULTS["huggingface"], **self.huggingface}
        self.cache = {**DEFAULT_CONFIG["cache"], **self.cache}
        
        self.validate()
    
    def validate(self) -> None:
        """Validate configuration values."""
        if not isinstance(self.adapter, str) or not self.adapter.strip():
            raise ConfigError("Tokenizer adapter must be specified")
        
        if not isinstance(self.model, str) or not self.model.strip():
            raise ConfigError("Tokenizer model must be specified")
        
        if self.max_tokens is not None:
            if not isinstance(self.max_tokens, int) or self.max_tokens <= 0:
                raise ConfigError("max_tokens must be positive if specified")
        
        if not isinstance(self.fallback_chain, list) or not self.fallback_chain:
            raise ConfigError("Fallback chain must not be empty")
        
        # Validate fallback chain contains known adapters
        valid_adapters = {"heuristic", "tiktoken", "huggingface"}
        for adapter_name in self.fallback_chain:
            if adapter_name not in valid_adapters:
                raise ConfigError(f"Unknown adapter in fallback chain: {adapter_name}")
        
        # Validate adapter-specific options
        self._validate_heuristic_options()
        self._validate_tiktoken_options()
        self._validate_huggingface_options()
        self._validate_cache_options()
    
    def _validate_heuristic_options(self) -> None:
        """Validate heuristic adapter options."""
        chars_per_token = self.heuristic.get("chars_per_token", 4.0)
        if not isinstance(chars_per_token, (int, float)) or chars_per_token <= 0:
            raise ConfigError("heuristic.chars_per_token must be a positive number")
    
    def _validate_tiktoken_options(self) -> None:
        """Validate tiktoken adapter options."""
        encoding = self.tiktoken.get("encoding")
        if encoding is not None and not isinstance(encoding, str):
            raise ConfigError("tiktoken.encoding must be a string if specified")
    
    def _validate_huggingface_options(self) -> None:
        """Validate HuggingFace adapter options."""
        use_fast = self.huggingface.get("use_fast", True)
        if not isinstance(use_fast, bool):
            raise ConfigError("huggingface.use_fast must be a boolean")
        
        trust_remote_code = self.huggingface.get("trust_remote_code", False)
        if not isinstance(trust_remote_code, bool):
            raise ConfigError("huggingface.trust_remote_code must be a boolean")
    
    def _validate_cache_options(self) -> None:
        """Validate cache configuration options."""
        enabled = self.cache.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ConfigError("cache.enabled must be a boolean")
        
        max_size = self.cache.get("max_size", 1000)
        if not isinstance(max_size, int) or max_size <= 0:
            raise ConfigError("cache.max_size must be a positive integer")
        
        ttl_seconds = self.cache.get("ttl_seconds")
        if ttl_seconds is not None and (not isinstance(ttl_seconds, (int, float)) or ttl_seconds <= 0):
            raise ConfigError("cache.ttl_seconds must be a positive number if specified")
    
    def get_adapter_options(self, adapter_name: str) -> Dict[str, Any]:
        """Get options for a specific adapter."""
        adapter_name = adapter_name.lower().strip()
        
        if adapter_name == "heuristic":
            return {**self.heuristic, **self.options.get("heuristic", {})}
        elif adapter_name == "tiktoken":
            return {**self.tiktoken, **self.options.get("tiktoken", {})}
        elif adapter_name == "huggingface":
            return {**self.huggingface, **self.options.get("huggingface", {})}
        else:
            return self.options.get(adapter_name, {})
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary format."""
        return {
            "adapter": self.adapter,
            "model": self.model,
            "max_tokens": self.max_tokens,
            "fallback_chain": self.fallback_chain,
            "options": self.options,
            "cache": self.cache,
            "heuristic": self.heuristic,
            "tiktoken": self.tiktoken,
            "huggingface": self.huggingface
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TokenizerConfig":
        """Create configuration from dictionary."""
        # Extract known fields with defaults
        adapter = data.get("adapter", DEFAULT_CONFIG["adapter"])
        model = data.get("model", DEFAULT_CONFIG["model"])
        max_tokens = data.get("max_tokens", DEFAULT_CONFIG["max_tokens"])
        fallback_chain = data.get("fallback_chain", DEFAULT_CONFIG["fallback_chain"].copy())
        options = data.get("options", DEFAULT_CONFIG["options"].copy())
        
        # Extract adapter-specific configurations
        heuristic = {**ADAPTER_DEFAULTS["heuristic"], **data.get("heuristic", {})}
        tiktoken = {**ADAPTER_DEFAULTS["tiktoken"], **data.get("tiktoken", {})}
        huggingface = {**ADAPTER_DEFAULTS["huggingface"], **data.get("huggingface", {})}
        cache = {**DEFAULT_CONFIG["cache"], **data.get("cache", {})}
        
        return cls(
            adapter=adapter,
            model=model,
            max_tokens=max_tokens,
            fallback_chain=fallback_chain,
            options=options,
            cache=cache,
            heuristic=heuristic,
            tiktoken=tiktoken,
            huggingface=huggingface
        )


class TokenizerConfigLoader:
    """Loader for tokenizer configuration with TOML support and environment overrides."""
    
    @staticmethod
    def _read_toml_file(path: Path) -> Dict[str, Any]:
        """Read TOML configuration file."""
        if not path.exists():
            return {}
        
        if tomllib is None:
            logger.warning("TOML support not available; install tomli for Python <3.11")
            return {}
        
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
            
            if not isinstance(data, dict):
                raise ConfigError(f"TOML file must contain a table: {path}")
            
            return data
        except Exception as e:
            raise ConfigError(f"Failed to load TOML from {path}: {e}")
    
    @staticmethod
    def _read_json_file(path: Path) -> Dict[str, Any]:
        """Read JSON configuration file (deprecated)."""
        if not path.exists():
            return {}
        
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if not isinstance(data, dict):
                raise ConfigError(f"JSON file must contain an object: {path}")
            
            warnings.warn(
                f"JSON config is deprecated; migrate to TOML: {path}",
                DeprecationWarning,
                stacklevel=3
            )
            
            return data
        except Exception as e:
            raise ConfigError(f"Failed to load JSON from {path}: {e}")
    
    @staticmethod
    def _apply_environment_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides to configuration."""
        result = config.copy()
        
        # Override main adapter settings
        if ENV_ADAPTER_PREFIX in os.environ:
            result["adapter"] = os.environ[ENV_ADAPTER_PREFIX]
        
        if ENV_MODEL_PREFIX in os.environ:
            result["model"] = os.environ[ENV_MODEL_PREFIX]
        
        if ENV_MAX_TOKENS_PREFIX in os.environ:
            try:
                result["max_tokens"] = int(os.environ[ENV_MAX_TOKENS_PREFIX])
            except ValueError:
                logger.warning(f"Invalid {ENV_MAX_TOKENS_PREFIX} value: {os.environ[ENV_MAX_TOKENS_PREFIX]}")
        
        # Override adapter-specific settings
        for adapter_name in ["heuristic", "tiktoken", "huggingface"]:
            adapter_prefix = f"{ENV_PREFIX}{adapter_name.upper()}_"
            adapter_config = result.setdefault(adapter_name, {})
            
            for env_key, env_value in os.environ.items():
                if env_key.startswith(adapter_prefix):
                    config_key = env_key[len(adapter_prefix):].lower()
                    
                    # Type conversion for known keys
                    if adapter_name == "heuristic" and config_key == "chars_per_token":
                        try:
                            parsed = float(env_value)
                            if not math.isfinite(parsed):
                                raise ValueError("chars_per_token must be finite")
                            adapter_config[config_key] = parsed
                        except ValueError:
                            logger.warning(f"Invalid {env_key} value: {env_value}")
                    elif adapter_name == "huggingface" and config_key in ["use_fast", "trust_remote_code"]:
                        adapter_config[config_key] = env_value.lower() in ("true", "1", "yes", "on")
                    else:
                        adapter_config[config_key] = env_value
        
        return result
    
    @staticmethod
    def load_from_file(config_path: Path) -> TokenizerConfig:
        """Load tokenizer configuration from file with environment overrides."""
        config_data = {}
        
        # Try TOML first, then JSON
        toml_path = config_path.with_suffix(".toml")
        json_path = config_path.with_suffix(".json")
        
        if toml_path.exists():
            config_data = TokenizerConfigLoader._read_toml_file(toml_path)
        elif json_path.exists():
            config_data = TokenizerConfigLoader._read_json_file(json_path)
        
        # Extract tokenizer section if it exists
        if "tokenizer" in config_data:
            config_data = config_data["tokenizer"]
        
        # Apply environment variable overrides
        config_data = TokenizerConfigLoader._apply_environment_overrides(config_data)
        
        return TokenizerConfig.from_dict(config_data)
    
    @staticmethod
    def load_from_dict(config_data: Dict[str, Any]) -> TokenizerConfig:
        """Load tokenizer configuration from dictionary with environment overrides."""
        # Apply environment variable overrides
        config_data = TokenizerConfigLoader._apply_environment_overrides(config_data)
        
        return TokenizerConfig.from_dict(config_data)
    
    @staticmethod
    def create_default_config() -> TokenizerConfig:
        """Create default tokenizer configuration with environment overrides."""
        return TokenizerConfigLoader.load_from_dict(DEFAULT_CONFIG.copy())


class TokenizerConfigMigrator:
    """Migrator for converting existing configuration formats to new TOML format."""
    
    @staticmethod
    def migrate_pipeline_config(old_config: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate old pipeline configuration format to new tokenizer configuration format."""
        result = DEFAULT_CONFIG.copy()
        result["cache"] = DEFAULT_CONFIG["cache"].copy()
        result["options"] = DEFAULT_CONFIG["options"].copy()
        result["heuristic"] = ADAPTER_DEFAULTS["heuristic"].copy()
        result["tiktoken"] = ADAPTER_DEFAULTS["tiktoken"].copy()
        result["huggingface"] = ADAPTER_DEFAULTS["huggingface"].copy()
        
        # Extract tokenizer section from pipeline config
        tokenizer_config = old_config.get("tokenizer", {})
        if not isinstance(tokenizer_config, dict):
            return result

        options = tokenizer_config.get("options", {})
        if options is None:
            options = {}

        has_adapter = isinstance(tokenizer_config.get("adapter"), str) and bool(
            tokenizer_config.get("adapter", "").strip()
        )
        has_model = isinstance(tokenizer_config.get("model"), str) and bool(
            tokenizer_config.get("model", "").strip()
        )
        has_max_tokens = tokenizer_config.get("max_tokens") is not None
        has_fallback_chain = isinstance(tokenizer_config.get("fallback_chain"), list) and bool(
            tokenizer_config.get("fallback_chain")
        )
        has_options = isinstance(options, dict) and bool(options)

        # Ignore incomplete tokenizer sections to avoid accidental config drift.
        # - adapter-only: ignore unless additional tokenizer settings exist
        # - options-only: ignore unless adapter/model context exists
        if has_adapter and not (has_model or has_max_tokens or has_fallback_chain or has_options):
            return result
        if has_options and not (has_adapter or has_model or has_max_tokens or has_fallback_chain):
            return result
        
        # Map old field names to new field names
        if has_adapter:
            result["adapter"] = tokenizer_config["adapter"]
        
        if has_model:
            result["model"] = tokenizer_config["model"]
        
        if "max_tokens" in tokenizer_config:
            result["max_tokens"] = tokenizer_config["max_tokens"]
        
        if "fallback_chain" in tokenizer_config:
            result["fallback_chain"] = tokenizer_config["fallback_chain"]
        
        if "options" in tokenizer_config and isinstance(tokenizer_config["options"], dict):
            result["options"] = tokenizer_config["options"]
        
        # Extract adapter-specific configurations from options
        options = result.get("options", {})
        if not isinstance(options, dict):
            options = {}
        
        # Migrate heuristic options
        if "chars_per_token" in options:
            if "heuristic" not in result:
                result["heuristic"] = ADAPTER_DEFAULTS["heuristic"].copy()
            result["heuristic"]["chars_per_token"] = options["chars_per_token"]
        if "heuristic" in options:
            base = result.get("heuristic", ADAPTER_DEFAULTS["heuristic"].copy())
            result["heuristic"] = {**ADAPTER_DEFAULTS["heuristic"], **base, **options["heuristic"]}
        
        # Migrate tiktoken options
        if "encoding" in options:
            if "tiktoken" not in result:
                result["tiktoken"] = ADAPTER_DEFAULTS["tiktoken"].copy()
            result["tiktoken"]["encoding"] = options["encoding"]
        if "tiktoken" in options:
            base = result.get("tiktoken", ADAPTER_DEFAULTS["tiktoken"].copy())
            result["tiktoken"] = {**ADAPTER_DEFAULTS["tiktoken"], **base, **options["tiktoken"]}
        
        # Migrate huggingface options
        if "huggingface" in options:
            result["huggingface"] = {**ADAPTER_DEFAULTS["huggingface"], **options["huggingface"]}
        
        return result
    
    @staticmethod
    def write_toml_config(config: TokenizerConfig, output_path: Path) -> None:
        """Write tokenizer configuration to TOML file."""
        try:
            import tomli_w  # For writing TOML files
        except ImportError:
            raise ConfigError("tomli_w package required for writing TOML files. Install with: pip install tomli_w")
        
        config_dict = config.to_dict()
        
        # Create output directory if it doesn't exist
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(output_path, "wb") as f:
                tomli_w.dump(config_dict, f)
            
            logger.info(f"Wrote tokenizer configuration to {output_path}")
        except Exception as e:
            raise ConfigError(f"Failed to write TOML config to {output_path}: {e}")
    
    @staticmethod
    def migrate_file(input_path: Path, output_path: Path) -> None:
        """Migrate configuration file from old format to new TOML format."""
        if not input_path.exists():
            raise ConfigError(f"Input configuration file not found: {input_path}")
        
        # Read old configuration
        if input_path.suffix.lower() == ".json":
            old_config = TokenizerConfigLoader._read_json_file(input_path)
        elif input_path.suffix.lower() == ".toml":
            old_config = TokenizerConfigLoader._read_toml_file(input_path)
        else:
            raise ConfigError(f"Unsupported configuration file format: {input_path}")
        
        # Migrate to new format
        migrated_config = TokenizerConfigMigrator.migrate_pipeline_config(old_config)
        new_config = TokenizerConfig.from_dict(migrated_config)
        
        # Write new TOML configuration
        TokenizerConfigMigrator.write_toml_config(new_config, output_path)
        
        logger.info(f"Migrated configuration from {input_path} to {output_path}")


def load_tokenizer_config(
    config_path: Optional[Path] = None,
    config_dict: Optional[Dict[str, Any]] = None
) -> TokenizerConfig:
    """Load tokenizer configuration from file or dictionary.
    
    Args:
        config_path: Path to configuration file (TOML or JSON)
        config_dict: Configuration dictionary (alternative to file)
    
    Returns:
        TokenizerConfig instance with validation and environment overrides applied
    
    Raises:
        ConfigError: If configuration is invalid or cannot be loaded
    """
    if config_path is not None and config_dict is not None:
        raise ConfigError("Cannot specify both config_path and config_dict")
    
    if config_path is not None:
        return TokenizerConfigLoader.load_from_file(config_path)
    elif config_dict is not None:
        return TokenizerConfigLoader.load_from_dict(config_dict)
    else:
        return TokenizerConfigLoader.create_default_config()


def create_example_config() -> str:
    """Create an example TOML configuration file content."""
    return '''# Tokenizer Adapter Configuration
# This file configures the tokenizer adapter system for accurate token counting

[tokenizer]
# Primary adapter to use ("auto" for fallback chain, or specific: "heuristic", "tiktoken", "huggingface")
adapter = "auto"

# Model name for tokenization (affects token limits and encoding selection)
model = "text-embedding-3-small"

# Optional: Override max tokens for the model (uses model defaults if not specified)
# max_tokens = 8192

# Fallback chain when primary adapter fails (tried in order)
fallback_chain = ["tiktoken", "huggingface", "heuristic"]

# Token count caching configuration
[tokenizer.cache]
enabled = true        # Enable/disable token count caching
max_size = 1000      # Maximum number of cached results
# ttl_seconds = 3600 # Optional: Cache expiration time in seconds

# Heuristic adapter configuration (fast approximation)
[tokenizer.heuristic]
chars_per_token = 4.0  # Average characters per token for estimation

# TikToken adapter configuration (OpenAI models)
[tokenizer.tiktoken]
# encoding = "cl100k_base"  # Optional: specific encoding (auto-detected if not specified)

# HuggingFace adapter configuration (transformer models)
[tokenizer.huggingface]
use_fast = true           # Use fast tokenizer implementation when available
trust_remote_code = false # Security: don't execute remote code from model repos

# Environment Variable Overrides:
# KANO_TOKENIZER_ADAPTER - Override adapter selection
# KANO_TOKENIZER_MODEL - Override model name
# KANO_TOKENIZER_MAX_TOKENS - Override max tokens
# KANO_TOKENIZER_CACHE_ENABLED - Override cache enabled (true/false)
# KANO_TOKENIZER_CACHE_MAX_SIZE - Override cache max size (integer)
# KANO_TOKENIZER_HEURISTIC_CHARS_PER_TOKEN - Override chars per token ratio
# KANO_TOKENIZER_HUGGINGFACE_USE_FAST - Override use_fast setting (true/false)
# KANO_TOKENIZER_HUGGINGFACE_TRUST_REMOTE_CODE - Override trust_remote_code (true/false)
'''
