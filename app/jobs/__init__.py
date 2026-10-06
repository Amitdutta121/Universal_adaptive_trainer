"""Background jobs: long professor actions that keep running after the request returns.

``queue`` is the one place work is handed to something that runs it later, so the
executor (today FastAPI ``BackgroundTasks``) can be swapped without touching a caller.
``runner`` is the lifecycle every ``background_jobs`` row shares, ``listing`` merges
every kind of job into the Jobs panel, and ``recovery`` cleans up after a restart.
"""
