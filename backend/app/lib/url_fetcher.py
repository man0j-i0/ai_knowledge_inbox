"""Server-side URL fetch + main-content extraction.

Two things matter here beyond "it downloads a page":

  * Every failure mode raises UrlFetchError with a message a human can act on
    ("timed out after 10s", "returned HTTP 404", "no readable article
    content"). The ingestion worker turns that straight into status='failed'
    plus that message, so a broken URL shows up in the UI as a stated reason
    rather than an item stuck on 'processing' forever.
  * trafilatura is synchronous and CPU-bound. Awaiting it directly would block
    the event loop and freeze every other request for the length of an ingest,
    so it runs in a worker thread via asyncio.to_thread.
"""
import asyncio

import httpx
import trafilatura

from app.config import settings

# Identify honestly. I measured a full Chrome UA string against the same set of
# sites and it made no difference — identical status codes everywhere, including
# Wikipedia, which blocks programmatic access by policy rather than by
# User-Agent sniffing. So there is nothing to buy by impersonating a browser.
USER_AGENT = "Mozilla/5.0 (compatible; AIKnowledgeInbox/1.0)"


class UrlFetchError(Exception):
    """URL could not be fetched or produced no usable content."""


async def fetch_and_extract(url: str) -> tuple[str, str]:
    """Return (title, main_text) for a web page. Raises UrlFetchError."""
    html = await _fetch_html(url)
    title, content = await asyncio.to_thread(_extract, html, url)

    if not content:
        raise UrlFetchError(
            "Page was fetched but no readable article content could be extracted"
        )

    return title, content[: settings.max_content_chars]


async def _fetch_html(url: str) -> str:
    try:
        async with httpx.AsyncClient(
            timeout=settings.url_fetch_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            response = await client.get(url)
    except httpx.TimeoutException as exc:
        raise UrlFetchError(
            f"Timed out after {settings.url_fetch_timeout_seconds}s fetching {url}"
        ) from exc
    except httpx.RequestError as exc:
        raise UrlFetchError(
            f"Could not reach {url} ({exc.__class__.__name__})"
        ) from exc

    if response.status_code >= 400:
        raise UrlFetchError(f"{url} returned HTTP {response.status_code}")

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type.lower():
        raise UrlFetchError(
            f"Unsupported content-type '{content_type or 'unknown'}' "
            "— only HTML pages can be ingested"
        )

    return response.text


def _extract(html: str, url: str) -> tuple[str, str]:
    """Synchronous and CPU-bound: only ever called via asyncio.to_thread."""
    content = trafilatura.extract(
        html,
        url=url,
        include_comments=False,   # comment threads are noise, not the article
        include_tables=True,      # tables often hold the facts worth asking about
    ) or ""

    title = ""
    metadata = trafilatura.extract_metadata(html)
    if metadata is not None:
        title = (getattr(metadata, "title", None) or "").strip()

    return (title or url), content.strip()
