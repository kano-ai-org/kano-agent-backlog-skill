# KOB Backboard Design System

This file codifies the existing implicit visual system of Backboard. It is an
extraction from `backboard_css.hpp`, `index_html.hpp`, and the accepted
Backboard design contracts, not a redesign. The current embedded HTML, CSS,
DOM-first rendering, and first-party vanilla JavaScript architecture remain the
implementation baseline. New Backboard UI must preserve this language and must
not add a frontend framework, package build, dark theme, font, color, or motion
without first revising this contract through reviewed design work.

## 1. Atmosphere & Identity

Backboard feels like a quiet, evidence-first operations board: compact, plain,
local, and trustworthy rather than promotional. The interface favors readable
document structure, visible state, bounded controls, and review context over
decoration. Its signature is blue-accented review focus on cool white layered
surfaces: thin blue-gray borders organize dense information, while selection,
loading, stale data, and evidence status are always explicit. Backboard opens
to the Review Inbox because it is a repeated human review surface, not a broad
project dashboard or marketing page.

Identity rules:

- Use `Backboard` in user-facing navigation and labels. Use `KOB Webview` only
  for the native service, runtime, routes, ports, Docker image, or developer
  commands.
- Keep review-critical content DOM-first, inspectable, copyable, and usable as
  text and links. Visualization is secondary and bounded.
- Preserve the no-npm, no-Vite, no-React baseline. Drogon-rendered HTML and
  partials, embedded CSS, and small first-party JavaScript are the default.
- Prefer explicit diagnostics and empty states over silent omission. Missing,
  stale, failed, inherited, and bounded data must say what they are.
- Assignment metadata is read-only display and filtering context. It does not
  grant authorization and must never imply an execution action.

## 2. Color

Backboard has one light theme. The palette is cool neutral with a restrained
KOB blue accent, green success, amber warning, red failure, and violet/green
graph relationship distinctions. No dark palette exists.

### Existing CSS variables

These are the only color custom properties currently declared in `:root`.
Implementations should use them where their roles apply and should not invent
additional values for assignment work.

| Role | Existing token | Exact value | Current usage |
| --- | --- | --- | --- |
| Accent | `--kob-accent` | `#1f4fa3` | Active tabs/workspaces, selected cards, links, progress, focus nodes |
| Accent soft | `--kob-accent-soft` | `#f2f6ff` | Hover fills, keyboard keys, focused graph nodes |
| Accent border/focus | `--kob-accent-border` | `#9fb5de` | Hover borders, focus outlines, callout rule |
| Border default | `--kob-border` | `#cfd9ea` | Controls and reusable outlined surfaces |
| Border strong | `--kob-border-strong` | `#9eb3d7` | Strong outlines and keyboard keys |
| Surface default | `--kob-surface` | `#fcfdff` | Cards, saved-query rows, light content cells |
| Surface strong | `--kob-surface-strong` | `#ffffff` | Selected and elevated white surfaces |
| Shadow tint | `--kob-shadow` | `rgba(30, 55, 95, 0.12)` | Selectable cards and graph node elevation |

### Existing literal palette

The current stylesheet also uses raw literals. They are documented here as
existing values, not as permission to expand the palette. Consolidating them
into custom properties is future work.

