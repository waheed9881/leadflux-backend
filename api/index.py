"""
Vercel serverless function entry point for FastAPI.

Vercel's Python runtime supports ASGI apps directly, so we export `app`.
"""

from app.api.server import app as app

# Some tooling expects a `handler` symbol; on Vercel it can be the ASGI app.
handler = app

__all__ = ["app", "handler"]

