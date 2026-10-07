"""Parses a UNC department course-listing page (catalog.unc.edu/courses/<dept>/)
into structured JSON: one entry per course with code, title, credit hours,
description, and prerequisite info.

Known limitation (v0): `requisite_codes` is a flat list of every course code
mentioned in the "Requisites:" line - it does not yet distinguish prerequisite
vs. corequisite, or AND vs. OR between alternatives (that logic lives in the
raw `requisites_text` for now, for a human - or a later Claude tool-use call -
to interpret). Good enough for "what feeds into this course" style questions
and for eligible_next_courses() to check "have they taken at least one
mentioned course", but not for exact eligibility logic yet.
"""

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

from scraper.fetch import fetch


def _parse_course_block(block) -> dict | None:
    code_el = block.find(class_="detail-code")
    title_el = block.find(class_="detail-title")
    hours_el = block.find(class_="detail-hours")
    if not code_el or not title_el:
        return None

    code = code_el.get_text(strip=True).rstrip(".").replace("\xa0", " ")
    title = title_el.get_text(strip=True).rstrip(".")

    hours_text = hours_el.get_text(strip=True) if hours_el else ""
    hours_match = re.search(r"[\d.]+", hours_text)
    credits = float(hours_match.group()) if hours_match else None

    desc_el = block.find(class_="courseblockextra")
    description = desc_el.get_text(" ", strip=True) if desc_el else ""

    req_el = block.find(class_="detail-requisites")
    requisites_text = ""
    requisite_codes: list[str] = []
    if req_el:
        text = req_el.get_text(" ", strip=True)
        requisites_text = re.sub(r"^Requisites:\s*", "", text).strip()
        # Use the `title` attribute, not the link text - catalog prose
        # abbreviates runs like "MATH 130, 152, 210" to bare numbers after
        # the first mention, but `title` always carries the full code.
        requisite_codes = [
            a.get("title", a.get_text(strip=True)).replace("\xa0", " ")
            for a in req_el.find_all("a", class_="code")
        ]

    return {
        "code": code,
        "title": title,
        "credits": credits,
        "description": description,
        "requisites_text": requisites_text,
        "requisite_codes": requisite_codes,
    }


def parse_department_page(url: str) -> list[dict]:
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")

    courses = []
    for block in soup.find_all("div", class_="courseblock"):
        parsed = _parse_course_block(block)
        if parsed:
            courses.append(parsed)
    return courses


def save_department(url: str, out_dir: Path) -> Path:
    courses = parse_department_page(url)
    slug = url.rstrip("/").split("/")[-1]
    out_path = out_dir / f"{slug}.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(courses, indent=2))
    return out_path
