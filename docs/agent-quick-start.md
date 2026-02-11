# Agent Quick Start Guide

This guide is for AI agents helping users set up and use kano-agent-backlog-skill from a cloned repository.

## For Agents: When to Use This Guide

Use this guide when:
- User has cloned the skill repository (not installed from PyPI)
- User wants to use the skill in development mode
- User asks you to "initialize the backlog skill" or "set up kano-backlog"
- You need to help set up a local-first backlog system

## Installation: Development Mode

When working with a cloned repository, install in **editable mode** so changes to the code take effect immediately.

### Step 0: Create Virtual Environment (Strongly Recommended)

**IMPORTANT:** Always use a virtual environment to avoid conflicts with system Python packages.

**Windows (PowerShell):**
```powershell
# Create venv
python -m venv .venv

# Activate venv
.\.venv\Scripts\Activate.ps1

# Verify you're in venv (should show .venv path)
where.exe python
```

**Linux/macOS (Bash):**
```bash
# Create venv
python -m venv .venv

# Activate venv
source .venv/bin/activate

# Verify you're in venv (should show .venv path)
which python
```

### Step 1: Verify Prerequisites

```bash
# Check Python version (must be 3.8+)
python --version

# Verify you're in a virtual environment (CRITICAL)
# Windows: where.exe python
# Linux/macOS: which python
# Should show .venv path, NOT system Python
```

### Step 2: Install in Editable Mode

```bash
# Navigate to the skill directory
cd skills/kano-agent-backlog-skill

# Install with dev dependencies
pip install -e ".[dev]"

# This installs:
# - The kano-backlog CLI command
# - All runtime dependencies
# - Development tools (pytest, black, isort, mypy)
```

**What `-e` (editable mode) does:**
- Creates a link to the source code instead of copying files
- Code changes take effect immediately without reinstalling
- Perfect for development and testing

### Step 3: Verify Installation

```bash
# Check CLI is available
kano-backlog --version
# Expected output: kano-backlog version 0.1.0

# Run environment check
kano-backlog doctor
# All checks should pass (✅)
```

## Initialization: Create First Backlog

After installation, initialize a backlog for the user's project.

### Step 1: Navigate to Project Root

```bash
# Go to the project root (where you want the backlog)
cd /path/to/user/project
```

### Step 2: Initialize Backlog

```bash
# Initialize with product name and agent identity
kano-backlog admin init --product <product-name> --agent <agent-id>

# Example:
kano-backlog admin init --product my-app --agent kiro
```

**What this creates:**
```
_kano/backlog/
├── products/
│   └── my-app/
│       ├── items/          # Work items organized by type
│       ├── decisions/      # Architecture Decision Records
│       ├── views/          # Generated dashboards
│       └── _meta/          # Metadata and sequences
```

### Step 3: Verify Structure

```bash
# Check that directories were created
ls -la _kano/backlog/products/my-app/

# Should see: items/, decisions/, views/, _meta/
```

### Step 4: Add Cache Directory to .gitignore (IMPORTANT)

**CRITICAL:** The backlog system creates cache files (SQLite databases, vector embeddings) that should NOT be committed to git.

**Add to your project's `.gitignore`:**

```bash
# Add cache directory to .gitignore
echo "" >> .gitignore
echo "# Kano backlog cache (derived data)" >> .gitignore
echo ".kano/cache" >> .gitignore
```

**Or manually edit `.gitignore` and add:**
```gitignore
# Kano backlog cache (derived data)
.kano/cache
```

**Why this is important:**
- Cache files can be large (embeddings, vector indexes)
- Cache is derived data that can be regenerated
- Prevents merge conflicts on binary files
- Keeps repository size manageable

**What gets cached:**
- `.kano/cache/backlog/` - Backlog-specific caches (chunks, embeddings)
- `.kano/cache/repo/` - Repository code analysis caches (if enabled)

## Common Agent Workflow

