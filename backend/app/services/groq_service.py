"""
LiveIQ — Groq LLM Service
Primary AI engine for the Copilot feature.

Groq is OpenAI-compatible and runs on custom LPU hardware delivering
300–1000+ tokens/second — effectively instant for our use case.

Model: llama-3.3-70b-versatile
  - 128K context window
  - Best for: data analysis, Q&A, trend summaries, recommendations
  - Speed: ~300 tok/s on Groq LPU

Alternative: moonshotai/kimi-k2-instruct
  - Most capable model on Groq
  - Best for: complex reasoning, multi-step analysis

API: https://console.groq.com/docs/openai
"""

from typing import AsyncGenerator, List, Optional
import structlog
from groq import AsyncGroq

from app.core.config import settings

logger = structlog.get_logger()

# System prompt that gives the AI full context of LiveIQ's purpose
LIVEIQ_SYSTEM_PROMPT = """You are LiveIQ Copilot, an elite events intelligence AI for District by Zomato.

Your role: Help District's business teams make data-driven decisions about events, artists, and entertainment across India.

You have deep knowledge of:
- Indian and international music artists (Bollywood, Punjabi, indie, pop, hip-hop, EDM, K-pop)
- India's live events market (concerts, comedy, sports, theatre, movies, experiences)
- District's 9 categories: Music, Comedy, Sports, Theatre, Movies, Nightlife, Dining, Activities, Workshops
- Competitor landscape: BookMyShow (60% market share), Swiggy Scenes, Paytm Insider (acquired by District)
- Indian cities: Mumbai, Delhi NCR, Bengaluru, Hyderabad, Pune, Chennai, Kolkata, Ahmedabad
- Trending artists: Karan Aujla, AP Dhillon, Diljit Dosanjh, Arijit Singh, AR Rahman, Prateek Kuhad, Ritviz
- International acts touring India: Coldplay, Ed Sheeran, Dua Lipa, The Weeknd, Martin Garrix

When answering:
1. Be specific and data-oriented — give numbers, percentages, comparisons where possible
2. Reference real artists, venues, and events when relevant
3. Always think about District's business angle — what helps them sell more tickets / grow GMV
4. Be concise but thorough — executives want insights, not essays
5. If asked about data you don't have real-time access to, say so and suggest what signals to watch

You speak like a senior analyst at a top-tier strategy consulting firm — sharp, confident, and always actionable.
"""


def _get_client() -> AsyncGroq:
    """Get authenticated Groq async client."""
    if not settings.is_api_configured("groq"):
        raise RuntimeError(
            "Groq API not configured. Add GROQ_API_KEY to .env\n"
            "Get a free key at: https://console.groq.com"
        )
    return AsyncGroq(api_key=settings.GROQ_API_KEY)


async def chat_completion(
    messages: List[dict],
    *,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    system_prompt: Optional[str] = None,
) -> str:
    """
    Single-turn chat completion. Returns the full response text.

    Args:
        messages: List of {"role": "user"|"assistant", "content": "..."} dicts
        model: Override default model (uses settings.GROQ_MODEL if None)
        temperature: 0.0 = deterministic, 1.0 = creative. 0.7 is a good default.
        max_tokens: Maximum tokens in response
        system_prompt: Override the LiveIQ system prompt

    Returns:
        Response text as a string
    """
    client = _get_client()
    model = model or settings.GROQ_MODEL

    # Prepend system message
    full_messages = [
        {"role": "system", "content": system_prompt or LIVEIQ_SYSTEM_PROMPT},
        *messages,
    ]

    log = logger.bind(model=model, message_count=len(messages))
    log.info("Groq chat request")

    response = await client.chat.completions.create(
        model=model,
        messages=full_messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    answer = response.choices[0].message.content
    usage = response.usage
    log.info(
        "Groq chat complete",
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
    )

    return answer


async def stream_completion(
    messages: List[dict],
    *,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    system_prompt: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """
    Streaming chat completion. Yields text chunks as they arrive.
    Use this for real-time UI streaming (Server-Sent Events / WebSocket).

    Usage:
        async for chunk in stream_completion(messages):
            print(chunk, end="", flush=True)
    """
    client = _get_client()
    model = model or settings.GROQ_MODEL

    full_messages = [
        {"role": "system", "content": system_prompt or LIVEIQ_SYSTEM_PROMPT},
        *messages,
    ]

    logger.info("Groq stream request", model=model)

    stream = await client.chat.completions.create(
        model=model,
        messages=full_messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=True,
    )
    async for chunk in stream:
        text = chunk.choices[0].delta.content if chunk.choices else None
        if text:
            yield text


async def quick_analyze(topic: str, context: str = "") -> str:
    """
    One-shot analysis helper — used internally by workers and routes.
    Example: quick_analyze("AP Dhillon", "listeners=134701, trending=True")
    """
    prompt = f"Analyze this entity for District's events platform:\n\nEntity: {topic}"
    if context:
        prompt += f"\n\nContext data:\n{context}"
    prompt += "\n\nProvide a concise intelligence summary (3-5 bullet points max)."

    return await chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=512,
    )
