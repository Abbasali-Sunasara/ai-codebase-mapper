import shutil
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Import our custom backend services
from app.services.repo_cloner import clone_repository
from app.services.ast_parser import analyze_repository_ast
from app.core.ai_client import ai_client

router = APIRouter()

class RepoAnalyzeRequest(BaseModel):
    repo_url: str

@router.post("/analyze")
async def analyze_codebase(payload: RepoAnalyzeRequest):
    """
    Master pipeline endpoint:
    1. Clone repository (repo_cloner creates its own temp dir)
    2. Run deterministic AST parsing + NetworkX graph generation
    3. Generate AI code summaries
    4. Cleanup and return graph data
    """
    temp_dir = None
    try:
        # Step 1: Clone the repository (returns the temp directory path)
        temp_dir = clone_repository(payload.repo_url)

        # Step 2: Run AST parser and build structural graph
        analysis_result = analyze_repository_ast(temp_dir)

        # Step 3: (Optional enrichment) Summarize key files using AI client
        file_metadata = analysis_result.get("file_metadata", {})
        enriched_summaries = {}

        count = 0
        for path, data in file_metadata.items():
            if count >= 3:
                break
            if isinstance(data, dict) and "error" not in data and (data.get("classes") or data.get("functions")):
                summary = ai_client.explain_code_component(
                    file_path=path,
                    code_snippet=f"Classes: {data.get('classes')}, Functions: {data.get('functions')}",
                    metadata=data
                )
                enriched_summaries[path] = summary
                count += 1

        analysis_result["ai_summaries"] = enriched_summaries

        return {
            "status": "success",
            "repo_url": payload.repo_url,
            "analysis": analysis_result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis pipeline failed: {str(e)}")
    
    finally:
        # Always clean up temporary directory storage
        if temp_dir and shutil.os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)