### Creating Work Items

**Before writing code, create a work item:**

```bash
# Create a task
kano-backlog item create \
  --type task \
  --title "Implement user authentication" \
  --product my-app \
  --agent kiro

# Output: Created task: MYAPP-TSK-0001
```

**Fill in required fields before starting work:**

```bash
# Edit the item file
code _kano/backlog/products/my-app/items/task/0000/MYAPP-TSK-0001_*.md

# Add these sections:
# - Context: Why this work is needed
# - Goal: What success looks like
# - Approach: How you'll implement it
# - Acceptance Criteria: How to verify it works
# - Risks / Dependencies: What could go wrong
```

**Move to Ready state (enforces required fields):**

```bash
kano-backlog item update-state MYAPP-TSK-0001 \
  --state Ready \
  --agent kiro \
  --product my-app
```

### State Transitions

```bash
# Start work
kano-backlog item update-state MYAPP-TSK-0001 \
  --state InProgress \
  --agent kiro \
  --product my-app

# Complete work
kano-backlog item update-state MYAPP-TSK-0001 \
  --state Done \
  --agent kiro \
  --product my-app
```

### Recording Decisions

**Create an ADR for significant decisions:**

```bash
kano-backlog admin adr create \
  --title "Use JWT for authentication" \
  --product my-app \
  --agent kiro

# Edit the ADR file to document:
# - Context: What's the situation?
# - Decision: What did you decide?
# - Consequences: What are the implications?
# - Alternatives: What else was considered?
```

## Agent Identity (CRITICAL)

**ALWAYS provide explicit `--agent` flag with your identity in EVERY command.**

This is a **required parameter** for auditability and worklog tracking. Commands will fail without it.

**Valid agent IDs:**
- `kiro` - Amazon Kiro
- `copilot` - GitHub Copilot
- `codex` - OpenAI Codex
- `claude` - Anthropic Claude
- `cursor` - Cursor AI
- `windsurf` - Windsurf
- `opencode` - OpenCode
- `antigravity` - Google Antigravity
- `amazon-q` - Amazon Q

**Never use placeholders like:**
- ❌ `<agent-id>`
- ❌ `<AGENT_NAME>`
- ❌ `auto`

**Example - ALL commands need --agent:**
```bash
# ✅ Correct
kano-backlog item create --type task --title "My task" --product my-app --agent kiro

# ❌ Wrong - missing --agent
kano-backlog item create --type task --title "My task" --product my-app
```

## Troubleshooting

### Windows: "ModuleNotFoundError: No module named 'kano_backlog_cli'"

**Problem:** The `kano-backlog.exe` wrapper may have issues finding modules in some Windows environments

**Solution (Recommended):** Use Python to call the script directly instead of the .exe wrapper:

```powershell
# Instead of: kano-backlog item create ...
# Use this:
python skills/kano-agent-backlog-skill/scripts/kano-backlog item create --type task --title "My task" --product my-app --agent kiro

# For all commands, replace:
# kano-backlog → python skills/kano-agent-backlog-skill/scripts/kano-backlog
```

**Why this happens:**
- The `.exe` wrapper installed by pip may not correctly resolve the module path in editable mode
- Calling Python directly bypasses the wrapper and uses the source code directly

**Alternative:** Reinstall in a clean venv:
```powershell
# Deactivate current venv
deactivate

# Remove old venv
Remove-Item -Recurse -Force .venv

# Create fresh venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Reinstall
cd skills/kano-agent-backlog-skill
pip install -e ".[dev]"
```

### "kano-backlog: command not found"

**Problem:** CLI not in PATH after installation

**Solution:**
```bash
# Verify installation
pip show kano-agent-backlog-skill

# If installed but not in PATH, use Python directly:
python skills/kano-agent-backlog-skill/scripts/kano-backlog --version

# Or reinstall:
pip uninstall kano-agent-backlog-skill
pip install -e ".[dev]"
```

