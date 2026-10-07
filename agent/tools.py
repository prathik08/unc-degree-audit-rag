"""Structured functions Claude calls via tool use for anything requiring
exact logic over the scraped data - as opposed to the RAG layer in rag/,
which handles fuzzy natural-language questions over course descriptions and
policy text.

Division of labor, and why: missing_requirements() only needs a major's
required-course list (data/majors/<slug>.json), which comes from a clean
HTML table - alternatives ("COMP 283 or MATH 381") are structured data there,
so this function's answer is exact.

eligible_next_courses() is different: a course's prerequisites
(data/courses/<dept>.json -> requisite_codes) come from free catalog prose
("Prerequisite, X and Y; Pre- or corequisite, A or B") whose AND/OR structure
is NOT reliably parseable - the same "Prerequisite," label phrasing is used
inconsistently across courses (confirmed by sampling COMP course pages).
Rather than hand-parse that English and risk a confidently wrong answer, this
function reports a conservative `prereqs_definitely_met` (true only if every
mentioned course is completed - never a false positive, can be a false
negative on "or" chains) and returns the raw `requisites_text` alongside it -
Claude reads that text and makes the final call on ambiguous cases, which is
what it's good at and hand-rolled parsing isn't.
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"


def _normalize(code: str) -> str:
    return code.replace("\xa0", " ").strip().upper()


def _load_major(major_slug: str) -> dict:
    path = DATA_DIR / "majors" / f"{major_slug}.json"
    if not path.exists():
        raise ValueError(f"No scraped data for major '{major_slug}' at {path}")
    return json.loads(path.read_text())


def _load_all_courses() -> dict[str, dict]:
    """Course code -> course record, merged across every scraped department."""
    courses = {}
    for path in (DATA_DIR / "courses").glob("*.json"):
        for course in json.loads(path.read_text()):
            courses[_normalize(course["code"])] = course
    return courses


def missing_requirements(major_slug: str, completed_courses: list[str]) -> dict:
    """Compare a major's required sections against completed_courses.

    Two different kinds of requirement, checked differently:
    - `required_courses`: every one must be satisfied (course itself or any
      of its `alternatives`).
    - `choose_groups`: only `n` of the listed `options` are needed (e.g. "Two
      science courses chosen from: [14 options]") - reporting all 14 as
      individually required would be wrong, not just imprecise.

    Sections with prose-only electives (e.g. "5 COMP courses 420+", which
    has no explicit option list to check against) stay in `unverifiable_notes`
    so the caller surfaces them instead of silently dropping them."""
    major = _load_major(major_slug)
    completed = {_normalize(c) for c in completed_courses}

    sections_out = []
    for section in major["sections"]:
        missing, satisfied = [], []
        for course in section["required_courses"]:
            codes = {_normalize(course["code"])} | {
                _normalize(alt["code"]) for alt in course["alternatives"]
            }
            (satisfied if codes & completed else missing).append(course["code"])

        choose_groups_out = []
        for group in section["choose_groups"]:
            option_codes = [o["code"] for o in group["options"]]
            satisfied_options = [c for c in option_codes if _normalize(c) in completed]
            choose_groups_out.append(
                {
                    "description": group["trigger_text"],
                    "required_count": group["n"],
                    "satisfied_options": satisfied_options,
                    "remaining_options": [c for c in option_codes if c not in satisfied_options],
                    "met": len(satisfied_options) >= group["n"],
                    "unverifiable_notes": group["notes"],
                }
            )

        sections_out.append(
            {
                "name": section["name"],
                "missing": missing,
                "satisfied": satisfied,
                "choose_groups": choose_groups_out,
                "unverifiable_notes": section["notes"],
            }
        )

    return {
        "major": major["major"],
        "total_hours": major["total_hours"],
        "sections": sections_out,
    }


def _check_prereqs(code: str, section_name: str, completed: set[str], all_courses: dict) -> dict:
    course = all_courses.get(_normalize(code))
    if course is None:
        return {
            "code": code,
            "section": section_name,
            "prereqs_definitely_met": None,
            "requisites_text": None,
            "note": "course not found in scraped department data",
        }

    requisite_codes = {_normalize(c) for c in course["requisite_codes"]}
    return {
        "code": code,
        "section": section_name,
        "prereqs_definitely_met": requisite_codes <= completed,
        "requisites_text": course["requisites_text"],
    }


def eligible_next_courses(major_slug: str, completed_courses: list[str]) -> list[dict]:
    """For each still-missing required course, and each remaining option in
    an unmet choose_group, look up its prerequisites and report whether
    they're conservatively satisfied. See module docstring for why this is
    conservative rather than exact."""
    audit = missing_requirements(major_slug, completed_courses)
    completed = {_normalize(c) for c in completed_courses}
    all_courses = _load_all_courses()

    results = []
    for section in audit["sections"]:
        for code in section["missing"]:
            results.append(_check_prereqs(code, section["name"], completed, all_courses))
        for group in section["choose_groups"]:
            if group["met"]:
                continue
            for code in group["remaining_options"]:
                result = _check_prereqs(code, section["name"], completed, all_courses)
                result["choose_group"] = group["description"]
                results.append(result)

    return results
