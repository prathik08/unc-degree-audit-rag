# UNC Degree-Audit RAG

Ask natural-language questions about UNC Chapel Hill degree requirements and
prerequisite chains, grounded in the real catalog (catalog.unc.edu) plus your
own completed-courses list - e.g. "what am I missing for the CS major" or
"what can I take next semester."

**Stack:** Python · Streamlit · Anthropic Claude API (Haiku 4.5 / Sonnet 5) ·
ChromaDB + sentence-transformers · SQLite · BeautifulSoup

## Highlights

- **Hybrid architecture, not naive RAG.** Requirement checking is an
  exact-match problem (has the student taken the 7 required courses or not) -
  vector search handles that badly. Structured Python logic answers those
  questions exactly; RAG only handles genuinely fuzzy questions (course
  content, gen-ed policy text). See Architecture below.
- **Built and ran a real eval, not vibes.** 17 cases, hybrid programmatic +
  LLM-judge grading, and it caught a genuine model-quality bug: the app
  misidentified a course when asked a narrowly-phrased question, even though
  the correct answer was sitting in the tool response it had just read.
- **Measured a model-routing decision instead of guessing.** Side-by-side
  Haiku vs. Sonnet on real questions before picking a default - quantified
  the quality/cost/latency tradeoff (Sonnet ran ~3-4x the cost, ~2x the
  latency, with a real quality gain only on ambiguous reasoning questions)
  rather than assuming.
- **Parsed real, messy data into structure.** One scraper generalizes across
  5 majors in unrelated departments by reverse-engineering UNC's actual
  HTML template - 1,206 courses, zero manual data entry.
- **Full pipeline, not a notebook demo.** Scraping -> structured data ->
  vector index -> LLM tool-use orchestration -> persistent storage -> a
  polished multi-view UI.

## Architecture

This is not a plain RAG app. Requirement checking and prereq logic are
exact-match problems, which vector search handles badly. So:

- **Structured data** (`scraper/`) - scrapes catalog.unc.edu into JSON: major
  requirements (`data/majors/`) and course details + prerequisites
  (`data/courses/`).
- **Structured functions** (`agent/tools.py`) - exact logic over that JSON:
  what's missing, what's eligible next.
- **RAG** (`rag/`) - embeds course descriptions and policy text for fuzzy
  questions the structured data can't answer directly.
- **Claude + tool use** (`agent/`) - routes each question to the structured
  functions and/or RAG retrieval, then answers.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in ANTHROPIC_API_KEY
