from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown hook.

    Nothing to hold open yet. The database engine and the scenario replay loop
    attach here when they land (docs/em_fusion_v2.md section 10).
    """
    yield


app = FastAPI(
    title="EM-Fusion API",
    version="0.1.0",
    description="ADS-B and synthetic RF anomaly monitoring and alerting system",
    lifespan=lifespan,
)

# Vite dev server, and the nginx-served frontend. Requests through nginx are
# same-origin and need no entry here; these cover direct browser calls in
# development.
origins = [
    "http://localhost:1234",
    "http://localhost:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