| Role | Exact values | Current usage |
| --- | --- | --- |
| Page and white surfaces | `#f7f8fa`, `#ffffff`, `#fff`, `#fcfdff` | Body, panels, lanes, cards, controls, modals |
| Cool soft surfaces | `#fbfcff`, `#f8fbff`, `#f6f8fc`, `#f5f8ff`, `#f4f6fa`, `#eef2f8`, `#edf1f7`, `#dfe8f7` | Graph, pills, code, callouts, separators, busy progress |
| Primary and secondary text | `#1a1f2e`, `#1d3158`, `#3c4a63`, `#47536a`, `#4f5a6e`, `#586074`, `#65738b`, `#66738a`, `#70809f`, `#7a879d` | Body, busy state, labels, muted text, graph labels and edges |
| Blue accent family | `#1f4fa3`, `#35588f`, `#4d7ed6`, `#4f6fa9`, `#5a6d8f`, `#9fb5de` | Links, active state, progress gradient, parent edges, markers |
| Blue-gray borders | `#9eb3d7`, `#a9bbb0`, `#b9c7de`, `#b9c9e8`, `#c5ccd9`, `#c9d7ef`, `#cbd6e8`, `#cfd9ea`, `#d7dfef`, `#d8e1f0`, `#dbe4f2`, `#dde3f0`, `#dfe6f3`, `#e7edf8` | Controls, panels, cards, modals, graph, status surfaces |
| Success | `#245c2a`, `#498264`, `#6d8a78`, `#7eb58d`, `#86c48b`, `#eef8f2`, `#f1fbf2`, `#f5f8f6` | Passed pills, topic edges/nodes, hierarchy references |
| Warning | `#6a4c0f`, `#7a5610`, `#b57b18`, `#d5b15d`, `#fff9e8` | Stale, blocked, cycle, hidden, and hierarchy warnings |
| Error | `#8a2525`, `#9c1c1c`, `#b44646`, `#c65f5f`, `#d48b8b`, `#db8a8a`, `#fff4f4` | Failed pills, status errors, dependency edges, missing nodes |
| Relationship violet | `#7d6aa6` | Relates graph edges |
| Backdrop and focus alpha | `rgba(20, 28, 44, 0.45)`, `rgba(30, 55, 95, 0.08)`, `rgba(159, 181, 222, 0.85)` | Modal scrim, busy shadow, graph focus ring |

### Usage rules

- Blue communicates navigation, selection, focus, links, and active work. It is
  not decorative.
- Green, amber, red, gray, and relationship colors retain their current
  semantic roles. Never communicate status by color alone; pair color with
  visible text, a symbol, border treatment, dash pattern, or state label.
- Assignment filters and metadata use existing neutral, accent, missing, and
  pill colors only. Actor aliases do not receive unique colors.
- Inherited assignment values must include the visible word `Inherited` and
  their source label; a tint alone is insufficient.
- Missing assignment values use the existing missing-state palette and visible
  text such as `Unassigned` or `No reviewer`; never render an empty cell.
- No dark mode is planned. Do not add theme-dependent values as part of
  assignment filtering.

## 3. Typography

### Font stack

The single existing interface stack is:

```css
"Segoe UI", "Yu Gothic UI", Meiryo, "Microsoft JhengHei UI",
"Microsoft YaHei UI", "Malgun Gothic", "PingFang SC",
"Hiragino Sans", sans-serif
```

It is chosen for native system rendering and broad CJK coverage. No web font,
serif family, or dedicated monospace family is loaded. Browser monospace is
used for `code` and `pre` through user-agent defaults.

### Existing scale

Backboard currently combines browser-default heading/body metrics with a small
explicit metadata scale. Preserve this hierarchy; do not introduce a new type
scale during assignment work.

| Level | Size | Weight | Line height/tracking | Usage |
| --- | --- | --- | --- | --- |
| Page/body | Browser default, normally `16px` | `400` | Browser `normal` | Main labels, values, headings by native element defaults |
| Filter/body small | `13px` | `400` | Browser `normal` | Checkbox filter labels |
| Metadata/caption | `12px` | `400` or `600` | Browser `normal` | Muted text, pills, refresh notes, graph labels, code language |
| Compact label | `11px` | `400` or `700` | `1` only on gate symbol; otherwise browser `normal` | Workspace metadata, gate badges, detail labels |
| Graph micro | `10px` | `400` | SVG/browser default | Graph metadata and edge labels |
| Emphasis | Inherits surrounding size | `600`, `650`, or `700` | Existing local value | Errors, titles, labels, hierarchy node titles |

### Rules

- Keep the current system stack exactly; do not add a font dependency.
- Use semantic heading elements for page and section hierarchy. Existing shell
  headings retain browser-default sizing.
- Use `12px`, uppercase, and weight `700` for filter-group titles. Use `11px`,
  uppercase, weight `700`, and `0.03em` tracking for detail labels.
