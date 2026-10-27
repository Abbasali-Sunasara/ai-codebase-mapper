import os
import shutil
import tempfile
from urllib.parse import urlparse
from fastapi import HTTPException
import git

def validate_github_url(url: str) -> bool:
    """Ensure the URL is a valid public github.com repository URL."""
    parsed = urlparse(url)
    if parsed.netloc != "github.com":
        return False
    # Path should have at least /owner/repo
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return False
    return True

def clone_repository(repo_url: str) -> str:
    """
    Safely shallow-clones a public GitHub repository into a temporary directory.
    Returns the path to the cloned repository.
    """
    if not validate_github_url(repo_url):
        raise HTTPException(
            status_code=400, 
            detail="Invalid repository URL. Only public github.com URLs are supported in v1."
        )

    # Create a secure temporary directory
    temp_dir = tempfile.mkdtemp(prefix="ai_mapper_")

    try:
        # Perform shallow clone (depth=1) as per blueprint[cite: 2]
        git.Repo.clone_from(repo_url, temp_dir, depth=1)
        return temp_dir
    except Exception as e:
        # Cleanup directory if clone fails
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to clone repository: {str(e)}"
        )