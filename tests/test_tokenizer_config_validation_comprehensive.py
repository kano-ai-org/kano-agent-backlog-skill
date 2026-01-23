"""Comprehensive tests for tokenizer configuration validation and parsing.

This module provides comprehensive tests for:
1. Configuration validation with extensive edge cases
2. Environment variable parsing and type conversion
3. Configuration migration from legacy formats
4. TOML and JSON parsing with error handling
5. Configuration loading with various file scenarios
6. Integration between configuration and tokenizer adapters

These tests ensure robust configuration handling across all scenarios.
"""

import pytest
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock
from typing import Any, Dict

from kano_backlog_core.tokenizer_config import (
    TokenizerConfig,
    TokenizerConfigLoader,
    TokenizerConfigMigrator,
    load_tokenizer_config,
    create_example_config,
    DEFAULT_CONFIG,
    ADAPTER_DEFAULTS,
    ENV_PREFIX,
)
from kano_backlog_core.errors import ConfigError


class TestTokenizerConfigValidationEdgeCases:
    """Comprehensive validation tests for TokenizerConfig."""
    
    @pytest.mark.parametrize("invalid_config,expected_error", [
        # Adapter validation
        ({"adapter": None}, "Tokenizer adapter must be specified"),
        ({"adapter": 123}, "Tokenizer adapter must be specified"),
        ({"adapter": []}, "Tokenizer adapter must be specified"),
        ({"adapter": {"nested": "dict"}}, "Tokenizer adapter must be specified"),
        
        # Model validation
        ({"model": None}, "Tokenizer model must be specified"),
        ({"model": 123}, "Tokenizer model must be specified"),
        ({"model": []}, "Tokenizer model must be specified"),
        ({"model": "   "}, "Tokenizer model must be specified"),  # Whitespace only
        
        # Max tokens validation
        ({"max_tokens": 0}, "max_tokens must be positive"),
        ({"max_tokens": -100}, "max_tokens must be positive"),
        ({"max_tokens": "invalid"}, "max_tokens must be positive"),
        ({"max_tokens": []}, "max_tokens must be positive"),
        
        # Fallback chain validation
        ({"fallback_chain": None}, "Fallback chain must not be empty"),
        ({"fallback_chain": "string"}, "Fallback chain must not be empty"),
        ({"fallback_chain": 123}, "Fallback chain must not be empty"),
        ({"fallback_chain": ["tiktoken", "unknown_adapter"]}, "Unknown adapter in fallback chain: unknown_adapter"),
        ({"fallback_chain": ["tiktoken", "tiktoken"]}, None),  # Duplicates should be allowed
        
        # Heuristic options validation
        ({"heuristic": {"chars_per_token": 0}}, "chars_per_token must be a positive number"),
        ({"heuristic": {"chars_per_token": -1.5}}, "chars_per_token must be a positive number"),
        ({"heuristic": {"chars_per_token": "invalid"}}, "chars_per_token must be a positive number"),
        ({"heuristic": {"chars_per_token": []}}, "chars_per_token must be a positive number"),
        ({"heuristic": {"chars_per_token": None}}, "chars_per_token must be a positive number"),
        
        # TikToken options validation
        ({"tiktoken": {"encoding": 123}}, "tiktoken.encoding must be a string"),
        ({"tiktoken": {"encoding": []}}, "tiktoken.encoding must be a string"),
        ({"tiktoken": {"encoding": {"nested": "dict"}}}, "tiktoken.encoding must be a string"),
        
        # HuggingFace options validation
        ({"huggingface": {"use_fast": "true"}}, "huggingface.use_fast must be a boolean"),
        ({"huggingface": {"use_fast": 1}}, "huggingface.use_fast must be a boolean"),
        ({"huggingface": {"use_fast": []}}, "huggingface.use_fast must be a boolean"),
        ({"huggingface": {"trust_remote_code": "false"}}, "huggingface.trust_remote_code must be a boolean"),
        ({"huggingface": {"trust_remote_code": 0}}, "huggingface.trust_remote_code must be a boolean"),
    ])
    def test_validation_edge_cases(self, invalid_config: Dict[str, Any], expected_error: str):
        """Test validation with various invalid configurations."""
        # Merge with valid base config
        base_config = {
            "adapter": "auto",
            "model": "test-model",
            "max_tokens": None,
            "fallback_chain": ["tiktoken", "huggingface", "heuristic"],
        }
        base_config.update(invalid_config)
        
        if expected_error:
            with pytest.raises(ConfigError, match=expected_error):
                TokenizerConfig.from_dict(base_config)
        else:
            # Should not raise an error
            config = TokenizerConfig.from_dict(base_config)
            assert config is not None
    
    def test_validation_with_nested_options(self):
        """Test validation with complex nested options."""
        # Valid nested configuration
        valid_config = {
            "adapter": "auto",
            "model": "test-model",
            "options": {
                "heuristic": {"custom_option": "value"},
                "tiktoken": {"custom_encoding": "test"},
                "huggingface": {"custom_model": "test"},
            },
            "heuristic": {"chars_per_token": 3.5},
            "tiktoken": {"encoding": "cl100k_base"},
            "huggingface": {"use_fast": False, "trust_remote_code": True},
        }
        
        config = TokenizerConfig.from_dict(valid_config)
        assert config.adapter == "auto"
        assert config.heuristic["chars_per_token"] == 3.5
        assert config.tiktoken["encoding"] == "cl100k_base"
        assert config.huggingface["use_fast"] is False
        assert config.huggingface["trust_remote_code"] is True
    
    def test_validation_with_extreme_values(self):
        """Test validation with extreme but valid values."""
        extreme_configs = [
            # Very small chars_per_token
            {"heuristic": {"chars_per_token": 0.001}},
            
            # Very large chars_per_token
            {"heuristic": {"chars_per_token": 10000.0}},
            
            # Very large max_tokens
            {"max_tokens": 1000000},
            
            # Very long model name
            {"model": "a" * 1000},
            
            # Very long adapter name
            {"adapter": "heuristic"},  # Still valid
            
            # Long fallback chain
            {"fallback_chain": ["heuristic"] * 100},  # Duplicates allowed
        ]
        
        base_config = {
            "adapter": "auto",
            "model": "test-model",
            "fallback_chain": ["heuristic"],
        }
        
        for extreme_config in extreme_configs:
            test_config = {**base_config, **extreme_config}
            config = TokenizerConfig.from_dict(test_config)
            config.validate()  # Should not raise
    
    def test_post_init_validation_integration(self):
        """Test that __post_init__ properly integrates validation."""
        # Test that validation is called during initialization
        with pytest.raises(ConfigError, match="Tokenizer adapter must be specified"):
            TokenizerConfig(adapter="")
        
        # Test that defaults are properly merged before validation
        config = TokenizerConfig()
        assert config.heuristic["chars_per_token"] == ADAPTER_DEFAULTS["heuristic"]["chars_per_token"]
        assert config.tiktoken["encoding"] == ADAPTER_DEFAULTS["tiktoken"]["encoding"]
        assert config.huggingface["use_fast"] == ADAPTER_DEFAULTS["huggingface"]["use_fast"]


