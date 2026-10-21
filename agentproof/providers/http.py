"""HTTP transport with retries, used by the provider implementations."""

from __future__ import annotations

import time
from typing import Any

import httpx

from agentproof.errors import ProviderError, RateLimitError

__all__ = ["HttpTransport"]


#: HTTP status codes that are worth retrying.
RETRYABLE_STATUS = frozenset({408, 409, 429, 500, 502, 503, 504, 529})


class HttpTransport:
    """A thin JSON-over-HTTP client with exponential backoff.

    Args:
        timeout: Per-request timeout in seconds.
        max_retries: Number of retries for retryable failures.
        backoff: Base delay in seconds for the exponential backoff.
        transport: Optional httpx transport, primarily useful for testing.
    """

    def __init__(
        self,
        *,
        timeout: float = 120.0,
        max_retries: int = 3,
        backoff: float = 2.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        """Configure the retry policy and open the HTTP client."""
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def post_json(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, Any],
        provider: str,
    ) -> dict[str, Any]:
        """POST a JSON payload and return the decoded JSON response.

        Args:
            url: Fully-qualified endpoint URL.
            headers: Request headers.
            payload: JSON-serialisable request body.
            provider: Provider name used in error messages.

        Returns:
            The decoded response body.

        Raises:
            RateLimitError: If the provider keeps returning HTTP 429.
            ProviderError: If the request fails for any other reason.
        """
        attempt = 0
        last_error: str = ""

        while attempt <= self.max_retries:
            attempt += 1
            try:
                response = self._client.post(url, headers=headers, json=payload)
            except httpx.TimeoutException as exc:
                last_error = f"request timed out after {self.timeout:g}s ({exc})"
            except httpx.HTTPError as exc:
                last_error = f"network error: {exc}"
            else:
                if response.status_code < 400:
                    try:
                        payload_data: dict[str, Any] = response.json()
                    except ValueError as exc:
                        raise ProviderError(
                            f"{provider} returned a non-JSON response: {exc}",
                            provider=provider,
                        ) from exc
                    return payload_data

                detail = _extract_error_detail(response)
                last_error = f"HTTP {response.status_code}: {detail}"

                if response.status_code == 429:
                    if attempt > self.max_retries:
                        raise RateLimitError(
                            f"{provider} rate limit exceeded after {attempt} attempts. {detail}",
                            provider=provider,
                            status_code=429,
                        )
                elif response.status_code not in RETRYABLE_STATUS:
                    raise ProviderError(
                        f"{provider} request failed. {last_error}",
                        provider=provider,
                        status_code=response.status_code,
                    )

            if attempt > self.max_retries:
                break

            delay = self.backoff * (2 ** (attempt - 1))
            time.sleep(min(delay, 30.0))

        raise ProviderError(
            f"{provider} request failed after {attempt} attempts. {last_error}",
            provider=provider,
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> HttpTransport:
        """Return the transport so it can be used as a context manager."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Close the HTTP client when leaving the context manager."""
        self.close()


def _extract_error_detail(response: httpx.Response) -> str:
    """Extract a human-readable error message from a failed response."""
    try:
        payload = response.json()
    except ValueError:
        return response.text[:500] or "<empty response>"

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("type") or ""
            return str(message)[:500]
        if isinstance(error, str):
            return error[:500]
        message = payload.get("message") or payload.get("detail")
        if message:
            return str(message)[:500]
    return str(payload)[:500]
