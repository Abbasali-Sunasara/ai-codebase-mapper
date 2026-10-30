import os
import shutil
import traceback
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, HttpUrl

from app.jobs import create_job, get_job, update_job
from app.services.ast_parser import analyze_repository_ast
from app.services.cache import cache
from app.services.repo_cloner import clone_repository, repository_commit_sha
from app.services.summarizer import summarize_metadata

router = APIRouter()


class RepoAnalyzeRequest(BaseModel):
    repo_url: HttpUrl


def _analyze_repository(repo_url: str, job_id: str) -> None:
    temp_dir = None
    try:
        update_job(job_id, status="cloning")
        temp_dir = clone_repository(repo_url)
        commit_sha = repository_commit_sha(temp_dir)
        cached = cache.get_analysis(f"v4:{commit_sha}")
        if cached is not None:
            cached["repo_url"] = repo_url
            update_job(job_id, status="done", result=cached)
            return

        update_job(job_id, status="parsing")
        analysis = analyze_repository_ast(temp_dir)
        update_job(job_id, status="analyzing")
        update_job(job_id, status="summarizing")
        analysis["ai_summaries"] = summarize_metadata(analysis.get("file_metadata", {}), temp_dir)
        result = {"status": "success", "repo_url": repo_url, "commit_sha": commit_sha, "analysis": analysis}
        unavailable = ("AI summarization unavailable:", "Summary withheld:")
        if not any(summary.startswith(unavailable) for summary in analysis["ai_summaries"].values()):
            cache.put_analysis(f"v4:{commit_sha}", result)
        update_job(job_id, status="done", result=result)
    except HTTPException as error:
        traceback.print_exc()
        update_job(job_id, status="error", error=error.detail)
    except Exception as error:
        traceback.print_exc()
        update_job(job_id, status="error", error=f"Analysis pipeline failed: {error}")
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


@router.post("/analyze", status_code=status.HTTP_202_ACCEPTED)
async def analyze_codebase(payload: RepoAnalyzeRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid4())
    create_job(job_id)
    background_tasks.add_task(_analyze_repository, str(payload.repo_url), job_id)
    return {"job_id": job_id, "status": "queued"}


@router.get("/jobs/{job_id}")
async def read_analysis_job(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job not found")
    return job