class TestEnvironmentVariableParsingEdgeCases:
    """Comprehensive tests for environment variable parsing."""
    
    @pytest.mark.parametrize("env_var,env_value,expected_result", [
        # String values
        (f"{ENV_PREFIX}ADAPTER", "heuristic", {"adapter": "heuristic"}),
        (f"{ENV_PREFIX}MODEL", "custom-model", {"model": "custom-model"}),
        
        # Numeric values
        (f"{ENV_PREFIX}MAX_TOKENS", "1024", {"max_tokens": 1024}),
        (f"{ENV_PREFIX}MAX_TOKENS", "0", {"max_tokens": 0}),  # Zero should be parsed
        (f"{ENV_PREFIX}MAX_TOKENS", "-1", {"max_tokens": -1}),  # Negative should be parsed
        
        # Float values
        (f"{ENV_PREFIX}HEURISTIC_CHARS_PER_TOKEN", "3.5", {"heuristic": {"chars_per_token": 3.5}}),
        (f"{ENV_PREFIX}HEURISTIC_CHARS_PER_TOKEN", "0.1", {"heuristic": {"chars_per_token": 0.1}}),
        (f"{ENV_PREFIX}HEURISTIC_CHARS_PER_TOKEN", "100.0", {"heuristic": {"chars_per_token": 100.0}}),
        
        # Boolean values - true variants
        (f"{ENV_PREFIX}HUGGINGFACE_USE_FAST", "true", {"huggingface": {"use_fast": True}}),
        (f"{ENV_PREFIX}HUGGINGFACE_USE_FAST", "True", {"huggingface": {"use_fast": True}}),
        (f"{ENV_PREFIX}HUGGINGFACE_USE_FAST", "TRUE", {"huggingface": {"use_fast": True}}),
        (f"{ENV_PREFIX}HUGGINGFACE_USE_FAST", "1", {"huggingface": {"use_fast": True}}),
        (f"{ENV_PREFIX}HUGGINGFACE_USE_FAST", "yes", {"huggingface": {"use_fast": True}}),
        (f"{ENV_PREFIX}HUGGINGFACE_USE_FAST", "on", {"huggingface": {"use_fast": True}}),
        
        # Boolean values - false variants
        (f"{ENV_PREFIX}HUGGINGFACE_USE_FAST", "false", {"huggingface": {"use_fast": False}}),
        (f"{ENV_PREFIX}HUGGINGFACE_USE_FAST", "False", {"huggingface": {"use_fast": False}}),
        (f"{ENV_PREFIX}HUGGINGFACE_USE_FAST", "FALSE", {"huggingface": {"use_fast": False}}),
        (f"{ENV_PREFIX}HUGGINGFACE_USE_FAST", "0", {"huggingface": {"use_fast": False}}),
        (f"{ENV_PREFIX}HUGGINGFACE_USE_FAST", "no", {"huggingface": {"use_fast": False}}),
        (f"{ENV_PREFIX}HUGGINGFACE_USE_FAST", "off", {"huggingface": {"use_fast": False}}),
        
        # Trust remote code boolean
        (f"{ENV_PREFIX}HUGGINGFACE_TRUST_REMOTE_CODE", "true", {"huggingface": {"trust_remote_code": True}}),
        (f"{ENV_PREFIX}HUGGINGFACE_TRUST_REMOTE_CODE", "false", {"huggingface": {"trust_remote_code": False}}),
        
        # String values for tiktoken
        (f"{ENV_PREFIX}TIKTOKEN_ENCODING", "p50k_base", {"tiktoken": {"encoding": "p50k_base"}}),
        (f"{ENV_PREFIX}TIKTOKEN_ENCODING", "", {"tiktoken": {"encoding": ""}}),  # Empty string
    ])
    def test_environment_variable_parsing(self, env_var: str, env_value: str, expected_result: Dict[str, Any]):
        """Test environment variable parsing with various values."""
        with patch.dict(os.environ, {env_var: env_value}):
            result = TokenizerConfigLoader._apply_environment_overrides({})
            
            for key, value in expected_result.items():
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        assert result[key][sub_key] == sub_value
                else:
                    assert result[key] == value
    
    @pytest.mark.parametrize("env_var,env_value,should_warn", [
        # Invalid numeric values
        (f"{ENV_PREFIX}MAX_TOKENS", "not_a_number", True),
        (f"{ENV_PREFIX}MAX_TOKENS", "12.5", True),  # Float for int field
        (f"{ENV_PREFIX}MAX_TOKENS", "", True),  # Empty string
        (f"{ENV_PREFIX}MAX_TOKENS", "  ", True),  # Whitespace
        
        # Invalid float values
        (f"{ENV_PREFIX}HEURISTIC_CHARS_PER_TOKEN", "not_a_float", True),
        (f"{ENV_PREFIX}HEURISTIC_CHARS_PER_TOKEN", "", True),
        (f"{ENV_PREFIX}HEURISTIC_CHARS_PER_TOKEN", "inf", True),
        (f"{ENV_PREFIX}HEURISTIC_CHARS_PER_TOKEN", "nan", True),
        
        # Valid values should not warn
        (f"{ENV_PREFIX}MAX_TOKENS", "1024", False),
        (f"{ENV_PREFIX}HEURISTIC_CHARS_PER_TOKEN", "3.5", False),
        (f"{ENV_PREFIX}HUGGINGFACE_USE_FAST", "true", False),
    ])
    def test_environment_variable_error_handling(self, env_var: str, env_value: str, should_warn: bool):
        """Test environment variable error handling and warnings."""
        with patch.dict(os.environ, {env_var: env_value}):
            with patch('kano_backlog_core.tokenizer_config.logger') as mock_logger:
                result = TokenizerConfigLoader._apply_environment_overrides({})
                
                if should_warn:
                    mock_logger.warning.assert_called()
                else:
                    mock_logger.warning.assert_not_called()
    
    def test_environment_variable_precedence(self):
        """Test environment variable precedence over config values."""
        base_config = {
            "adapter": "tiktoken",
            "model": "gpt-3.5-turbo",
            "max_tokens": 4096,
            "heuristic": {"chars_per_token": 4.0},
            "huggingface": {"use_fast": True},
        }
        
        env_overrides = {
            f"{ENV_PREFIX}ADAPTER": "heuristic",
            f"{ENV_PREFIX}MODEL": "custom-model",
            f"{ENV_PREFIX}MAX_TOKENS": "2048",
            f"{ENV_PREFIX}HEURISTIC_CHARS_PER_TOKEN": "3.0",
            f"{ENV_PREFIX}HUGGINGFACE_USE_FAST": "false",
        }
        
        with patch.dict(os.environ, env_overrides):
            result = TokenizerConfigLoader._apply_environment_overrides(base_config)
            
            # Environment variables should override config values
            assert result["adapter"] == "heuristic"
            assert result["model"] == "custom-model"
            assert result["max_tokens"] == 2048
            assert result["heuristic"]["chars_per_token"] == 3.0
            assert result["huggingface"]["use_fast"] is False
    
    def test_partial_environment_overrides(self):
        """Test partial environment overrides don't affect other values."""
        base_config = {
            "adapter": "tiktoken",
            "model": "gpt-4",
            "max_tokens": 8192,
            "heuristic": {"chars_per_token": 4.0},
            "huggingface": {"use_fast": True, "trust_remote_code": False},
        }
        
        # Only override one value
        with patch.dict(os.environ, {f"{ENV_PREFIX}ADAPTER": "heuristic"}):
            result = TokenizerConfigLoader._apply_environment_overrides(base_config)
            
            # Only adapter should change
            assert result["adapter"] == "heuristic"
            assert result["model"] == "gpt-4"  # Unchanged
            assert result["max_tokens"] == 8192  # Unchanged
            assert result["heuristic"]["chars_per_token"] == 4.0  # Unchanged
            assert result["huggingface"]["use_fast"] is True  # Unchanged