- Use normal case for actor aliases. Aliases may contain dots, underscores, and
  dashes and must wrap safely rather than truncate essential identity context.
- Reserve uppercase for labels and compact metadata, not assignment values.
- Body and control text should remain at inherited browser size unless they
  are one of the documented metadata roles.

## 4. Spacing & Layout

### Existing spacing rhythm

The implicit rhythm is compact and primarily based on `2px`, `4px`, and `8px`
increments. There are no spacing custom properties. The values below are the
observed design scale; assignment additions should compose from `4px`, `6px`,
`8px`, `10px`, and `12px` instead of adding new values.

| Value | Current intent |
| --- | --- |
| `1px`, `2px` | Code padding, compact metadata offset, tree item rhythm |
| `4px` | Tight labels, icon button padding, title-to-detail separation |
| `5px`, `6px`, `7px` | Dense hierarchy/card gaps, compact controls, status clusters |
| `8px` | Default card/cell padding, compact stack gap, repeated vertical rhythm |
| `9px`, `10px` | Compact callout padding, adaptive grid gaps, grouped surface padding |
| `12px` | Shell gap, panel padding, row gap, section stack, body mobile padding |
| `14px` | Modal horizontal padding and nested tree indent |
| `16px` | Desktop body padding and sticky sidebar offset |
| `18px`, `20px`, `22px`, `24px` | Tree/list indents and modal/backdrop breathing room |

### Radii

| Radius | Usage |
| --- | --- |
| `4px` | Inline code |
| `6px` | Buttons, icon buttons, refresh notes, warnings, hierarchy nodes |
| `8px` | Tabs, cards, review lanes, detail facts, inputs, keys, callouts |
| `10px` | Panels, lanes, modals, graph canvas |
| `999px` | Pills and progress tracks |
| `50%` | Spinner circle |
| SVG `rx: 8` | Graph nodes |

### App shell and responsive behavior

- Desktop body padding is `16px`; at `720px` and below it is `12px`.
- The app shell is a two-column grid: `280px minmax(0, 1fr)` with a `12px`
  gap and start alignment.
- The sidebar is sticky at `top: 16px`. At the single existing breakpoint,
  `@media (max-width: 720px)`, the shell becomes one `minmax(0, 1fr)` column
  and the sidebar becomes static.
- The main column and dense nested grids use `min-width: 0` so long content can
  wrap without forcing horizontal page overflow.
- Panels use `12px` padding and `12px` bottom separation. Cards and lanes use
  `8px` padding. Rows use flexible wrapping with a `12px` gap.
- Filter and review grids use
  `repeat(auto-fit, minmax(220px, 1fr))` with `12px` and `10px` gaps
  respectively. Detail facts use
  `repeat(auto-fit, minmax(180px, 1fr))` with a `10px` gap.
- The five-lane flow grid uses
  `repeat(5, minmax(180px, 1fr))`; it is intentionally dense and may require
  page-level horizontal accommodation on narrow screens until separately
  reviewed.
- Assignment metadata follows the existing adaptive fact-grid grammar. It must
  collapse naturally, preserve `min-width: 0`, and never require a second
  assignment-specific breakpoint.

### Scroll ownership

- The document is the default page scroll owner.
- `.workspace-list` is its own vertical scroll owner at `max-height: 45vh` and
  `overflow: auto`.
- `.modal` is its own vertical scroll owner at `max-height: 88vh` and
  `overflow: auto`; the backdrop does not scroll the modal content.
- `.graph-canvas` owns pan/zoom interaction and clips canvas overflow with
  `overflow: hidden`; text diagnostics remain outside it in the DOM.
- Filter groups, assignment metadata grids, cards, and detail facts do not own
  scrolling. They wrap and let their containing page or modal own overflow.

## 5. Components

All components remain semantic HTML or server-rendered partials enhanced by
first-party JavaScript. Planned assignment additions for KOB-TSK-0056 are
defined here before implementation and reuse the existing component grammar.

