"""Tests for lib/url_fetcher.py — the extraction guard.

HTTP is stubbed at the _fetch_html seam so these run offline. What is under
test is the judgement after the fetch: deciding whether what came back is
actually an article.

Coroutines are driven with asyncio.run rather than pytest-asyncio — four tests
do not justify a plugin and its mode configuration.
"""
import asyncio

import pytest

from app.config import settings
from app.lib import url_fetcher
from app.lib.url_fetcher import UrlFetchError, fetch_and_extract

ARTICLE_HTML = """
<html><head><title>A Real Article</title></head><body><article>
<h1>A Real Article</h1>
{paragraphs}
</article></body></html>
"""

# What an aggregator or paywalled page actually looks like: a headline and a
# one-line teaser, with the article itself somewhere else.
TEASER_HTML = """
<html><head><title>Random Article</title></head><body><article>
<h1>Operation London Bridge: The Secret Plans</h1>
<p>She is venerated around the world and has outlasted 12 US presidents.</p>
</article></body></html>
"""


@pytest.fixture
def stub_fetch(monkeypatch):
    def _install(html: str) -> None:
        async def fake_fetch_html(url: str) -> str:
            return html

        monkeypatch.setattr(url_fetcher, "_fetch_html", fake_fetch_html)

    return _install


def _article_html(paragraph_count: int) -> str:
    body = "\n".join(
        f"<p>Paragraph {i} carries several sentences of genuine article prose "
        "so that the extracted text comfortably clears the minimum length.</p>"
        for i in range(paragraph_count)
    )
    return ARTICLE_HTML.format(paragraphs=body)


def test_real_article_is_extracted(stub_fetch):
    stub_fetch(_article_html(20))

    title, content = asyncio.run(fetch_and_extract("https://example.com/article"))

    assert len(content) >= settings.min_extracted_chars
    assert "Paragraph 0" in content
    assert title


def test_teaser_page_is_rejected_with_an_actionable_message(stub_fetch):
    stub_fetch(TEASER_HTML)

    with pytest.raises(UrlFetchError) as caught:
        asyncio.run(fetch_and_extract("https://longform.org/random"))

    message = str(caught.value)
    assert "article" in message.lower()
    assert str(settings.min_extracted_chars) in message


def test_page_with_no_prose_is_rejected(stub_fetch):
    stub_fetch("<html><body><nav><a href='/a'>one</a></nav></body></html>")

    with pytest.raises(UrlFetchError):
        asyncio.run(fetch_and_extract("https://example.com/nav-only"))


def test_extracted_content_is_capped(stub_fetch, monkeypatch):
    monkeypatch.setattr(settings, "max_content_chars", 900)
    stub_fetch(_article_html(200))

    _, content = asyncio.run(fetch_and_extract("https://example.com/long"))

    assert len(content) == 900
