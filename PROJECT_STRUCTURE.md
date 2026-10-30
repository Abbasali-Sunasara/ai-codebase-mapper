# AI Codebase Mapper — Project Structure

This document describes the current repository layout, how a repository analysis moves through the system, and what the graph nodes and edges represent.

## Project at a glance

AI Codebase Mapper accepts a public GitHub repository URL, clones the current repository snapshot into a temporary directory, and analyzes Python source files without executing them. Deterministic AST parsing and rule-based checks produce the structural data. A Groq model can add short natural-language summaries. The React frontend polls the backend job and displays repository metrics, a module dependency graph, and file details.

```text
GitHub URL
   │
   ▼
FastAPI job ──► shallow clone ──► Python AST + rule checks ──► graph and metrics
                                                           └──► optional Groq summaries
   │
   ▼
JSON job result ──► React UI ──► Dagre layout + React Flow graph + inspector
```

## Repository layout

```text
ai-codebase-mapper/
├── README.md                    # Project overview and local startup instructions
├── PROJECT_STRUCTURE.md         # This architecture and file guide
├── render.yaml                  # Render deployment configuration template
├── eval/
│   ├── repos.txt                # Repositories used as evaluation inputs
│   ├── results.md               # Evaluation notes/results
│   └── run_eval.py              # Evaluation helper
├── backend/
│   ├── .env                     # Local secrets/settings; do not commit
│   ├── .env.example             # Safe template for required settings
│   ├── requirements.txt         # Python dependencies
│   ├── Dockerfile               # Backend container build instructions
│   └── app/
│       ├── __init__.py
│       ├── main.py              # FastAPI app, CORS, health/root routes
│       ├── jobs.py              # In-memory analysis-job state
│       ├── api/
│       │   └── endpoints.py     # POST /api/analyze and GET /api/jobs/{job_id}
│       ├── core/
│       │   ├── config.py        # Environment-backed settings
│       │   └── ai_client.py     # OpenAI-compatible Groq client
│       └── services/
│           ├── repo_cloner.py       # GitHub URL validation, shallow clone, cleanup support
│           ├── ast_parser.py        # Python AST traversal and graph-analysis orchestration
│           ├── classifier.py        # Deterministic file/component classification
│           ├── graph_builder.py      # Module/symbol nodes and import/containment edges
│           ├── graph_metrics.py      # Cycles, fan-in/out, and oversized module metrics
│           ├── container_detector.py# Container/dependency manifest discovery
│           ├── security_checks.py    # Heuristic security scans with file/line evidence
│           ├── summarizer.py         # Optional, cached AI summary enrichment
│           ├── cache.py              # SQLite analysis and summary cache
│           └── jobs.py               # Compatibility exports for app.jobs
└── frontend/
    ├── index.html                 # Vite HTML entry point
    ├── package.json               # React/Vite and UI dependencies/scripts
    ├── package-lock.json
    ├── vite.config.js             # Vite configuration
    ├── vercel.json                # Vercel frontend routing/configuration
    ├── public/                    # Static icons and favicon
    └── src/
        ├── main.jsx               # Mounts the React application
        ├── App.jsx                # Re-export of components/App.jsx
        ├── App.css                # Legacy/additional stylesheet
        ├── index.css              # Global application styles
        ├── assets/                # Image and starter assets
        ├── components/
        │   ├── App.jsx            # Form, request state, result composition
        │   ├── Header.jsx         # Application header
        │   ├── JobStatus.jsx      # Analysis progress and error display
        │   ├── MetricsPanel.jsx   # Repository and graph metrics
        │   ├── FlowCanvas.jsx     # React Flow graph visualization
        │   └── InspectorSidebar.jsx # Selected file metadata and summary
        ├── lib/
        │   └── layout.js          # Folder grouping and Dagre layout
        └── services/
            └── api.js             # Axios client and job polling
```

The local `backend/.env` is intentionally omitted from version control; `backend/.env.example` documents the expected variables. There is currently no `backend/tests/` directory in the repository listing.

## Backend responsibilities

### Application and API

- `app/main.py` constructs the FastAPI application, configures CORS, includes the `/api` router, and exposes `/` and `/health`.
- `app/api/endpoints.py` creates a job for each request. `POST /api/analyze` responds with HTTP 202 and a job ID; `GET /api/jobs/{job_id}` returns its current status, result, or error.
- The background job advances through `cloning`, `parsing`, `analyzing`, and `summarizing`, then becomes `done` or `error`. Pipeline exceptions print a traceback, and a `finally` block removes a successfully created temporary clone.
- `app/jobs.py` stores job state in a process-local dictionary guarded by a thread lock. Restarting the backend clears this job state.

### Clone and source analysis