### Panel

- **Structure**: A `.panel` section around a heading, controls, or page content.
- **Variants**: Base panel; sticky sidebar panel; active `.page`; hidden `.page`.
- **Spacing**: `12px` padding and bottom margin; `10px` radius.
- **States**: Pages toggle `display: none/block`; refreshing and stale pages add
  a labeled `::before` note. Panels have no decorative hover state.
- **Accessibility**: Use a semantic `aside`, `main`, `section`, or grouping
  element when the content has that meaning. Page state text must remain
  exposed, not color-only.
- **Motion**: None.
- **Layout/scroll**: Panel content participates in document flow. Sidebar is
  sticky above `720px`; panels are not scroll owners.

### Card and Selectable Card

- **Structure**: `.card`; selectable cards add `data-selectable-item`, keyboard
  semantics, and `.is-selected` when current.
- **Variants**: Static card; selectable card; selected card; review-lane card.
- **Spacing**: `8px` padding and bottom margin; `8px` radius. Selected cards use
  a `6px` left border and `10px` left padding.
- **States**: Default cool-white surface; hover gains accent border and shadow;
  focus-visible gains a `3px` accent-border outline at `2px` offset; selected
  gains accent border/ring, stronger shadow, white surface, and `2px` horizontal
  translation.
- **Accessibility**: Selectable cards must remain reachable by keyboard and
  expose selection with the existing text/DOM state, not only translation or
  color. Enter opens current item detail; `j`, `k`, and arrow keys move visible
  selection outside editable controls.
- **Motion**: Border color, shadow, and transform transition for `0.16s ease`.
- **Layout/scroll**: Cards wrap content and are not scroll owners. Long aliases
  and identifiers must not widen the card.

### Pill and Gate Badge

- **Structure**: `.pill` for compact labeled state; `.gate-badge` for a symbol
  plus label inside `.gate-strip`.
- **Variants**: Neutral, passed, failed, blocked, missing; gate symbols supplied
  by `data-gate-symbol`.
- **Spacing**: Pill padding `2px 7px`, `999px` radius; gate strip gap `6px`.
- **States**: Static semantic states only. Links may combine `.item-link.pill`
  and gain underline on hover through the link pattern.
- **Accessibility**: Every state includes readable text. Gate symbols and color
  are redundant cues, not the sole label.
- **Motion**: None.
- **Layout/scroll**: Inline and wrapping cluster; no scroll ownership.

### Filter Group

- **Structure**: `.filter-panel` contains peer `.filter-group` blocks. Each has
  a `.filter-group-title` and a wrapping `.filters` cluster of native labeled
  controls.
- **Variants**: Products, States, Types, and the planned Assignment group.
- **Spacing**: Panel grid gap `12px`; group gap `8px`; control cluster gap
  `10px`; label-to-control gap `6px`.
- **States**: Native unchecked, checked, hover, focus, and disabled control
  states; current filter selection remains visible in the control itself.
- **Accessibility**: Keep visible labels bound to native controls. A group must
  have a readable title and preserve native keyboard behavior. Filter changes
  must update visible result/status text.
- **Motion**: No visual animation; existing JavaScript may debounce requests.
- **Layout/scroll**: Adaptive `220px` minimum grid cells. Controls wrap; the
  panel does not become an inner scroll region.

### Assignment Filter Group (planned)

- **Structure**: One peer `.filter-group` titled `Assignment`, containing two
  visibly labeled exact-match filter clusters: `Assignee` and `Reviewer`.
  Alias choices use the existing native labeled-control pattern. Query values
  are exact repo-visible aliases; display text is the same alias.
- **Variants**: No assignment filter; exact assignee filter; exact reviewer
  filter; both filters active; missing-assignee or missing-reviewer choice when
  supported by the response contract.
- **Spacing**: Reuse filter-group `8px` stacks, `.filters` `10px` wrapping gap,
  and `6px` label gap. Do not add an assignment-only spacing value.
- **States**: Native default, checked/selected, hover, focus, disabled while the
  option source is unavailable, and an explicit empty option state. Active
  exact filters must remain visible after partial refresh and URL restoration.
