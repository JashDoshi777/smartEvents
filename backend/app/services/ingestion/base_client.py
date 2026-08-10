"""
LiveIQ — Async HTTP Base Client
All API clients inherit from this. Provides:
  - Async httpx session with connection pooling
  - Exponential backoff retry (up to 3 attempts)
  - Per-host rate limiting via asyncio.Semaphore
  - Structured logging on every request
  - Circuit breaker: after 5 consecutive failures, stops for 60s
"""

import asyncio
import time
from typing import Any, Dict, Optional
import httpx
import structlog

logger = structlog.get_logger()


class CircuitBreaker:
    """
    Simple circuit breaker.
    After `max_failures` consecutive errors, opens for `reset_timeout` seconds.
    """
    def __init__(self, max_failures: int = 5, reset_timeout: float = 60.0):
        self.max_failures = max_failures
        self.reset_timeout = reset_timeout
        self._failures = 0
        self._opened_at: Optional[float] = None

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at >= self.reset_timeout:
            # Auto-reset after timeout
            self._failures = 0
            self._opened_at = None
            return False
        return True

    def record_success(self):
        self._failures = 0
        self._opened_at = None

    def record_failure(self):
        self._failures += 1
        if self._failures >= self.max_failures:
            self._opened_at = time.monotonic()
            logger.warning(
                "Circuit breaker OPENED",
                failures=self._failures,
                reset_in_seconds=self.reset_timeout,
            )


class BaseAPIClient:
    """
    Base class for all LiveIQ external API clients.
    Usage:
        class SpotifyClient(BaseAPIClient):
            BASE_URL = "https://api.spotify.com/v1"
            RATE_LIMIT = 5   # max 5 concurrent requests
    """

    BASE_URL: str = ""
    RATE_LIMIT: int = 10       # Max concurrent requests to this API
    TIMEOUT: float = 15.0      # Seconds
    MAX_RETRIES: int = 3
    RETRY_BACKOFF: float = 1.5 # Seconds (doubles each retry)

    def __init__(self):
        self._semaphore = asyncio.Semaphore(self.RATE_LIMIT)
        self._circuit_breaker = CircuitBreaker()
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=httpx.Timeout(self.TIMEOUT),
            follow_redirects=True,
            limits=httpx.Limits(max_connections=self.RATE_LIMIT, max_keepalive_connections=5),
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """GET request with rate limiting, retry, and circuit breaker."""
        return await self._request("GET", path, params=params, headers=headers, **kwargs)

    async def post(
        self,
        path: str,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """POST request with rate limiting, retry, and circuit breaker."""
        return await self._request("POST", path, json=json, data=data, headers=headers, **kwargs)

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """Core request method: semaphore → circuit check → retry loop."""
        if self._circuit_breaker.is_open:
            raise RuntimeError(
                f"Circuit breaker OPEN for {self.__class__.__name__}. "
                f"Too many failures — backing off."
            )

        if self._client is None:
            raise RuntimeError(
                f"{self.__class__.__name__} must be used as an async context manager"
            )

        async with self._semaphore:
            last_exc: Optional[Exception] = None
            for attempt in range(1, self.MAX_RETRIES + 1):
                try:
                    response = await self._client.request(method, path, **kwargs)
                    response.raise_for_status()
                    self._circuit_breaker.record_success()
                    logger.debug(
                        "API request success",
                        client=self.__class__.__name__,
                        method=method,
                        path=path,
                        status=response.status_code,
                        attempt=attempt,
                    )
                    return response.json()

                except httpx.HTTPStatusError as e:
                    status = e.response.status_code
                    # 4xx errors (except 429) are NOT retried — they are caller errors
                    if status == 429:
                        retry_after = float(e.response.headers.get("Retry-After", 5))
                        logger.warning(
                            "Rate limited — waiting",
                            client=self.__class__.__name__,
                            retry_after=retry_after,
                        )
                        await asyncio.sleep(retry_after)
                        last_exc = e
                        continue
                    elif 400 <= status < 500:
                        logger.error(
                            "API client error — not retrying",
                            client=self.__class__.__name__,
                            status=status,
                            path=path,
                        )
                        raise
                    else:
                        # 5xx — retryable
                        last_exc = e

                except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError) as e:
                    last_exc = e

                # Exponential backoff before retry
                if attempt < self.MAX_RETRIES:
                    wait = self.RETRY_BACKOFF * (2 ** (attempt - 1))
                    logger.warning(
                        "API request failed — retrying",
                        client=self.__class__.__name__,
                        method=method,
                        path=path,
                        attempt=attempt,
                        wait_seconds=wait,
                        error=str(last_exc),
                    )
                    await asyncio.sleep(wait)

            # All retries exhausted
            self._circuit_breaker.record_failure()
            logger.error(
                "API request FAILED after all retries",
                client=self.__class__.__name__,
                method=method,
                path=path,
                attempts=self.MAX_RETRIES,
                error=str(last_exc),
            )
            if last_exc is not None:
                raise last_exc
            raise RuntimeError(
                f"{self.__class__.__name__}: all {self.MAX_RETRIES} retries exhausted "
                f"for {method} {path} with no captured exception"
            )
