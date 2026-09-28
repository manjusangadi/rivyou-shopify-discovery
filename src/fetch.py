"""
Asynchronous HTTP client with connection pooling, retries, concurrency limits, and polite delays.
"""
import asyncio
from dataclasses import dataclass
import logging
import random
import time
from typing import Optional, Dict, Any, Tuple
import httpx

from src.config import Config, default_config

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    url: str
    final_url: str
    status_code: int
    text: str
    headers: Dict[str, str]
    error: Optional[str] = None
    elapsed_seconds: float = 0.0


class AsyncFetcher:
    """
    Polite and resilient HTTP client wrapping httpx.AsyncClient.
    """

    def __init__(self, config: Optional[Config] = None):
        self.config = config or default_config
        self.semaphore = asyncio.Semaphore(self.config.max_concurrency)
        self._client: Optional[httpx.AsyncClient] = None
        self._domain_last_request: Dict[str, float] = {}

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            limits = httpx.Limits(
                max_keepalive_connections=20,
                max_connections=self.config.max_concurrency * 2,
                keepalive_expiry=30.0
            )
            headers = {
                "User-Agent": self.config.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1"
            }
            self._client = httpx.AsyncClient(
                headers=headers,
                timeout=httpx.Timeout(self.config.request_timeout, connect=10.0),
                follow_redirects=True,
                limits=limits,
                verify=False  # Avoid halting on outdated SSL intermediate certs on Indian SMB domains
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _polite_delay(self, domain: str):
        """Ensures at least config.request_delay between successive requests to the same domain."""
        if not self.config.request_delay:
            return

        last_time = self._domain_last_request.get(domain, 0.0)
        now = time.time()
        time_since_last = now - last_time
        if time_since_last < self.config.request_delay:
            sleep_needed = self.config.request_delay - time_since_last
            await asyncio.sleep(sleep_needed)
        self._domain_last_request[domain] = time.time()

    async def fetch(self, url: str, domain_key: Optional[str] = None) -> FetchResult:
        """
        Fetches a URL with retries on temporary failures and polite domain throttling.
        """
        domain = domain_key or url
        client = await self.get_client()

        for attempt in range(1, self.config.max_retries + 2):
            async with self.semaphore:
                await self._polite_delay(domain)
                start_time = time.time()
                try:
                    resp = await client.get(url)
                    elapsed = time.time() - start_time

                    # If temporary 5xx error or rate limit 429, retry
                    if resp.status_code in {429, 502, 503, 504} and attempt <= self.config.max_retries:
                        backoff = (2 ** attempt) * 0.5 + random.uniform(0.1, 0.4)
                        logger.debug(f"[fetch] Status {resp.status_code} for {url}. Retrying in {backoff:.2f}s (attempt {attempt}).")
                        await asyncio.sleep(backoff)
                        continue

                    headers_dict = {k.lower(): v for k, v in resp.headers.items()}
                    return FetchResult(
                        url=url,
                        final_url=str(resp.url),
                        status_code=resp.status_code,
                        text=resp.text,
                        headers=headers_dict,
                        error=None,
                        elapsed_seconds=elapsed
                    )

                except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as e:
                    elapsed = time.time() - start_time
                    if attempt <= self.config.max_retries:
                        backoff = 1.0 * attempt
                        await asyncio.sleep(backoff)
                        continue
                    return FetchResult(
                        url=url,
                        final_url=url,
                        status_code=0,
                        text="",
                        headers={},
                        error=f"Timeout: {type(e).__name__}",
                        elapsed_seconds=elapsed
                    )

                except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.RequestError) as e:
                    elapsed = time.time() - start_time
                    if attempt <= self.config.max_retries:
                        backoff = 1.0 * attempt
                        await asyncio.sleep(backoff)
                        continue
                    return FetchResult(
                        url=url,
                        final_url=url,
                        status_code=0,
                        text="",
                        headers={},
                        error=f"NetworkError: {type(e).__name__}",
                        elapsed_seconds=elapsed
                    )

                except Exception as e:
                    elapsed = time.time() - start_time
                    return FetchResult(
                        url=url,
                        final_url=url,
                        status_code=0,
                        text="",
                        headers={},
                        error=f"UnexpectedError: {str(e)}",
                        elapsed_seconds=elapsed
                    )

        # Fallback return
        return FetchResult(
            url=url,
            final_url=url,
            status_code=0,
            text="",
            headers={},
            error="MaxRetriesExceeded",
            elapsed_seconds=0.0
        )
