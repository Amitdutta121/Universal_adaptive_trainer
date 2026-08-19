"""HTTP boundary.

This package now contains the FastAPI JSON API only. Routes stay thin: they
resolve a session, call a repository or service, and serialize the result.
Business rules belong in the subsystem packages, not here.
"""
