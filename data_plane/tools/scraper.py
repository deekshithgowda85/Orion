"""Web scraper: Firecrawl primary, httpx + BeautifulSoup4 fallback (quota / outage)."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import httpx
from pydantic import BaseModel, Field

from .common import ToolError, g, get_logger, guarded, is_retryable, log_event, make_soup, with_retry

log = get_logger("scraper")

_UA = "Mozilla/5.0 (compatible; MarketResearchAgent/1.0)"
_PREFERRED_TRANSCRIPT_HOSTS = ("fool.com", "seekingalpha.com", "investing.com", "insidermonkey.com",
                               "gurufocus.com", "marketbeat.com", "finance.yahoo.com")
_FC_COOLDOWN_S = 900


class ScraperError(ToolError):
    pass


class TranscriptNotFoundError(ScraperError):
    pass


class ScrapedPage(BaseModel):
    url: str
    title: str | None = None
    description: str | None = None
    markdown: str
    links: list[str] = Field(default_factory=list)
    status_code: int | None = None
    source: Literal["firecrawl", "httpx"]
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _is_quota_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(t in msg for t in ("402", "payment required", "insufficient credits", "quota", "out of credits",
                                  "credits exhausted", "plan limit"))


def _html_to_markdown(html: str, base_url: str) -> tuple[str, str | None, str | None, list[str]]:
    soup = make_soup(html)
    title = soup.title.get_text(strip=True) if soup.title else None
    md_tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
    description = md_tag.get("content") if md_tag and md_tag.get("content") else None

    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "form", "iframe", "aside"]):
        tag.decompose()

    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        if href.startswith(("http://", "https://")) and href not in links:
            links.append(href)
        label = a.get_text(" ", strip=True)
        if label and href.startswith(("http://", "https://")):
            a.replace_with(f"[{label}]({href})")
    for level in range(1, 7):
        for h in soup.find_all(f"h{level}"):
            h.insert_before("\n\n" + "#" * level + " ")
            h.insert_after("\n\n")
    for li in soup.find_all("li"):
        li.insert_before("\n- ")
    for tag in soup.find_all(["p", "div", "br", "tr", "section", "article", "blockquote"]):
        tag.insert_after("\n")
    for td in soup.find_all(["td", "th"]):
        td.insert_after(" | ")
    text = soup.get_text().replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text).strip()
    return text, title, description, links[:200]


class ScraperTool:
    def __init__(self, firecrawl_api_key: str | None = None, client: httpx.AsyncClient | None = None,
                 max_concurrency: int = 3) -> None:
        self._fc: Any = None
        self._fc_disabled_until = 0.0
        if firecrawl_api_key:
            try:
                try:
                    from firecrawl import Firecrawl as _FC  # firecrawl-py >= 2
                except ImportError:
                    from firecrawl import FirecrawlApp as _FC  # firecrawl-py 1.x
                self._fc = _FC(api_key=firecrawl_api_key)
            except Exception as exc:  # noqa: BLE001
                log_event(log, logging.ERROR, "firecrawl_init_failed", error=repr(exc))
        self._client = client or httpx.AsyncClient(
            headers={"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml"},
            timeout=httpx.Timeout(30.0), follow_redirects=True)
        self._sem = asyncio.Semaphore(max_concurrency)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _fc_available(self) -> bool:
        return self._fc is not None and time.monotonic() >= self._fc_disabled_until

    def _fc_trip(self, exc: BaseException) -> None:
        if _is_quota_error(exc):
            self._fc_disabled_until = time.monotonic() + _FC_COOLDOWN_S
            log_event(log, logging.WARNING, "firecrawl_quota_exhausted_using_fallback",
                      cooldown_s=_FC_COOLDOWN_S, error=repr(exc))

    # ---- firecrawl
    def _fc_scrape_sync(self, url: str) -> ScrapedPage:
        fn = getattr(self._fc, "scrape", None) or getattr(self._fc, "scrape_url")
        res = fn(url, formats=["markdown", "links"])
        md = g(res, "markdown") or ""
        if not md.strip():
            raise ScraperError(f"firecrawl returned empty markdown for {url}")
        meta = g(res, "metadata")
        return ScrapedPage(
            url=url, markdown=md, source="firecrawl",
            title=g(meta, "title"), description=g(meta, "description"),
            links=[str(x) for x in (g(res, "links") or [])][:200],
            status_code=g(meta, "status_code") or g(meta, "statusCode"),
        )

    async def _scrape_firecrawl(self, url: str) -> ScrapedPage:
        async def attempt() -> ScrapedPage:
            return await asyncio.to_thread(self._fc_scrape_sync, url)

        return await with_retry(attempt, op="firecrawl.scrape", logger=log, ctx={"url": url},
                                retryable=lambda e: is_retryable(e) and not _is_quota_error(e))

    # ---- httpx fallback
    async def _scrape_httpx(self, url: str) -> ScrapedPage:
        async def attempt() -> httpx.Response:
            resp = await self._client.get(url)
            resp.raise_for_status()
            return resp

        resp = await with_retry(attempt, op="httpx.scrape", logger=log, ctx={"url": url})
        md, title, desc, links = await asyncio.to_thread(_html_to_markdown, resp.text, str(resp.url))
        return ScrapedPage(url=url, markdown=md, title=title, description=desc, links=links,
                           status_code=resp.status_code, source="httpx")

    # ---- public API
    @guarded("scraper.scrape_url", ScraperError)
    async def scrape_url(self, url: str) -> ScrapedPage:
        if self._fc_available():
            try:
                return await self._scrape_firecrawl(url)
            except Exception as exc:  # noqa: BLE001
                self._fc_trip(exc)
                log_event(log, logging.WARNING, "firecrawl_scrape_failed_fallback", url=url, error=repr(exc))
        return await self._scrape_httpx(url)

    async def _search_firecrawl(self, query: str, n: int) -> list[str]:
        def run() -> list[str]:
            res = self._fc.search(query, limit=n)
            items = res if isinstance(res, list) else (
                g(res, "web") or g(res, "data") or g(g(res, "data"), "web") or [])
            return [u for u in (g(i, "url") for i in items) if u]

        async def attempt() -> list[str]:
            return await asyncio.to_thread(run)

        return await with_retry(attempt, op="firecrawl.search", logger=log, ctx={"query": query},
                                retryable=lambda e: is_retryable(e) and not _is_quota_error(e))

    async def _search_ddg(self, query: str, n: int) -> list[str]:
        async def attempt() -> httpx.Response:
            resp = await self._client.get("https://html.duckduckgo.com/html/", params={"q": query})
            resp.raise_for_status()
            return resp

        resp = await with_retry(attempt, op="ddg.search", logger=log, ctx={"query": query})
        soup = make_soup(resp.text)
        urls: list[str] = []
        for a in soup.select("a.result__a"):
            href = a.get("href", "")
            if "uddg=" in href:
                href = unquote(parse_qs(urlparse(href).query).get("uddg", [""])[0])
            elif href.startswith("//"):
                href = "https:" + href
            if href.startswith("http") and href not in urls:
                urls.append(href)
            if len(urls) >= n:
                break
        return urls

    async def _search_urls(self, query: str, n: int) -> list[str]:
        if self._fc_available():
            try:
                urls = await self._search_firecrawl(query, n)
                if urls:
                    return urls
            except Exception as exc:  # noqa: BLE001
                self._fc_trip(exc)
                log_event(log, logging.WARNING, "firecrawl_search_failed_fallback", query=query, error=repr(exc))
        return await self._search_ddg(query, n)

    @guarded("scraper.search_and_scrape", ScraperError)
    async def search_and_scrape(self, query: str, num_results: int = 5) -> list[ScrapedPage]:
        urls = await self._search_urls(query, num_results)

        async def one(u: str) -> ScrapedPage | None:
            async with self._sem:
                try:
                    return await self.scrape_url(u)
                except ToolError as exc:
                    log_event(log, logging.WARNING, "search_result_scrape_failed", url=u, error=repr(exc))
                    return None

        pages = await asyncio.gather(*(one(u) for u in urls))
        return [p for p in pages if p is not None]

    @guarded("scraper.scrape_earnings_transcript", ScraperError)
    async def scrape_earnings_transcript(self, ticker: str, quarter: str) -> str:
        """`quarter` e.g. "Q3 2025". Returns the transcript as markdown."""
        pages = await self.search_and_scrape(f"{ticker} {quarter} earnings call transcript", num_results=8)

        def rank(p: ScrapedPage) -> tuple[int, int]:
            host = urlparse(p.url).netloc.lower()
            pref = next((i for i, h in enumerate(_PREFERRED_TRANSCRIPT_HOSTS) if h in host),
                        len(_PREFERRED_TRANSCRIPT_HOSTS))
            return (pref, -len(p.markdown))

        qtok = quarter.upper().replace(" ", "")
        for p in sorted(pages, key=rank):
            low = p.markdown.lower()
            if len(p.markdown) > 5000 and "transcript" in low[:20000] and (
                    ticker.lower() in low or qtok.lower() in low.replace(" ", "")):
                return p.markdown
        raise TranscriptNotFoundError(f"no transcript found for {ticker} {quarter} ({len(pages)} pages checked)")


# --------------------------------------------------------------------------- smoke test
async def _demo() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    tool = ScraperTool(os.environ.get("FIRECRAWL_API_KEY"))
    try:
        try:
            page = await tool.scrape_url("https://example.com")
            print("scrape_url:", page.source, page.title, len(page.markdown), "chars,", len(page.links), "links")
            results = await tool.search_and_scrape("Apple Inc investor relations", num_results=2)
            print("search_and_scrape:", [(p.source, p.url) for p in results])
            t = await tool.scrape_earnings_transcript("AAPL", "Q3 2025")
            print("transcript chars:", len(t))
        except ToolError as exc:
            print("scraper demo stopped:", exc)
    finally:
        await tool.aclose()


if __name__ == "__main__":
    asyncio.run(_demo())
