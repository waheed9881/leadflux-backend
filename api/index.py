"""
Vercel serverless function entry point for FastAPI.

Vercel's Python runtime supports ASGI apps directly, so we export `app`.
"""

from app.api.server import app

__all__ = ["app"]

