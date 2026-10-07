"""Parses a UNC policy/explainer page (e.g. catalog.unc.edu/undergraduate/ideas-in-action/,
the general-education requirements page) into heading-delimited text chunks
for RAG - this is prose, not the structured major/course-list format, so
there's nothing to extract into exact fields; chunking by heading (h2/h3)
keeps each chunk topically coherent instead of splitting mid-explanation.

These pages sometimes embed a `table.sc_courselist` (the same format
major_parser.py parses) as a plain summary table - e.g. gen-ed's "Focus
Capacity" category names ("Power and Society", "Quantitative Reasoning", ...)
with no course list attached (the actual approved courses live on a separate
interactive tool, not scraped here). Gluing that whole table into one text
blob buried each category name in one large chunk, diluting its embedding -
confirmed empirically: "what counts as a social science gen-ed" retrieved
random Psychology courses instead of the "Power and Society" category
because that name was mixed into 2600+ characters of unrelated categories.
Splitting the table by row (grouped under its area-header) fixes that.

Not the same problem as major_parser.py's course-list tables generally: a
policy page answers "what does this requirement mean" (semantic search's
job), not "does completed_courses satisfy requirement X" (exact logic's
job) - see agent/tools.py's docstring for that distinction.
"""

import json
from pathlib import Path

from bs4 import BeautifulSoup

from scraper.fetch import fetch

HEADING_TAGS = {"h2", "h3"}


def _table_row_chunks(table, page_heading: str, url: str) -> list[dict]:
    chunks = []
    area = None
    for row in table.find_all("tr"):
        classes = row.get("class", [])
        if "hidden" in classes:
            continue
        text = row.get_text(" ", strip=True)
        if not text:
            continue
        if "areaheader" in classes:
            area = text
            continue
        heading = f"{page_heading} > {area}" if area else page_heading
        chunks.append({"heading": heading, "text": text, "url": url})
    return chunks


def parse_policy_page(url: str) -> list[dict]:
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")

    main = soup.find("div", id="textcontainer") or soup.find("main") or soup
    title_el = soup.find("h1")
    page_title = title_el.get_text(strip=True) if title_el else url

    chunks = []
    current_heading = page_title
    current_text: list[str] = []

    def flush():
        text = " ".join(current_text).strip()
        if text:
            chunks.append({"heading": current_heading, "text": text, "url": url})

    for el in main.find_all(recursive=False):
        if el.name in HEADING_TAGS:
            flush()
            current_heading = el.get_text(" ", strip=True)
            current_text = []
        elif el.name == "table" and "sc_courselist" in (el.get("class") or []):
            flush()
            chunks.extend(_table_row_chunks(el, current_heading, url))
            current_text = []
        else:
            current_text.append(el.get_text(" ", strip=True))
    flush()

    return chunks


def save_policy_page(url: str, out_dir: Path, slug: str) -> Path:
    chunks = parse_policy_page(url)
    out_path = out_dir / f"{slug}.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(chunks, indent=2))
    return out_path