class TestConfigurationFileParsingEdgeCases:
    """Comprehensive tests for configuration file parsing."""
    
    def test_toml_parsing_edge_cases(self):
        """Test TOML parsing with various edge cases."""
        toml_scenarios = [
            # Basic TOML
            ('adapter = "heuristic"\nmodel = "test"', {"adapter": "heuristic", "model": "test"}),
            
            # TOML with sections
            ('[tokenizer]\nadapter = "auto"\n[tokenizer.heuristic]\nchars_per_token = 3.5', 
             {"tokenizer": {"adapter": "auto", "heuristic": {"chars_per_token": 3.5}}}),
            
            # TOML with comments
            ('# Configuration\nadapter = "heuristic"  # Comment\nmodel = "test"', 
             {"adapter": "heuristic", "model": "test"}),
            
            # TOML with arrays
            ('fallback_chain = ["tiktoken", "heuristic"]', 
             {"fallback_chain": ["tiktoken", "heuristic"]}),
            
            # TOML with booleans
            ('[huggingface]\nuse_fast = true\ntrust_remote_code = false', 
             {"huggingface": {"use_fast": True, "trust_remote_code": False}}),
            
            # TOML with numbers
            ('max_tokens = 1024\n[heuristic]\nchars_per_token = 3.5', 
             {"max_tokens": 1024, "heuristic": {"chars_per_token": 3.5}}),
        ]
        
        for toml_content, expected in toml_scenarios:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
                f.write(toml_content)
                f.flush()
                f.close()
                
                try:
                    result = TokenizerConfigLoader._read_toml_file(Path(f.name))
                    
                    # Check expected keys and values
                    for key, value in expected.items():
                        assert key in result
                        if isinstance(value, dict):
                            for sub_key, sub_value in value.items():
                                assert result[key][sub_key] == sub_value
                        else:
                            assert result[key] == value
                            
                finally:
                    os.unlink(f.name)
    
    def test_toml_parsing_error_handling(self):
        """Test TOML parsing error handling."""
        invalid_toml_scenarios = [
            # Invalid TOML syntax
            'adapter = "unclosed string',
            'adapter = invalid_value_without_quotes',
            '[invalid section\nkey = "value"',
            'key = value = "double assignment"',
            'adapter = "test"\n[adapter]\nconflict = true',  # Table conflict
        ]
        
        for invalid_toml in invalid_toml_scenarios:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
                f.write(invalid_toml)
                f.flush()
                f.close()
                
                try:
                    with pytest.raises(ConfigError, match="Failed to load TOML"):
                        TokenizerConfigLoader._read_toml_file(Path(f.name))
                finally:
                    os.unlink(f.name)
    
    def test_json_parsing_edge_cases(self):
        """Test JSON parsing with various edge cases."""
        json_scenarios = [
            # Basic JSON
            ('{"adapter": "heuristic", "model": "test"}', {"adapter": "heuristic", "model": "test"}),
            
            # Nested JSON
            ('{"tokenizer": {"adapter": "auto", "heuristic": {"chars_per_token": 3.5}}}',
             {"tokenizer": {"adapter": "auto", "heuristic": {"chars_per_token": 3.5}}}),
            
            # JSON with arrays
            ('{"fallback_chain": ["tiktoken", "heuristic"]}',
             {"fallback_chain": ["tiktoken", "heuristic"]}),
            
            # JSON with booleans and null
            ('{"use_fast": true, "trust_remote_code": false, "encoding": null}',
             {"use_fast": True, "trust_remote_code": False, "encoding": None}),
            
            # JSON with numbers
            ('{"max_tokens": 1024, "chars_per_token": 3.5}',
             {"max_tokens": 1024, "chars_per_token": 3.5}),
        ]
        
        for json_content, expected in json_scenarios:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                f.write(json_content)
                f.flush()
                f.close()
                
                try:
                    with pytest.warns(DeprecationWarning, match="JSON config is deprecated"):
                        result = TokenizerConfigLoader._read_json_file(Path(f.name))
                    
                    # Check expected keys and values
                    for key, value in expected.items():
                        assert key in result
                        if isinstance(value, dict):
                            for sub_key, sub_value in value.items():
                                assert result[key][sub_key] == sub_value
                        else:
                            assert result[key] == value
                            
                finally:
                    os.unlink(f.name)
    
    def test_json_parsing_error_handling(self):
        """Test JSON parsing error handling."""
        invalid_json_scenarios = [
            # Invalid JSON syntax
            '{"adapter": "unclosed string}',
            '{"adapter": invalid_value}',
            '{"adapter": "test",}',  # Trailing comma
            '{adapter: "test"}',  # Unquoted key
            '{"adapter": "test" "model": "test"}',  # Missing comma
        ]
        
        for invalid_json in invalid_json_scenarios:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                f.write(invalid_json)
                f.flush()
                f.close()
                
                try:
                    with pytest.raises(ConfigError, match="Failed to load JSON"):
                        TokenizerConfigLoader._read_json_file(Path(f.name))
                finally:
                    os.unlink(f.name)
    
    def test_file_not_found_handling(self):
        """Test handling of non-existent files."""
        # TOML file not found
        result = TokenizerConfigLoader._read_toml_file(Path("nonexistent.toml"))
        assert result == {}
        
        # JSON file not found
        result = TokenizerConfigLoader._read_json_file(Path("nonexistent.json"))
        assert result == {}
    
    def test_file_permission_errors(self):
        """Test handling of file permission errors."""
        if os.name == "nt":
            pytest.skip("chmod-based permission tests are not reliable on Windows")

        # Create a file and make it unreadable
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write('adapter = "test"')
            f.flush()
            f.close()
            
            try:
                # Make file unreadable (Unix-like systems)
                if hasattr(os, 'chmod'):
                    os.chmod(f.name, 0o000)
                    
                    with pytest.raises(ConfigError):
                        TokenizerConfigLoader._read_toml_file(Path(f.name))
                
            finally:
                # Restore permissions and clean up
                if hasattr(os, 'chmod'):
                    os.chmod(f.name, 0o644)
                os.unlink(f.name)


