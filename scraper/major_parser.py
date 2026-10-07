"""Parses a UNC major-requirements page (catalog.unc.edu/undergraduate/programs-study/<slug>/)
into structured JSON.

These pages use CourseLeaf's `table.sc_courselist` format: section header rows
(class="areaheader"), course rows, and "orclass" rows that are an alternative
to the row directly above them. This format is shared across UNC majors (and
many other CourseLeaf-catalog schools), so this parser is not CS-specific.

Each section splits courses into two kinds, because treating them the same
was a real bug: `required_courses` (must all be satisfied) vs. `choose_groups`
(pick N from a listed set - e.g. "Two science courses chosen from: [14
options]" only requires 2, not all 14). Sampled across 5 majors in different
departments, "choose N" buckets are introduced by prose matching one of
CHOOSE_TRIGGER_RE's patterns ("chosen from", "select N of the following",
"a choice of N ... selected from") - detected via a spelled-out number word
("two", "three", ...) since the digits near these notes are usually a
footnote marker or hour total, not the count.

Known limitation (still unsolved, v0): elective buckets described as a
*rule* rather than a list (e.g. "five additional COMP courses numbered 420
or higher") have no explicit candidates to capture - they stay in a
section's `notes` as raw text. Checking those needs a numeric/department
rule matcher, not a course list - a different problem than choose_groups.
"""

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from scraper.fetch import fetch

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
CHOOSE_TRIGGER_RE = re.compile(r"chosen from|of the following|selected from", re.IGNORECASE)


def _clean_code(text: str) -> str:
    return text.replace("\xa0", " ").strip()


def _extract_choose_n(note_text: str) -> int | None:
    if not CHOOSE_TRIGGER_RE.search(note_text):
        return None
    for word, n in NUMBER_WORDS.items():
        if re.search(rf"\b{word}\b", note_text, re.IGNORECASE):
            return n
    match = re.search(r"\b(\d+)\b", note_text)
    return int(match.group(1)) if match else None


def _row_course(row) -> dict | None:
    """Extract (code, title, hours) from a normal or orclass course row."""
    tds = row.find_all("td")
    if len(tds) < 2:
        return None

    code_cell = tds[0]
    for sup in code_cell.find_all("sup"):
        sup.decompose()
    code = _clean_code(code_cell.get_text(strip=True))
    code = re.sub(r"^or", "", code)  # orclass rows prefix the code with "or"
    if not code:
        return None

    title_cell = tds[1]
    for sup in title_cell.find_all("sup"):
        sup.decompose()
    title = title_cell.get_text(" ", strip=True)

    hours_text = tds[2].get_text(strip=True) if len(tds) > 2 else ""
    hours = float(hours_text) if re.fullmatch(r"\d+(\.\d+)?", hours_text) else None

    return {"code": code, "title": title, "hours": hours, "alternatives": []}


def parse_major_page(url: str) -> dict:
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.find("h1", class_="page-title") or soup.find("h1")
    major_name = title_el.get_text(strip=True) if title_el else url

    table = soup.find("table", class_="sc_courselist")
    sections: list[dict] = []
    current_section = None
    active_group = None  # the choose_group new course rows should join, if any
    total_hours = None

    def ensure_section():
        nonlocal current_section
        if current_section is None:
            current_section = {
                "name": "Requirements", "required_courses": [], "choose_groups": [], "notes": [],
            }
            sections.append(current_section)
        return current_section

    if table:
        for row in table.find_all("tr"):
            classes = row.get("class", [])
            if "hidden" in classes:
                continue

            tds = row.find_all("td")
            is_header_row = bool(tds) and tds[0].get("colspan") is not None

            if is_header_row:
                header_text = row.get_text(" ", strip=True)
                if "total hours" in header_text.lower():
                    match = re.search(r"[\d.]+\s*$", header_text)
                    total_hours = float(match.group()) if match else None
                    continue

                if "areaheader" in classes:
                    # A genuine new section (e.g. "Core Requirements").
                    current_section = {
                        "name": header_text, "required_courses": [], "choose_groups": [], "notes": [],
                    }
                    sections.append(current_section)
                    active_group = None
                    continue

                section = ensure_section()
                choose_n = _extract_choose_n(header_text)
                if choose_n is not None:
                    # Starts (or replaces) the bucket that following course
                    # rows join, e.g. "Two science courses chosen from:".
                    active_group = {"n": choose_n, "trigger_text": header_text, "options": [], "notes": []}
                    section["choose_groups"].append(active_group)
                elif active_group is not None:
                    # Prose while a group is open (e.g. the ASTR alternatives
                    # line) - keep it visible on the group rather than
                    # silently ending the group or dropping it.
                    active_group["notes"].append(header_text)
                else:
                    section["notes"].append(header_text)
                continue

            section = ensure_section()
            entry = _row_course(row)
            if entry is None:
                continue

            target_list = active_group["options"] if active_group is not None else section["required_courses"]
            if "orclass" in classes and target_list:
                target_list[-1]["alternatives"].append({"code": entry["code"], "title": entry["title"]})
            else:
                target_list.append(entry)

    return {
        "major": major_name,
        "url": url,
        "total_hours": total_hours,
        "sections": sections,
    }


def save_major(url: str, out_dir: Path, slug: str) -> Path:
    """`slug` is the registry key from scraper/majors.py (e.g.
    "computer-science-bs"), not derived from the URL, so tools.py can look
    up data/majors/<slug>.json by the same key used everywhere else."""
    data = parse_major_page(url)
    out_path = out_dir / f"{slug}.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2))
    return out_path
