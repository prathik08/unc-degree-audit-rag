"""Grades one case's agent.claude_agent.ask() output against its computed
expected ground truth (eval/cases.json).

Two graders, per the hybrid design signed off on:
- Programmatic (free, deterministic): regex-extracts course codes from the
  answer and set-compares them against the case's known data. Catches
  "did it mention the missing courses" (recall) and "did it invent a code
  that isn't real for this case" (hallucination) - both are exact-match
  problems, not judgment calls.
- Judge (Haiku 4.5, only called when the case has a choose_group): checks
  the one thing regex can't reliably catch - whether "choose N from M
  options" is correctly framed as a group requirement, or flattened into
  M individually-"missing" courses. This is literally the bug class found
  and fixed in agent/tools.py before this eval existed; it's the reason
  this eval exists.
"""

import json
import os
import re

from anthropic import Anthropic
from pydantic import BaseModel

JUDGE_MODEL = "claude-haiku-4-5"

# Course codes look like "COMP 211", "BIOL 101&101L", "MATH 129P" - two to
# five letters, a number, optional trailing letter(s), optionally paired
# with a second number for a lab code joined by "&". The "&" gets optional
# spacing on both sides - found via a real false positive: Haiku wrote
# "BIOL 101 & 101L" (spaced), which split into a non-matching partial code
# and triggered both a false hallucination flag and a wrong recall count.
CODE_RE = re.compile(r"\b([A-Z]{2,5})\s?(\d{2,3}[A-Z]{0,2})(?:\s?&\s?(\d{2,3}[A-Z]{0,2}))?\b")


def extract_codes(text: str) -> set[str]:
    codes = set()
    for dept, num, lab_num in CODE_RE.findall(text):
        code = f"{dept} {num}"
        if lab_num:
            code += f"&{lab_num}"
        codes.add(code)
    return codes


def _all_section_codes(expected: dict) -> set[str]:
    """Every course code that's legitimately groundable in this case's data -
    including codes mentioned only in prose notes (e.g. "excluding COMP 496
    and COMP 692H" in an unverifiable_notes string). Found via a real false
    positive: Haiku correctly quoted an exclusion clause from the catalog's
    own note text, and the grader flagged it as a hallucination because
    "mentioned in a note" wasn't in the known universe - a grader bug, not
    a model error. Caught by eyeballing the first pilot row, which is
    exactly why the guide says to read the row before trusting the number."""
    codes = set()
    for section in expected["sections"]:
        codes.update(section["missing"])
        codes.update(section["satisfied"])
        for note in section["unverifiable_notes"]:
            codes.update(extract_codes(note))
        for group in section["choose_groups"]:
            codes.update(group["satisfied_options"])
            codes.update(group["remaining_options"])
            for note in group["unverifiable_notes"]:
                codes.update(extract_codes(note))
    return codes


def _expected_missing_required(expected: dict) -> set[str]:
    return {code for section in expected["sections"] for code in section["missing"]}


def grade_programmatic(case: dict, answer: str) -> dict:
    mentioned = extract_codes(answer)
    expected = case["expected"]

    known_universe = (
        set(case["completed_courses"]) | _all_section_codes(expected)
    )
    expected_missing = _expected_missing_required(expected)

    recall = (
        len(mentioned & expected_missing) / len(expected_missing)
        if expected_missing
        else 1.0
    )
    hallucinated = mentioned - known_universe

    return {
        "missing_recall": recall,
        "no_hallucination": 0 if hallucinated else 1,
        "_hallucinated_codes": sorted(hallucinated),  # debugging aid, not a metric
    }


class ChooseGroupJudgment(BaseModel):
    correctly_framed: bool
    reasoning: str


JUDGE_PROMPT = """A student asked a degree-audit assistant: "{question}"

The assistant answered:
---
{answer}
---

This major has the following "choose N from a list" requirements, where \
only N of the listed options are needed - NOT all of them:

{groups_text}

Does the answer correctly communicate this "choose N" framing for every \
group above (e.g. "you need 2 more science courses, choose from: ...", \
"pick one of these three"), rather than listing some or all of a group's \
options as if each were individually required/missing? The answer does \
not need to mention every single option in a group - judge only whether \
the courses it does mention from a group are framed as a choice, not as \
individually mandatory requirements."""


def grade_choose_group_framing(case: dict, answer: str) -> dict:
    groups = [
        group
        for section in case["expected"]["sections"]
        for group in section["choose_groups"]
    ]
    if not groups:
        return {"choose_group_framing": 1, "_judge_reasoning": "no choose_groups in this case"}

    groups_text = "\n".join(
        f"- \"{g['description']}\" - need {g['required_count']}, options: "
        f"{', '.join(g['satisfied_options'] + g['remaining_options'])}"
        for g in groups
    )

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.parse(
        model=JUDGE_MODEL,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": JUDGE_PROMPT.format(
                    question=case["question"], answer=answer, groups_text=groups_text
                ),
            }
        ],
        output_format=ChooseGroupJudgment,
    )
    judgment = response.parsed_output
    return {
        "choose_group_framing": 1 if judgment.correctly_framed else 0,
        "_judge_reasoning": judgment.reasoning,
        "_judge_usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    }


def grade(case: dict, answer: str) -> dict:
    prog = grade_programmatic(case, answer)
    judge = grade_choose_group_framing(case, answer)
    return {**prog, **judge}