- **Accessibility**: Use native controls with explicit `Assignee` and
  `Reviewer` names. Do not combine the two dimensions under an unlabeled input.
  Announce refreshed result status through the existing polite status region.
- **Motion**: None beyond existing request lifecycle indicators.
- **Layout/scroll**: The group is a normal auto-fit filter-panel cell. Alias
  choices wrap; no inner scrolling, horizontal carousel, truncation-only label,
  or sticky behavior is introduced.

### Button and Input

- **Structure**: `.btn` for buttons/links, `.icon-btn` for compact icon actions,
  `.tab-btn` for navigation, and native `input`/`select` controls with existing
  local classes where dimensions are needed.
- **Variants**: Neutral, hover, active tab/workspace, disabled graph action,
  numeric, text, select, and wide text input.
- **Spacing**: Buttons use `4px 10px` or icon `4px 6px`; tabs use `6px 12px`;
  graph inputs use `6px 10px`. Radii are `6px` or `8px` by variant.
- **States**: Hover uses accent-soft fill. Active tabs/workspaces use accent
  fill, white text, and accent border. Disabled graph actions use `0.65`
  opacity and default cursor. Inputs use native state behavior.
- **Accessibility**: Use native `button`, `input`, and `select`; bind labels;
  include `type="button"` when form submission is not intended; retain shortcut
  and toolbar ARIA already used by Backboard. Do not remove browser focus.
- **Motion**: None currently defined for controls.
- **Layout/scroll**: Inline-flex controls wrap in rows/toolbars; controls do not
  own scroll.

### Clear-Filter Action (planned)

- **Structure**: A native `button` with `.btn`, visible text `Clear filters`, and
  `type="button"`, placed with filter actions rather than inside one alias list.
- **Variants**: Enabled when any product, state, type, search, assignee, or
  reviewer filter is active; disabled when there is nothing to clear. If scope
  rules require assignment-only clearing, label it `Clear assignment filters`
  rather than changing behavior behind the generic label.
- **Spacing**: Reuse `.btn` padding/radius and existing `8px` or `12px` toolbar
  gaps.
- **States**: Default, accent-soft hover, visible focus, disabled at `0.65`
  opacity with default cursor, busy through the existing global request state,
  and restored enabled/disabled state after partial swaps.
- **Accessibility**: The accessible name must state the actual scope. Activation
  is keyboard-equivalent to pointer activation, preserves focus in the filter
  area, updates the URL/query state, and triggers the polite result status.
- **Motion**: None.
- **Layout/scroll**: Wraps with filter actions and never floats over results or
  creates a new scroll owner.

### Detail Fact

- **Structure**: `.detail-facts` contains `.detail-fact` cells; each cell has a
  `.detail-label` and wrapping `.detail-value`.
- **Variants**: Plain value, link cluster, pill value, missing value, and
  assignment value with provenance marker.
- **Spacing**: Grid gap `10px`; cell padding `8px`; label bottom margin `4px`;
  `8px` radius.
- **States**: Static/read-only. Missing values show explicit missing text and
  the existing missing pill treatment.
- **Accessibility**: Preserve label/value association in DOM order. Values must
  remain selectable and copyable. Do not replace assignment text with icons.
- **Motion**: None.
- **Layout/scroll**: Adaptive `180px` minimum cells with `min-width: 0`; values
  wrap and cells are not scroll owners.

### Assignment Metadata Grid and Cells (planned)

- **Structure**: A read-only grid following `.detail-facts`/`.detail-fact` or
  the existing adaptive fact-grid grammar. Provide distinct `Assignee` and
  `Reviewer` cells/columns. Each cell contains its visible label, exact alias or
  missing-state text, and optional provenance marker.
- **Variants**: Explicit assignee; inherited assignee; missing assignee;
  explicit reviewer; inherited Bug reviewer; no reviewer. Reviewer inheritance
  is not inferred for non-Bug items.
