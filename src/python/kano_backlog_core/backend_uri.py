"""Backend URI compilation.

Local-first only:
- Compiles human-friendly backend config blocks into canonical URIs.
- Does not make any network calls.
- Does not execute any commands (including MCP); MCP URIs are string-compiled only.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.parse import quote, urlparse

from .errors import ConfigError


_SECRET_KEY_SUFFIXES = ("_token", "_password", "_key")


def _require_str(data: Mapping[str, Any], key: str, *, ctx: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Missing or invalid '{key}' for {ctx}")
    return value.strip()


def _validate_no_secrets_in_config(data: Mapping[str, Any], *, ctx: str) -> None:
    """Reject obvious secrets unless they are env: references."""
    for key, value in data.items():
        if isinstance(key, str) and key.lower().endswith(_SECRET_KEY_SUFFIXES):
            if isinstance(value, str) and value.strip().startswith("env:"):
                continue
            raise ConfigError(f"Secrets must not be stored in config ({ctx}.{key}); use env:VAR")


def compile_backend_uri(
    backend_name: str,
    backend: Mapping[str, Any],
    *,
    default_filesystem_root: Optional[Path] = None,
) -> dict[str, Any]:
    """Compile a single backend block, adding a 'uri' field.

    Returns a new dict (does not mutate input).
    """
    if not isinstance(backend, Mapping):
        raise ConfigError(f"Backend '{backend_name}' must be a table/object")

    backend_dict: dict[str, Any] = dict(backend)
    ctx = f"backends.{backend_name}"

    _validate_no_secrets_in_config(backend_dict, ctx=ctx)

    backend_type = _require_str(backend_dict, "type", ctx=ctx).lower()

    if backend_type == "filesystem":
        root_value = backend_dict.get("root")
        root_path: Optional[Path]
        if isinstance(root_value, str) and root_value.strip():
            root_path = Path(root_value).expanduser()
        else:
            root_path = default_filesystem_root

        if root_path is None:
            raise ConfigError(f"filesystem backend requires 'root' or a default root ({ctx})")

        root_path = root_path.resolve()
        # RFC 8089 style file URI
        backend_dict["uri"] = root_path.as_uri()
        return backend_dict

    if backend_type == "jira":
        host = _require_str(backend_dict, "host", ctx=ctx)
        project = _require_str(backend_dict, "project", ctx=ctx)
        backend_dict["uri"] = f"jira://{host}/{project}"
        return backend_dict

    if backend_type in {"azure-devops", "azure"}:
        org = _require_str(backend_dict, "organization", ctx=ctx)
        project = _require_str(backend_dict, "project", ctx=ctx)
        backend_dict["uri"] = f"azure://dev.azure.com/{org}/{project}"
        return backend_dict

    if backend_type == "http":
        base_url = _require_str(backend_dict, "base_url", ctx=ctx)
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"}:
            raise ConfigError(f"http backend base_url must start with http:// or https:// ({ctx}.base_url)")
        backend_dict["uri"] = base_url
        return backend_dict

    if backend_type == "mcp":
        # Spec-only: compile to a URI string; never execute.
        transport = _require_str(backend_dict, "transport", ctx=ctx).lower()
        if transport != "stdio":
            raise ConfigError(f"Unsupported mcp transport '{transport}' ({ctx}.transport)")

        command = _require_str(backend_dict, "command", ctx=ctx)
        args = backend_dict.get("args")
        if args is None:
            args_list: list[str] = []
        elif isinstance(args, list) and all(isinstance(a, str) for a in args):
            args_list = [a for a in args]
        else:
            raise ConfigError(f"mcp args must be an array of strings ({ctx}.args)")

        # Encode path segments for safe URI representation
        segments = [quote(command, safe=""), *[quote(a, safe="") for a in args_list]]
        backend_dict["uri"] = "mcp+stdio://" + "/".join(segments)
        return backend_dict

    raise ConfigError(f"Unsupported backend type '{backend_type}' ({ctx}.type)")


def compile_backends(
    backends: Mapping[str, Any],
    *,
    default_filesystem_root: Optional[Path] = None,
) -> dict[str, Any]:
    """Compile all backends in a [backends] table.

    Returns a new dict with each backend augmented with a compiled 'uri'.
    """
    if not isinstance(backends, Mapping):
        raise ConfigError("backends must be a table/object")

    compiled: dict[str, Any] = {}
    for name, backend in backends.items():
        if not isinstance(name, str) or not name.strip():
            raise ConfigError("backend names must be non-empty strings")
        compiled[name] = compile_backend_uri(
            name,
            backend if isinstance(backend, Mapping) else {},
            default_filesystem_root=default_filesystem_root,
        )
    return compiled


def compile_effective_config(
    effective: Mapping[str, Any],
    *,
    default_filesystem_root: Optional[Path] = None,
) -> dict[str, Any]:
    """Return a copy of effective config with compiled backend URIs."""
    if not isinstance(effective, Mapping):
        raise ConfigError("effective config must be a dict")

    out: dict[str, Any] = deepcopy(dict(effective))
    backends = out.get("backends")
    if isinstance(backends, Mapping):
        out["backends"] = compile_backends(backends, default_filesystem_root=default_filesystem_root)
    return out
