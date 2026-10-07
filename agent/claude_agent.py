"""Wires Claude to the structured functions (agent/tools.py) and RAG search
(rag/retrieve.py) via tool use, and answers a student's question.

The major/completed-courses tools take no LLM-supplied arguments - they're
closures over the actual values passed into ask(), not parameters Claude
fills in. That's deliberate: letting Claude supply "the student's completed
courses" as a tool argument would let it hallucinate or misremember that
data instead of it coming from the real source of truth.

ask() returns a dict, not a bare string - {"answer", "model", "input_tokens",
"output_tokens", "cost_usd", "elapsed_s", "tool_calls", "stop_reason"} - so
callers (the Streamlit UI, the eval runner) can show which model answered,
what it actually cost, which tools it used, and whether it got cut off -
using real numbers from the response itself rather than an estimate.
"""

import json
import os
import time

from anthropic import Anthropic, beta_tool
from dotenv import load_dotenv

load_dotenv()

from agent import tools
from rag.retrieve import search as rag_search

MODEL_DEFAULT = "claude-haiku-4-5"
MODEL_ELIGIBILITY = "claude-sonnet-5"

# $/1M tokens, current as of this project's build - update if pricing changes.
PRICING = {
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "claude-sonnet-5": {"input": 2.00, "output": 10.00},
}

# Measured side-by-side on real questions before adding this: on ambiguous
# OR-prereq eligibility reasoning, Sonnet gave a resolved, concrete answer
# ("you have COMP 210 but not COMP 283, so these stay blocked") where Haiku
# hedged vaguely without actually resolving the logic - a real quality gap,
# not a hypothetical one. On straightforward requirement-listing questions
# the two were equivalent, so Haiku stays the default (Sonnet ran ~3-4x more
# expensive and ~2x slower in that same test, not just the 2x per-token
# price difference - it also wrote longer answers).
#
# The model has to be picked before the conversation starts (the tool
# runner doesn't support switching models mid-run), so which question needs
# the stronger model is decided by keyword match, not by which tool Claude
# actually ends up calling. That's a real limitation - unusual phrasings
# ("am I ready for the next class") can miss this list and fall through to
# Haiku - but it's zero extra cost/latency versus a pre-classification call,
# which was the explicit tradeoff made here.
ELIGIBILITY_KEYWORDS = (
    "next semester", "next course", "next class", "what can i take",
    "what should i take", "eligible", "eligibility", "can i take", "ready for",
)


def _needs_eligibility_reasoning(question: str) -> bool:
    lowered = question.lower()
    return any(keyword in lowered for keyword in ELIGIBILITY_KEYWORDS)


SYSTEM_PROMPT = """You are a UNC Chapel Hill degree-planning assistant for a \
specific student in the {major_slug} major.

Use check_missing_requirements and check_eligible_next_courses for anything \
about degree requirements or what to take next - they run exact logic over \
the real catalog, don't reason about this yourself. Their eligibility check \
is conservative: `prereqs_definitely_met: false` can mean "not actually met" \
OR "met via an 'or' alternative the tool couldn't verify automatically" - \
read the accompanying `requisites_text` yourself to tell which, and say so \
in your answer if it's ambiguous rather than guessing.

Use search_courses for open-ended questions about course content or topics \
(e.g. "what's a good course about X"), not for requirement/prereq questions.

Always cite specific course codes. If a bucket of electives has no \
structured course list (only a text note), say so explicitly rather than \
inventing which courses satisfy it. When listing more than a handful of \
courses, use a markdown table (columns: Code, Status/Notes) instead of a \
bullet list - it's easier to scan."""


def _pretty(value) -> str:
    try:
        return json.dumps(json.loads(value) if isinstance(value, str) else value, indent=2)
    except (TypeError, ValueError):
        return str(value)


