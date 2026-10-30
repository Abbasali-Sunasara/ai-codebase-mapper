from threading import RLock


_jobs: dict[str, dict] = {}
_lock = RLock()


def create_job(job_id: str) -> None:
    with _lock:
        _jobs[job_id] = {"job_id": job_id, "status": "queued", "result": None, "error": None}


def update_job(job_id: str, **fields) -> None:
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)


def get_job(job_id: str) -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None
