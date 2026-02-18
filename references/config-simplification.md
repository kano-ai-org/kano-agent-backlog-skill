# Multi-Product Config Simplification

## Current Problem

The current multi-product configuration approach has several limitations:

1. **Scattered Configuration**: Each product requires its own config at `_kano/backlog/products/<product>/_config/config.toml`
2. **Fixed Structure**: Backlog data must be under `_kano/backlog/products/<product>/`
3. **Management Overhead**: With many products, configuration becomes unwieldy
4. **Limited Flexibility**: Cannot easily point to different backlog root locations

## Proposed Solution

### Project-Level Configuration

Introduce `.kano/backlog_config.toml` at the project root that can define multiple products:

```toml
# .kano/backlog_config.toml - Project-level multi-product backlog configuration

# Global defaults
[defaults]
skill_developer = true
persona = "developer"
auto_refresh = true

# Product definitions
[products.kano-agent-backlog-skill]
name = "kano-agent-backlog-skill-demo"
prefix = "KABSD"
backlog_root = "_kano/backlog/products/kano-agent-backlog-skill"

[products.kano-opencode-quickstart]
name = "kano-opencode-quickstart"
prefix = "KO"
backlog_root = "../kano-opencode-quickstart/_kano/backlog"

[products.my-other-project]
name = "my-other-project"
prefix = "MOP"
backlog_root = "/path/to/external/backlog"

# Shared settings for all products
[shared.log]
verbosity = "warning"
debug = false

[shared.index]
enabled = true
backend = "sqlite"
mode = "rebuild"
```

### Configuration Resolution Hierarchy

1. **CLI Arguments** (highest priority)
2. **Project Config** (`.kano/backlog_config.toml`)
3. **Product Config** (`<backlog_root>/_config/config.toml`)
4. **Defaults** (lowest priority)

### Backward Compatibility

- Existing per-product configs continue to work
- If no project config exists, fall back to current behavior
- Project config can override or extend per-product settings

## Implementation Plan

### Phase 1: Core Config System

1. **Config Schema Extension**
   ```python
   # New schema support
   class ProjectConfig:
       defaults: Dict[str, Any]
       products: Dict[str, ProductDefinition]
       shared: Dict[str, Any]
   
   class ProductDefinition:
       name: str
       prefix: str
       backlog_root: str
       overrides: Dict[str, Any] = {}
   ```

2. **Config Resolution Logic**
   ```python
   def resolve_config(product_name: str, cli_args: Dict) -> Config:
       # 1. Load project config if exists
       project_config = load_project_config(".kano/backlog.toml")
       
       # 2. Load product-specific config
       product_config = load_product_config(backlog_root, product_name)
       
       # 3. Merge with precedence
       return merge_configs(
           defaults=get_defaults(),
           product_config=product_config,
           project_config=project_config,
           cli_args=cli_args
       )
   ```

### Phase 2: CLI Integration

1. **New CLI Parameters**
   ```bash
   # Specify project config file
   kano-backlog --config-file .kano/backlog_config.toml workitem create ...
   
   # Auto-detect project config
   kano-backlog workitem create --product my-project ...
   ```

2. **Enhanced Init Command**
   ```bash
   # Initialize with project config
   kano-backlog admin init-project --config-file .kano/backlog_config.toml
   
   # Add product to existing project config
   kano-backlog admin add-product --name my-project --prefix MP --backlog-root ./backlog
   ```

### Phase 3: Migration Tools

1. **Migration Command**
   ```bash
   # Convert existing multi-product setup to project config
   kano-backlog admin migrate-to-project-config --output .kano/backlog.toml
   ```

2. **Validation Tools**
   ```bash
   # Validate project config
   kano-backlog admin validate-project-config .kano/backlog_config.toml
   
   # Show effective config for a product
   kano-backlog admin show-effective-config --product my-project
   ```

## Benefits

### For Skill Developers

1. **Centralized Management**: All product configs in one place
2. **Flexible Locations**: Point backlog roots anywhere
3. **Shared Settings**: Common configuration across products
4. **Easy Maintenance**: Single file to manage

### For Users

1. **Simplified Setup**: One config file per project
2. **Clear Structure**: Obvious where configuration lives
3. **Flexible Deployment**: Support various project layouts
4. **Backward Compatible**: Existing setups continue working

## Example Use Cases

### Use Case 1: Monorepo with Multiple Products

```toml
# .kano/backlog_config.toml
[products.frontend]
name = "frontend-app"
prefix = "FE"
backlog_root = "_kano/backlog/frontend"

[products.backend]
name = "backend-api"
prefix = "BE"
backlog_root = "_kano/backlog/backend"

[products.mobile]
name = "mobile-app"
prefix = "MOB"
backlog_root = "_kano/backlog/mobile"
```

### Use Case 2: External Backlog Management

```toml
# .kano/backlog_config.toml - Central backlog management project
[products.project-a]
name = "project-a"
prefix = "PA"
backlog_root = "/projects/project-a/_kano/backlog"

[products.project-b]
name = "project-b"
prefix = "PB"
backlog_root = "/projects/project-b/_kano/backlog"
```

### Use Case 3: Skill Development

```toml
# .kano/backlog_config.toml - Skill developer managing multiple demos
[defaults]
skill_developer = true

[products.skill-demo]
name = "kano-agent-backlog-skill-demo"
prefix = "KABSD"
backlog_root = "_kano/backlog/products/kano-agent-backlog-skill"

[products.quickstart-demo]
name = "kano-opencode-quickstart"
prefix = "KO"
backlog_root = "../kano-opencode-quickstart/_kano/backlog"
```

## Migration Strategy

### Automatic Detection

1. Check for `.kano/backlog_config.toml` first
2. If not found, use existing per-product config discovery
3. Provide migration tools for existing setups

### Gradual Adoption

1. Phase 1: Support both config styles
2. Phase 2: Recommend project config for new setups
3. Phase 3: Deprecate per-product configs (with long transition period)

## Implementation Notes

### Config File Location

- Primary: `.kano/backlog_config.toml` (project root)
- Alternative: `--config-file` CLI parameter
- Environment: `KANO_CONFIG_FILE` environment variable

### Path Resolution

- Relative paths in `backlog_root` are relative to config file location
- Absolute paths are used as-is
- Support environment variable expansion: `${HOME}/backlog`

### Validation

- Validate all `backlog_root` paths exist or can be created
- Ensure product names and prefixes are unique
- Check for conflicting configurations

This design provides the flexibility you're looking for while maintaining backward compatibility and supporting various project layouts.