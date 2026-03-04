import logging
from typing import Any

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from config import get_settings
from src.api.auth import CognitoAuth, get_cognito_auth, get_current_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()
app = FastAPI(title="Stock Query Agent", version="0.1.0")


# ── Request / Response models ───────────────────────────────────────

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
    question: str


class QueryResponse(BaseModel):
    answer: str
    metadata: dict[str, Any] = {}


# ── Auth routes ─────────────────────────────────────────────────────

@app.get("/auth/login")
async def login_redirect():
    """Return the Cognito Hosted UI URL for browser-based login."""
    pool_id = settings.cognito_user_pool_id
    region = settings.aws_region
    client_id = settings.cognito_client_id
    domain_prefix = pool_id.split("_")[1].lower() if "_" in pool_id else pool_id
    url = (
        f"https://{domain_prefix}.auth.{region}.amazoncognito.com/login"
        f"?client_id={client_id}"
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

@app.post("/query", response_model=QueryResponse)
async def query_stock(
    body: QueryRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Main endpoint: receives a natural-language question about Amazon
    stock and returns an answer.  Agent logic will be wired here later.
    """
    # TODO: replace stub with LangGraph agent invocation
    return QueryResponse(
        answer=f"Received your question: '{body.question}' — agent coming soon.",
        metadata={"user": current_user["username"]},
    )


# ── Health ──────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}
