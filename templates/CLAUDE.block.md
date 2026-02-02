<!-- kano-agent-backlog-skill:start -->
## Backlog workflow (kano-agent-backlog-skill)
- Skill entrypoint: `{{SKILL_ROOT}}/SKILL.md`
- Backlog root: `{{BACKLOG_ROOT}}`
- Before coding, create/update backlog items and meet the Ready gate.
- Worklog is append-only; record decisions and state changes.
- Prefer running the `kano` CLI so actions are auditable (and dashboards stay current):
  - `python {{SKILL_ROOT}}/scripts/kano-backlog admin init --product <name> --agent <agent-name>`
  - `python {{SKILL_ROOT}}/scripts/kano-backlog workitem create|update-state ... --agent <agent-name> [--product <name>]`
  - `python {{SKILL_ROOT}}/scripts/kano-backlog view refresh --agent <agent-name> --product <name>`
- Dashboards auto-refresh after item changes by default (`views.auto_refresh=true`); use `--no-refresh` or set it to `false` if needed.
- **Container note**: `admin init` requires Python + pip. If pip is unavailable in the container, run `admin init` outside and mount `_kano/backlog` + `.kano/backlog_config.toml` into the container.
<!-- kano-agent-backlog-skill:end -->
