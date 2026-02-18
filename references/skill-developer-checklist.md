# Skill Developer Maintenance Checklist

This document lists files and patterns that skill developers (with `skill_developer = true`) should maintain when making changes to the kano-backlog system.

## Configuration System Changes

When modifying the configuration system (adding/removing/changing config fields):

### 1. Update System Defaults
- **File**: `src/kano_backlog_core/config.py`
- **Function**: `get_system_defaults()`
- Ensure all default values are documented and reasonable

### 2. Update Configuration Templates
- **File**: `templates/config.template.toml`
- Add new fields with comments explaining their purpose
- Mark optional vs required fields

### 3. Update Gitignore Template
- **File**: `references/gitignore-template.txt`
- Add patterns for new cache/derived data locations
- Update comments if directory structure changes

### 4. Update Documentation
- **File**: `SKILL.md` - Main skill documentation
- **File**: `references/gitignore.md` - Gitignore patterns explanation
- Document new config fields and their effects

## Directory Structure Changes

When adding new directories or changing storage locations:

### 1. Update Gitignore Template
- **File**: `references/gitignore-template.txt`
- Add patterns for new derived/cache directories
- Never ignore canonical data (items, ADRs, config files)

### 2. Update Path Resolution
- **File**: `src/kano_backlog_core/config.py` - Config resolution logic
- **File**: `src/kano_backlog_core/project_config.py` - Project config paths
- Ensure relative paths work correctly

### 3. Update CLI Commands
- **File**: `src/kano_backlog_cli/commands/*.py`
- Update path parameters and defaults
- Update help text to reflect new structure

## Debug/Development Features

When adding debug output or development tools:

### 1. Respect Debug Mode
- Check `log.debug` config before generating debug output
- Write debug files to `.kano/debug/` (project-level, not backlog-level)
- Never commit debug output to version control

### 2. Demo Project Only
- **Demo project**: `kano-agent-backlog-skill-demo`
- Can include example debug files with gitignore exceptions
- Can commit `.kano/debug/README.md` as documentation

### 3. User Projects
- **User projects**: All other projects using the skill
- Should NOT commit any `.kano/debug/` content
- Gitignore template should ignore entire `.kano/debug/` directory

## Testing Changes

When modifying core functionality:

### 1. Update Tests
- **Directory**: `tests/`
- Add tests for new features
- Update existing tests if behavior changes

### 2. Test with Demo Project
- Run commands in `kano-agent-backlog-skill-demo`
- Verify backlog operations work correctly
- Check that derived data is properly gitignored

### 3. Test with External Backlog
- Use `kano-opencode-quickstart` as test case
- Verify external backlog architecture works
- Check config resolution across project boundaries

## Release Checklist

Before releasing a new version:

### 1. Version Bump
- **File**: `setup.py` or `pyproject.toml`
- Update version number
- Update changelog/release notes

### 2. Documentation Review
- Review all documentation for accuracy
- Update examples if CLI changed
- Check that gitignore template is current

### 3. Template Files
- Verify `gitignore-template.txt` is up to date
- Verify `config.template.toml` includes all fields
- Check that templates match actual usage

### 4. Demo Project State
- Ensure demo backlog is in good state
- Commit any example items/ADRs
- Update `.kano/debug/README.md` if debug features changed

## Files to Maintain

### Always Keep Updated
- `references/gitignore-template.txt` - User gitignore patterns
- `references/gitignore.md` - Gitignore documentation
- `templates/config.template.toml` - Config template
- `SKILL.md` - Main documentation
- `src/kano_backlog_core/config.py` - System defaults

### Demo Project Only
- `kano-agent-backlog-skill-demo/.kano/debug/README.md` - Debug feature docs
- `kano-agent-backlog-skill-demo/.gitignore` - Can have exceptions for examples

### Never Commit (Even in Demo)
- `.kano/cache/*` - Runtime cache
- `.kano/debug/backlog_config.toml` - Environment-specific debug output
- `_kano/backlog/**/.cache/` - Backlog-level cache
- `_kano/backlog/**/_index/` - Derived indexes

## Common Mistakes to Avoid

1. **Don't ignore canonical data**
   - Items, ADRs, views, config files should always be committed
   - Only ignore derived/cache/logs

2. **Don't hardcode paths**
   - Use config resolution for all paths
   - Support both relative and absolute paths

3. **Don't mix project-level and backlog-level state**
   - `.kano/` is project-level (config, cache, debug)
   - `_kano/backlog/` is backlog-level (items, views, canonical data)

4. **Don't commit debug output**
   - Debug files are environment-specific
   - Only commit README.md in demo project

5. **Don't forget to update templates**
   - When adding config fields, update template
   - When changing directory structure, update gitignore template

## Questions?

If you're unsure whether something should be maintained or committed:
1. Is it derived/regenerable? → Ignore it
2. Is it canonical/source-of-truth? → Commit it
3. Is it environment-specific? → Ignore it
4. Is it documentation/example? → Commit it (demo project only)