- **Spacing**: Reuse `8px` cell padding, `8px` or `10px` grid gap, `4px` label
  separation, and `8px` radius. Compact card/list presentations may omit the
  outer cell border only when the label/value hierarchy remains clear.
- **States**: Read-only in every context. Loading uses the containing page/busy
  state; absent data uses a missing state; malformed/unknown source remains
  visible as diagnostic text rather than being silently treated as explicit.
- **Accessibility**: Assignment metadata is read-only. Use text labels and DOM
  order suitable for screen readers. Aliases may wrap safely with
  `overflow-wrap: anywhere` and `word-break: break-word`; never rely on a title
  tooltip to reveal a truncated alias.
- **Motion**: None.
- **Layout/scroll**: Auto-fit cells collapse to one readable column when needed.
  Assignment rows/cells do not own scroll and must not cause horizontal page,
  card, or modal overflow.

### Inherited Source Marker (planned)

- **Structure**: A neutral `.pill` adjacent to the assignment alias with visible
  text `Inherited` and readable source context such as
  `product.default_assignee` or `product.default_bug_reviewer`.
- **Variants**: Inherited assignee; inherited Bug reviewer. Explicit values may
  display `Explicit` where provenance comparison is useful, but inherited is the
  required marker.
- **Spacing**: Reuse pill padding and a `6px` wrapping inline gap.
- **States**: Static. Unknown provenance is labeled `Source unknown`; it must not
  be styled as inherited.
- **Accessibility**: Inheritance is distinguishable without color alone through
  the word `Inherited` and source text. Keep source text in the accessibility
  tree and do not encode it only in `title`, color, or a symbol.
- **Motion**: None.
- **Layout/scroll**: Wraps beside or below the alias; no scroll ownership.

### Missing Assignment State (planned)

- **Structure**: A `.pill.missing` or equivalent existing missing-state surface
  containing `Unassigned` for assignee and `No reviewer` for reviewer.
- **Variants**: Missing assignee; missing reviewer; unavailable assignment data
  with a diagnostic message.
- **Spacing**: Existing missing pill spacing only.
- **States**: Static missing state. Do not substitute an empty string, dash-only
  cell, fabricated default, or inherited value that was not recorded.
- **Accessibility**: The missing condition is literal text and therefore does
  not depend on gray color. It remains readable in card, grid, and detail views.
- **Motion**: None.
- **Layout/scroll**: Inline wrapping content; no scroll ownership.

### Modal

- **Structure**: Fixed `.modal-backdrop`; `.modal` with `.modal-head` and
  `.modal-body`; semantic `role="dialog"`, `aria-modal="true"`, and a labeled
  title. Current modals are Item Detail and Shortcut Help.
- **Variants**: Closed backdrop; open backdrop; item detail; shortcut help.
- **Spacing**: Backdrop `24px`; header/body `12px 14px`; `10px` modal radius.
- **States**: Closed `display: none`; open `display: flex`; Close button; Escape
  closes the topmost relevant dialog.
- **Accessibility**: Keep title association, `aria-hidden` state, Escape support,
  and keyboard-operable Close. Focus management must remain explicit in the
  first-party runtime.
- **Motion**: None; open/close is immediate.
- **Layout/scroll**: Centered, width `min(980px, 92vw)`, max height `88vh`; the
  modal itself owns vertical scrolling.

### Status and Empty State

- **Structure**: Polite `.status-wrap`; optional spinner; `.busy-banner` with
  title, detail, progress, and Cancel/Retry/Copy actions; page refresh/stale
  note; visible lane or graph empty-state text.
- **Variants**: Ready, busy, refreshing, stale, failed, canceled, retryable,
  empty, and bounded/truncated diagnostic.
- **Spacing**: Status gap `7px`; banner gap `12px`, padding `10px 12px`, `8px`
  radius; progress margin `8px`.
- **States**: Busy reveals spinner/banner; stale changes label, border, text, and
  fill; errors use `.status-error`; empty states use exact human-readable
  sentences appropriate to the surface.