def _build_trace(system_prompt: str, runner_messages: list, final_message) -> list[dict]:
    """Reconstructs the conversation as the Turn[] list the eval report
    schema expects (shared/evals/report/SCHEMA.md). Built from the tool
    runner's own internal message history - see the "no public API for
    this" note on `tool_calls` above; same caveat applies here."""
    turns = [{"role": "system", "content": system_prompt}]

    for message in runner_messages:
        content = message["content"]
        if isinstance(content, str):
            turns.append({"role": message["role"], "content": content})
            continue
        for block in content:
            block_type = block.type if hasattr(block, "type") else block.get("type")
            if block_type == "text":
                text = block.text if hasattr(block, "text") else block["text"]
                turns.append({"role": "assistant", "content": text})
            elif block_type == "tool_use":
                name = block.name if hasattr(block, "name") else block["name"]
                tool_input = block.input if hasattr(block, "input") else block["input"]
                turns.append({"role": "tool_call", "name": name, "content": _pretty(tool_input)})
            elif block_type == "tool_result":
                result = block["content"] if isinstance(block, dict) else block.content
                turns.append({"role": "tool_result", "content": _pretty(result)})

    final_text = "".join(b.text for b in final_message.content if b.type == "text")
    if final_text:
        turns.append({"role": "assistant", "content": final_text})
    return turns


def ask(question: str, major_slug: str, completed_courses: list[str]) -> dict:
    # beta_tool functions must return str (or content blocks) - not a raw
    # dict/list - so every tool below JSON-encodes its result.

    @beta_tool
    def check_missing_requirements() -> str:
        """Return which of the student's major requirements are satisfied,
        missing, or unverifiable (prose-only elective buckets)."""
        return json.dumps(tools.missing_requirements(major_slug, completed_courses))

    @beta_tool
    def check_eligible_next_courses() -> str:
        """For each still-missing required course, report whether its
        prerequisites are conservatively satisfied, plus the raw
        prerequisite text for courses that need judgment."""
        return json.dumps(tools.eligible_next_courses(major_slug, completed_courses))

    @beta_tool
    def search_courses(question: str) -> str:
        """Semantic search over course descriptions for open-ended,
        non-requirement questions (e.g. course content/topic questions)."""
        return json.dumps(rag_search(question, k=5))

    model = MODEL_ELIGIBILITY if _needs_eligibility_reasoning(question) else MODEL_DEFAULT

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    start = time.time()
    runner = client.beta.messages.tool_runner(
        model=model,
        # 2048 was too low - confirmed by hitting stop_reason "max_tokens"
        # on a real question and getting a mid-sentence cutoff. Sonnet's
        # eligibility answers plus the markdown-table formatting nudge in
        # the system prompt both push output length up.
        max_tokens=4096,
        system=SYSTEM_PROMPT.format(major_slug=major_slug),
        tools=[check_missing_requirements, check_eligible_next_courses, search_courses],
        messages=[{"role": "user", "content": question}],
    )
    final_message = runner.until_done()
    elapsed_s = time.time() - start

    answer = "".join(block.text for block in final_message.content if block.type == "text")
    usage = final_message.usage
    price = PRICING[model]
    cost_usd = (usage.input_tokens / 1_000_000) * price["input"] + (
        usage.output_tokens / 1_000_000
    ) * price["output"]

    # The tool runner has no public API for "the full conversation" or
    # "which tools were called this run" - reading them off the runner's
    # own internal message history (an underscore-prefixed attribute, so
    # this could break on a future SDK version) is the only way to get
    # them without re-implementing the loop. Worth it here: eval grading
    # needs the trace and the tool-routing decision, not just the text.
    trace = _build_trace(
        SYSTEM_PROMPT.format(major_slug=major_slug), runner._params["messages"], final_message
    )
    tool_calls = [turn["name"] for turn in trace if turn["role"] == "tool_call"]

    return {
        "answer": answer,
        "model": model,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cost_usd": cost_usd,
        "elapsed_s": elapsed_s,
        "tool_calls": tool_calls,
        "trace": trace,
        "stop_reason": final_message.stop_reason,
    }
