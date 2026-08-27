from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.db.session import dispose_engine, init_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown hook.

    The Engine is built here and nowhere else (`db-005`), so exactly one pool
    exists per process and it is released on shutdown. Construction opens no
    connection, so a database that is down does not stop the app starting --
    `/api/v1/health` keeps answering, and a degraded database does not present
    as an unreachable service. A *missing* `DATABASE_URL` is different and
    fails here, loudly: that is misconfiguration rather than an outage, and
    the alternative is discovering it at the first query.

    The scenario replay loop attaches here when it lands
    (docs/em_fusion_v2.md section 10).
    """
    init_engine()
    try:
        yield
    finally:
        dispose_engine()


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
