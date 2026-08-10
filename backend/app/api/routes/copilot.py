"""
LiveIQ — AI Copilot Routes
Powered by Groq (llama-3.3-70b-versatile).

Endpoints:
  POST /copilot/chat         → Single-turn Q&A (JSON response)
  POST /copilot/stream       → Streaming response (Server-Sent Events)
  WS   /copilot/ws           → WebSocket for real-time chat UI
  GET  /copilot/models       → List available models
"""

import json
from typing import List, Optional
from uuid import UUID
import structlog
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.groq_service import chat_completion, stream_completion
from app.core.config import settings
from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.services.auth_service import decode_token

router = APIRouter()
logger = structlog.get_logger()


# ─── Request / Response Schemas ────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    question: Optional[str] = None           # Simple single question
    messages: Optional[List[ChatMessage]] = None  # Full conversation history
    model: Optional[str] = None              # Override model (optional)
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)
    max_tokens: int = Field(default=1024, ge=64, le=4096)
    stream: bool = False                     # Use /stream endpoint instead for SSE


class ChatResponse(BaseModel):
    response: str
    model: str
    sources: List[str] = []                  # Will be populated with DB sources in Sprint 3
    tokens_used: Optional[int] = None


# ─── Routes ────────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, user: User = Depends(get_current_user)):
    """
    Single-turn Copilot chat.

    Accepts either:
    - `question`: a simple string question
    - `messages`: a full conversation history (for multi-turn)

    Returns a complete answer from Groq llama-3.3-70b-versatile.
    """
    if not settings.is_api_configured("groq"):
        raise HTTPException(
            status_code=503,
            detail="AI Copilot not available — GROQ_API_KEY not configured",
        )

    # Build message list
    if req.messages:
        messages = [{"role": m.role, "content": m.content} for m in req.messages]
    elif req.question:
        messages = [{"role": "user", "content": req.question}]
    else:
        raise HTTPException(status_code=422, detail="Provide either 'question' or 'messages'")

    log = logger.bind(model=req.model or settings.GROQ_MODEL)
    log.info("Copilot chat request", message_count=len(messages))

    try:
        answer = await chat_completion(
            messages=messages,
            model=req.model,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        log.error("Groq API error", error=str(e))
        raise HTTPException(status_code=502, detail=f"AI service error: {type(e).__name__}")

    return ChatResponse(
        response=answer,
        model=req.model or settings.GROQ_MODEL,
        sources=[],  # TODO Sprint 3: inject RAG sources from vector DB
    )


@router.post("/stream")
async def chat_stream(req: ChatRequest, user: User = Depends(get_current_user)):
    """
    Streaming Copilot chat using Server-Sent Events (SSE).

    The response streams as text/event-stream. Each chunk is a partial answer.
    The stream ends with a `[DONE]` event.

    Frontend usage:
        const es = await fetch('/copilot/stream', {method:'POST', body: JSON.stringify({question:'...'})})
        const reader = es.body.getReader()
    """
    if not settings.is_api_configured("groq"):
        raise HTTPException(status_code=503, detail="AI Copilot not configured")

    if req.messages:
        messages = [{"role": m.role, "content": m.content} for m in req.messages]
    elif req.question:
        messages = [{"role": "user", "content": req.question}]
    else:
        raise HTTPException(status_code=422, detail="Provide either 'question' or 'messages'")

    async def event_generator():
        try:
            async for chunk in stream_completion(
                messages=messages,
                model=req.model,
                temperature=req.temperature,
                max_tokens=req.max_tokens,
            ):
                # SSE format: data: <content>\n\n
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error("Groq stream error", error=str(e))
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering for SSE
        },
    )


@router.websocket("/ws")
async def copilot_websocket(websocket: WebSocket, db: AsyncSession = Depends(get_db)):
    """
    WebSocket endpoint for real-time streaming chat UI.

    Protocol:
      Client → connects with: /copilot/ws?token=<access_token>
      Client → sends: JSON {"question": "...", "history": [...]}
      Server → streams: text chunks then "[DONE]"

    WebSocket connections can't carry an Authorization: Bearer header the
    way get_current_user (HTTPBearer) expects, so the access token is
    validated here directly from a `token` query param using the same
    decode_token + active-user lookup get_current_user performs.
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing auth token")
        return

    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired token")
        return

    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token payload")
        return

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="User not found or deactivated")
        return

    await websocket.accept()
    logger.info("Copilot WebSocket connected", user_id=str(user.id))

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
                question = payload.get("question", raw)
                history = payload.get("history", [])
            except json.JSONDecodeError:
                question = raw
                history = []

            if not settings.is_api_configured("groq"):
                await websocket.send_text("[ERROR] Groq API not configured")
                continue

            # Build messages with optional history
            messages = [*history, {"role": "user", "content": question}]

            try:
                async for chunk in stream_completion(messages=messages, max_tokens=2048):
                    await websocket.send_text(chunk)
                await websocket.send_text("[DONE]")
            except Exception as e:
                logger.error("WS stream error", error=str(e))
                await websocket.send_text(f"[ERROR] {e}")

    except WebSocketDisconnect:
        logger.info("Copilot WebSocket disconnected")


@router.get("/models")
async def list_models(user: User = Depends(get_current_user)):
    """List available Groq models for the copilot."""
    return {
        "current_model": settings.GROQ_MODEL,
        "available_models": [
            {
                "id": "llama-3.3-70b-versatile",
                "name": "Llama 3.3 70B Versatile",
                "context_window": 128000,
                "description": "Best all-round model — fast, smart, 128K context",
                "recommended": settings.GROQ_MODEL == "llama-3.3-70b-versatile",
            },
            {
                "id": "moonshotai/kimi-k2-instruct",
                "name": "Kimi K2 Instruct",
                "context_window": 131072,
                "description": "Most capable — 1T parameter MoE, best for complex reasoning",
                "recommended": settings.GROQ_MODEL == "moonshotai/kimi-k2-instruct",
            },
            {
                "id": "llama-3.1-8b-instant",
                "name": "Llama 3.1 8B Instant",
                "context_window": 128000,
                "description": "Ultra-fast lightweight model for simple queries",
                "recommended": False,
            },
        ],
        "groq_configured": settings.is_api_configured("groq"),
    }
