# Versioning

This skill uses **Git tags** as the source of truth for released versions: `vX.Y.Z`.

## Where to check the current version

- File: `VERSION` (the intended version for the next release tag)
- Command: `python -c "import pathlib; print((pathlib.Path('skills/kano-agent-backlog-skill') / 'VERSION').read_text().strip())"`
- Release notes: `CHANGELOG.md`

## Pre-1.0 policy

While `< 1.0.0`, we treat releases as milestones and iterate quickly, but we still follow a predictable rule:

- `0.0.Z`: patch / bugfix / non-breaking improvement
- `0.Y.0`: may include breaking changes (schema/CLI/layout), with migration notes

## 1.0+ policy (SemVer)

After `1.0.0` we follow SemVer strictly:

- `X.Y.Z`
  - `Z` (patch): backward-compatible bugfix only
  - `Y` (minor): backward-compatible features + optional deprecations
  - `X` (major): breaking changes (must include migration guidance)

## What counts as breaking

Non-exhaustive examples:

- Renaming/removing required frontmatter keys, or changing the meaning of states/groups
- Changing the canonical backlog root layout (`_kano/backlog/**`) or bucket rules
- Removing/renaming CLI flags, or changing defaults that alter deterministic outputs
- Renaming/removing config keys under `_kano/backlog/products/<product>/_config/config.toml`
- Changing canonical dashboard filenames or their grouping semantics

## Release checklist (minimum)

- Docs reflect current behavior (`README*`, `REFERENCE.md`, `references/*`)
- Canonical CLI commands run end-to-end:
  - `python skills/kano-agent-backlog-skill/scripts/kano-backlog view refresh --agent <id>`
  - `python skills/kano-agent-backlog-skill/scripts/kano-backlog workitem update-state <item> --state Done --agent <id>`
- Demo views are regenerated
