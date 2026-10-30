# AI Codebase Mapper

AI Codebase Mapper builds a Python repository architecture graph from deterministic AST analysis, then asks a Groq hosted model to explain extracted components. Repository code is read only and is never executed.

## Run locally

Configure `GROQ_API_KEY` in the environment or `backend/.env` (see `backend/.env.example`). `GROQ_MODEL` selects the Groq model and defaults to `openai/gpt-oss-120b`. Install backend dependencies from `backend/requirements.txt`, then start the backend from `backend/` with `venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`; start the frontend from `frontend/` with `npm install && npm run dev`.

The frontend API client uses `http://127.0.0.1:8000`, submits a public GitHub URL to `POST /api/analyze`, and polls `GET /api/jobs/{job_id}`. The backend removes each temporary clone after analysis and caches completed results by commit SHA and summaries by source-file hash in SQLite.

## Current limits

The current analyzer supports public GitHub repositories and Python AST parsing. Zip uploads, git-history secret scanning, dependency vulnerability database checks, C4 view switching, graph export, and measured evaluation results are not implemented yet. Static security checks are heuristics and should be reviewed before treating findings as confirmed vulnerabilities.

Evaluation inputs and the precision/recall helper live under `eval/`. No evaluation scores are published until ground truth has been labeled and results have been run.
