"""Upload a book through ``POST /api/books`` and get the imported book back.

The import is a background job (``202 {job_id}``). Under ``TestClient`` a background
task runs before the response is returned, so the job has ended by the time this
reads it back from ``GET /api/jobs``.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


def finished_job(client: TestClient, job_id: str, **kwargs: Any) -> dict:
    """The ``GET /api/jobs`` entry of ``job_id``."""
    jobs = client.get("/api/jobs", **kwargs).json()["jobs"]
    return next(job for job in jobs if job["id"] == job_id)


def upload_book(client: TestClient, **kwargs: Any) -> dict:
    """POST ``kwargs`` (``files``, ``data``, ``headers``) to /api/books; the imported book."""
    response = client.post("/api/books", **kwargs)
    assert response.status_code == 202, response.text
    headers = {"headers": kwargs["headers"]} if "headers" in kwargs else {}
    job = finished_job(client, response.json()["job_id"], **headers)
    assert job["status"] == "done", job
    return job["result"]["book"]
