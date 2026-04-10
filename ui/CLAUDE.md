# CLAUDE.md — ui/

The entire frontend is a single-page app — one HTML file, one CSS file, one JS file. No build step, no framework, no bundler.

```
ui/
├── index.html        ← markup, modals, views, PDF panel HTML
├── static/
│   ├── css/app.css   ← all styles, CSS custom properties
│   └── js/app.js     ← all logic, no external state management
```

---

## CSS custom properties (design tokens)

All colours and dimensions are CSS variables defined in `:root`. Never hardcode colours.

Key variables:
```css
--bg           /* page background */
--sidebar-bg   /* sidebar + PDF panel background */
--card-bg      /* card/input background */
--panel-bg     /* input area background */
--border       /* default border */
--border-light /* highlighted border */
--text         /* primary text */
--text-muted   /* secondary text */
--text-dim     /* placeholder / disabled text */
--accent       /* blue accent (#4f8ef7) */
--accent-dim   /* semi-transparent accent background */
--accent-glow  /* accent glow for active states */
--green        /* success colour */
--green-bg     /* success background */
--font-main    /* 'Sora', sans-serif */
--font-mono    /* monospace */
--sidebar-w    /* sidebar width */
```

---

## JS globals — key variables

| Variable | Type | Purpose |
|---|---|---|
| `docs` | `Array` | All indexed documents from `/documents`. Source of truth for doc list. |
| `activeDocIds` | `Array<string>` | Doc IDs currently selected for chat. Sent with every query. |
| `currentProject` | `string` | Currently open project name. |
| `isQuerying` | `bool` | True while a query is in-flight. Blocks duplicate sends. |
| `isIndexing` | `bool` | True while upload/indexing is in progress. |
| `_pageCtxItems` | `Array` | Page context chips added via "Add page to chat". Each: `{chipId, docId, page, docName}`. |
| `_pdfPanelDocId` | `string\|null` | Doc ID currently open in PDF panel. |
| `_pdfPanelPage` | `number\|null` | Page currently shown in PDF panel. |
| `_pdfPanelTotal` | `number\|null` | Total pages of open doc (for nav limits). |
| `_pdfPanelName` | `string\|null` | Display name of open doc. |
| `_pdfZoom` | `number` | Current zoom percent (50–300, default 100). |
| `API` | `string` | Base URL, always `""` (same origin). |

---

## Views

The UI has three main views toggled by sidebar buttons:
- `#view-chat` — chat interface (default)
- `#view-docs` — projects + document library
- `#view-indexing` — upload + indexing settings

Switching is done by `showView(id)` which hides all views and shows the target.

---

## PDF side panel

Lives as a flex sibling of `#main` in the DOM — NOT a fixed overlay. When `.open` class is added, `width` transitions from `0` to `520px`, pushing the chat left.

**Key elements:**
- `#pdf-panel` — the panel container
- `#pdf-resizer` — 5px drag handle between chat and panel
- `#pdf-panel-img` — the `<img>` tag loading from `/pdf/{doc_id}/page/{page}`
- `#pdf-panel-label` — filename in header
- `#pdf-page-label` — "p. X / Y" in footer
- `#pdf-zoom-label` — "100%" in footer
- `#pdf-nav-prev`, `#pdf-nav-next` — page nav buttons

**Opening:** `openPdfPanel(docId, page)` — called from source chip `onclick`.

**Resizer drag:** `_initResizer()` IIFE — sets `panel.style.width` directly during drag, removes `transition` for snappy feel, restores on mouseup. Min 300px, max 75vw.

**Zoom:** `pdfZoomIn()` / `pdfZoomOut()` change `_pdfZoom` in 25% steps and set `img.style.width`. `.zoomable` class added to `.pdf-panel-body` when zoom > 100% — enables `cursor: grab`.

**Drag-to-pan:** `_initPdfPan()` IIFE — scrolls `.pdf-panel-body` on mousemove when dragging. Only active when `_pdfZoom > 100`.

**Important CSS:** `.pdf-panel-body` uses `align-items: flex-start` (NOT center) and `overflow-x: auto`. The image uses `min-width: 100%`. This is required so the left side of a zoomed image is reachable by scrolling — centering would clip the left edge with no scrollable overflow.

---

## Page context chips (Add Page to Chat)

**`_pageCtxItems`** — array of active page chips. Each item: `{chipId, docId, page, docName}`.

**`#page-ctx-stack`** — div inside `.input-bar`, above the textarea. Rendered by `_renderPageChips()`. Hidden via CSS when empty (`display: none` on `:empty`).

**Flow:**
1. User clicks "Add page to chat" in PDF footer → `pdfAddToChat()` → pushes to `_pageCtxItems`, renders chip
2. Each chip has `×` button → `_removePageChip(chipId)` → splices from array, re-renders
3. `sendQuery()` calls `_buildPageCtxPrefix()` → if chips present, prepends `[Focus only on pages X, Y of "docname"]` to the query
4. `_getQueryDocIds()` → if chips present, returns only the doc IDs in chips (not all `activeDocIds`)
5. When all chips removed → normal tree-based query across all active docs resumes

**Duplicate prevention:** `pdfAddToChat()` checks for existing `{docId, page}` match before pushing.

---

## Query flow

`sendQuery()`:
1. Read `query-input` value
2. Guard: `isQuerying`, `isIndexing`, no active docs
3. `appendUserMsg(query)` → show user bubble
4. `appendLoadingMsg()` → show typing indicator
5. `_buildPageCtxPrefix()` + `_getQueryDocIds()` → build final query + doc list
6. `POST /query` with `{query: _fullQuery, doc_id, doc_ids}`
7. On response: `appendAIResponse(query, data)` — note `query` (original, no prefix) is passed for display

`appendAIResponse(query, data)`:
- Renders thinking block (traversal steps, collapsible)
- Renders context block (retrieved sections, collapsible)
- Renders source chips (clickable, call `openPdfPanel(docId, firstPage)`)
- Renders answer via `marked.parse(answer)`

**Source chips** are rendered from `data.traversal` steps where `tool === "get_page_content"`. Each chip calls `openPdfPanel(docId, firstPage)` with the first page of the range.

---

## Input bar structure

```html
<div class="input-bar" id="input-bar">
  <div id="page-ctx-stack"></div>   <!-- hidden when empty, chips appear here -->
  <div class="input-bar-row">
    <textarea id="query-input"></textarea>
    <button class="send-btn" id="send-btn"></button>
  </div>
</div>
```

The `input-bar` is a flex column. `page-ctx-stack` uses `border-bottom` when non-empty to visually separate chips from the textarea.

---

## Indexing overlay

`#proc-overlay` — full-screen overlay shown during upload. Steps are rendered by `_renderProcSteps()` and updated by `_pollUntilDone()` which polls:
- `/queue_status` — shows "Queued" banner if busy
- `/indexing_phase` — activates `page_extract` step when PageIndex finishes
- `/log_latest` — JSON log from PageIndex's `JsonLogger` for step details
- `/documents` — detects completion by matching `d.doc_name === fname`

---

## Key UI rules

- `user-select: none` and `outline: none` on all clickable non-input divs (doc rows, project cards) — prevents the browser text cursor from appearing on click
- Never use `position: fixed` for the PDF panel — it must be a flex sibling to push the chat
- `esc()` helper must be used on all user-provided text inserted into innerHTML
- `marked.parse()` is used for markdown rendering in AI responses
- `autoResize(el)` is called on textarea `oninput` to auto-grow height (max 120px)