- **Accessibility**: Existing status regions use `role="status"` and/or
  `aria-live="polite"`; spinners/progress decoration are `aria-hidden`. Empty
  states must explain the result, not merely show zero.
- **Motion**: Spinner rotates at `0.8s linear infinite`; busy progress translates
  at `1.1s ease-in-out infinite`.
- **Layout/scroll**: Status content wraps in its panel; no additional scroll
  region. Retry/cancel actions remain in normal reading order.

## 6. Motion & Interaction

Backboard motion is sparse and functional. It communicates selection or request
activity; there are no decorative entrances, page transitions, or scroll-driven
effects.

| Interaction | Existing timing | Property | Purpose |
| --- | --- | --- | --- |
| Selectable card | `0.16s ease` | `border-color`, `box-shadow`, `transform` | Clarify hover and selected review focus |
| Spinner | `0.8s linear infinite` | `transform: rotate(...)` | Show active request work |
| Busy progress | `1.1s ease-in-out infinite` | `transform: translateX(...)` | Show indeterminate loading progress |
| Page/modal/tab visibility | Immediate | `display` | Keep navigation and dialog behavior direct |

Interaction rules:

- Keep motion tied to state and use the existing durations. Assignment filters,
  metadata, source markers, missing states, and clear-filter action add no new
  animation.
- Preserve keyboard shortcuts only outside inputs, textareas, selects, and
  editable content. Visible shortcut help remains the source of truth.
- Native controls retain native keyboard and focus behavior. Custom selectable
  cards, graph nodes, jump actions, and new clear-filter actions require visible
  focus treatment.
- The established custom focus treatment is a `3px` accent-border outline with
  `2px` offset; the graph canvas uses a `3px` alpha accent ring. Do not remove
  browser focus where a custom treatment is not yet defined.
- Hover must communicate interactivity. Static metadata, pills, and panels do
  not receive decorative hover effects.
- Reduced-motion handling is not currently implemented; it is accepted debt in
  Section 8 and must be addressed before adding any new non-essential motion.

## 7. Depth & Surface

### Strategy: mixed borders and restrained shadows

Backboard uses borders as the default structural layer and reserves shadow for
selection, hover, busy emphasis, graph focus, and modal separation. Tonal shifts
support borders rather than replacing them.

| Level | Existing recipe | Usage |
| --- | --- | --- |
| Page | `#f7f8fa` body behind white/cool-white content | Root separation |
| Structural surface | White or `#fcfdff`, `1px` cool border, `8px` or `10px` radius, no shadow | Panels, lanes, cards, facts, inputs |
| Hover | Accent-border plus `0 4px 10px var(--kob-shadow)` | Selectable cards and graph nodes |
| Selected | Accent border, `0 0 0 1px var(--kob-accent)`, `0 8px 18px var(--kob-shadow)`, white fill | Current selectable card |
| Busy | Blue left rule, pale blue fill, `0 1px 2px rgba(30, 55, 95, 0.08)` | Global busy banner |
| Modal | White fill, cool border, dark alpha backdrop | Item detail and shortcut help |
| Warning/error | Semantic pale fill plus border and, where important, a thicker left rule or dashed stroke | Stale, blocked, cycle, missing, hierarchy diagnostics |

Surface rules:

- Do not place shadows on every panel or card. Most hierarchy comes from border,
  radius, and small tonal differences.
- Use `10px` radii for outer panels/lanes/modals, `8px` for cards/cells/controls,
  and `6px` for compact actions/warnings. Pills remain fully rounded.
- Assignment metadata cells use the existing detail-fact surface. In compact
  cards they may be borderless only to avoid nested box noise; labels, spacing,
  and wrapping must preserve the hierarchy.
- Inherited and missing assignment states use pills and visible text, not new
  elevation or unique actor-colored surfaces.
- The current graph gradient is an existing visualization surface, not a general
  background treatment for dashboard panels.

## 8. Accessibility Constraints & Accepted Debt

### Constraints

