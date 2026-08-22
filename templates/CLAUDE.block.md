<!-- kano-agent-backlog-skill:start -->
## Backlog workflow (kano-agent-backlog-skill)
- Skill entrypoint: `{{SKILL_ROOT}}/SKILL.md`
- Backlog root: `{{BACKLOG_ROOT}}`
- Before coding, create/update backlog items and meet the Ready gate.
- Worklog is append-only; record decisions and state changes.
- Before code-changing Done, record branch convergence: target branch (repo default unless human names another), implementation commit, reachable-from-target, remote publication, side-branch human choice when applicable, nested gitlink evidence when applicable, or blocked convergence with blocker/branch/reason/next.
- Prefer running the native `kob` CLI so actions are auditable:
  - `{{SKILL_ROOT}}/scripts/kob admin init --product <name> --agent <agent-name>`
  - `{{SKILL_ROOT}}/scripts/kob workitem create|update-state ... --agent <agent-name> [--product <name>]`
  - `{{SKILL_ROOT}}/scripts/kob view list --product <name>`
  - Run Backboard with `pixi run webview` from the skill repository for maintained backlog review.
- **Container note**: `admin init` requires the native binary for the container platform, not Python/pip.
<!-- kano-agent-backlog-skill:end -->
