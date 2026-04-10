# PageIndex — Vectorless RAG

A local document Q&A system that builds a hierarchical section tree from your PDFs and answers questions by reasoning over that structure — no embeddings, no vector database, everything runs on your own machine.

---

## How it works

1. Upload a PDF through the browser UI
2. The server sends the document to your local LLM (via vLLM), which generates a structured section tree
3. Ask a question — the LLM navigates the tree, reads only the relevant pages, and synthesises an answer
4. Your documents never leave your machine

---

## Requirements

- Python 3.11+
- A running vLLM server (Qwen 2.5 72B or similar recommended)
- WSL or native Linux (avoid running from `/mnt/c/` on Windows — use `~/` inside WSL)

---

## Project layout

```
<ProjectDir>/
├── main.py              ← FastAPI app factory (routers, middleware, lifespan)
├── config.py            ← All env vars, path constants, default indexing opts, prompt loading
├── indexing.py          ← PageIndex module loading, PageIndexClient singleton, page extractors
├── query.py             ← Agent-style RAG loop
├── .env                 ← your configuration
├── requirements.txt
├── models/              ← Pydantic models for all API boundaries
│   ├── __init__.py      ← re-exports all models
│   ├── agent.py         ← AgentResponse, ToolCall, ToolCallArgs
│   ├── documents.py     ← DocumentSummary, DocumentsResponse, DeleteResponse, HealthResponse
│   ├── pages.py         ← PageContent
│   ├── query.py         ← QueryRequest, QueryResponse, TraversalStep, ContextPassage
│   └── upload.py        ← UploadSettings, UploadFileResult, UploadResponse
├── routes/              ← FastAPI route handlers (one file per concern)
│   ├── __init__.py
│   ├── upload.py        ← POST /upload
│   ├── documents.py     ← GET /documents, DELETE /document/{id}
│   ├── query_route.py   ← POST /query
│   └── ops.py           ← GET /health, /log_latest, /indexing_phase, /queue_status, POST /cancel_indexing
├── ui/                  ← browser frontend
│   ├── index.html
│   └── static/
│       ├── css/app.css
│       └── js/app.js
├── prompts/
│   ├── vision_extraction.txt   ← prompt for LLM Vision page extraction (retrieval layer)
│   └── vision_indexing.txt     ← prompt for tree-building extraction (scanned PDFs)
├── PageIndex/           ← open-source library (do not modify)
├── workspace/           ← auto-created, stores indexed documents
└── logs/                ← auto-created, stores indexing logs
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure `.env`

```env
OPENAI_API_BASE=http://localhost:8000/v1
OPENAI_API_KEY=vllm
INDEXER_MODEL=openai/qwen_35b_agent

PAGEINDEX_DIR=./PageIndex
UI_DIR=./ui
WORKSPACE_DIR=./workspace

MAX_UPLOAD_MB=100
HOST=0.0.0.0
PORT=8080
```

`INDEXER_MODEL` must match the `--served-model-name` you pass to vLLM.

### 3. Start your vLLM server

```bash
vllm serve <model_path> \
    --tensor-parallel-size 2 \
    --dtype auto \
    --max-model-len 60000 \
    --gpu-memory-utilization 0.90 \
    --served-model-name qwen_35b_agent \
    --port 8000 \
    --reasoning-parser qwen3 \
    --enable-auto-tool-choice \
    --tool-call-parser qwen3_coder \
    --max-num-seqs 32 \
    --max-num-batched-tokens 60000 \
    --enable-chunked-prefill
```

> `--max-num-batched-tokens` must equal `--max-model-len` or vLLM will error on startup.

### 4. Start the server

```bash
python main.py
```

Open your browser at `http://localhost:8080`.

---

## Using the UI

### Uploading documents

1. Click **Documents** in the sidebar
2. Drop a PDF onto the upload zone or click to browse
3. The progress overlay shows each indexing step in real time — including page extraction
4. Once complete the document appears in the library and is automatically selected for chat

Multiple files can be staged and uploaded together. They are processed one at a time so your LLM is never overloaded.

### Indexing settings

Expand **⚙️ Indexing Settings** before uploading to tune how the index is built:

