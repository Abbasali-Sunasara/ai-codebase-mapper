import os
import shutil
import tempfile
from urllib.parse import urlparse
from fastapi import HTTPException
import git

MAX_REPOSITORY_BYTES = 100 * 1024 * 1024
MAX_REPOSITORY_FILES = 10000
CLONE_TIMEOUT_SECONDS = 120

def validate_github_url(url: str) -> bool:
    """Ensure the URL is a valid public github.com repository URL."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or parsed.username or parsed.password:
        return False
    if parsed.query or parsed.fragment or parsed.params:
        return False
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) != 2 or parts[0] in {".", ".."} or parts[1] in {".", ".."}:
        return False
    return bool(parts[0] and parts[1].removesuffix(".git"))

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
        git.Repo.clone_from(
            repo_url,
            temp_dir,
            depth=1,
            kill_after_timeout=CLONE_TIMEOUT_SECONDS,
            env={"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_LFS_SKIP_SMUDGE": "1"},
        )
        total_bytes = 0
        file_count = 0
        for root, dirs, files in os.walk(temp_dir):
            dirs[:] = [name for name in dirs if name != ".git"]
            for filename in files:
                file_path = os.path.join(root, filename)
                if os.path.islink(file_path):
                    continue
                file_count += 1
                total_bytes += os.path.getsize(file_path)
                if file_count > MAX_REPOSITORY_FILES or total_bytes > MAX_REPOSITORY_BYTES:
                    raise HTTPException(status_code=413, detail="Repository exceeds the analysis size or file-count limit.")
        return temp_dir
    except HTTPException:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise
    except Exception as e:
        # Cleanup directory if clone fails
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to clone repository: {str(e)}"
        )


def repository_commit_sha(repo_path: str) -> str:
    """Return the checked-out commit used to identify cached analysis results."""
    return git.Repo(repo_path).head.commit.hexsha