class TestConfigurationMigrationEdgeCases:
    """Comprehensive tests for configuration migration."""
    
    def test_migration_with_complex_nested_structures(self):
        """Test migration with complex nested configuration structures."""
        complex_old_config = {
            "tokenizer": {
                "adapter": "heuristic",
                "model": "custom-model",
                "max_tokens": 2048,
                "fallback_chain": ["heuristic", "tiktoken"],
                "options": {
                    "chars_per_token": 3.5,
                    "encoding": "p50k_base",
                    "heuristic": {
                        "chars_per_token": 3.0,  # Should override top-level
                        "custom_option": "value",
                    },
                    "tiktoken": {
                        "encoding": "cl100k_base",  # Should override top-level
                        "custom_tiktoken_option": "tiktoken_value",
                    },
                    "huggingface": {
                        "use_fast": False,
                        "trust_remote_code": True,
                        "custom_hf_option": "hf_value",
                    },
                    "custom_adapter": {
                        "custom_option": "custom_value",
                    },
                },
            },
            "other_section": {
                "unrelated_key": "unrelated_value",
            },
        }
        
        result = TokenizerConfigMigrator.migrate_pipeline_config(complex_old_config)
        
        # Check basic fields
        assert result["adapter"] == "heuristic"
        assert result["model"] == "custom-model"
        assert result["max_tokens"] == 2048
        assert result["fallback_chain"] == ["heuristic", "tiktoken"]
        
        # Check heuristic options (nested should override top-level)
        assert result["heuristic"]["chars_per_token"] == 3.0
        assert result["heuristic"]["custom_option"] == "value"
        
        # Check tiktoken options
        assert result["tiktoken"]["encoding"] == "cl100k_base"
        assert result["tiktoken"]["custom_tiktoken_option"] == "tiktoken_value"
        
        # Check huggingface options
        assert result["huggingface"]["use_fast"] is False
        assert result["huggingface"]["trust_remote_code"] is True
        assert result["huggingface"]["custom_hf_option"] == "hf_value"
        
        # Check that custom adapter options are preserved
        assert result["options"]["custom_adapter"]["custom_option"] == "custom_value"
    
    def test_migration_with_missing_sections(self):
        """Test migration with missing or incomplete sections."""
        incomplete_configs = [
            # No tokenizer section
            {"other_section": {"key": "value"}},
            
            # Empty tokenizer section
            {"tokenizer": {}},
            
            # Tokenizer section with only some fields
            {"tokenizer": {"adapter": "tiktoken"}},
            
            # Tokenizer section with only options
            {"tokenizer": {"options": {"chars_per_token": 3.5}}},
        ]
        
        for incomplete_config in incomplete_configs:
            result = TokenizerConfigMigrator.migrate_pipeline_config(incomplete_config)
            
            # Should have all default values
            assert result["adapter"] == DEFAULT_CONFIG["adapter"]
            assert result["model"] == DEFAULT_CONFIG["model"]
            assert result["max_tokens"] == DEFAULT_CONFIG["max_tokens"]
            assert result["fallback_chain"] == DEFAULT_CONFIG["fallback_chain"]
            
            # Should have default adapter configurations
            assert result["heuristic"] == ADAPTER_DEFAULTS["heuristic"]
            assert result["tiktoken"] == ADAPTER_DEFAULTS["tiktoken"]
            assert result["huggingface"] == ADAPTER_DEFAULTS["huggingface"]
    
    def test_migration_with_invalid_data_types(self):
        """Test migration with invalid data types in old config."""
        invalid_configs = [
            # Non-dict tokenizer section
            {"tokenizer": "string_instead_of_dict"},
            {"tokenizer": 123},
            {"tokenizer": []},
            
            # Invalid options section
            {"tokenizer": {"options": "string_instead_of_dict"}},
            {"tokenizer": {"options": 123}},
            {"tokenizer": {"options": []}},
        ]
        
        for invalid_config in invalid_configs:
            # Should not raise an exception, but use defaults
            result = TokenizerConfigMigrator.migrate_pipeline_config(invalid_config)
            
            # Should fall back to defaults
            assert result["adapter"] == DEFAULT_CONFIG["adapter"]
            assert result["model"] == DEFAULT_CONFIG["model"]
    
    def test_migration_file_operations(self):
        """Test migration file operations with various scenarios."""
        # Test successful migration
        old_config = {
            "tokenizer": {
                "adapter": "tiktoken",
                "model": "gpt-4",
                "options": {"encoding": "cl100k_base"}
            }
        }
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as input_file:
            json.dump(old_config, input_file)
            input_file.flush()
            input_file.close()
            
            with tempfile.NamedTemporaryFile(suffix=".toml", delete=False) as output_file:
                output_file.close()
                os.unlink(output_file.name)  # Remove so it doesn't exist
                
                try:
                    # Mock the TOML writing functionality
                    with patch('kano_backlog_core.tokenizer_config.TokenizerConfigMigrator.write_toml_config') as mock_write:
                        TokenizerConfigMigrator.migrate_file(Path(input_file.name), Path(output_file.name))
                        mock_write.assert_called_once()
                        
                finally:
                    os.unlink(input_file.name)
                    if os.path.exists(output_file.name):
                        os.unlink(output_file.name)
    
    def test_migration_error_handling(self):
        """Test migration error handling."""
        # Test with non-existent input file
        with pytest.raises(ConfigError, match="Input configuration file not found"):
            TokenizerConfigMigrator.migrate_file(Path("nonexistent.json"), Path("output.toml"))


