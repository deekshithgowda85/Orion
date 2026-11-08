"""Report rendering: report JSON -> Markdown -> PDF via Pandoc (with clear errors if it is missing)."""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from typing import Any

PDF_ENGINES = ("xelatex", "lualatex", "pdflatex", "wkhtmltopdf", "weasyprint")


class PdfUnavailable(Exception):
    """Pandoc or a PDF engine is not installed (-> HTTP 501 with an install hint)."""


def _esc_cell(v: Any) -> str:
    return str(v if v is not None else "").replace("|", "\\|").replace("\n", " ")


def report_to_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# {report.get('ticker', '')} Research Report",
        "",
        f"**Query:** {report.get('query', '')}  ",
        f"**Quarter:** {report.get('quarter') or 'n/a'}  ",
        f"**Workflow:** {report.get('workflow_type', '')}  ",
        f"**Generated:** {report.get('generated_at', '')}",
        "",
        "## Summary",
        "",
        str(report.get("summary", "")) or "_No summary provided._",
        "",
    ]
    for sec in report.get("sections", []):
        lines += [f"## {sec.get('title', 'Section')}", "", str(sec.get("content", "")), ""]
    if not report.get("sections") and report.get("report"):
        # Report shape is unknown (Layer 3 state dump): render each top-level key as a section.
        import json

        for k, v in report["report"].items():
            if k in ("summary",):
                continue
            body = v if isinstance(v, str) else "```json\n" + json.dumps(v, indent=2, default=str)[:20000] + "\n```"
            lines += [f"## {k.replace('_', ' ').title()}", "", body, ""]
    conflicts = report.get("conflicts", [])
    if conflicts:
        lines += ["## Data Conflicts", ""]
        for c in conflicts:
            lines.append(f"- {c.get('description', c) if isinstance(c, dict) else c}")
        lines.append("")
    cites = report.get("citations", [])
    if cites:
        lines += ["## Citations", "", "| Metric | Value | Period | Source | Confidence |", "|---|---|---|---|---|"]
        for c in cites:
            lines.append(
                f"| {_esc_cell(c.get('metric_name'))} | {_esc_cell(c.get('value'))} | {_esc_cell(c.get('period'))} "
                f"| {_esc_cell(c.get('source_url'))} | {_esc_cell(c.get('confidence'))} |"
            )
    return "\n".join(lines)


def _find_engine() -> str:
    if not shutil.which("pandoc"):
        raise PdfUnavailable("Pandoc is not installed on the server (install from https://pandoc.org/installing.html)")
    for eng in PDF_ENGINES:
        if shutil.which(eng):
            return eng
    raise PdfUnavailable("No PDF engine found; install a LaTeX distribution (MiKTeX/TeX Live) or wkhtmltopdf")


async def markdown_to_pdf(markdown: str) -> bytes:
    engine = _find_engine()
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "report.md")
        out = os.path.join(tmp, "report.pdf")
        with open(src, "w", encoding="utf-8") as f:
            f.write(markdown)
        # raw_tex/raw_html disabled: report text comes from scraped web content and must not be able to
        # inject LaTeX commands (e.g. \input{...}) into the PDF build.
        proc = await asyncio.create_subprocess_exec(
            "pandoc", src, "--from=markdown-raw_tex-raw_html-raw_attribute-tex_math_dollars",
            "-o", out, f"--pdf-engine={engine}", "-V", "geometry:margin=1in",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError("pandoc timed out after 120s") from None
        if proc.returncode != 0:
            raise RuntimeError(f"pandoc failed: {stderr.decode(errors='replace')[:500]}")
        with open(out, "rb") as f:
            return f.read()
