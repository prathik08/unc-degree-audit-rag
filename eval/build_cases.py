"""Builds eval/cases.json for the requirement-lookup flow
(agent.claude_agent.ask() questions like "what am I missing for my major").

Each case's `expected` field is computed from agent.tools.missing_requirements()
- the same ground-truth function the app itself uses - not hand-typed, so it's
guaranteed consistent with what the structured layer actually produces.

Usage: python -m eval.build_cases (run from the project root)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent import tools

CASES = [
    # --- Computer Science ---
    {"id": "cs_freshman", "tags": ["requirement_lookup", "cs", "zero_progress"],
     "major_slug": "computer-science-bs", "completed_courses": [],
     "question": "What am I missing for my major?"},
    {"id": "cs_partial", "tags": ["requirement_lookup", "cs", "partial_progress"],
     "major_slug": "computer-science-bs", "completed_courses": ["COMP 110", "COMP 210", "MATH 231", "MATH 232"],
     "question": "What do I still need to graduate?"},
    {"id": "cs_alternative_satisfied", "tags": ["requirement_lookup", "cs", "alternatives"],
     "major_slug": "computer-science-bs", "completed_courses": ["COMP 110", "COMP 210", "STOR 315", "MATH 231"],
     "question": "Have I completed the discrete math requirement?"},
    {"id": "cs_choose_group_partial", "tags": ["requirement_lookup", "cs", "choose_group_partial"],
     "major_slug": "computer-science-bs",
     "completed_courses": ["COMP 110", "COMP 210", "COMP 211", "COMP 283", "COMP 301", "COMP 311",
                            "COMP 455", "COMP 550", "MATH 231", "MATH 232", "MATH 233", "MATH 347",
                            "STOR 435", "BIOL 101&101L"],
     "question": "Am I done with my science requirement?"},

    # --- Psychology ---
    {"id": "psyc_freshman", "tags": ["requirement_lookup", "psychology", "zero_progress"],
     "major_slug": "psychology-ba", "completed_courses": [],
     "question": "What am I missing for my major?"},
    {"id": "psyc_partial", "tags": ["requirement_lookup", "psychology", "partial_progress"],
     "major_slug": "psychology-ba", "completed_courses": ["PSYC 101", "PSYC 210", "PSYC 270"],
     "question": "What do I still need to graduate?"},
    {"id": "psyc_duplicate_requirement", "tags": ["requirement_lookup", "psychology", "data_quirk"],
     "major_slug": "psychology-ba", "completed_courses": ["PSYC 101", "NSCI 225"],
     "question": "Have I satisfied the NSCI 225 requirement?"},

    # --- Biology ---
    {"id": "bio_freshman", "tags": ["requirement_lookup", "biology", "zero_progress", "data_quirk"],
     "major_slug": "biology-bs", "completed_courses": [],
     "question": "What am I missing for my major?"},
    {"id": "bio_partial", "tags": ["requirement_lookup", "biology", "partial_progress"],
     "major_slug": "biology-bs", "completed_courses": ["BIOL 101&101L", "BIOL 103", "BIOL 104", "BIOL 105L", "CHEM 101&101L"],
     "question": "What do I still need to graduate?"},
    {"id": "bio_choose_group_partial", "tags": ["requirement_lookup", "biology", "choose_group_partial"],
     "major_slug": "biology-bs",
     "completed_courses": ["BIOL 101&101L", "BIOL 103", "BIOL 104", "BIOL 105L", "BIOL 220",
                            "BIOL 240", "BIOL 250", "BIOL 260", "CHEM 101&101L", "CHEM 102&102L",
                            "CHEM 261", "MATH 231", "MATH 232"],
     "question": "What's left for me to finish the major?"},

    # --- Economics ---
    {"id": "econ_freshman", "tags": ["requirement_lookup", "economics", "zero_progress"],
     "major_slug": "economics-bs", "completed_courses": [],
     "question": "What am I missing for my major?"},
    {"id": "econ_partial", "tags": ["requirement_lookup", "economics", "partial_progress"],
     "major_slug": "economics-bs", "completed_courses": ["ECON 101", "ECON 400", "MATH 231", "MATH 232"],
     "question": "What do I still need to graduate?"},
    {"id": "econ_choose_group_partial", "tags": ["requirement_lookup", "economics", "choose_group_partial"],
     "major_slug": "economics-bs",
     "completed_courses": ["ECON 101", "ECON 400", "ECON 410", "ECON 420", "ECON 470",
                            "MATH 231", "MATH 232", "MATH 233", "COMP 110"],
     "question": "Am I done with my electives requirement?"},

    # --- Political Science ---
    {"id": "poli_freshman", "tags": ["requirement_lookup", "political_science", "zero_progress"],
     "major_slug": "political-science-ba", "completed_courses": [],
     "question": "What am I missing for my major?"},
    {"id": "poli_one_group_satisfied", "tags": ["requirement_lookup", "political_science", "choose_group_partial"],
     "major_slug": "political-science-ba", "completed_courses": ["POLI 100", "POLI 150", "POLI 130"],
     "question": "What do I still need to graduate?"},
    {"id": "poli_two_groups_satisfied", "tags": ["requirement_lookup", "political_science", "choose_group_partial"],
     "major_slug": "political-science-ba",
     "completed_courses": ["POLI 100", "POLI 150", "POLI 130", "POLI 265"],
     "question": "How close am I to finishing my major requirements?"},
    {"id": "poli_near_complete", "tags": ["requirement_lookup", "political_science", "near_complete"],
     "major_slug": "political-science-ba",
     "completed_courses": ["POLI 100", "POLI 150", "POLI 130", "POLI 265", "POLI 209"],
     "question": "Am I done with my major requirements?"},
]


def main() -> None:
    for case in CASES:
        case["expected"] = tools.missing_requirements(case["major_slug"], case["completed_courses"])

    out_path = Path(__file__).parent / "cases.json"
    out_path.write_text(json.dumps(CASES, indent=2))
    print(f"Wrote {len(CASES)} cases to {out_path}")


if __name__ == "__main__":
    main()