class TestConfigurationLoadingIntegration:
    """Integration tests for configuration loading."""
    
    def test_load_config_with_file_precedence(self):
        """Test configuration loading with file precedence (TOML over JSON)."""
        toml_config = {"adapter": "heuristic", "model": "toml-model"}
        json_config = {"adapter": "tiktoken", "model": "json-model"}
        
        with tempfile.TemporaryDirectory() as temp_dir:
            config_base = Path(temp_dir) / "config"
            toml_path = config_base.with_suffix(".toml")
            json_path = config_base.with_suffix(".json")
            
            # Write both files
            with open(toml_path, "w") as f:
                f.write('adapter = "heuristic"\nmodel = "toml-model"')
            
            with open(json_path, "w") as f:
                json.dump(json_config, f)
            
            # Should prefer TOML over JSON
            config = load_tokenizer_config(config_path=config_base)
            assert config.adapter == "heuristic"
            assert config.model == "toml-model"
    
    def test_load_config_with_tokenizer_section_extraction(self):
        """Test configuration loading with tokenizer section extraction."""
        full_config = {
            "other_section": {"key": "value"},
            "tokenizer": {
                "adapter": "heuristic",
                "model": "test-model",
                "heuristic": {"chars_per_token": 3.5}
            }
        }
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write('[other_section]\nkey = "value"\n[tokenizer]\nadapter = "heuristic"\nmodel = "test-model"\n[tokenizer.heuristic]\nchars_per_token = 3.5')
            f.flush()
            f.close()
            
            try:
                config = load_tokenizer_config(config_path=Path(f.name))
                
                # Should extract only tokenizer section
                assert config.adapter == "heuristic"
                assert config.model == "test-model"
                assert config.heuristic["chars_per_token"] == 3.5
                
            finally:
                os.unlink(f.name)
    
    def test_load_config_with_environment_integration(self):
        """Test configuration loading with environment variable integration."""
        file_config = {"adapter": "tiktoken", "model": "file-model"}
        
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(file_config, f)
            f.flush()
            f.close()
            
            try:
                # Environment should override file
                with patch.dict(os.environ, {f"{ENV_PREFIX}ADAPTER": "heuristic", f"{ENV_PREFIX}MODEL": "env-model"}):
                    config = load_tokenizer_config(config_path=Path(f.name))
                    
                    assert config.adapter == "heuristic"
                    assert config.model == "env-model"
                    
            finally:
                os.unlink(f.name)
    
    def test_create_example_config_completeness(self):
        """Test that create_example_config produces complete, valid configuration."""
        example = create_example_config()
        
        # Should be valid TOML
        assert isinstance(example, str)
        assert len(example) > 0
        
        # Should contain all major sections
        assert "[tokenizer]" in example
        assert "[tokenizer.heuristic]" in example
        assert "[tokenizer.tiktoken]" in example
        assert "[tokenizer.huggingface]" in example
        
        # Should contain environment variable documentation
        assert "KANO_TOKENIZER_ADAPTER" in example
        assert "KANO_TOKENIZER_MODEL" in example
        assert "KANO_TOKENIZER_MAX_TOKENS" in example
        
        # Should contain comments explaining options
        assert "#" in example
        assert "adapter" in example
        assert "model" in example


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
