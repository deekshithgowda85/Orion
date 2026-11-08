"""SEC EDGAR full-text search + filing download + LlamaParse-based section extraction."""
from __future__ import annotations

import asyncio
import bisect
import logging
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from .common import (AsyncRateLimiter, ToolError, get_logger, guarded, log_event, make_soup, with_retry)

log = get_logger("sec_filings")

FormType = Literal["10-K", "10-Q", "8-K", "DEF 14A"]
EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data"
PSEUDO_PAGE_CHARS = 3500
MAX_SECTION_CHARS = 400_000


class FilingsError(ToolError):
    pass


class FilingNotFoundError(FilingsError):
    pass


# --------------------------------------------------------------------------- models
class FilingMeta(BaseModel):
    accession_number: str
    cik: str
    company_name: str | None = None
    form_type: str
    filing_date: date | None = None
    period_ending: date | None = None
    primary_document: str
    url: str


class ParsedSection(BaseModel):
    name: str
    text: str
    start_page: int
    end_page: int
    char_count: int


class ParsedFiling(BaseModel):
    accession_number: str
    form_type: str
    parser: Literal["llamaparse", "heuristic"]
    total_pages: int
    sections: dict[str, ParsedSection] = Field(default_factory=dict)
    missing_sections: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- section patterns
_SEP = r"[\s\.\:\-–—]*"
_MGMT = r"management[’'`]?s?\s+discussion\s+and\s+analysis"


def _item(num: str, title: str) -> re.Pattern[str]:
    return re.compile(
        rf"^[\s#*|>_]*(?:part\s+[iv]+[\s,.\-–—]*)?item\s*{num}{_SEP}{title}", re.I | re.M)


_PATTERNS: dict[str, dict[str, re.Pattern[str]]] = {
    "10-K": {
        "MD&A": _item("7", _MGMT),
        "Risk Factors": _item("1A", r"risk\s+factors"),
        "Financial Statements": _item("8", r"financial\s+statements"),
    },
    "10-Q": {
        "MD&A": _item("2", _MGMT),
        "Risk Factors": _item("1A", r"risk\s+factors"),
        "Financial Statements": _item("1", r"financial\s+statements"),
    },
}
_HEADING_RX = re.compile(
    r"^[\s#*|>_]*(?:part\s+[iv]+[\s,.\-–—]*)?item\s*\d{1,2}[abc]?\b", re.I | re.M)

_ALIASES = {
    "mdna": "MD&A", "md&a": "MD&A", "managements discussion and analysis": "MD&A",
    "management discussion and analysis": "MD&A",
    "risk factors": "Risk Factors", "risk": "Risk Factors",
    "financial statements": "Financial Statements", "financials": "Financial Statements",
}


def _canon(name: str) -> str | None:
    key = name.lower().replace("’", "").replace("'", "").strip()
    return _ALIASES.get(key)


