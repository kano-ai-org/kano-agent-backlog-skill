<!-- kano-agent-backlog-skill:start -->
## Project backlog discipline (kano-agent-backlog-skill)
- Use `{{SKILL_ROOT}}/SKILL.md` for any planning/backlog work.
- Backlog root is `{{BACKLOG_ROOT}}` (items are file-first; index/logs are derived).
- Before any code change, create/update items in `{{BACKLOG_ROOT}}/items/` (Epic -> Feature -> UserStory -> Task/Bug).
- Enforce the Ready gate on Task/Bug before starting; Worklog is append-only.
- Before code-changing Done, record branch convergence: target branch (repo default unless human names another), implementation commit, reachable-from-target, remote publication, side-branch human choice when applicable, nested gitlink evidence when applicable, or blocked convergence with blocker/branch/reason/next.
- Use the native `kob` CLI (not ad-hoc edits) so audit logs capture actions:
  - Bootstrap: `{{SKILL_ROOT}}/scripts/kob admin init --product <name> --agent <agent-name>`
  - Create/update: `{{SKILL_ROOT}}/scripts/kob workitem create|update-state ... --agent <agent-name>`
  - Custom views: `{{SKILL_ROOT}}/scripts/kob view list --product <name>`
  - Review surface: run Backboard with `pixi run webview` from the skill repository.
- **Container note**: `admin init` requires the native binary for the container platform, not Python/pip.
<!-- kano-agent-backlog-skill:end -->
