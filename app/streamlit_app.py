"""Streamlit UI: major picker + completed-courses input + chat + a live
degree-audit view, wired to agent.claude_agent.ask() and
agent.tools.missing_requirements().

Run with: streamlit run app/streamlit_app.py
"""

import html
import sys
from pathlib import Path

# Streamlit only adds this script's own directory (app/) to sys.path, not
# the project root - without this, `from agent...` / `from scraper...`
# fail with ModuleNotFoundError regardless of the working directory.
sys.path.insert(0, str(Path(__file__).parent.parent))

import json

import streamlit as st

from agent import tools
from agent.claude_agent import ask
from app import storage
from scraper.majors import MAJORS

storage.init_db()

DATA_DIR = Path(__file__).parent.parent / "data"
ASSETS_DIR = Path(__file__).parent / "assets"

EXAMPLE_QUESTIONS = [
    "What am I missing for my major?",
    "What can I take next semester?",
    "Is there a good course about AI?",
]

DEGREE_ABBREVIATIONS = {"bs", "ba"}


def format_major_name(slug: str) -> str:
    """"computer-science-bs" -> "Computer Science BS" - plain .title() turns
    the degree suffix into "Bs"/"Ba" instead of the correct "BS"/"BA"."""
    return " ".join(
        word.upper() if word in DEGREE_ABBREVIATIONS else word.capitalize()
        for word in slug.split("-")
    )


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --sp-1: 4px; --sp-2: 8px; --sp-3: 12px; --sp-4: 16px; --sp-6: 24px; --sp-8: 32px;
            --radius: 12px;
            --navy: #13294B;
            --blue: #4B9CD3;
            --blue-tint: #E8F2FA;
            --cream: #FBF8F1;
            --cream-2: #F1EBDD;
            --border-warm: #DCD3C0;
            --green: #1E8E5A; --green-bg: #E3F5EC;
            --amber: #9C6A12; --amber-bg: #FBF0DC;
            --red: #A23D3D; --red-bg: #F6E8E8;
        }

        /* ---- hide Streamlit chrome ----
           NOT a blanket `header { display:none }` - that was tried first
           and broke sidebar re-expand on mobile/after collapsing: the
           expand-sidebar control (stExpandSidebarButton) lives inside
           stHeader too, so hiding the whole header hid the only way back
           once a viewer collapsed the sidebar. Make the header itself
           transparent/zero-height instead, and hide only the specific
           buttons the spec asked to remove. */
        header[data-testid="stHeader"] { background: transparent; height: 0; }
        [data-testid="stAppDeployButton"] { display: none; }
        [data-testid="stMainMenu"] { display: none; }
        footer { visibility: hidden; }

        [data-testid="stAppViewContainer"] { background: var(--cream); }
        [data-testid="stMainBlockContainer"] {
            max-width: 820px;
            padding-top: var(--sp-4);
        }

        /* ---- top banner ----
           stMainBlockContainer has a fixed 16px pad on all sides (confirmed
           via devtools, not assumed) - bleed to its edges with matching
           negative margins. A 100vw-based full-bleed trick was tried first
           and rejected: it ignored the sidebar's own stacking context, so
           the sidebar's solid background painted over the banner's left
           portion - and "pinned to the top of the main area" means the
           main area's width, not the whole viewport including the sidebar. */
        .app-banner {
            margin: calc(-1 * var(--sp-4)) calc(-1 * var(--sp-4)) 0 calc(-1 * var(--sp-4));
            height: 72px;
            background: var(--blue);
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 var(--sp-6);
            box-shadow: 0 2px 8px rgba(19, 41, 75, 0.18);
            box-sizing: border-box;
        }
        .app-banner-title {
            color: #FFFFFF;
            font-weight: 600;
            font-size: 22px;
            letter-spacing: -0.01em;
        }
        .app-banner-meta {
            color: rgba(255, 255, 255, 0.92);
            font-size: 13px;
            font-weight: 500;
        }
        .app-lead {
            color: var(--navy);
            opacity: 0.72;
            font-size: 14.5px;
            line-height: 1.5;
            margin: var(--sp-4) 0 var(--sp-6);
            max-width: 640px;
        }
        @media (max-width: 480px) {
            .app-banner { padding: 0 var(--sp-4); height: 64px; }
            .app-banner-meta { display: none; }
            .app-banner-title { font-size: 19px; }
        }

        /* ---- sidebar ---- */
        [data-testid="stSidebar"] {
            background: var(--navy);
        }
        [data-testid="stSidebar"] * { color: #E8EDF4; }
        [data-testid="stSidebarUserContent"] { padding-top: var(--sp-4); }
        /* The real flex siblings (one per top-level st.container() call) are
           two DOM levels below stSidebarUserContent - stVerticalBlock's
           direct children, each a stLayoutWrapper - confirmed by walking the
           tree in devtools after `margin-top:auto` on the container itself
           (and even an inline !important override) silently resolved to
           0px: it was never being applied to an actual flex item.
           Must use child combinators (>), not a descendant selector: each
           st.container() wraps its own content in another nested
           stVerticalBlock, so a bare descendant match forces min-height on
           those too and compounds 100vh per card - confirmed by measuring
           stSidebarContent.scrollHeight at 2521px (~3x one viewport) before
           this fix. */
        [data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] {
            display: flex;
            flex-direction: column;
            min-height: calc(100vh - 190px);
            gap: var(--sp-4);
        }
        .card-label {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: #9FB2C8;
            font-weight: 600;
            margin-bottom: var(--sp-2);
        }
        [data-testid="stSidebar"] .st-key-major-card,
        [data-testid="stSidebar"] .st-key-courses-card {
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: var(--radius);
            padding: var(--sp-4);
        }
        .big-metric {
            font-size: 2rem;
            font-weight: 700;
            color: var(--blue);
            line-height: 1;
            margin-top: var(--sp-2);
        }
        .metric-label {
            font-size: 12px;
            color: #9FB2C8;
            margin-top: 2px;
        }
        .sidebar-progress-track {
            height: 6px;
            background: rgba(255, 255, 255, 0.12);
            border-radius: 999px;
            overflow: hidden;
            margin-top: var(--sp-3);
        }
        .sidebar-progress-fill {
            height: 100%;
            background: var(--blue);
            border-radius: 999px;
        }
        .sidebar-progress-caption {
            font-size: 11.5px;
            color: #9FB2C8;
            margin-top: var(--sp-1);
        }

        /* multiselect chips */
        [data-testid="stSidebar"] [data-testid="stMultiSelect"] span[data-baseweb="tag"] {
            background-color: var(--blue) !important;
            border-radius: 7px;
        }
        [data-testid="stSidebar"] [data-testid="stMultiSelect"] span[data-baseweb="tag"] * {
            color: #FFFFFF !important;
            font-weight: 500;
        }
        /* Same bug as the Major input below, just harder to spot: this field
           sits on the white input background, so its text (including the
           placeholder, which browsers render as a toned-down version of
           this color) needs dark navy, not the light sidebar-label color -
           confirmed via computed style: this was rgb(232,237,244) while the
           Major input was rgb(19,41,75), which is what actually produced
           the "fonts don't match" look (the font-family/weight were
           already identical - it was a color mismatch). */
        [data-testid="stSidebar"] [data-testid="stMultiSelectTagsContainer"] input {
            color: var(--navy) !important;
        }
        /* The Major selectbox's displayed value is a plain <input> (react-aria
           combobox, not a `[data-baseweb="select"]` wrapper as guessed on the
           first pass - that selector matched nothing, confirmed via devtools:
           the real markup is `input[role="combobox"]` with its value in the
           `value` attribute). It sits on the white input background, so it
           needs dark text - the blanket `[data-testid="stSidebar"] * { color:
           #E8EDF4 }` rule above was washing it out to near-invisible, since
           that rule is meant for text on the navy sidebar background, not
           inside the light-background form inputs. */
        [data-testid="stSidebar"] [data-testid="stSelectbox"] input {
            color: var(--navy) !important;
        }

        /* Clear chat: pinned to bottom via margin-top:auto - applied to the
           stLayoutWrapper that's the actual flex item (the direct child of
           the flex stVerticalBlock above), not to .st-key-clear-chat-wrap
           itself, which is nested one level deeper and so isn't a flex item
           margin:auto can act on. */
        [data-testid="stSidebarUserContent"] [data-testid="stLayoutWrapper"]:has(.st-key-clear-chat-wrap) {
            margin-top: auto;
        }
        [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {
            background: transparent;
            border: 1px solid rgba(255, 255, 255, 0.3);
            color: #E8EDF4;
        }
        [data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover {
            border-color: var(--blue);
            color: #FFFFFF;
            background: rgba(75, 156, 211, 0.15);
        }

        /* ---- sidebar view nav (radio) ----
           Real attribute confirmed via devtools: [data-testid="stRadioOption"]
           with data-selected="true" - not the label/data-checked guess tried
           first, which silently matched nothing. */
        [data-testid="stSidebar"] .st-key-view-nav [data-testid="stRadioOption"] {
            background: transparent;
            border-radius: 8px;
            padding: var(--sp-2) var(--sp-3);
            width: 100%;
            transition: background-color 150ms ease;
        }
        [data-testid="stSidebar"] .st-key-view-nav [data-testid="stRadioOption"]:hover {
            background: rgba(255, 255, 255, 0.06);
        }
        [data-testid="stSidebar"] .st-key-view-nav [data-testid="stRadioOption"][data-selected="true"] {
            background: rgba(75, 156, 211, 0.18);
        }
        [data-testid="stSidebar"] .st-key-view-nav [data-testid="stRadioOption"][data-selected="true"] p {
            color: #FFFFFF;
            font-weight: 600;
        }

        /* ---- example-prompt pills (main area buttons only) ---- */
        [data-testid="stMain"] [data-testid="stBaseButton-secondary"] {
            background: #FFFFFF;
            border: 1px solid var(--border-warm);
            border-radius: 999px;
            color: var(--navy);
            font-weight: 500;
            transition: background-color 150ms ease, border-color 150ms ease;
        }
        [data-testid="stMain"] [data-testid="stBaseButton-secondary"]:hover {
            background: var(--blue-tint);
            border-color: var(--blue);
            color: var(--navy);
        }

        /* ---- chat input ---- */
        [data-testid="stChatInput"] {
            background: #FFFFFF;
            border-radius: var(--radius);
            box-shadow: 0 1px 3px rgba(19, 41, 75, 0.08);
            border: 1px solid var(--border-warm);
        }
        [data-testid="stChatInput"]:focus-within {
            border-color: var(--blue);
            box-shadow: 0 0 0 3px rgba(75, 156, 211, 0.25);
        }

        /* ---- chat bubbles ---- */
        [data-testid="stChatMessage"] {
            border-radius: var(--radius);
            padding: var(--sp-3) var(--sp-4);
            margin-bottom: var(--sp-2);
        }
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
            background: var(--blue-tint);
        }
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
            background: #FFFFFF;
            border: 1px solid var(--border-warm);
        }

        /* ---- degree-audit requirement cards ---- */
        .req-card {
            background: #FFFFFF;
            border: 1px solid var(--border-warm);
            border-radius: var(--radius);
            padding: var(--sp-4);
            margin-bottom: var(--sp-4);
        }
        .req-card-title {
            font-weight: 600;
            font-size: 15px;
            color: var(--navy);
            margin-bottom: var(--sp-3);
        }
        .req-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: var(--sp-3);
            padding: var(--sp-2) 0;
            border-bottom: 1px solid #F0EADC;
            font-size: 14px;
        }
        .req-row:last-of-type { border-bottom: none; }
        .req-code { color: var(--navy); font-weight: 500; }
        .req-title { color: var(--navy); opacity: 0.6; font-size: 12.5px; }
        .pill {
            display: inline-block;
            font-size: 11.5px;
            font-weight: 600;
            padding: 3px 10px;
            border-radius: 999px;
            white-space: nowrap;
        }
        .pill-complete { background: var(--green-bg); color: var(--green); }
        .pill-progress { background: var(--amber-bg); color: var(--amber); }
        .pill-missing { background: var(--red-bg); color: var(--red); }

        .group-block { margin-top: var(--sp-3); padding-top: var(--sp-3); border-top: 1px dashed var(--border-warm); }
        .group-head { display: flex; align-items: center; justify-content: space-between; gap: var(--sp-3); margin-bottom: var(--sp-2); }
        .group-desc { font-size: 13.5px; color: var(--navy); }
        .group-options { font-size: 12px; color: var(--navy); opacity: 0.6; font-family: ui-monospace, monospace; line-height: 1.6; }
        .req-note { font-size: 12px; color: var(--navy); opacity: 0.55; background: #FAF6EC; border-left: 3px solid var(--border-warm); padding: var(--sp-2) var(--sp-3); margin-top: var(--sp-2); border-radius: 0 6px 6px 0; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def pill(status: str) -> str:
    label = {"complete": "Complete", "progress": "In progress", "missing": "Missing"}[status]
    return f'<span class="pill pill-{status}">{label}</span>'


def render_requirement_card(section: dict, course_titles: dict[str, str]) -> str:
    rows = []
    for code in section["satisfied"]:
        title = html.escape(course_titles.get(code, ""))
        rows.append(
            f'<div class="req-row"><span><span class="req-code">{html.escape(code)}</span> '
            f'<span class="req-title">{title}</span></span>{pill("complete")}</div>'
        )
    for code in section["missing"]:
        title = html.escape(course_titles.get(code, ""))
        rows.append(
            f'<div class="req-row"><span><span class="req-code">{html.escape(code)}</span> '
            f'<span class="req-title">{title}</span></span>{pill("missing")}</div>'
        )

    groups = []
    for group in section["choose_groups"]:
        met_count = len(group["satisfied_options"])
        status = "complete" if group["met"] else ("progress" if met_count else "missing")
        options = ", ".join(group["satisfied_options"] + group["remaining_options"])
        groups.append(
            f'<div class="group-block">'
            f'<div class="group-head"><span class="group-desc">{html.escape(group["description"])} '
            f'({met_count} of {group["required_count"]})</span>{pill(status)}</div>'
            f'<div class="group-options">{html.escape(options)}</div>'
            + "".join(f'<div class="req-note">{html.escape(n)}</div>' for n in group["unverifiable_notes"])
            + "</div>"
        )

    notes = "".join(f'<div class="req-note">{html.escape(n)}</div>' for n in section["unverifiable_notes"])

    if not (rows or groups or notes):
        return ""

    return (
        f'<div class="req-card"><div class="req-card-title">{html.escape(section["name"])}</div>'
        + "".join(rows)
        + "".join(groups)
        + notes
        + "</div>"
    )


st.set_page_config(page_title="UNC Degree Audit", page_icon="🎓")
inject_styles()

st.markdown(
    '<div class="app-banner">'
    '<span class="app-banner-title">Degree-Audit Assistant</span>'
    '<span class="app-banner-meta">UNC Chapel Hill · Unofficial tool</span>'
    "</div>",
    unsafe_allow_html=True,
)
st.markdown(
    '<p class="app-lead">Ask about degree requirements, prerequisites, or gen-ed rules. '
    "Grounded in the real UNC catalog, not a general knowledge guess.</p>",
    unsafe_allow_html=True,
)


@st.cache_data
def load_course_titles() -> dict[str, str]:
    titles = {}
    for path in (DATA_DIR / "courses").glob("*.json"):
        for course in json.loads(path.read_text()):
            titles[course["code"]] = course["title"]
    return titles


course_titles = load_course_titles()

with st.sidebar:
    with st.container(key="view-nav"):
        view = st.radio(
            "View",
            ["Chat", "Degree Audit"],
            label_visibility="collapsed",
        )

    with st.container(key="major-card"):
        st.markdown('<div class="card-label">Major</div>', unsafe_allow_html=True)
        major_slug = st.selectbox(
            "Major",
            options=list(MAJORS.keys()),
            format_func=format_major_name,
            label_visibility="collapsed",
        )

    with st.container(key="courses-card"):
        st.markdown('<div class="card-label">Completed Courses</div>', unsafe_allow_html=True)
        completed_courses = st.multiselect(
            "Completed courses",
            options=sorted(course_titles.keys()),
            format_func=lambda code: f"{code} — {course_titles[code]}",
            label_visibility="collapsed",
            placeholder="Search and select courses you've completed",
        )

        audit_preview = tools.missing_requirements(major_slug, completed_courses)
        total_required = sum(len(s["satisfied"]) + len(s["missing"]) for s in audit_preview["sections"])
        total_satisfied = sum(len(s["satisfied"]) for s in audit_preview["sections"])

        st.markdown(
            f'<div class="big-metric">{len(completed_courses)}</div>'
            '<div class="metric-label">Courses completed</div>',
            unsafe_allow_html=True,
        )
        if total_required:
            pct = round(100 * total_satisfied / total_required)
            st.markdown(
                f'<div class="sidebar-progress-track"><div class="sidebar-progress-fill" '
                f'style="width:{pct}%"></div></div>'
                f'<div class="sidebar-progress-caption">{total_satisfied} of {total_required} '
                f"required courses ({pct}%)</div>",
                unsafe_allow_html=True,
            )

    with st.container(key="clear-chat-wrap"):
        if st.button("Clear chat", use_container_width=True):
            st.session_state.messages = []
            st.session_state.current_conversation_id = None
            st.rerun()

if view == "Chat":
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "current_conversation_id" not in st.session_state:
        st.session_state.current_conversation_id = None

    username = st.text_input(
        "Username",
        key="username",
        placeholder="Enter a username to save and revisit your conversations",
        label_visibility="collapsed",
    )

    if username:
        previous = storage.list_conversations(username)
        if previous:
            with st.expander(f"Previous conversations ({len(previous)})"):
                for convo in previous:
                    when = convo["updated_at"][:16].replace("T", " ")
                    label = f"{convo['title']} — {when}"
                    if st.button(label, key=f"load_convo_{convo['id']}", use_container_width=True):
                        loaded = storage.load_conversation(convo["id"])
                        st.session_state.messages = loaded["messages"]
                        st.session_state.current_conversation_id = convo["id"]
                        st.rerun()
    else:
        st.caption("Enter a username above to save and revisit your conversations across visits. "
                    "No password - anyone who types the same username sees that history.")

    if not st.session_state.messages:
        st.markdown("**Try asking:**")
        cols = st.columns(len(EXAMPLE_QUESTIONS))
        for col, example in zip(cols, EXAMPLE_QUESTIONS):
            if col.button(example, use_container_width=True):
                st.session_state.pending_question = example

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            meta = message.get("meta")
            if meta:
                st.caption(
                    f"{meta['model']} · ${meta['cost_usd']:.4f} · {meta['elapsed_s']:.1f}s"
                )

    question = st.chat_input("e.g. What am I missing for the major?")
    if not question:
        question = st.session_state.pop("pending_question", None)

    if question:
        if not completed_courses:
            st.warning("Add your completed courses in the sidebar first for an accurate answer.")

        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        meta = None
        with st.chat_message("assistant"):
            with st.spinner("Checking the catalog..."):
                try:
                    result = ask(question, major_slug, completed_courses)
                    answer = result["answer"]
                    meta = {
                        "model": result["model"],
                        "cost_usd": result["cost_usd"],
                        "elapsed_s": result["elapsed_s"],
                    }
                except KeyError:
                    answer = (
                        "No `ANTHROPIC_API_KEY` found. Add one to `.env` "
                        "(see `.env.example`) and restart the app."
                    )
                except Exception as exc:
                    answer = f"Something went wrong: {exc}"
            st.markdown(answer)
            if meta:
                st.caption(
                    f"{meta['model']} · ${meta['cost_usd']:.4f} · {meta['elapsed_s']:.1f}s"
                )

        st.session_state.messages.append({"role": "assistant", "content": answer, "meta": meta})

        if username:
            st.session_state.current_conversation_id = storage.save_conversation(
                st.session_state.current_conversation_id,
                username,
                major_slug,
                st.session_state.messages,
            )

else:
    st.caption("Computed instantly from the scraped catalog - no API call, no cost.")

    audit = tools.missing_requirements(major_slug, completed_courses)
    hours = int(audit["total_hours"]) if audit["total_hours"] else "—"

    col1, col2 = st.columns(2)
    col1.metric("Required courses satisfied", f"{total_satisfied} / {total_required}")
    col2.metric("Total hours for major", hours)

    for section in audit["sections"]:
        card_html = render_requirement_card(section, course_titles)
        if card_html:
            st.markdown(card_html, unsafe_allow_html=True)
