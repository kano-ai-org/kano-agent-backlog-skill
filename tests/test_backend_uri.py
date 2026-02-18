from pathlib import Path

import pytest

from kano_backlog_core.backend_uri import (
    compile_backend_uri,
    compile_backends,
    compile_effective_config,
)
from kano_backlog_core.errors import ConfigError


def test_compile_filesystem_with_explicit_root(tmp_path: Path):
    out = compile_backend_uri("local", {"type": "filesystem", "root": str(tmp_path)})
    assert out["uri"].startswith("file:///")


def test_compile_filesystem_with_default_root(tmp_path: Path):
    out = compile_backend_uri("local", {"type": "filesystem"}, default_filesystem_root=tmp_path)
    assert out["uri"].startswith("file:///")


def test_compile_filesystem_missing_root_raises():
    with pytest.raises(ConfigError, match="filesystem backend requires"):
        compile_backend_uri("local", {"type": "filesystem"})


def test_compile_jira():
    out = compile_backend_uri("jira", {"type": "jira", "host": "example.atlassian.net", "project": "PROJ"})
    assert out["uri"] == "jira://example.atlassian.net/PROJ"


def test_compile_azure_devops():
    out = compile_backend_uri(
        "azure",
        {"type": "azure-devops", "organization": "myorg", "project": "MyProject"},
    )
    assert out["uri"] == "azure://dev.azure.com/myorg/MyProject"


def test_compile_http():
    out = compile_backend_uri("api", {"type": "http", "base_url": "https://example.com/api/v1"})
    assert out["uri"] == "https://example.com/api/v1"


def test_compile_http_rejects_non_http_scheme():
    with pytest.raises(ConfigError, match="must start with http"):
        compile_backend_uri("api", {"type": "http", "base_url": "file:///tmp"})


def test_compile_mcp_stdio():
    out = compile_backend_uri(
        "mcp",
        {"type": "mcp", "transport": "stdio", "command": "npx", "args": ["-y", "@mcp/server"]},
    )
    assert out["uri"].startswith("mcp+stdio://")


def test_compile_mcp_rejects_unknown_transport():
    with pytest.raises(ConfigError, match="Unsupported mcp transport"):
        compile_backend_uri("mcp", {"type": "mcp", "transport": "tcp", "command": "x"})


def test_compile_backends_compiles_each():
    out = compile_backends(
        {
            "jira": {"type": "jira", "host": "h", "project": "P"},
            "api": {"type": "http", "base_url": "https://x"},
        }
    )
    assert out["jira"]["uri"] == "jira://h/P"
    assert out["api"]["uri"] == "https://x"


def test_compile_effective_config_augments_backends():
    effective = {
        "project": {"prefix": "KABSD"},
        "backends": {"jira": {"type": "jira", "host": "h", "project": "P"}},
    }
    out = compile_effective_config(effective)
    assert out["backends"]["jira"]["uri"] == "jira://h/P"


def test_reject_secrets_in_backend_config():
    with pytest.raises(ConfigError, match="Secrets must not be stored"):
        compile_backend_uri("api", {"type": "http", "base_url": "https://x", "api_token": "secret"})


def test_allow_env_secret_reference():
    out = compile_backend_uri(
        "api",
        {"type": "http", "base_url": "https://x", "api_token": "env:BACKLOG_API_TOKEN"},
    )
    assert out["uri"] == "https://x"
