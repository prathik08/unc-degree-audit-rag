"""Runs the requirement-lookup eval: calls the real entry point
(agent.claude_agent.ask) for every case in eval/cases.json, grades each
answer (eval/grade.py), and writes results in the shape
shared/evals/report/SCHEMA.md and build-report-lite.mjs expect.

Output: .claude/hillclimb/requirement-lookup/baseline/
  results.jsonl   - one row per case, written as it completes (resumable)
  traces/<id>_rep0.json - full conversation per case
  errors.jsonl    - failed attempts (timeout, API error) - never in results.jsonl

No harness-integrity gate here (the scaffold's sha-over-runner-file +
--approve-harness check): that machinery exists to stop an autonomous
hillclimb loop from silently rewriting its own runner between rounds.
This is a baseline-only, human-run build with no loop yet - add it if/when
/claude-api hillclimb starts iterating on this flow.

Usage: python -m eval.run_eval (run from the project root)
"""

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.claude_agent import PRICING, ask
from eval.grade import JUDGE_MODEL, grade

FLOW_DIR = Path(__file__).parent.parent / ".claude" / "hillclimb" / "requirement-lookup"
BASELINE_DIR = FLOW_DIR / "baseline"
CASE_WALL_CLOCK_CEILING_S = 90


def load_existing_ids(results_path: Path) -> set[str]:
    if not results_path.exists():
        return set()
    ids = set()
    for line in results_path.read_text().splitlines():
        if line.strip():
            ids.add(json.loads(line)["prompt_id"])
    return ids


def run_case(case: dict) -> dict:
    start = time.time()
    result = ask(case["question"], case["major_slug"], case["completed_courses"])
    elapsed_s = time.time() - start

    scores = grade(case, result["answer"])
    scores["called_correct_tool"] = 1 if "check_missing_requirements" in result["tool_calls"] else 0

    # Judge spend is invisible unless added explicitly - cost_usd otherwise
    # only reflects the main agent call, silently undercounting the real
    # per-case cost whenever a judge call happened (per build-eval.md's own
    # warning: "up to half the real cost is invisible" if this is skipped).
    judge_usage = scores.get("_judge_usage")
    judge_cost = 0.0
    if judge_usage:
        price = PRICING[JUDGE_MODEL]
        judge_cost = (judge_usage["input_tokens"] / 1_000_000) * price["input"] + (
            judge_usage["output_tokens"] / 1_000_000
        ) * price["output"]

    row = {
        "prompt_id": case["id"],
        "prompt": case["question"],
        "tags": case["tags"],
        "meta": {"major_slug": case["major_slug"], "completed_courses": case["completed_courses"]},
        "status": "truncated" if result["stop_reason"] == "max_tokens" else "ok",
        "model": result["model"],
        "grade": {k: v for k, v in scores.items() if not k.startswith("_")},
        "explanation": {"choose_group_framing": scores["_judge_reasoning"]} if "_judge_reasoning" in scores else {},
        "perf": {
            "cost_usd": result["cost_usd"] + judge_cost,
            "latency_s": elapsed_s,
            "tool_calls": len(result["tool_calls"]),
        },
    }
    return row, result["trace"]


def main() -> None:
    cases = json.loads((Path(__file__).parent / "cases.json").read_text())
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    (BASELINE_DIR / "traces").mkdir(exist_ok=True)
    results_path = BASELINE_DIR / "results.jsonl"
    errors_path = BASELINE_DIR / "errors.jsonl"

    already_done = load_existing_ids(results_path)
    todo = [c for c in cases if c["id"] not in already_done]
    print(f"{len(already_done)} cases already done, {len(todo)} to run")

    with results_path.open("a") as results_f, errors_path.open("a") as errors_f:
        for i, case in enumerate(todo, 1):
            print(f"[{i}/{len(todo)}] {case['id']}...", end=" ", flush=True)
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_case, case)
                try:
                    row, trace = future.result(timeout=CASE_WALL_CLOCK_CEILING_S)
                except FutureTimeoutError:
                    errors_f.write(json.dumps({
                        "prompt_id": case["id"], "failure_class": "timeout",
                        "note": f"exceeded {CASE_WALL_CLOCK_CEILING_S}s wall-clock ceiling",
                    }) + "\n")
                    errors_f.flush()
                    print("TIMEOUT")
                    continue
                except Exception as exc:
                    errors_f.write(json.dumps({
                        "prompt_id": case["id"], "failure_class": "harness_or_api_error",
                        "note": str(exc),
                    }) + "\n")
                    errors_f.flush()
                    print(f"ERROR: {exc}")
                    continue

            results_f.write(json.dumps(row) + "\n")
            results_f.flush()
            (BASELINE_DIR / "traces" / f"{case['id']}_rep0.json").write_text(json.dumps(trace, indent=2))
            print(f"ok  grade={row['grade']}  ${row['perf']['cost_usd']:.4f}  {row['perf']['latency_s']:.1f}s")

    print(f"\nDone. Results: {results_path}")


if __name__ == "__main__":
    main()