# --------------------------------------------------------------------------- tool
class SECFilingsTool:
    def __init__(self, user_agent: str, llama_api_key: str | None = None,
                 client: httpx.AsyncClient | None = None) -> None:
        if "@" not in user_agent:
            raise ValueError('EDGAR requires a User-Agent like "YourName yourname@example.com"')
        self._ua = user_agent
        self._llama_key = llama_api_key
        self._client = client or httpx.AsyncClient(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=httpx.Timeout(30.0), follow_redirects=True)
        self._limiter = AsyncRateLimiter(10, 1.0)  # EDGAR hard limit: 10 req/sec
        self._ticker_map: dict[str, tuple[str, str]] | None = None
        self._acc_index: dict[str, tuple[str, str]] = {}  # accession -> (cik, primary_doc)

    async def aclose(self) -> None:
        await self._client.aclose()

    # ---- HTTP
    async def _get(self, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
        async def attempt() -> httpx.Response:
            await self._limiter.acquire()
            resp = await self._client.get(url, params=params)
            resp.raise_for_status()
            return resp

        return await with_retry(attempt, op="edgar.get", logger=log, ctx={"url": url})

    async def _resolve_cik(self, ticker: str) -> tuple[str, str] | None:
        if self._ticker_map is None:
            data = (await self._get(TICKERS_URL)).json()
            self._ticker_map = {
                str(v["ticker"]).upper(): (str(v["cik_str"]).zfill(10), v.get("title", ""))
                for v in data.values()
            }
        return self._ticker_map.get(ticker.upper())

    # ---- search
    @guarded("edgar.search_filings", FilingsError)
    async def search_filings(self, ticker: str, form_type: FormType, limit: int = 5) -> list[FilingMeta]:
        ticker = ticker.upper().strip()
        resolved = await self._resolve_cik(ticker)
        params: dict[str, Any] = {"q": ticker, "forms": form_type}
        if resolved:
            params["ciks"] = resolved[0]
        data = (await self._get(EFTS_URL, params=params)).json()
        hits = data.get("hits", {}).get("hits", [])

        seen: set[str] = set()
        results: list[FilingMeta] = []
        for h in hits:
            src = h.get("_source", {})
            adsh = src.get("adsh")
            hit_id = h.get("_id", "")
            if not adsh or ":" not in hit_id or adsh in seen:
                continue
            ftype = (src.get("file_type") or src.get("form") or "").upper()
            if ftype and not ftype.startswith(form_type.upper()):
                continue  # skip exhibits (EX-31, EX-99, ...)
            doc = hit_id.split(":", 1)[1]
            ciks = src.get("ciks") or []
            cik = resolved[0] if resolved else (ciks[0] if ciks else "")
            if not cik:
                continue
            seen.add(adsh)
            self._acc_index[adsh] = (cik, doc)
            names = src.get("display_names") or []
            results.append(FilingMeta(
                accession_number=adsh, cik=cik,
                company_name=(names[0] if names else (resolved[1] if resolved else None)),
                form_type=src.get("form") or form_type,
                filing_date=src.get("file_date") or None,
                period_ending=src.get("period_ending") or None,
                primary_document=doc,
                url=f"{ARCHIVES_URL}/{int(cik)}/{adsh.replace('-', '')}/{doc}",
            ))
        results.sort(key=lambda m: m.filing_date or date.min, reverse=True)
        log_event(log, logging.INFO, "edgar_search_ok", ticker=ticker, form=form_type, hits=len(results))
        return results[:limit]

    # ---- download
    @guarded("edgar.download_filing", FilingsError)
    async def download_filing(self, accession_number: str) -> str:
        """Returns the raw primary-document text (HTML for modern filings)."""
        acc = accession_number.strip()
        nodash = acc.replace("-", "")
        loc = self._acc_index.get(acc)
        if loc is None:
            # Not seen in a search this process: discover the primary doc from the directory index.
            prefix_cik = str(int(acc.split("-")[0]))
            idx = (await self._get(f"{ARCHIVES_URL}/{prefix_cik}/{nodash}/index.json")).json()
            items = idx.get("directory", {}).get("item", [])
            docs = [i["name"] for i in items
                    if i["name"].lower().endswith((".htm", ".html", ".txt"))
                    and not i["name"].lower().startswith(("ex", "r1", "r2"))
                    and "index" not in i["name"].lower()]
            if not docs:
                raise FilingNotFoundError(f"no primary document found for {acc}")
            loc = (prefix_cik, docs[0])
            self._acc_index[acc] = loc
        cik, doc = loc
        resp = await self._get(f"{ARCHIVES_URL}/{int(cik)}/{nodash}/{doc}")
        log_event(log, logging.INFO, "edgar_download_ok", accession=acc, bytes=len(resp.content))
        return resp.text

    # ---- parsing
    async def _pages_via_llamaparse(self, filing_text: str) -> list[str]:
        try:
            from llama_cloud_services import LlamaParse  # newer package name
        except ImportError:
            from llama_parse import LlamaParse

        parser = LlamaParse(api_key=self._llama_key, result_type="markdown", verbose=False)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "filing.html"
            path.write_text(filing_text, encoding="utf-8")
            docs = await asyncio.wait_for(parser.aload_data(str(path)), timeout=300)
        pages = [d.text for d in docs if getattr(d, "text", "").strip()]
        if not pages:
            raise FilingsError("LlamaParse returned no content")
        return pages

    @staticmethod
    def _pages_heuristic(filing_text: str) -> list[str]:
        soup = make_soup(filing_text)
        for tag in soup(["script", "style", "noscript", "head"]):
            tag.decompose()
        for tag in soup.find_all(["div", "p", "tr", "br", "li", "h1", "h2", "h3", "h4", "table"]):
            tag.insert_after("\n")
        text = soup.get_text()
        text = text.replace("\xa0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text)
        pages: list[str] = []
        buf = ""
        for para in text.split("\n"):
            buf += para + "\n"
            if len(buf) >= PSEUDO_PAGE_CHARS:
                pages.append(buf)
                buf = ""
        if buf.strip():
            pages.append(buf)
        return pages

    @guarded("edgar.parse_filing_with_llama", FilingsError)
    async def parse_filing_with_llama(self, filing_text: str, extract_sections: list[str],
                                      form_type: str = "10-K", accession_number: str = "") -> ParsedFiling:
        parser_used: Literal["llamaparse", "heuristic"] = "heuristic"
        pages: list[str] | None = None
        if self._llama_key:
            try:
                pages = await self._pages_via_llamaparse(filing_text)
                parser_used = "llamaparse"
            except Exception as exc:  # noqa: BLE001 - fall back to local parsing
                log_event(log, logging.WARNING, "llamaparse_failed_fallback", error=repr(exc),
                          accession=accession_number)
        if pages is None:
            pages = await asyncio.to_thread(self._pages_heuristic, filing_text)

        full_parts: list[str] = []
        page_starts: list[int] = []
        offset = 0
        for p in pages:
            page_starts.append(offset)
            full_parts.append(p)
            offset += len(p) + 2
        full = "\n\n".join(full_parts)

        def page_of(pos: int) -> int:
            return max(bisect.bisect_right(page_starts, pos) - 1, 0) + 1

        patterns = _PATTERNS.get(form_type, {})
        heads = [m.start() for m in _HEADING_RX.finditer(full)]
        sections: dict[str, ParsedSection] = {}
        missing: list[str] = []
        for requested in extract_sections:
            name = _canon(requested)
            rx = patterns.get(name) if name else None
            if rx is None:
                missing.append(requested)
                continue
            best: tuple[int, int] | None = None
            for m in rx.finditer(full):
                i = bisect.bisect_right(heads, m.end())
                end = heads[i] if i < len(heads) else len(full)
                if best is None or (end - m.start()) > (best[1] - best[0]):
                    best = (m.start(), end)  # longest span skips the table-of-contents hit
            if best is None or (best[1] - best[0]) < 300:
                missing.append(requested)
                continue
            start, end = best
            text = full[start:min(end, start + MAX_SECTION_CHARS)].strip()
            sections[name] = ParsedSection(name=name, text=text, start_page=page_of(start),
                                           end_page=page_of(end - 1), char_count=len(text))
        log_event(log, logging.INFO, "filing_parsed", accession=accession_number, parser=parser_used,
                  pages=len(pages), sections=list(sections), missing=missing)
        return ParsedFiling(accession_number=accession_number, form_type=form_type, parser=parser_used,
                            total_pages=len(pages), sections=sections, missing_sections=missing)


# --------------------------------------------------------------------------- smoke test
async def _demo() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    ua = os.environ.get("SEC_EDGAR_USER_AGENT", "").strip('"')
    if "@" not in ua:
        print("SEC_EDGAR_USER_AGENT not set — skipping live test")
        return
    tool = SECFilingsTool(ua, os.environ.get("LLAMA_CLOUD_API_KEY"))
    try:
        metas = await tool.search_filings("AAPL", "10-K", limit=2)
        for m in metas:
            print(m.model_dump_json())
        text = await tool.download_filing(metas[0].accession_number)
        parsed = await tool.parse_filing_with_llama(
            text, ["MD&A", "Risk Factors", "Financial Statements"], "10-K", metas[0].accession_number)
        print("parser:", parsed.parser, "pages:", parsed.total_pages, "missing:", parsed.missing_sections)
        for s in parsed.sections.values():
            print(f"- {s.name}: pages {s.start_page}-{s.end_page}, {s.char_count} chars")
    finally:
        await tool.aclose()


if __name__ == "__main__":
    asyncio.run(_demo())
