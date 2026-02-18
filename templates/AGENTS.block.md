<!-- kano-agent-backlog-skill:start -->
## Project backlog discipline (kano-agent-backlog-skill)
- Use `{{SKILL_ROOT}}/SKILL.md` for any planning/backlog work.
- Backlog root is `{{BACKLOG_ROOT}}` (items are file-first; index/logs are derived).
- Before any code change, create/update items in `{{BACKLOG_ROOT}}/items/` (Epic -> Feature -> UserStory -> Task/Bug).
- Enforce the Ready gate on Task/Bug before starting; Worklog is append-only.
- Use the `kano` CLI (not ad-hoc edits) so audit logs capture actions:
  - Bootstrap: `python {{SKILL_ROOT}}/scripts/kano-backlog admin init --product <name> --agent <agent-name>`
  - Create/update: `python {{SKILL_ROOT}}/scripts/kano-backlog workitem create|update-state ... --agent <agent-name>`
  - Views: `python {{SKILL_ROOT}}/scripts/kano-backlog view refresh --agent <agent-name> --product <name>`
- Dashboards auto-refresh after item changes by default (`views.auto_refresh=true`); use `--no-refresh` or set it to `false` if needed.
- **Container note**: `admin init` requires Python + pip. If pip is unavailable in the container, run `admin init` outside and mount `_kano/backlog` + `.kano/backlog_config.toml` into the container.
<!-- kano-agent-backlog-skill:end -->