| Setting | Default | What it does |
|---|---|---|
| TOC Scan Pages | 0 | Pages to scan for an embedded Table of Contents. Keep at 0 unless your model reliably handles very large outputs — higher values can hit output token limits. |
| Max Pages Per Node | 5 | Sections longer than this are split into smaller nodes. Lower = finer tree, more LLM calls. |
| Node Summaries | Off | Generate a one-sentence summary per section. Adds ~1 LLM call per section. |
| Document Description | Off | Generate a short description of the whole document. Requires Node Summaries on. |
| LLM Vision Parser | Off | Extract page text using the vision LLM instead of PyMuPDF. Slower but captures text in scanned PDFs, diagrams, and complex layouts. |

### Asking questions

Type a question in the chat input and press Enter. The response panel shows:

- **Thought steps** — which tools the LLM called and in what order (expandable)
- **Retrieved pages** — clickable source chips showing which pages were read. Click a chip to open the PDF viewer at that page.
- **Answer** — the final response, rendered as markdown

### PDF viewer

Click any source chip in a response to open the PDF panel on the right side. The chat automatically shifts left to make room.

- **Resize** — drag the divider between chat and PDF to adjust the split
- **Navigate** — use the `←` `→` buttons in the footer to move between pages
- **Zoom** — use `−` and `+` in the footer (50%–300%). At zoom > 100% you can click-and-drag to pan the image
- **Add page to chat** — click the `+ Add page to chat` button in the footer to pin that page as context. A chip appears above the chat input. Any question you ask while chips are present will be answered focusing on those specific pages. Remove chips individually with `×` to return to normal full-document querying.

### Projects

Documents are organised into projects. The default project is created automatically. Create new projects from the Documents view to keep different document sets separate.

### Multiple documents

Select multiple documents in a project to query across all of them at once.

---

## Persistence

Indexed documents survive server restarts. When you start the server again, all previously indexed documents are automatically reloaded from the `workspace/` folder.

Each document is stored as three files:
- `workspace/<doc_id>.pdf` — a copy of the uploaded PDF
- `workspace/<doc_id>.json` — the section tree and page contents
- `workspace/_meta.json` — lightweight index used for fast startup reload

> The warning `corrupt _meta.json: No such file or directory` on first run is expected and harmless. The file is created after the first successful index.

---

## API reference

The server exposes a REST API in addition to the browser UI:

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Server status and active model |
| `POST` | `/upload` | Upload and index files (multipart: `files[]` + `settings` JSON) |
| `GET` | `/documents` | List all indexed documents |
| `DELETE` | `/document/{doc_id}` | Delete a document and its workspace files |
| `GET` | `/log_latest` | Latest indexing log as JSON array |
| `GET` | `/indexing_phase` | Current indexing stage — `idle`, `pageindex`, `page_extract`, or `done` |
| `GET` | `/queue_status` | How many indexing/query jobs are waiting |
| `POST` | `/cancel_indexing` | Stop after the current document finishes indexing |
| `GET` | `/pdf/{doc_id}/page/{page_num}` | Render a PDF page as JPEG (used by PDF viewer) |
| `POST` | `/query` | Query a document (`{ query, doc_id, doc_ids }`) |

Interactive docs: `http://localhost:8080/docs`

---

## Troubleshooting

**UI hangs after upload and the document never appears**
The server is still busy with a previous job. The progress banner will show "Queued — waiting for previous indexing job to finish…" and update automatically when the slot is free. This is expected behaviour — jobs are serialised intentionally to keep the LLM focused on one task at a time.

**`finish reason: max_output_reached` during indexing**
Your model hit its output token limit. Keep **TOC Scan Pages** at 0 (the default). If it persists, reduce **Max Pages Per Node** to 3.

**`PermissionError: [Errno 1] Operation not permitted` during upload**
You are running the project from `/mnt/c/` on WSL. Move the entire project folder to a native Linux path (e.g. `~/PageIndexWithVLLM`) and re-run.

**`InternalServerError: Connection error`**
The vLLM server is down or unreachable. Check the vLLM process and confirm `OPENAI_API_BASE` in `.env` matches the port vLLM is listening on.

**`KeyError: 'toc_detected'` or malformed JSON errors in logs**
The LLM returned an unexpected response. Usually caused by the model being overloaded or an OOM event on the GPU. Restart the vLLM server and try again.

**Retrying request messages in logs**
Seen as `Retrying request to /chat/completions in X seconds`. vLLM is returning 429 or 503. Most common cause is the model being overloaded. Wait a moment before retrying, or restart the vLLM server to clear it.
