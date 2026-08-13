"""Version 1 of the API.

The `/api/v1` prefix is declared here once. Route modules stay prefix-free so
the version lives in exactly one place, and each resource gets its own module
rather than a shared routes.py that every future feature would edit at once.
"""

from fastapi import APIRouter

from app.api.v1 import health

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
