"""
pdf_renderer.py — Converts Jinja2 HTML templates to professional PDF research notes.

Uses WeasyPrint (HTML→PDF) as primary renderer.
Falls back to a pure-HTML file if WeasyPrint is not installed.

Usage:
    from trg_workbench.reporting.pdf_renderer import render_research_note_pdf
    render_research_note_pdf(context, output_path)
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import sys
from tqdm import tqdm

from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _load_image_b64(path: Path) -> str:
    """Embed a PNG as a base64 data URI for inline HTML."""
    if path and path.exists():
        with open(path, "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode()
    return ""


def build_jinja_env(templates_dir: Path = TEMPLATES_DIR) -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    # Custom filters
    env.filters["pct"] = lambda v, d=1: f"{float(v):.{d}%}" if v is not None and v == v else "N/A"
    env.filters["dollar"] = lambda v, d=2: f"${float(v):,.{d}f}" if v is not None and v == v else "N/A"
    env.filters["number"] = lambda v: (
        f"{float(v)/1e9:.1f}B" if abs(float(v)) >= 1e9
        else f"{float(v)/1e6:.1f}M" if abs(float(v)) >= 1e6
        else f"{float(v)/1e3:.1f}K" if abs(float(v)) >= 1e3
        else f"{float(v):.2f}"
    ) if v is not None and v == v else "N/A"
    env.filters["x"] = lambda v, d=1: f"{float(v):.{d}f}x" if v is not None and v == v else "N/A"
    env.filters["signed_pct"] = lambda v, d=1: (
        f"+{float(v):.{d}%}" if float(v) > 0 else f"{float(v):.{d}%}"
    ) if v is not None and v == v else "N/A"
    env.filters["img_b64"] = lambda p: _load_image_b64(Path(p)) if p else ""
    return env


def render_html_report(
    context: Dict[str, Any],
    template_name: str = "research_note.html.j2",
    templates_dir: Path = TEMPLATES_DIR,
) -> str:
    """Render Jinja2 HTML template → HTML string."""
    env = build_jinja_env(templates_dir)
    template = env.get_template(template_name)
    return template.render(**context)


def render_research_note_pdf(
    context: Dict[str, Any],
    output_path: Path,
    template_name: str = "research_note.html.j2",
    templates_dir: Path = TEMPLATES_DIR,
    quiet: bool = False,
) -> Path:
    """
    Render a research note to PDF via WeasyPrint.
    Falls back to saving HTML if WeasyPrint unavailable.

    Args:
        context: Template context dict (from pipeline).
        output_path: Where to save the .pdf (or .html fallback).
        template_name: Jinja2 template file name.
        templates_dir: Directory containing templates.

    Returns:
        Path to the written file.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    disable_prog = quiet or not sys.stdout.isatty()

    with tqdm(total=3, desc="Rendering PDF", disable=disable_prog) as pbar:
        html_str = render_html_report(context, template_name, templates_dir)
        pbar.update(1)
        try:
            import weasyprint  # type: ignore
            pbar.update(1)

            pdf_path = output_path.with_suffix(".pdf")
            weasyprint.HTML(string=html_str, base_url=str(templates_dir)).write_pdf(str(pdf_path))
            logger.info("PDF written: %s", pdf_path)
            pbar.update(1)
            return pdf_path

        except (ImportError, OSError, Exception) as exc:
            pbar.update(3 - pbar.n)
            # Fallback: write as standalone HTML (open in browser or print-to-PDF)
            html_path = output_path.with_suffix(".html")
            html_path.write_text(html_str, encoding="utf-8")
            logger.warning(
                "WeasyPrint not installed — saved as HTML: %s\n"
                "Install with: pip install weasyprint\n"
                "Or open the HTML in Chrome and print to PDF.",
                html_path,
            )
            return html_path


def render_html_only(
    context: Dict[str, Any],
    output_path: Path,
    template_name: str = "research_note.html.j2",
    templates_dir: Path = TEMPLATES_DIR,
) -> Path:
    """Always write as standalone HTML (interactive, no WeasyPrint needed)."""
    output_path = Path(output_path).with_suffix(".html")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html_str = render_html_report(context, template_name, templates_dir)
    output_path.write_text(html_str, encoding="utf-8")
    logger.info("HTML report written: %s", output_path)
    return output_path