```

## Scraping the catalog

```bash
python3 -m scraper.run_scrape
```

Scrapes every major/department listed in `scraper/majors.py` into
`data/majors/*.json` and `data/courses/*.json`. Raw HTML is cached in
`data/raw/` (gitignored) so re-runs during development don't re-hit UNC's
servers.

To add a major: find its slug from its catalog.unc.edu URL and add it to
`MAJORS` in `scraper/majors.py`. To add a department's courses, verify the
slug first (`curl -s -o /dev/null -w "%{http_code}" catalog.unc.edu/courses/<slug>/`
should return 200 - department slugs don't always match the obvious
abbreviation, e.g. political science is `poli`, not `plsc`).

## Running the app

```bash
streamlit run app/streamlit_app.py
```

`app/streamlit_app.py` inserts the project root onto `sys.path` at the top of
the file before importing `agent`/`scraper` - Streamlit only auto-adds the
script's own directory (`app/`), not the project root, so without that line
the app fails immediately with `ModuleNotFoundError: No module named 'agent'`
regardless of what directory you run the command from. Found by actually
testing in a browser, not just checking the process started (an `HTTP 200`
from the server proved nothing here - the import error only shows up once the
page renders).

## Known limitations (v0 scraper)

- `requisite_codes` on a course is a flat list of every course code
  mentioned in its "Requisites:" text - it doesn't yet distinguish
  prerequisite vs. corequisite, or AND vs. OR between alternatives. The raw
  text is kept in `requisites_text` for now.
- Elective buckets described as a *rule* rather than a list (e.g. "five
  additional COMP courses numbered 420 or higher" - no explicit candidates
  to check against, just a department/number pattern) land in a section's
  `notes` field as raw text, not as a structured, checkable rule. (Buckets
  described as "choose N from this explicit list" - e.g. "two science
  courses chosen from: [14 options]" - *are* structured, as `choose_groups`;
  this only affects the rule-shaped ones with no list to check.)
- `requisite_codes` only catches course codes that are hyperlinked in UNC's
  HTML - occasionally a mentioned code isn't linked (seen on COMP 283's "MATH
  231 or MATH 241", where MATH 241 has no link) and is invisible to
  `eligible_next_courses()`'s check, though still present in the raw
  `requisites_text` it also returns.
- No rate limiting on the chat endpoint, and auth is a plain typed username
  with no password (see "Persistent conversation history" below) - this
  project stayed a local/personal deployment throughout and was never
  hardened for public hosting.

## Your own progress

Not scraped from any authenticated system (e.g. ConnectCarolina) - maintain
your completed courses yourself in a JSON file shaped like
`student_data/example_completed_courses.json`.

---

## Development log

The detailed build history below - what was built in what order, every real
bug found and how it was diagnosed, and the reasoning behind each design
decision. Kept in full rather than summarized, since the process (how a bug
was actually found and fixed) is more informative than just the outcome.

- [x] Week 1: catalog scraper (majors + department course pages), verified
      against 5 majors across different departments
- [x] Week 2a: structured functions (`agent/tools.py`) - `missing_requirements`
      and `eligible_next_courses`, tested against `student_data/example_completed_courses.json`
- [x] Week 2b: Chroma index over 1,206 courses (`rag/`), Claude tool-use wiring
      (`agent/claude_agent.py`, Haiku 4.5) - verified end-to-end on real
      requirement, eligibility, and fuzzy search questions
- [x] Week 3a: Streamlit UI (`app/streamlit_app.py`) - major picker,
      completed-courses input, multi-turn chat. Tested in a real browser
      (not just direct Python calls): golden path, follow-up questions,
      and "Clear chat" all verified working.
- [x] Week 3a-refine: searchable course multiselect (replaces typo-prone
      free text), a "Degree Audit" tab rendering `agent.tools.missing_requirements`
      directly - instant, no LLM call, no cost - with progress bars for
      choose_groups, plus visual polish (Carolina Blue theme, bordered
      sidebar sections, metrics). Verified in browser: multiselect
      filtering, the audit tab matches known-correct CLI-tested data, and
      the chat tab still works with no regression.
- [x] Model routing: measured Haiku 4.5 vs Sonnet 5 side-by-side on real
      questions before changing anything (not guessing) - on ambiguous
      OR-prereq eligibility reasoning, Sonnet gave a resolved, concrete
      answer where Haiku hedged without resolving the logic; on
      straightforward requirement-listing they were equivalent, and Sonnet
      ran ~3-4x more expensive, ~2x slower. Landed on a middle ground:
      Haiku by default, Sonnet only for questions matching eligibility
      keywords (`agent/claude_agent.py` - `ELIGIBILITY_KEYWORDS`). The
      model has to be picked before the tool-use loop starts, so this is a
      keyword match on the question text, not on which tool Claude actually
      calls - a real limitation (unusual phrasings can fall through to
      Haiku), traded deliberately against the cost/latency of an extra
      pre-classification call.
- [x] UI/UX polish round 2, all verified in browser:
      - Real UNC wordmark logo as branding (`app/assets/unc-logo.png`)
      - Example-prompt buttons on first load (click-to-ask, no typing needed)
      - Cost/model transparency: every chat answer shows which model
        answered and its real cost/latency (`agent/claude_agent.py`'s
        `ask()` now returns a dict with usage data, not a bare string)
      - Degree Audit tab renders proper tables (Code/Title/Status) instead
        of bullet lists
      - Found and fixed a real bug while testing this: `max_tokens=2048`
        was too low - a real question hit `stop_reason: "max_tokens"` and
        got cut off mid-sentence (Sonnet's answers plus the new
        markdown-table system-prompt nudge both push output length up).
        Bumped to 4096, confirmed fixed on the same question.
- [x] Week 3b: requirement-lookup eval (`eval/`) - 17 cases across all 5
      majors, ground truth computed from `agent.tools.missing_requirements`
      (not hand-typed), reviewed and signed off before grading was built.
      Hybrid grading: programmatic course-code precision/recall +
      hallucination check, plus a Haiku 4.5 judge for the one thing regex
      can't catch - whether "choose N from M" is correctly framed or
      flattened into individually-missing courses (the exact bug class
      fixed earlier in `agent/tools.py`). Full run: 17/17 called the right
      tool, 15/17 correct choose-group framing, mean missing-recall 0.95.
      Report: `.claude/hillclimb/requirement-lookup/report.html`.

  One real finding survived investigation, three others were chased down
  and ruled out as grading artifacts (not swept under the rug - documented
  so the numbers aren't taken at face value):
  - **Real bug, confirmed against the raw tool data**: asked "have I
    completed the discrete math requirement?", Haiku answered that MATH 232
    was missing and called it "Discrete Math" - MATH 232 is Calculus II,
    not discrete math, and the model ignored that COMP 283 (the actual
    discrete-structures-equivalent) was already satisfied via the STOR 315
    alternative in the same tool response it had just read. Narrow,
    naturally-phrased questions about a specific requirement are a weaker
    spot than direct "what's missing" questions - not reflected in the
    `cs_partial`/`cs_choose_group_partial` cases, which ask broadly.
  - **Grader artifact**: the course-code regex extracted "COMP 420" from
    "five COMP courses numbered 420 or higher" - a numeric threshold in
    prose, not a real course - and flagged it as a hallucination. Same
    class of issue hit ASTR/CHEM lab-code paraphrasing (the model writing
    "CHEM 102" and "CHEM 102L" separately where the data has them joined
    as "CHEM 102&102L"). Diminishing returns on chasing every regex edge
    case further right now.
  - **Judge over-strictness**: one case was marked framed-incorrectly, but
    the judge's own reasoning admitted "this part is actually correct
    mathematically" before flagging it anyway over a phrasing nitpick
    (not re-listing one course alongside the others in a single sentence).
- [x] UI visual polish pass (theme, banner, sidebar cards, degree-audit
      status-pill cards) - verified in browser at desktop and mobile widths,
      with three real bugs found and fixed via devtools inspection rather
      than guessed at:
      - A full-bleed banner using the `100vw` trick ignored the sidebar's
        own stacking context - the sidebar's solid background painted over
        the banner's left portion. Fixed by bleeding to
        `stMainBlockContainer`'s own confirmed 16px padding instead (the
        spec's "pinned to the top of the main area" means the main area's
        width, not the full viewport).
      - Sidebar "card" styling silently did nothing - the targeted
        `stVerticalBlockBorderWrapper` testid only appears when
        `st.container(border=True)` is used; switched to
        `st.container(key=...)`, which exposes a stable `st-key-<key>` CSS
        hook regardless of border setting.
      - Pinning "Clear chat" to the sidebar bottom via `margin-top:auto`
        silently resolved to 0px - the element wasn't a direct flex child
        of the container the rule targeted (two DOM levels off). Once
        retargeted to the right element, a broader selector match (descendant
        instead of child combinator) caused each nested card's own internal
        block to independently inherit `min-height:100vh`, ballooning the
        sidebar to ~2521px (confirmed via `scrollHeight`) before narrowing
        the selector fixed it.
- [x] Navigation moved from main-area tabs to a sidebar radio (Chat /
      Degree Audit) per request - replaced `st.tabs()` with `st.radio()` in
      a sidebar container, main area renders one view or the other based on
      the selection. Caught a real regression while testing: the original
      chrome-hiding CSS did `header[data-testid="stHeader"] { display: none }`,
      which also hid `stExpandSidebarButton` - that control lives inside the
      header too, so once a viewer collapsed the sidebar there was no way
      back. Fixed by making the header transparent/zero-height instead of
      hiding it outright, and hiding only the specific deploy-button/menu
      elements the spec asked to remove.
- [x] Persistent conversation history (`app/storage.py`) - local SQLite
      (`data/conversations.db`, gitignored), keyed by a simple typed
      username with **no password** - explicitly not real auth, just
      enough to separate "my conversations" from "someone else's" on a
      single local/personal deployment. Anyone who types the same username
      sees that history; real authentication was never built - this project
      stayed local/single-deployment throughout (see "Running the app"
      above for what that does and doesn't cover). Each conversation is one
      row, upserted after every exchange (insert on the first message,
      update in place after that) so a browser crash mid-chat doesn't lose
      anything already sent. "Clear chat" starts a fresh row instead of
      deleting the old one - past conversations stay listed. Verified
      end-to-end in a real browser: save, full page reload, re-enter the
      same username, see the conversation listed, click to reload its full
      history; confirmed a different username sees none of it, and
      confirmed no duplicate/stray rows from repeated testing.
- [x] Two small front-end fixes from a direct visual bug report:
      - Major dropdown showed "Bs"/"Ba" instead of "BS"/"BA" - Python's
        `.title()` only capitalizes the first letter of each word. Replaced
        with a formatter that uppercases the degree-suffix word specifically.
      - The Major box's and Completed Courses box's text looked like
        different fonts - turned out to be identical font-family/weight
        (confirmed via computed style) but different *color*: one input's
        text was still forced to the light sidebar-label color from an
        earlier CSS pass, which only became obvious once compared side by
        side against the (already-fixed) Major box.

### Fixed during testing: `choose_groups` bug and gen-ed retrieval

- **Fixed:** `choose_groups` bug - "choose N from a list" electives (e.g.
  "two science courses chosen from: [14 options]") were being audited as if
  all N options were individually required. Confirmed present in 4 of 5
  scraped majors, not CS-specific. Now correctly reports "need 2, have 0"
  instead of listing 14 false-missing requirements. `agent/tools.py` +
  `scraper/major_parser.py`.
- **Fixed, in three steps (documenting all of them since not every step
  worked as intended - useful record of what actually moved the needle):**
  gen-ed policy pages were never scraped at all, so any gen-ed question
  retrieved random unrelated courses.
  1. Added `scraper/policy_parser.py` (data/policy/) and indexed it -
     fixed on-terminology queries ("quantitative reasoning" correctly
     retrieved UNC's own category text), but off-terminology queries
     ("social science" vs. UNC's actual "Power and Society" category)
     still failed.
  2. Added a synonym/alias map (`CATEGORY_ALIASES` in `rag/embed.py`) -
     measured no material improvement; confirmed directly against the
     stored embedding that the target chunk was still out-competed by
     15+ course descriptions with more literal word overlap.
  3. Along the way, found and fixed a real bug unrelated to the alias
     work: the Chroma collection was using the default L2 distance metric
     instead of cosine, which is wrong for sentence-transformer embeddings
     - this was silently hurting every query, not just gen-ed ones.
  4. Swapped the embedding model from `all-MiniLM-L6-v2` to the larger
     `all-mpnet-base-v2` (still local/free, symmetric encoding, no code
     restructuring needed) - this is what actually fixed it: "social
     science gen-ed" now correctly retrieves "Disciplinary Distribution"
     and "Power and Society" in the top 2 results.

  Trade-off, reported honestly rather than only counting the win: the
  larger model isn't a strict improvement on every query - "intro course
  for someone interested in AI" no longer surfaces COMP 560 "Artificial
  Intelligence" in the top 8, where the smaller model had ranked it
  reasonably. No local embedding model is going to be perfect on every
  query; this is a real, expected trade-off of the swap, not a bug to
  chase further right now.
