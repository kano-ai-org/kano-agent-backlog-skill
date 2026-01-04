# Audit Logging (Agent Tool Invocations)

## Log location (default)

- Root: `_kano/backlog/_logs/agent_tools/`
- File: `tool_invocations.jsonl`

## Log format (JSONL)

Each line is a JSON object:

```
{
  "version": 1,
  "timestamp": "2026-01-04T10:50:12Z",
  "tool": "shell_command",
  "cwd": "D:/_work/_Kano/kano-agent-backlog-skill-demo",
  "status": "ok",
  "exit_code": 0,
  "duration_ms": 123,
  "command_args": ["python", "script.py", "--flag", "***"],
  "replay_command": "python script.py --flag ***",
  "notes": "optional"
}
```

### Required fields

- `version`
- `timestamp`
- `tool`
- `cwd`
- `status`
- `command_args`
- `replay_command`

### Optional fields

- `exit_code`
- `duration_ms`
- `notes`
- `error`

## Redaction rules

Redact any value that is likely sensitive. Defaults include:

- Flags: `--token`, `--api-key`, `--secret`, `--password`, `--passwd`, `--pwd`,
  `--client-secret`, `--access-key`, `--authorization`, `--bearer`, `--cookie`
- Key-value pairs: `token=...`, `api_key=...`, `secret=...`, `password=...`
- Env-style keys (case-insensitive): `*_TOKEN`, `*_KEY`, `*_SECRET`, `*_PASSWORD`

Redaction replaces the value with `***` while leaving the flag/key intact.

## Rotation and retention (defaults)

- Rotate when file size exceeds 5 MB.
- Keep the last 10 rotated files.
- File naming: `tool_invocations.jsonl`, `tool_invocations.1.jsonl`, ...

These values can be made configurable later, but the defaults must exist.

## Script integration

Backlog and filesystem scripts call `scripts/logging/audit_runner.py` at
entrypoint so every invocation appends an audit log entry.
