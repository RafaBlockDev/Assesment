"""FastAPI application for the Stock Query Agent."""

from __future__ import annotations

import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from config import get_langfuse, get_settings
from src.agent.graph import run_agent_stream
from src.api.auth import CognitoAuth, get_cognito_auth, get_current_user
from src.knowledge_base.retriever import initialize_knowledge_base

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Lifespan (startup / shutdown) ───────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── startup ──
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    logger.info("Starting Stock Query Agent …")

    # 1. Knowledge base
    try:
        initialize_knowledge_base()
        logger.info("Knowledge base loaded.")
    except Exception as e:
        logger.warning("Knowledge base init failed (non-fatal): %s", e)

    # 2. Langfuse connectivity
    try:
        lf = get_langfuse()
        lf.flush()
        logger.info("Langfuse connection OK.")
    except Exception as e:
        logger.warning("Langfuse not reachable (non-fatal): %s", e)

    yield

    # ── shutdown ──
    logger.info("Shutting down.")


# ── App ─────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.api_title,
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global exception handler ───────────────────────────────────────


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# ── Request / Response models ──────────────────────────────────────


class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    id_token: str
    refresh_token: str
    expires_in: int
    token_type: str


class QueryRequest(BaseModel):
    query: str
    stream: bool = True


class QueryResponse(BaseModel):
    answer: str
    sources: list[str] = []
    trace_id: str


# ── Health ──────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "environment": settings.api_environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Auth routes ─────────────────────────────────────────────────────


@app.get("/auth/login")
async def login_redirect():
    """Return the Cognito Hosted UI URL for browser-based login."""
    if settings.cognito_domain:
        base_url = settings.cognito_domain
    else:
        pool_id = settings.cognito_user_pool_id
        region = settings.aws_region
        domain_prefix = pool_id.split("_")[1].lower() if "_" in pool_id else pool_id
        base_url = f"https://{domain_prefix}.auth.{region}.amazoncognito.com"

    url = (
        f"{base_url}/login"
        f"?client_id={settings.cognito_client_id}"
        f"&response_type=code"
        f"&scope=openid+email+profile"
        f"&redirect_uri=http://localhost:{settings.app_port}/auth/callback"
    )
    return {"login_url": url}


@app.post("/auth/token", response_model=TokenResponse)
async def exchange_token(
    body: TokenRequest,
    auth: CognitoAuth = Depends(get_cognito_auth),
):
    """Exchange username/password for Cognito tokens."""
    return auth.initiate_auth(body.username, body.password)


@app.get("/auth/user")
async def get_user(current_user: dict = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return current_user


# ── Main query endpoint ────────────────────────────────────────────


async def _sse_generator(query: str, user_id: str, trace_id: str):
    """Yield SSE-formatted events from the agent stream."""
    async for event in run_agent_stream(query, user_id, trace_id=trace_id):
        event["trace_id"] = trace_id
        yield f"data: {json.dumps(event)}\n\n"
    yield f"data: {json.dumps({'type': 'done', 'trace_id': trace_id})}\n\n"


@app.post("/query")
async def query_stock(
    body: QueryRequest,
    current_user: dict = Depends(get_current_user),
):
    """Main endpoint: answer natural-language stock questions.

    If ``stream=true`` (default), returns an SSE stream with incremental
    agent events.  If ``stream=false``, collects the full answer and
    returns a single JSON response.
    """
    user_id = current_user.get("sub") or current_user.get("username", "anonymous")
    trace_id = str(uuid.uuid4())

    if body.stream:
        return StreamingResponse(
            _sse_generator(body.query, user_id, trace_id),
            media_type="text/event-stream",
            headers={"X-Trace-Id": trace_id},
        )

    # Non-streaming: collect all events
    final_answer = ""
    sources: list[str] = []

    async for event in run_agent_stream(body.query, user_id, trace_id=trace_id):
        if event["type"] == "final_answer":
            final_answer = event["content"]
        elif event["type"] == "observation":
            sources.append(event["content"][:200])

    return QueryResponse(
        answer=final_answer or "No answer produced.",
        sources=sources,
        trace_id=trace_id,
    )