### "Missing --agent parameter"

**Problem:** Command fails with error about missing `--agent` parameter

**Solution:** The `--agent` flag is **REQUIRED** for all commands that modify the backlog:

```bash
# ❌ Wrong - will fail
kano-backlog item create --type task --title "My task" --product my-app

# ✅ Correct - includes --agent
kano-backlog item create --type task --title "My task" --product my-app --agent kiro
```

**Commands that require --agent:**
- `admin init`
- `admin adr create`
- `item create`
- `item update-state`
- `worklog append`
- `workset init`
- `topic create`

See the [Agent Identity](#agent-identity-critical) section for valid agent IDs.

### "No module named 'kano_backlog_core'"

**Problem:** Package not installed or installed incorrectly

**Solution:**
```bash
# Ensure you're in the skill directory
cd skills/kano-agent-backlog-skill

# Reinstall in editable mode
pip install -e ".[dev]"
```

### "Invalid state transition"

**Problem:** Trying to skip required states (e.g., Proposed → Done)

**Solution:**
```bash
# Follow the state machine:
# Proposed → Planned → Ready → InProgress → Done

# Move through states sequentially:
kano-backlog item update-state <ID> --state Planned --agent <agent> --product <product>
kano-backlog item update-state <ID> --state Ready --agent <agent> --product <product>
kano-backlog item update-state <ID> --state InProgress --agent <agent> --product <product>
kano-backlog item update-state <ID> --state Done --agent <agent> --product <product>
```

### "Ready gate validation failed"

**Problem:** Task/Bug missing required fields

**Solution:**
```bash
# Edit the item file and fill in all required sections:
# - Context
# - Goal
# - Approach
# - Acceptance Criteria
# - Risks / Dependencies

# Then try the state transition again
```

## Quick Reference

### Installation
```bash
cd skills/kano-agent-backlog-skill
pip install -e ".[dev]"
kano-backlog --version
kano-backlog doctor
```

### Initialization
```bash
cd /path/to/project
kano-backlog admin init --product <product> --agent <agent>
```

### Common Commands
```bash
# Create item
kano-backlog item create --type task --title "<title>" --product <product> --agent <agent>

# List items
kano-backlog item list --product <product>

# Update state
kano-backlog item update-state <ID> --state <state> --agent <agent> --product <product>

# Create ADR
kano-backlog admin adr create --title "<title>" --product <product> --agent <agent>

# Check environment
kano-backlog doctor
```

## For Users: Installing from PyPI

If the user wants to install the released version instead of development mode:

```bash
# Install from PyPI (when available)
pip install kano-agent-backlog-skill

# Verify
kano-backlog --version
kano-backlog doctor
```

See [Quick Start Guide](quick-start.md) for the standard installation workflow.

## Next Steps

After setup, guide the user through:

1. **Create their first work item** - Use `item create` to track work
2. **Understand the Ready gate** - Enforce required fields before starting work
3. **Learn state transitions** - Move items through the workflow
4. **Record decisions** - Use ADRs for significant technical choices
5. **Explore views** - Generate dashboards with `view refresh`

## Additional Resources

- **[Quick Start Guide](quick-start.md)** - Standard installation and usage
- **[Installation Guide](installation.md)** - Detailed setup and troubleshooting
- **[SKILL.md](../SKILL.md)** - Complete workflow rules for agents
- **[CONTRIBUTING.md](../CONTRIBUTING.md)** - Development guidelines
- **[Configuration Guide](configuration.md)** - Advanced configuration options

---

**Remember:** 
- **Always use a virtual environment** (`.venv`) to avoid package conflicts
- **Always provide explicit `--agent` flags** for auditability
- **On Windows, if you encounter module errors**, use `python skills/kano-agent-backlog-skill/scripts/kano-backlog` instead of `kano-backlog.exe`
- Install with `pip install -e ".[dev]"` for development mode