- `repo_cloner.py` only accepts HTTPS GitHub repository URLs, shallow-clones with `depth=1`, and applies a 120-second Git timeout. It checks the cloned content against a 100 MB and 10,000-file limit. Those size/file checks happen after cloning; they do not cap bytes downloaded during the clone itself.
- `ast_parser.py` walks Python files and skips common generated/dependency directories such as `.git`, `node_modules`, virtual environments, build outputs, and `__pycache__`. It extracts class/function names, function arguments, decorators, imports, route declarations, and line ranges. It does not execute repository code.
- The parser marks imports as internal or external using the repository module index. Import resolution is heuristic, so ambiguous module names can remain unresolved.
- `classifier.py`, `container_detector.py`, and `security_checks.py` use deterministic rules. Security matches are heuristics and should be treated as flags for review, not confirmed vulnerabilities.

### Graph and metrics

`graph_builder.py` builds the full graph from AST metadata. The current API data model is:

| Graph item | Meaning | Evidence |
| --- | --- | --- |
| Module node (`type: "module"`) | A Python source file | File path and line 1 |
| Symbol node | A class or function in a module; its `type` is the rule-based classification, such as `api_route`, `service`, or `source` | File path and AST declaration line |
| `contains` edge | A module contains one of its class/function symbols | File path and symbol declaration line |
| `imports` edge | A source module imports another module resolved inside the repository | Importing file, import line, and original import text |

The symbol classifier may label components as `api_route`, `background_worker`, `database_model`, `test`, `api`, `service`, `model`, or `source`. These are classification values rather than separate graph edge types.

`graph_metrics.py` calculates module fan-in/fan-out, dependency cycles (up to 100 reported cycles), and oversized modules (500 or more lines). `container_detector.py` adds repository-relative container and dependency-manifest paths. `security_checks.py` adds finding records with file, line, and finding type.

### Cache and AI summaries

- `cache.py` stores analysis JSON in SQLite keyed by commit SHA and summaries keyed by a SHA-256 hash of file contents.
- `summarizer.py` selects up to three Python files with classes/functions, sends their extracted metadata and numbered source text to the AI client, validates any cited line numbers, then caches valid summaries.
- `core/config.py` loads `GROQ_API_KEY` and `GROQ_MODEL` from the backend `.env` or process environment. The default model is `openai/gpt-oss-120b`.
- `core/ai_client.py` calls Groq through the OpenAI-compatible SDK. Missing credentials, rate limits, timeouts, and other API failures return an “AI summarization unavailable” string so AI failure does not abort the deterministic analysis pipeline.

## Frontend responsibilities

- `main.jsx` mounts the React app. `src/App.jsx` forwards the import to `components/App.jsx`.
- `components/App.jsx` accepts the GitHub URL, starts analysis, tracks progress/error/result state, and composes the result panels.
- `services/api.js` uses Axios. The default API base URL is `http://127.0.0.1:8000` and can be overridden with `VITE_API_BASE_URL`. It submits the URL and polls the job endpoint every 1.2 seconds until completion or failure.
- `MetricsPanel.jsx` presents file, component, dependency, cycle, fan, oversized-module, and security counts.
- `FlowCanvas.jsx` displays the module dependency graph with React Flow controls and minimap. `lib/layout.js` uses Dagre to lay out modules and adds folder grouping nodes for visual organization.
- `InspectorSidebar.jsx` shows selected-file classification, classes, functions, fields, imports, routes, security findings, evidence symbols, and any AI summary.
- `Header.jsx` and `JobStatus.jsx` display branding and job progress/errors.

### What appears as graph nodes in the UI

The backend returns both module and symbol nodes in `analysis.nodes`, but the current graph canvas draws `analysis.module_nodes` and `analysis.module_edges` only. In practice, the visible graph shows Python files connected by internal imports. Class/function symbols are counted in `component_nodes_count` and their details appear in the inspector, but they are not currently drawn as individual React Flow nodes. Folder grouping nodes are created by the frontend layout and are visual containers, not backend analysis nodes.

## Main request and response shapes

Request:

```json
{
  "repo_url": "https://github.com/owner/repository"
}
```

Initial response from `POST /api/analyze`:

```json
{
  "job_id": "<generated-id>",
  "status": "queued"
}
```

When polling reports `done`, the job result has this general shape:

```json
{
  "status": "success",
  "repo_url": "https://github.com/owner/repository",
  "commit_sha": "<checked-out-commit>",
  "analysis": {
    "file_metadata": {},
    "nodes": [],
    "edges": [],
    "module_nodes": [],
    "module_edges": [],
    "graph_metrics": {},
    "container_files": [],
    "security_findings": [],
    "ai_summaries": {}
  }
}
```

## Local startup

1. Add a Groq key to `backend/.env` as `GROQ_API_KEY=...`.
2. Install Python packages from `backend/requirements.txt` and start FastAPI from `backend/` on `127.0.0.1:8000`.
3. Install frontend packages in `frontend/` and run Vite, typically at `127.0.0.1:5173`.
4. Open the frontend, submit a public GitHub repository URL, and watch the job progress while it polls the backend.

## Current scope notes

- Repository and AST analysis is Python-focused; other languages may be scanned by a few security heuristics but are not represented as parsed modules.
- The visible graph is file/module-level; caller relationships and individual symbol nodes are not currently displayed as graph elements.
- Job state is in memory, while completed analyses and summaries use SQLite.
- Clone size and file-count checks are post-download.
- Static security findings are heuristic and require human review.