The implementation target for new work is WCAG 2.2 AA while preserving the
current semantic, DOM-first architecture. Body text and interactive controls
target `4.5:1` contrast; large text and non-text UI boundaries target `3:1`.
These constraints apply especially to repeated backlog reviewers, keyboard-only
reviewers, low-vision reviewers, CJK users, and reviewers working with long or
unfamiliar actor aliases.

- Every interactive element is keyboard reachable and has a visible focus
  indicator. Do not replace native controls with clickable generic elements.
- Focus must remain visible after partial swaps, filter clearing, modal open and
  close, card selection, and graph re-rooting.
- Status, loading, stale, error, empty, inherited, and missing states use text in
  addition to color. Polite live regions announce request/result changes without
  repeatedly interrupting the reviewer.
- Assignment metadata is read-only. It must not look editable, and filters must
  not be confused with ownership mutation controls.
- Repo-visible actor aliases may wrap safely at dots, underscores, dashes, or
  arbitrary long segments. Primary review content must not require horizontal
  scrolling to reveal an alias.
- Inherited values are distinguishable without color alone through visible
  `Inherited` text and the recorded source. Missing values use explicit
  `Unassigned` or `No reviewer` text.
- Filter groups and assignment cells preserve visible labels and logical DOM
  order at and below the `720px` shell breakpoint.
- Modal dialogs retain a programmatic title, modal semantics, Escape behavior,
  focus entry, focus containment, and focus return.
- Any future motion must honor `prefers-reduced-motion`. Until the current busy
  and selection motion is covered, do not add non-essential animation.
- Graph visualization retains DOM diagnostics/text fallback for review-critical
  information. Color and line style are redundant relationship cues.

### Accepted debt

The following debt describes the current implementation. It is recorded for
honesty and future reviewed consolidation, not as scope for KOB-TSK-0056.

| Item | Location | Why accepted now | Owner / exit condition |
| --- | --- | --- | --- |
| Color and spacing literals are only partly tokenized | `backboard_css.hpp` | The current UI predates this extracted contract; changing CSS would exceed documentation-only scope | Future reviewed Backboard CSS consolidation; no assignment feature should add new literals |
| `--kob-panel` is referenced but not declared | `.hierarchy-node` in `backboard_css.hpp` | Fixing the fallback is a source change and is unrelated to assignment filters | Future CSS maintenance adds a reviewed existing-palette fallback or token |
| Seventeen shell declarations use inline `style` attributes | `index_html.hpp` | They are part of the existing embedded shell; this task must not refactor UI source | Future template/style consolidation under the Drogon-native modernization boundary |
| The page application is a large embedded vanilla-JavaScript program split across a roughly 4,400-line C++ header | `backboard_app_js.hpp` | It preserves the no-build first-party runtime but has high maintenance cost; refactoring is explicitly out of scope | Future reviewed modularization that keeps no-npm and server authority unless a separate contract changes the boundary |
| Heading, body line-height, code font, and many native-control metrics depend on browser defaults | `index_html.hpp` and `backboard_css.hpp` | This is the current visual language and changing it would be a redesign | Revisit only with cross-platform visual and accessibility evidence |
| Focus styling is explicit for selectable cards, graph canvas/nodes, and jump actions but not normalized for every button/input | `backboard_css.hpp` | Native browser focus remains available; a full focus audit is outside this documentation task | Dedicated accessibility pass verifies all controls and adds one existing-palette treatment |
| `prefers-reduced-motion` does not currently suppress spinner, busy progress, or selectable-card transitions | `backboard_css.hpp` | Existing functional motion is preserved; no UI source changes are allowed here | Dedicated accessibility work adds reduced-motion behavior and verifies request status remains understandable |
| The five-lane flow grid has no dedicated narrow-screen reflow rule | `.kanban` in `backboard_css.hpp` | Existing dashboard behavior is being documented, not redesigned | Future responsive review with content-stress evidence at narrow widths |
| Visual and interaction accessibility findings are inferred from source for this extraction | Entire Backboard surface | Browser automation was explicitly excluded from this task | Verify in a future UI implementation/review with keyboard, screen reader, reduced-motion, and breakpoint evidence |
