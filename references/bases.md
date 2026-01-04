# Obsidian Bases (plugin-free views)

This skill currently ships Dataview examples and a plugin-free view generator. If you want to reduce plugin dependencies, Obsidian **Bases** can replace many Dataview table-style dashboards.

Note: Bases is an Obsidian core feature, but it is newer than Dataview and may have limitations depending on your Obsidian version and platform.

## What Bases can cover well

- Table-style lists of items from a folder (e.g. `_kano/backlog/items`)
- Filtering by simple frontmatter fields (e.g. `type`, `state`, `priority`, `area`, `iteration`)
- Sorting and grouping (where supported by your Bases version)

## What might still require alternatives

- More complex computed fields
- Parent/child tree rendering from `parent` links (Dataview is still better here)
- Custom JS logic (DataviewJS-only)

For tree/MOC, keep Epic `.index.md` files and Obsidian wikilinks in the body.

## Recommended frontmatter conventions for Bases

To keep Bases filtering predictable, prefer:

- Scalars: `id`, `type`, `title`, `state`, `priority`, `parent`, `area`, `iteration`, `created`, `updated`
- Arrays: `tags`, `decisions`

Avoid relying on nested objects for filtering. Keep nested objects only for external references if needed.

## Create a Base for "InProgress Work"

In Obsidian:

1) Create a new Base
2) Set the source folder to `_kano/backlog/items`
3) Add columns: `id`, `type`, `title`, `state`, `priority`, `parent`, `area`, `iteration`, `updated`
4) Add a filter:
   - `state` is one of: `Proposed`, `Planned`, `Ready`, `InProgress`, `Review`, `Blocked`
   - (Optionally hide `Done` and `Dropped`)
5) Save the Base in your vault

## Keep a zero-plugin fallback

Even if you adopt Bases, keep these generator commands as a no-plugin fallback for sharing/CI artifacts:

- `python skills/kano-agent-backlog-skill/scripts/backlog/generate_view.py --groups "New,InProgress" --title "InProgress Work" --output _kano/backlog/views/Dashboard_PlainMarkdown_Active.md`
- `python skills/kano-agent-backlog-skill/scripts/backlog/generate_view.py --groups "New" --title "New Work" --output _kano/backlog/views/Dashboard_PlainMarkdown_New.md`
- `python skills/kano-agent-backlog-skill/scripts/backlog/generate_view.py --groups "Done" --title "Done Work" --output _kano/backlog/views/Dashboard_PlainMarkdown_Done.md`
