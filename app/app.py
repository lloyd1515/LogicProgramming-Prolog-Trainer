import os
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

import hashlib
import html
import json
import math
import re
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import streamlit as st
from streamlit_cookies_controller import CookieController

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
sys.path = [path for path in sys.path if Path(path or ".").resolve() != APP_DIR]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import llm_client, quiz_logic, settings, vector_store, telemetry
from app.env import load_env_file
from app.styles import APP_CSS

load_env_file(settings.ROOT_DIR)

ADMIN_SESSION_COOKIE = "lp_admin_session"
ADMIN_SESSION_TTL_SECONDS = 7200
RESERVED_USERNAMES = {"admin"}

st.set_page_config(
    page_title="Logic Programming Quiz Trainer",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(f"<style>{APP_CSS}</style>", unsafe_allow_html=True)

# ── Autocomplete terms (real data, zero API) ──────────────────────────────────
_PROLOG_TERMS = (
    "backtracking", "cut (!)", "unification", "recursion",
    "incomplete lists", "append", "member", "length",
    "negation as failure", "assert", "retract", "functor",
    "findall", "bagof", "setof", "DCG",
    "Horn clauses", "SLD resolution", "arithmetic operators",
    "difference lists", "binary trees", "graphs", "metapredicate",
)


@st.cache_data
def _autocomplete_options(quiz_topics: tuple[str, ...]) -> list[str]:
    """Cached list of searchable terms: topics + prolog terms, deduplicated."""
    return sorted(set(list(quiz_topics) + list(_PROLOG_TERMS)))


@st.cache_resource
def cached_collection(db_path: str, fingerprint: int):
    return vector_store.get_collection(Path(db_path))


@st.cache_resource
def cached_cache_collection(db_path: str):
    return vector_store.get_cache_collection(Path(db_path))


@st.cache_data
def cached_load_quizzes(path_str: str, modified_at: float | None = None) -> list[dict]:
    _ = modified_at
    return quiz_logic.load_quizzes(Path(path_str))


@st.cache_data(ttl=60)
def cached_db_fingerprint(db_path_str: str) -> int:
    return vector_store.db_fingerprint(Path(db_path_str))





# ── Header ─────────────────────────────────────────────────────────────────────

def render_header() -> None:
    # setdefault keeps the user's model choice across reruns (was overwriting on every rerun before)
    st.session_state.setdefault("selected_model", settings.GEMINI_MODEL)
    st.session_state.setdefault("exhausted_models", set())

    st.markdown("<div class='app-title'>🧬 Logic Programming Quiz Trainer</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='app-subtitle'>"
        "Semantic Search · Exam Quiz · AI Generator "
        "<span class='private-beta-badge'>Private beta</span>"
        "</div>",
        unsafe_allow_html=True,
    )

    # Show current logged in user and a logout button
    if "username" in st.session_state and st.session_state.username:
        username = st.session_state.username
        if username != "Admin":
            col_usr, col_logo = st.columns([8, 2])
            with col_usr:
                st.write(f"Logged in as: **{username}**")
            with col_logo:
                if st.button("Logout", key="user_logout_btn", type="secondary", width="stretch"):
                    # Delete the user from database immediately so anyone can use it
                    try:
                        telemetry.delete_user_by_username(username)
                    except Exception:
                        pass
                    # Reset state and cookies
                    st.session_state.username = None
                    st.session_state.user_id = None
                    try:
                        from streamlit_cookies_controller import CookieController
                        controller = CookieController()
                        controller.remove("lp_username")
                        controller.remove("lp_user_id")
                    except Exception:
                        pass
                    st.rerun()


# ── Telemetry Helpers ──────────────────────────────────────────────────────────

def get_client_ip() -> str:
    # If client-side IP was successfully fetched, use it
    try:
        import streamlit as st
        if "public_ip" in st.session_state and st.session_state.public_ip:
            return st.session_state.public_ip
    except Exception:
        pass

    try:
        import streamlit as st
        import ipaddress

        def is_public(ip_str: str) -> bool:
            try:
                ip = ipaddress.ip_address(ip_str)
                return not (ip.is_private or ip.is_loopback or ip.is_link_local)
            except ValueError:
                return False

        all_headers = {}

        # 1. Gather from st.context.headers
        if hasattr(st, "context") and st.context and hasattr(st.context, "headers") and st.context.headers:
            all_headers.update(st.context.headers)

        # 2. Gather from WebSocket headers
        try:
            from streamlit.web.server.websocket_headers import _get_websocket_headers
            headers_ws = _get_websocket_headers()
            if headers_ws:
                all_headers.update(headers_ws)
        except Exception:
            pass

        # 3. First, look for known public IP headers
        for h in ["x-forwarded-for", "x-real-ip", "cf-connecting-ip", "client-ip", "true-client-ip"]:
            for key, val in all_headers.items():
                if key.lower() == h and val:
                    ips = [ip.strip() for ip in val.split(",")]
                    for ip in ips:
                        if is_public(ip):
                            return ip

        # 4. If not found in known headers, scan ALL headers for any public IP
        for key, val in all_headers.items():
            if val and isinstance(val, str):
                ips = [ip.strip() for ip in val.split(",")]
                for ip in ips:
                    if is_public(ip):
                        return ip

        # 5. Fall back to ip_address if it's a public IP
        if hasattr(st, "context") and st.context and hasattr(st.context, "ip_address") and st.context.ip_address:
            fallback_ip = st.context.ip_address
            if is_public(fallback_ip):
                return fallback_ip

        # 6. If we still don't have a public IP, but we have a private IP from st.context.ip_address, use it
        if hasattr(st, "context") and st.context and hasattr(st.context, "ip_address") and st.context.ip_address:
            return st.context.ip_address

    except Exception:
        pass
    return "127.0.0.1"


def get_active_sessions_count() -> int:
    try:
        from streamlit.runtime import Runtime
        runtime = Runtime.instance()
        if runtime:
            return len(runtime._session_mgr.list_active_sessions())
    except Exception:
        pass
    return 1


def run_indexing():
    return subprocess.run(
        [sys.executable, str(settings.INDEX_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(settings.ROOT_DIR),
    )


def log_quiz_submission(quiz_type: str, filtered_quizzes: list[dict], answers: dict) -> None:
    attempts = []
    score = 0
    for idx, quiz in enumerate(filtered_quizzes):
        user_ans = answers.get(idx, "")
        correct_ans = quiz.get("correct_answer", "")
        q_type = quiz.get("type", "multiple_choice")
        is_correct = quiz_logic.is_answer_correct(user_ans, correct_ans, q_type)
        if is_correct:
            score += 1
        attempts.append({
            "question_text": quiz.get("question_text", ""),
            "code": quiz.get("code", ""),
            "options": quiz.get("blanks_or_options", []),
            "user_answer": user_ans,
            "correct_answer": correct_ans,
            "is_correct": is_correct
        })
    
    try:
        telemetry.log_event(
            user_id=get_user_id(),
            ip=get_client_ip(),
            event_type="quiz_submit",
            query=quiz_type,
            details={
                "score": score,
                "total_questions": len(filtered_quizzes),
                "attempts": attempts
            }
        )
    except Exception:
        pass



# ── Missing DB ─────────────────────────────────────────────────────────────────

def render_missing_database() -> None:
    st.warning("⚠️ The database is not indexed.")
    if st.session_state.get("is_admin", False):
        if st.button("🚀 Index courses now", type="primary", key="missing_db_index_btn"):
            with st.spinner("Indexing..."):
                result = run_indexing()
            if result.returncode == 0:
                st.success("✅ Indexing completed!")
                st.cache_resource.clear()
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("Error during indexing:")
                st.code(result.stderr)


# ── Slide card ──────────────────────────────────────────────────────────────────

_PROLOG_CODE_MARKERS = (":-", "?-", "->", r"\+", "is ", "nl.", "write(", "assert(", "retract(", "%", "/*", "*/", "fail.", "true.")


def _looks_like_prolog(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False

    # 1. Classic Prolog syntax elements
    if any(marker in stripped for marker in _PROLOG_CODE_MARKERS):
        return True

    # 2. Comments
    if stripped.startswith(("//", "%", "/*")) or stripped.endswith("*/"):
        return True
    if "//" in stripped and stripped.count("//") > stripped.count("://"):
        return True

    # 3. Predicate definitions/calls: starts with lowercase word, then '('
    if re.search(r'^[a-z][a-zA-Z0-9_]*\s*\(', stripped):
        return True

    # 4. List structures
    if "[" in stripped and "]" in stripped:
        return True
    if "|" in stripped and ("[" in stripped or "]" in stripped):
        return True

    # 5. Lines that end with '.' or ',' and start with lowercase word, and contain structure characters
    if (stripped.endswith(".") or stripped.endswith(",")) and re.match(r'^[a-z]', stripped):
        if any(c in stripped for c in ("(", ")", "[", "]", "|", "_")):
            return True

    return False


def _split_slide_text(text: str) -> list[tuple[str, bool]]:
    """Split slide text into (chunk, is_code) segments."""
    lines = (text or "").splitlines()
    segments: list[tuple[str, bool]] = []
    buffer: list[str] = []
    current_is_code: bool | None = None

    for line in lines:
        is_code = _looks_like_prolog(line)
        if current_is_code is None:
            current_is_code = is_code
        if is_code != current_is_code:
            if buffer:
                segments.append(("\n".join(buffer), current_is_code))
            buffer = [line]
            current_is_code = is_code
        else:
            buffer.append(line)

    if buffer:
        segments.append(("\n".join(buffer), current_is_code or False))
    return segments


def _format_slide_text_as_markdown(text: str) -> str:
    """Convert raw slide text to readable markdown paragraphs."""
    lines = (text or "").splitlines()
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append("")
            continue
        # Preserve bullet-like lines
        if stripped.startswith(("•", "-", "*", "–", "→")) or stripped[0].isdigit() and stripped[1:3] in (". ", ") "):
            out.append(stripped)
        else:
            out.append(stripped)
        out.append("")  # blank line after each → forces paragraph break in markdown
    return "\n".join(out).strip()


def render_slide_card(index: int, slide: vector_store.SlideResult) -> None:
    sim = slide.similarity
    sim_class = "badge-similarity" if sim >= 65 else "badge-similarity low"

    with st.container(border=True):
        st.markdown(
            f"<div class='slide-card-header'>"
            f"<span class='badge {sim_class}'>{sim:.0f}% match</span>"
            f"<span class='badge badge-source'>📄 {html.escape(slide.source)}</span>"
            f"<span class='badge badge-page'>pag. {slide.page}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        st.markdown(f"**{slide.title}**")

        segments = _split_slide_text(slide.text)
        for chunk, is_code in segments:
            if is_code:
                st.code(chunk.strip(), language="prolog")
            else:
                st.markdown(_format_slide_text_as_markdown(chunk))


def _render_usage_tracker() -> None:
    """Render the session's token and request usage tracker."""
    current_model = st.session_state.get("selected_model", settings.GEMINI_MODEL)
    info = settings.MODEL_LIMITS.get(current_model, settings.MODEL_LIMITS[settings.GEMINI_MODEL])
    usage = llm_client.get_session_usage_per_model(current_model)
    if usage.requests == 0:
        return

    st.markdown("---")
    cols = st.columns(3)
    with cols[0]:
        st.metric(
            label=f"Session requests ({info['name']})",
            value=f"{usage.requests}",
            help=f"Daily limit: {info['rpd']} RPD"
        )
    with cols[1]:
        st.metric(
            label="Session tokens used",
            value=f"{usage.total_tokens:,}",
            help=f"Consumption: {usage.input_tokens:,} input, {usage.output_tokens:,} output"
        )
    with cols[2]:
        pct = (usage.total_tokens / info['tpd']) * 100
        st.metric(
            label="Percent of daily limit",
            value=f"{pct:.2f}%",
            help=f"Daily limit: {info['tpd']:,} tokens"
        )


@st.cache_data(show_spinner=False, persist="disk")
def cached_answer_from_slides(api_key: str, model_name: str, context_text: str, question: str) -> str:
    return llm_client.answer_from_slides(api_key, model_name, context_text, question)


def render_search_tab(collection, cache_collection, api_key: str, quizzes: list[dict]) -> None:
    topics = tuple(quiz_logic.topics_for(quizzes))
    autocomplete_opts = list(_autocomplete_options(topics))

    with st.form("search_form"):
        selected_query = st.selectbox(
            "Search a concept:",
            options=autocomplete_opts,
            index=None,
            placeholder="Select a concept or type any custom question...",
            label_visibility="collapsed",
            key="search_selectbox_val",
            accept_new_options=True,
        )
        submitted = st.form_submit_button("Search", type="primary")

    if submitted and selected_query:
        st.session_state.last_search_query = selected_query
        st.session_state.pop("last_search_slides", None)
        st.session_state.pop("last_search_answer", None)
        st.session_state.pop("last_search_answer_meta", None)

    query = st.session_state.get("last_search_query")

    if not query:
        return

    slides = st.session_state.get("last_search_slides")
    if slides is None:
        with st.spinner("Searching..."):
            slides = vector_store.search_slides(
                collection, query, settings.SEARCH_CONTEXT_SLIDES, None
            )
        st.session_state.last_search_slides = slides

        # Log search event only when a new explicit search is executed.
        try:
            telemetry.log_event(
                user_id=get_user_id(),
                ip=get_client_ip(),
                event_type="search",
                query=query,
                details={
                    "slides_count": len(slides),
                    "top_slides": [{"source": s.source, "page": s.page, "title": s.title} for s in slides[:3]]
                }
            )
        except Exception:
            pass

    if not slides:
        st.info("No slides with sufficient semantic match.")
        return

    if api_key:
        with st.container(border=True):
            answer_meta = st.session_state.get("last_search_answer_meta")
            answer = st.session_state.get("last_search_answer")
            if answer:
                st.markdown(answer)
                if answer_meta:
                    st.caption(answer_meta)
            else:
                with st.spinner("Generating answer..."):
                    try:
                        current_model = st.session_state.get("selected_model", settings.GEMINI_MODEL)
                        # Check semantic cache first
                        cached_hit = vector_store.search_query_cache(cache_collection, query)
                        if cached_hit:
                            answer, similarity = cached_hit
                            answer_meta = f"⚡ Cached answer (Semantic similarity: {similarity:.1f}%)"
                        else:
                            answer = cached_answer_from_slides(
                                api_key,
                                current_model,
                                vector_store.slides_to_context(slides),
                                query,
                            )
                            answer_meta = None
                            vector_store.add_to_query_cache(cache_collection, query, answer)

                        st.session_state.last_search_answer = answer
                        st.session_state.last_search_answer_meta = answer_meta
                        st.markdown(answer)
                        if answer_meta:
                            st.caption(answer_meta)

                        # Log Q&A generation event only when the answer is generated/fetched.
                        try:
                            telemetry.log_event(
                                user_id=get_user_id(),
                                ip=get_client_ip(),
                                event_type="qa",
                                query=query,
                                details={
                                    "answer": answer,
                                    "cached": bool(cached_hit),
                                    "model": current_model if not cached_hit else "cached"
                                }
                            )
                        except Exception:
                            pass
                    except Exception as exc:
                        msg, retry_after = llm_client.parse_api_error(exc)
                        if llm_client.is_daily_limit(exc):
                            current_model = st.session_state.get("selected_model", settings.GEMINI_MODEL)
                            st.session_state.setdefault("exhausted_models", set()).add(current_model)
                            st.error(f"❌ {msg}")
                            st.info("💡 The current model has reached the daily limit (20 req/day on Free Tier). Please change the model in the top-right corner (e.g., Gemini 2.5 Flash).")
                        elif retry_after:
                            st.warning(f"⏳ {msg}")
                        else:
                            st.error(f"❌ {msg}")

    st.markdown(f"### 📚 Relevant Slides ({len(slides)})")
    for index, slide in enumerate(slides, start=1):
        render_slide_card(index, slide)


# ── Quiz state helpers ─────────────────────────────────────────────────────────

def answer_key(index: int) -> str:
    return f"quiz_answer_{index}"


def blank_key(question_index: int, label: str) -> str:
    return f"quiz_blank_{question_index}_{label}"


def clear_quiz_widget_answers() -> None:
    for key in list(st.session_state.keys()):
        if str(key).startswith(("quiz_answer_", "quiz_blank_")):
            del st.session_state[key]


def save_current_answer(index: int, value) -> None:
    answers = dict(st.session_state.get("quiz_answers", {}))
    answers[index] = value or ""
    st.session_state.quiz_answers = answers
    save_official_quiz_state_helper()


def is_answered(value) -> bool:
    return bool(str(value or "").strip())


def quiz_nav_label(index: int, answered: bool, flagged: bool = False) -> str:
    marker = "✅ " if answered else ""
    flag = " ⚑" if flagged else ""
    return f"{marker}{index + 1}{flag}"


def reset_quiz_state_for_topic(selected_topic: str) -> None:
    if st.session_state.get("last_selected_topic") != selected_topic:
        st.session_state.last_selected_topic = selected_topic
        st.session_state.current_index = 0
        st.session_state.quiz_answers = {}
        st.session_state.quiz_flags = set()
        st.session_state.quiz_submitted = False
        st.session_state.quiz_summary = False
        st.session_state.pop("quiz_sample", None)
        clear_quiz_widget_answers()
        
        user_id = get_user_id()
        cache_path = get_official_cache_path(user_id)
        if cache_path.exists():
            try:
                cache_path.unlink()
            except Exception:
                pass


def restore_answer_widget_for_question(quiz: dict, index: int, saved_answer) -> None:
    if not is_answered(saved_answer):
        return

    question_type = quiz.get("type", "multiple_choice")
    blank_labels = quiz_logic.blank_labels_for_quiz(quiz)
    if quiz.get("code") and blank_labels and question_type != "multiple_choice":
        parsed = {}
        for part in str(saved_answer).split(","):
            if "=" in part:
                key, value = part.split("=", 1)
                parsed[key.strip().lower()] = value.strip()
        for label in blank_labels:
            key = blank_key(index, label.lower())
            if key not in st.session_state and label.lower() in parsed:
                st.session_state[key] = parsed[label.lower()]
        return

    key = answer_key(index)
    if key not in st.session_state:
        st.session_state[key] = saved_answer


def render_graph_visual(visual: dict) -> None:
    nodes = [str(node) for node in visual.get("nodes") or []]
    edges = visual.get("edges") or []
    if not nodes:
        return

    width = 520
    height = 300
    radius = 21
    raw_positions = visual.get("positions") or {}
    positions: dict[str, tuple[float, float]] = {}
    for idx, node in enumerate(nodes):
        if node in raw_positions and len(raw_positions[node]) >= 2:
            x, y = raw_positions[node][:2]
            positions[node] = (float(x), float(y))
        else:
            angle = (2 * math.pi * idx / len(nodes)) - (math.pi / 2)
            positions[node] = (
                width / 2 + math.cos(angle) * 150,
                height / 2 + math.sin(angle) * 105,
            )

    edge_lines = []
    for edge in edges:
        if not isinstance(edge, list | tuple) or len(edge) < 2:
            continue
        source, target = str(edge[0]), str(edge[1])
        if source not in positions or target not in positions:
            continue
        x1, y1 = positions[source]
        x2, y2 = positions[target]
        edge_lines.append(
            f"<line x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}' "
            "stroke='#8fb9e8' stroke-width='2.4' stroke-linecap='round' />"
        )

    node_shapes = []
    for node in nodes:
        x, y = positions[node]
        label = html.escape(node)
        node_shapes.append(
            f"<circle cx='{x:.1f}' cy='{y:.1f}' r='{radius}' fill='#4f91d9' "
            "stroke='#2d5f9f' stroke-width='2' />"
            f"<text x='{x:.1f}' y='{y + 5:.1f}' text-anchor='middle' "
            "font-family='Arial, sans-serif' font-size='15' font-weight='700' "
            f"fill='white'>{label}</text>"
        )

    title = html.escape(str(visual.get("title") or "Graph"))
    svg = (
        "<div class='quiz-visual'>"
        f"<div class='quiz-visual-title'>{title}</div>"
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='{title}'>"
        "<rect x='1' y='1' width='518' height='298' rx='8' fill='#f8fbff' stroke='#d8e5f5' />"
        f"{''.join(edge_lines)}{''.join(node_shapes)}"
        "</svg></div>"
    )
    st.markdown(svg, unsafe_allow_html=True)


def render_quiz_visual(quiz: dict) -> None:
    visual = quiz.get("visual")
    if not isinstance(visual, dict):
        return

    visual_type = visual.get("type")
    if visual_type == "graph":
        render_graph_visual(visual)
        return

    if visual_type == "image":
        image_path = visual.get("path")
        if not image_path:
            return
        path = Path(image_path)
        if not path.is_absolute():
            path = APP_DIR / path
        if path.exists():
            st.image(str(path), caption=visual.get("caption") or visual.get("alt"))
        else:
            st.warning(f"Question image not found: {image_path}")


# ── Inline blank rendering ─────────────────────────────────────────────────────

def inline_code_piece_weight(value: str) -> int:
    return max(1, min(18, len(value.expandtabs(4)) // 2))


def inline_blank_weight(label: str) -> int:
    return 5 if "_" in label else 4


def render_inline_blank_code(code: str, question_index: int, labels: list[str], *, disabled: bool = False) -> str:
    lines = (code or "").splitlines()
    for line_index, line in enumerate(lines):
        parts = quiz_logic.BLANK_PATTERN.split(line)
        if len(parts) == 1:
            st.markdown(f"<pre class='inline-code-line'>{html.escape(line) or ' '}</pre>", unsafe_allow_html=True)
            continue

        weights = [
            inline_code_piece_weight(part) if idx % 2 == 0 else inline_blank_weight(part)
            for idx, part in enumerate(parts)
        ]
        weights.append(max(10, 42 - sum(weights)))
        columns = st.columns(weights, gap="small")
        for idx, part in enumerate(parts):
            with columns[idx]:
                if idx % 2 == 0:
                    st.markdown(f"<pre class='inline-code-piece'>{html.escape(part) or ' '}</pre>", unsafe_allow_html=True)
                else:
                    label = part.lower()
                    st.text_input(
                        label,
                        key=blank_key(question_index, label),
                        disabled=disabled,
                        label_visibility="collapsed",
                    )
        with columns[-1]:
            st.markdown("<span class='inline-code-filler'></span>", unsafe_allow_html=True)
        if line_index < len(lines) - 1:
            st.markdown("<div class='inline-code-gap'></div>", unsafe_allow_html=True)

    values = {label: st.session_state.get(blank_key(question_index, label), "") for label in labels}
    if not any(is_answered(value) for value in values.values()):
        return ""
    return quiz_logic.compose_blank_answer(values)


# ── Question rendering ─────────────────────────────────────────────────────────

def render_question(quiz: dict, index: int, *, disabled: bool = False):
    with st.container(border=True):
        st.markdown(f"<div class='moodle-qnumber'>Question {index + 1}</div>", unsafe_allow_html=True)
        st.caption(f"Source: {quiz.get('source', 'Generated')} | Topic: {quiz.get('topic', 'General')}")
        st.markdown(f"**{quiz.get('question_text')}**")

        question_type = quiz.get("type", "multiple_choice")
        render_quiz_visual(quiz)
        blank_labels = quiz_logic.blank_labels_for_quiz(quiz)
        if quiz.get("code") and blank_labels and question_type != "multiple_choice":
            return render_inline_blank_code(quiz.get("code", ""), index, blank_labels, disabled=disabled)

        if quiz.get("code"):
            st.code(quiz.get("code"), language="prolog")

        if question_type == "multiple_choice" and quiz.get("blanks_or_options"):
            return st.radio(
                "Answer",
                options=quiz.get("blanks_or_options"),
                index=None,
                key=answer_key(index),
                disabled=disabled,
                label_visibility="collapsed",
            )

        return st.text_input(
            "Answer",
            key=answer_key(index),
            disabled=disabled,
            label_visibility="collapsed",
        )


# ── Quiz navigation panel ──────────────────────────────────────────────────────

def render_quiz_navigation(filtered_quizzes: list[dict], current_index: int) -> None:
    with st.container(border=True):
        st.markdown("<div class='moodle-nav-title'>Quiz navigation</div>", unsafe_allow_html=True)
        answers = st.session_state.get("quiz_answers", {})
        flags = st.session_state.get("quiz_flags", set())

        for row_start in range(0, len(filtered_quizzes), 5):
            cols = st.columns(5)
            for offset, col in enumerate(cols):
                index = row_start + offset
                if index >= len(filtered_quizzes):
                    continue
                answered = is_answered(answers.get(index))
                status = "current" if index == current_index else "answered" if answered else "empty"
                label = quiz_nav_label(index, answered, index in flags)
                button_type = "primary" if index == current_index else "secondary"
                if col.button(label, key=f"quiz_nav_{index}", help=status, type=button_type):
                    st.session_state.current_index = index
                    st.session_state.quiz_summary = False
                    save_official_quiz_state_helper()
                    st.rerun()

        answered_count = sum(1 for index in range(len(filtered_quizzes)) if is_answered(answers.get(index)))
        st.caption(f"✅ answered · {answered_count} of {len(filtered_quizzes)} saved")

        if st.button("Finish attempt ...", type="primary", key="finish_btn_nav"):
            st.session_state.quiz_summary = True
            save_official_quiz_state_helper()
            st.rerun()


# ── Attempt summary + review ───────────────────────────────────────────────────

def render_attempt_summary(filtered_quizzes: list[dict]) -> None:
    st.markdown("#### Summary of attempt")
    answers = st.session_state.get("quiz_answers", {})
    rows = [
        {
            "Question": index + 1,
            "Status": "Answer saved" if is_answered(answers.get(index)) else "Not yet answered",
            "Topic": quiz.get("topic", "General"),
        }
        for index, quiz in enumerate(filtered_quizzes)
    ]
    st.dataframe(rows, hide_index=True, width="stretch")
    st.warning("After submit, the attempt is graded and feedback becomes visible.")
    col_return, col_submit = st.columns([1, 2])
    if col_return.button("Return to attempt"):
        st.session_state.quiz_summary = False
        save_official_quiz_state_helper()
        st.rerun()
    if col_submit.button("Submit all and finish", type="primary"):
        st.session_state.quiz_submitted = True
        st.session_state.quiz_summary = False
        save_official_quiz_state_helper()
        log_quiz_submission(
            quiz_type=f"Official Exam (Topic: {st.session_state.get('last_selected_topic', 'All')})",
            filtered_quizzes=filtered_quizzes,
            answers=st.session_state.get("quiz_answers", {})
        )
        st.rerun()


def render_attempt_review(filtered_quizzes: list[dict]) -> None:
    answers = st.session_state.get("quiz_answers", {})
    score = sum(
        1
        for index, quiz in enumerate(filtered_quizzes)
        if quiz_logic.is_answer_correct(answers.get(index), quiz.get("correct_answer"), quiz.get("type", "multiple_choice"))
    )

    st.success(f"Attempt submitted. Grade: {score:.2f} / {len(filtered_quizzes):.2f}")
    st.progress(score / len(filtered_quizzes))

    for index, quiz in enumerate(filtered_quizzes):
        user_answer = answers.get(index, "")
        is_correct = quiz_logic.is_answer_correct(
            user_answer, quiz.get("correct_answer"), quiz.get("type", "multiple_choice")
        )
        with st.expander(f"Question {index + 1}: {'✅ Correct' if is_correct else '❌ Incorrect'}"):
            st.markdown(quiz.get("question_text", ""))
            render_quiz_visual(quiz)
            if quiz.get("code"):
                st.code(quiz.get("code"), language="prolog")
            st.markdown(f"**Your answer:** `{user_answer or 'Not answered'}`")
            st.markdown(f"**Correct answer:** `{quiz.get('correct_answer')}`")

    if st.button("Start a new attempt"):
        st.session_state.quiz_answers = {}
        st.session_state.quiz_flags = set()
        st.session_state.quiz_submitted = False
        st.session_state.quiz_summary = False
        st.session_state.current_index = 0
        st.session_state.pop("quiz_sample", None)
        clear_quiz_widget_answers()
        
        user_id = get_user_id()
        cache_path = get_official_cache_path(user_id)
        if cache_path.exists():
            try:
                cache_path.unlink()
            except Exception:
                pass
        st.rerun()


# ── Official quiz (max 24 sampled) ────────────────────────────────────────────

def render_official_quiz(quizzes: list[dict]) -> None:
    if not quizzes:
        st.error("⚠️ `quizzes.json` was not found or contains no questions.")
        return

    # Load from persistent cache if session state is empty
    if "quiz_sample" not in st.session_state:
        cached = load_official_quiz_cache()
        if cached:
            batch, answers, flags, index, submitted, summary, topic = cached
            st.session_state.quiz_sample = batch
            st.session_state.quiz_answers = answers
            st.session_state.quiz_flags = flags
            st.session_state.current_index = index
            st.session_state.quiz_submitted = submitted
            st.session_state.quiz_summary = summary
            st.session_state.last_selected_topic = topic
            st.session_state.quiz_topic_selectbox = topic
            restore_blank_answers_for_batch(batch, answers)

    selected_topic = st.selectbox("Topic:", ["All"] + quiz_logic.topics_for(quizzes), key="quiz_topic_selectbox")
    reset_quiz_state_for_topic(selected_topic)
    all_for_topic = quiz_logic.filter_by_topic(quizzes, selected_topic)

    # Sample max 24 and keep stable in session
    if "quiz_sample" not in st.session_state:
        import random
        st.session_state.quiz_sample = random.sample(
            all_for_topic, min(settings.MAX_QUIZ_PER_ATTEMPT, len(all_for_topic))
        )
        st.session_state.quiz_answers = {}
        st.session_state.quiz_flags = set()
        st.session_state.quiz_submitted = False
        st.session_state.quiz_summary = False
        st.session_state.current_index = 0
        st.session_state.last_selected_topic = selected_topic
        save_official_quiz_state_helper()
    filtered_quizzes = st.session_state.quiz_sample

    total = len(all_for_topic)
    showing = len(filtered_quizzes)
    st.caption(f"Showing: **{showing}** of {total} available questions")

    if not filtered_quizzes:
        return

    st.session_state.current_index = min(st.session_state.get("current_index", 0), len(filtered_quizzes) - 1)
    st.session_state.setdefault("quiz_answers", {})
    st.session_state.setdefault("quiz_flags", set())
    st.session_state.setdefault("quiz_submitted", False)
    st.session_state.setdefault("quiz_summary", False)

    if st.session_state.quiz_submitted:
        render_attempt_review(filtered_quizzes)
        return

    if st.session_state.quiz_summary:
        render_attempt_summary(filtered_quizzes)
        return

    current_index = st.session_state.current_index
    quiz = filtered_quizzes[current_index]

    main_col, nav_col = st.columns([3, 1])
    with main_col:
        st.markdown("#### Attempt")
        st.caption(f"Question {current_index + 1} of {len(filtered_quizzes)}")
        restore_answer_widget_for_question(
            quiz,
            current_index,
            st.session_state.get("quiz_answers", {}).get(current_index),
        )
        user_answer = render_question(quiz, current_index)
        save_current_answer(current_index, user_answer)

        col_prev, col_flag, col_next = st.columns([1, 1, 1])
        if col_prev.button("Previous page", disabled=current_index == 0):
            st.session_state.current_index = max(0, current_index - 1)
            save_official_quiz_state_helper()
            st.rerun()
        flag_label = "Remove flag" if current_index in st.session_state.quiz_flags else "Flag question"
        if col_flag.button(flag_label):
            flags = set(st.session_state.quiz_flags)
            if current_index in flags:
                flags.remove(current_index)
            else:
                flags.add(current_index)
            st.session_state.quiz_flags = flags
            save_official_quiz_state_helper()
            st.rerun()
        if current_index < len(filtered_quizzes) - 1:
            if col_next.button("Next page", type="primary"):
                st.session_state.current_index = current_index + 1
                save_official_quiz_state_helper()
                st.rerun()
        elif col_next.button("Finish attempt ...", type="primary", key="finish_btn_main"):
            st.session_state.quiz_summary = True
            save_official_quiz_state_helper()
            st.rerun()

    with nav_col:
        render_quiz_navigation(filtered_quizzes, current_index)


# ── Generated quiz (batch 24) ─────────────────────────────────────────────────


def get_user_id() -> str:
    if "user_id" in st.query_params:
        try:
            del st.query_params["user_id"]
        except Exception:
            pass

    # 1. Try session state
    if "user_id" in st.session_state and st.session_state.user_id:
        return st.session_state.user_id

    # 2. Try cookies (read-only synchronous access via st.context)
    cookie_user_id = None
    if hasattr(st, "context") and st.context and hasattr(st.context, "cookies"):
        raw_cookie = st.context.cookies.get("lp_user_id")
        cookie_user_id = verify_signed_value(raw_cookie)
    
    if cookie_user_id:
        st.session_state.user_id = cookie_user_id
        return cookie_user_id

    # 3. Generate new UUID. Query params are intentionally ignored so callers
    # cannot choose another user's cache/session identity.
    import uuid
    uid = str(uuid.uuid4())
    st.session_state.user_id = uid
    return uid


def is_valid_username(username: str) -> bool:
    username = username.strip()
    return (
        3 <= len(username) <= 25
        and username.lower() not in RESERVED_USERNAMES
        and re.match(r"^[a-zA-Z0-9_ ]+$", username) is not None
    )


AUTHORIZED_STUDENT_HASHES = {
    "5d323cd655174356396585925d0325bae4a81108bc121dcf63f26886f8e3e739",
    "3131ee7e7e41eac372043c3cdea46d13e9bda4ba3f496239b604e78d25cb2186",
    "4177d46d74897aff0e23f98964999e99ac10a0ce244d859d06d8dd026550a377",
    "d6e57c962ce2bb1c1fca67cd4026b28d52fee7e14498390fdd36c5bd6b43b3d9",
    "e5edd15dd79c7b3d02a6f8ff11f367b95df0dab5adb61f53297d0df6f9acb8a8",
    "5418a08ed0f3ad7e831f0e4b67c28a561413620517897b9e4a893085c0c852d0",
    "d0f558ca04a485d4856f93cf0f9c766a3b688624a6d25bee7c5b80b6da5cc5f1",
    "4032608481f3ca92aa1c47a0fcdf16be66d8d8553209e7d5bf6d1518b5dcef44",
    "eb1690c1bbb9406277d731089ff03a67877af1063d84d1a786b469ef80e976f2",
    "39d584d4582ca24c9df3354209fadebe352ff06169434242f4c7489fef3e9b34",
    "cb40db54d345d35b18caebaa5fb96cbfd01152f07c000a6ecc8309f8e71d3dca",
    "2d53c030bdd51d69f205ed010abd218112111a854ca5018791f835a1cd5f8922",
    "ae6487c6d49d4788ced078730472fddee0400842c6cec4d92b8ee86a37c98675",
    "4a8c5381ef6fa76a70965f2232d50b6f05c74c9b7dc13f20c91105481c38106d",
    "e009909453ffdbe48f7b9a8f5befadb7ef128924066c3d35a8c2a74fc29de5b6",
    "835ceae9b4736e95c2a425e97a269bc048cfefb27e3220611d0a2146ea3d8ac2",
    "6f907f50ed8b9942307ab59592e8a5f63d2bc69da4175b6c1bb519cce45c48cd",
    "0cbc5328c3e8e0ffa1393c71aee3b36151c21402b7c8da39df8e4671fce32cd8",
    "0b01309815c16928b81edfe10c4e77f77c004d089e9d3abb2eeaa7b37ce79678",
    "3673a582398619b8fe95512b9c262e0b2ee6cb8786ecb6929833770489ef0cc8",
    "e7c0f9e8dc43d046d844cd5900c212347bda0f9494ae6ea6cef11702203cee85",
    "3a051f423ca0b269a4af6224d82b76d7b2d016b96d456605abaca3ef542dc6fb",
    "aa162a947df987201e0f3855228bc64f2220b33cbfde7909dfb12f82bcf54baf",
    "da0d2dcafb10c3e75eed4f04183c77de280ab49c266a4f598001a0ceef5c4ba7",
    "22887046e0af28c73b4644c6af171b7b18f77b5634ae704afbe84ee1f57708ca",
    "48d4a32336650e685251b3403b0d3dc1112ceedbb824b0ef8e393bc1fda17ce6",
    "7deace29d64b6f52d0ab79b6ae85884eb85a86e1daae44c6f12fb81eb58d4187",
    "51a5b8c387b8dd3d4a7e9de885b39cfb47a6e50d12934fa3838457c909798f27"
}


def get_cookie_secret() -> bytes:
    import os
    secret_path = Path(__file__).resolve().parent / "cookie_secret.txt"
    try:
        if secret_path.exists():
            return secret_path.read_bytes()
    except Exception:
        pass
    import secrets
    secret = secrets.token_bytes(32)
    try:
        secret_path.write_bytes(secret)
        try:
            os.chmod(secret_path, 0o600)
        except Exception:
            pass
    except Exception:
        pass
    return secret


def sign_value(value: str) -> str:
    import hmac
    import hashlib
    secret = get_cookie_secret()
    signature = hmac.new(secret, value.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"{value}|{signature}"


def verify_signed_value(signed_value: str | None) -> str | None:
    if not signed_value or "|" not in signed_value:
        return None
    try:
        import hmac
        import hashlib
        value, signature = signed_value.rsplit("|", 1)
        secret = get_cookie_secret()
        expected = hmac.new(secret, value.encode('utf-8'), hashlib.sha256).hexdigest()
        if hmac.compare_digest(signature, expected):
            return value
    except Exception:
        pass
    return None


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    replacements = {
        'ă': 'a', 'â': 'a', 'î': 'i', 'ș': 's', 'ț': 't',
        'ş': 's', 'ţ': 't', 'ã': 'a'
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    text = re.sub(r'[^a-z0-9]', '', text)
    return text


def clean_phone(phone: str) -> str:
    if not phone:
        return ""
    digits = "".join(c for c in phone if c.isdigit())
    return digits[-9:] if len(digits) >= 9 else digits


def generate_student_uuid(nume: str, prenume: str, phone: str) -> str:
    import uuid
    norm_nume = normalize_text(nume)
    norm_prenume = normalize_text(prenume)
    norm_phone = clean_phone(phone)
    key = f"{norm_nume}-{norm_prenume}-{norm_phone}"
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, key))


def find_student_match(nume: str, prenume: str, phone: str) -> dict | None:
    norm_nume = normalize_text(nume)
    norm_prenume = normalize_text(prenume)
    norm_phone = clean_phone(phone)
    
    if not norm_nume or not norm_prenume or not norm_phone:
        return None
        
    key = f"{norm_nume}-{norm_prenume}-{norm_phone}"
    h = hashlib.sha256(key.encode('utf-8')).hexdigest()
    
    if h in AUTHORIZED_STUDENT_HASHES:
        return {
            "nume": nume.strip().title(),
            "prenume": prenume.strip().title(),
            "telefon": phone.strip()
        }
    return None


def cookie_username_is_usable(user_id: str, username: str | None) -> bool:
    if not username or not is_valid_username(username):
        return False
    db_username = telemetry.get_user_username(user_id)
    if db_username == username:
        return True
    if telemetry.check_username_exists(username):
        return False
    return db_username is None or db_username == telemetry.generate_random_username(user_id)


def get_secure_cache_dir() -> Path:
    cache_dir = APP_DIR / "cache"
    try:
        if not cache_dir.exists():
            cache_dir.mkdir(parents=True, exist_ok=True)
            try:
                import os
                os.chmod(cache_dir, 0o700)
            except Exception:
                pass
    except Exception:
        pass
    return cache_dir


def get_quiz_cache_path(user_id: str) -> Path:
    return get_secure_cache_dir() / f"gen_cache_{user_id}.json"


def get_official_cache_path(user_id: str) -> Path:
    return get_secure_cache_dir() / f"official_cache_{user_id}.json"


def save_official_quiz_cache(batch: list[dict], answers: dict, flags: set[int], index: int, submitted: bool, summary: bool, topic: str) -> None:
    user_id = get_user_id()
    cache_path = get_official_cache_path(user_id)
    data = {
        "batch": batch,
        "answers": answers,
        "flags": list(flags),
        "index": index,
        "submitted": submitted,
        "summary": summary,
        "topic": topic,
    }
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_official_quiz_cache() -> tuple[list[dict], dict, set[int], int, bool, bool, str] | None:
    user_id = get_user_id()
    cache_path = get_official_cache_path(user_id)
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        raw_answers = data.get("answers", {})
        answers = {int(k): v for k, v in raw_answers.items()}
        flags = set(data.get("flags", []))
        return (
            data.get("batch", []),
            answers,
            flags,
            data.get("index", 0),
            data.get("submitted", False),
            data.get("summary", False),
            data.get("topic", "All"),
        )
    except Exception:
        return None


def save_official_quiz_state_helper() -> None:
    if "quiz_sample" in st.session_state:
        save_official_quiz_cache(
            batch=st.session_state.quiz_sample,
            answers=st.session_state.get("quiz_answers", {}),
            flags=st.session_state.get("quiz_flags", set()),
            index=st.session_state.get("current_index", 0),
            submitted=st.session_state.get("quiz_submitted", False),
            summary=st.session_state.get("quiz_summary", False),
            topic=st.session_state.get("last_selected_topic", "All"),
        )


def restore_blank_answers_for_batch(batch: list[dict], answers: dict) -> None:
    for question_index, quiz in enumerate(batch):
        composed = answers.get(question_index, "")
        if not composed:
            continue
        
        parsed = {}
        for part in composed.split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                parsed[k.strip().lower()] = v.strip()
                
        blank_labels = quiz_logic.blank_labels_for_quiz(quiz)
        question_type = quiz.get("type", "multiple_choice")
        if quiz.get("code") and blank_labels and question_type != "multiple_choice":
            for label in blank_labels:
                lbl_lower = label.lower()
                if lbl_lower in parsed:
                    st.session_state[blank_key(question_index, lbl_lower)] = parsed[lbl_lower]


def save_generated_quiz_cache(batch: list[dict], answers: dict, index: int, submitted: bool) -> None:
    user_id = get_user_id()
    cache_path = get_quiz_cache_path(user_id)
    data = {
        "batch": batch,
        "answers": answers,
        "index": index,
        "submitted": submitted,
    }
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_generated_quiz_cache() -> tuple[list[dict], dict, int, bool]:
    user_id = get_user_id()
    cache_path = get_quiz_cache_path(user_id)
    if not cache_path.exists():
        return [], {}, 0, False
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        raw_answers = data.get("answers", {})
        answers = {int(k): v for k, v in raw_answers.items()}
        return data.get("batch", []), answers, data.get("index", 0), data.get("submitted", False)
    except Exception:
        return [], {}, 0, False


def _admin_session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_admin_session_path(token: str) -> Path:
    return get_secure_cache_dir() / f"admin_session_{_admin_session_token_hash(token)}.json"


def _get_admin_session_token() -> str | None:
    token = st.session_state.get(ADMIN_SESSION_COOKIE)
    if token:
        return token
    if hasattr(st, "context") and st.context and hasattr(st.context, "cookies"):
        token = st.context.cookies.get(ADMIN_SESSION_COOKIE)
        if token:
            st.session_state[ADMIN_SESSION_COOKIE] = token
            return token
    return None


def save_admin_session(user_id: str) -> None:
    _ = user_id
    token = secrets.token_urlsafe(32)
    st.session_state[ADMIN_SESSION_COOKIE] = token
    try:
        CookieController().set(ADMIN_SESSION_COOKIE, token)
    except Exception:
        pass
    path = get_admin_session_path(token)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"authenticated": True, "login_time": time.time()}, f)
    except Exception:
        pass


def is_admin_session_valid(user_id: str) -> bool:
    _ = user_id
    token = _get_admin_session_token()
    if not token:
        return False
    path = get_admin_session_path(token)
    if not path.exists():
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("authenticated") and time.time() - data.get("login_time", 0) < ADMIN_SESSION_TTL_SECONDS:
            return True
    except Exception:
        pass
    return False


def clear_admin_session(user_id: str) -> None:
    _ = user_id
    token = _get_admin_session_token()
    try:
        if token:
            path = get_admin_session_path(token)
            if path.exists():
                path.unlink()
        st.session_state.pop(ADMIN_SESSION_COOKIE, None)
        try:
            CookieController().remove(ADMIN_SESSION_COOKIE)
        except Exception:
            pass
    except Exception:
        pass


def cleanup_legacy_admin_session(user_id: str) -> None:
    import tempfile
    path = Path(tempfile.gettempdir()) / f"admin_session_{user_id}.json"
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


def cleanup_old_caches() -> None:
    """Remove generated, official, and admin session files older than 2 hours."""
    try:
        now = time.time()
        cachedir = get_secure_cache_dir()
        for pattern in ("gen_cache_*.json", "official_cache_*.json", "admin_session_*.json"):
            for path in cachedir.glob(pattern):
                if now - path.stat().st_mtime > 7200:
                    path.unlink()
    except Exception:
        pass


def render_generated_quiz(collection, quizzes: list[dict], api_key: str) -> None:
    if not api_key:
        st.warning("⚠️ `GEMINI_API_KEY` is not set.")
        return

    # Load from persistent cache if session state is empty
    if "generated_batch" not in st.session_state:
        batch, answers, index, submitted = load_generated_quiz_cache()
        if batch:
            st.session_state.generated_batch = batch
            st.session_state.gen_answers = answers
            st.session_state.gen_index = index
            st.session_state.gen_submitted = submitted
            restore_blank_answers_for_batch(batch, answers)

    st.caption("Generate 24 new questions from all lectures, following the official exam pattern.")

    # ── Slide selection
    gen_query = st.text_input(
        "Concept to search (seed):",
        value="Prolog",
        placeholder="e.g. backtracking, lists, cut...",
    )

    seed_slides_all = vector_store.search_slides(collection, gen_query, 30) if gen_query else []
    if not seed_slides_all:
        st.info("Enter a term to find source slides.")
        return

    # Pick diverse slides for the batch
    target_slides = quiz_logic.select_diverse_slides(seed_slides_all, settings.MAX_BATCH_TOTAL)

    with st.expander(f"📚 {len(target_slides)} slides selected from various lectures"):
        for s in target_slides[:6]:
            st.caption(f"• {s.source} pag. {s.page} — {s.title}")
        if len(target_slides) > 6:
            st.caption(f"... and {len(target_slides) - 6} others")

    if st.button("🚀 Generate 24 questions", type="primary"):
        batch: list[dict] = []
        progress = st.progress(0, text="Generating...")
        status_text = st.empty()

        examples_text = quiz_logic.few_shot_examples(quizzes, "multiple_choice")
        status_text.caption("Sending the 24 slides to Gemini...")

        try:
            current_model = st.session_state.get("selected_model", settings.GEMINI_MODEL)
            new_qs = llm_client.generate_quiz_batch(
                api_key,
                current_model,
                target_slides,
                examples_text,
            )
            batch.extend(new_qs)

            # Complement if Gemini generated fewer questions (e.g. 20 instead of 24)
            if len(batch) < len(target_slides) and len(batch) > 0:
                remaining_slides = target_slides[len(batch):]
                status_text.caption(f"Generated only {len(batch)} questions. Completing the remaining {len(remaining_slides)}...")
                extra_qs = llm_client.generate_quiz_batch(
                    api_key,
                    current_model,
                    remaining_slides,
                    examples_text,
                )
                batch.extend(extra_qs)
        except Exception as exc:
            msg, _ = llm_client.parse_api_error(exc)
            st.error(f"❌ {msg}")

        progress.empty()
        status_text.empty()

        if not batch:
            st.error(
                "❌ No questions were generated. This usually means the API returned an "
                "empty or malformed response. Check your API quota in "
                "[AI Studio](https://aistudio.google.com/rate-limit) and try again."
            )
            return

        st.session_state.generated_batch = batch[:settings.MAX_BATCH_TOTAL]
        st.session_state.gen_index = 0
        st.session_state.gen_answers = {}
        st.session_state.gen_submitted = False
        save_generated_quiz_cache(
            st.session_state.generated_batch,
            st.session_state.gen_answers,
            st.session_state.gen_index,
            st.session_state.gen_submitted,
        )
        
        # Log quiz generation event
        try:
            telemetry.log_event(
                user_id=get_user_id(),
                ip=get_client_ip(),
                event_type="quiz_gen",
                query=gen_query,
                details={
                    "questions_count": len(st.session_state.generated_batch),
                    "model": current_model,
                    "slides_used": [{"source": s.source, "page": s.page, "title": s.title} for s in target_slides],
                    "questions": [
                        {
                            "text": q.get("question_text", ""),
                            "code": q.get("code"),
                            "visual": q.get("visual"),
                            "options": q.get("blanks_or_options"),
                            "correct": q.get("correct_answer")
                        }
                        for q in st.session_state.generated_batch
                    ]
                }
            )
        except Exception:
            pass
        
        if len(batch) < settings.MAX_BATCH_TOTAL:
            st.warning(f"⚠️ Generated {len(batch)} of {settings.MAX_BATCH_TOTAL} questions (partial response).")
        else:
            st.success(f"✅ {len(st.session_state.generated_batch)} questions generated successfully!")
        st.rerun()

    # ── Navigate generated batch
    batch = st.session_state.get("generated_batch")
    if not batch:
        return

    st.markdown("---")
    gen_submitted = st.session_state.get("gen_submitted", False)

    if gen_submitted:
        # Review mode
        answers = st.session_state.get("gen_answers", {})
        score = sum(
            1
            for i, q in enumerate(batch)
            if quiz_logic.is_answer_correct(answers.get(i), q.get("correct_answer"), q.get("type", "multiple_choice"))
        )
        st.success(f"Grade: {score} / {len(batch)}")
        st.progress(score / len(batch))
        for i, q in enumerate(batch):
            user_ans = answers.get(i, "")
            ok = quiz_logic.is_answer_correct(user_ans, q.get("correct_answer"), q.get("type", "multiple_choice"))
            with st.expander(f"Q{i+1}: {'✅' if ok else '❌'} {q.get('question_text', '')[:60]}..."):
                render_quiz_visual(q)
                if q.get("code"):
                    st.code(q["code"], language="prolog")
                st.markdown(f"**Your answer:** `{user_ans or 'Unanswered'}`")
                st.markdown(f"**Correct:** `{q.get('correct_answer')}`")
        if st.button("🔄 New attempt"):
            st.session_state.gen_submitted = False
            st.session_state.gen_answers = {}
            st.session_state.gen_index = 0
            save_generated_quiz_cache(batch, {}, 0, False)
            st.rerun()
        return

    # Active quiz mode for generated batch
    gen_index = st.session_state.get("gen_index", 0)
    quiz = batch[gen_index]

    main_col, nav_col = st.columns([3, 1])
    with main_col:
        st.markdown("#### Attempt (generated)")
        st.caption(f"Question {gen_index + 1} of {len(batch)}")
        restore_answer_widget_for_question(
            quiz,
            gen_index,
            st.session_state.get("gen_answers", {}).get(gen_index),
        )
        user_answer = render_question(quiz, gen_index)

        # Save answer
        gen_answers = dict(st.session_state.get("gen_answers", {}))
        if gen_answers.get(gen_index) != (user_answer or ""):
            gen_answers[gen_index] = user_answer or ""
            st.session_state.gen_answers = gen_answers
            save_generated_quiz_cache(batch, gen_answers, gen_index, gen_submitted)

        col_prev, col_next = st.columns(2)
        if col_prev.button("← Previous", disabled=gen_index == 0):
            st.session_state.gen_index = gen_index - 1
            save_generated_quiz_cache(batch, gen_answers, gen_index - 1, gen_submitted)
            st.rerun()
        if gen_index < len(batch) - 1:
            if col_next.button("Next →", type="primary"):
                st.session_state.gen_index = gen_index + 1
                save_generated_quiz_cache(batch, gen_answers, gen_index + 1, gen_submitted)
                st.rerun()
        else:
            if col_next.button("Finish & Submit", type="primary"):
                st.session_state.gen_submitted = True
                save_generated_quiz_cache(batch, gen_answers, gen_index, True)
                log_quiz_submission(
                    quiz_type="Generated Quiz",
                    filtered_quizzes=batch,
                    answers=gen_answers
                )
                st.rerun()

    with nav_col:
        with st.container(border=True):
            st.markdown("<div class='moodle-nav-title'>Navigation</div>", unsafe_allow_html=True)
            gen_answers = st.session_state.get("gen_answers", {})
            for row_start in range(0, len(batch), 5):
                cols = st.columns(5)
                for offset, col in enumerate(cols):
                    idx = row_start + offset
                    if idx >= len(batch):
                        continue
                    answered = is_answered(gen_answers.get(idx))
                    status = "current" if idx == gen_index else "answered" if answered else "empty"
                    button_type = "primary" if idx == gen_index else "secondary"
                    if col.button(quiz_nav_label(idx, answered), key=f"gen_nav_{idx}", help=status, type=button_type):
                        st.session_state.gen_index = idx
                        save_generated_quiz_cache(batch, gen_answers, idx, gen_submitted)
                        st.rerun()
            answered = sum(1 for idx in range(len(batch)) if is_answered(gen_answers.get(idx)))
            st.caption(f"✅ answered · {answered} / {len(batch)} saved")


# ── Quiz tab ───────────────────────────────────────────────────────────────────

def render_quiz_tab(collection, api_key: str) -> None:
    try:
        quizzes = cached_load_quizzes(
            str(settings.QUIZZES_PATH),
            settings.QUIZZES_PATH.stat().st_mtime if settings.QUIZZES_PATH.exists() else None,
        )
    except Exception as exc:
        st.error(f"Error reading quizzes.json: {exc}")
        quizzes = []

    mode = st.radio(
        "Mode:",
        ["Official exam", "Generate new questions"],
        horizontal=True,
        label_visibility="collapsed",
    )

    if mode == "Official exam":
        render_official_quiz(quizzes)
    else:
        render_generated_quiz(collection, quizzes, api_key)


# ── Admin Dashboard ─────────────────────────────────────────────────────────────

def is_public_ip(ip_str: str) -> bool:
    import ipaddress
    try:
        ip = ipaddress.ip_address(ip_str)
        return not (ip.is_private or ip.is_loopback or ip.is_link_local)
    except ValueError:
        return False

def format_ip(ip_str: str) -> str:
    if not ip_str:
        return "Unknown"
    is_pub = is_public_ip(ip_str)
    return f"{ip_str} ({'Public' if is_pub else 'Private'})"


def render_admin_login(user_id: str, subtitle: str) -> None:
    import pyotp

    st.markdown(
        "<div class='admin-shell'>"
        "<div class='admin-kicker'>Admin console</div>"
        "<div class='admin-title'>Analytics and controls</div>"
        f"<div class='admin-subtitle'>{html.escape(subtitle)}</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    # Try st.secrets first, then fall back to os.environ
    admin_pwd = ""
    totp_secret = ""
    try:
        if "ADMIN_PASSWORD" in st.secrets:
            admin_pwd = st.secrets["ADMIN_PASSWORD"]
        if "ADMIN_TOTP_SECRET" in st.secrets:
            totp_secret = st.secrets["ADMIN_TOTP_SECRET"]
    except Exception:
        pass

    if not admin_pwd:
        admin_pwd = os.environ.get("ADMIN_PASSWORD", "")
    if not totp_secret:
        totp_secret = os.environ.get("ADMIN_TOTP_SECRET", "")

    # Clean secrets from any wrapping quotes or whitespace
    if isinstance(admin_pwd, str):
        admin_pwd = admin_pwd.strip().strip('"').strip("'")
    if isinstance(totp_secret, str):
        totp_secret = totp_secret.strip().strip('"').strip("'")

    if not admin_pwd or not totp_secret:
        st.info("Setup required")
        if "temp_totp_secret" not in st.session_state:
            st.session_state.temp_totp_secret = pyotp.random_base32()
        st.code(
            f"ADMIN_PASSWORD=your_secure_password\n"
            f"ADMIN_TOTP_SECRET={st.session_state.temp_totp_secret}"
        )
        st.markdown(
            "Once configured, add the secret to your Google Authenticator/2FA app manually."
        )
        return

    st.markdown("<div class='admin-section-title'>Admin login</div>", unsafe_allow_html=True)
    with st.form("admin_login_form"):
        password = st.text_input("Admin Password:", type="password")
        otp_code = st.text_input("2FA OTP Code (Google Authenticator):", max_chars=6)
        submit = st.form_submit_button("Authenticate")

        if submit:
            totp = pyotp.TOTP(totp_secret)
            # Use valid_window=2 to allow for clock drift (up to 60 seconds tolerance)
            if password == admin_pwd and totp.verify(otp_code.strip(), valid_window=2):
                st.session_state.is_admin = True
                save_admin_session(user_id)
                cleanup_legacy_admin_session(user_id)
                try:
                    telemetry.get_or_create_user(user_id, get_client_ip())
                    telemetry.update_user_username(user_id, "Admin")
                except Exception:
                    pass
                st.success("Authenticated successfully.")
                st.rerun()
            else:
                st.error("Invalid password or 2FA code.")


@st.fragment(run_every=5)
def render_live_data(selected_events, selected_users, selected_ips, search_query):
    """Auto-refreshing fragment: re-queries DB and redraws every 5 seconds."""
    import psutil
    import pandas as pd

    # Log current server metrics
    try:
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory().percent
        active_sessions = get_active_sessions_count()
        telemetry.log_server_metrics(cpu, ram, active_sessions)
    except Exception:
        cpu, ram, active_sessions = 0.0, 0.0, 1

    # Telemetry summary metrics
    st.markdown("<div class='admin-section-title'>Telemetry summary</div>", unsafe_allow_html=True)
    st.markdown("<div class='admin-live-note'>Live data, refreshed every 5 seconds.</div>", unsafe_allow_html=True)
    sum_data = telemetry.get_dashboard_summary()
    metrics = [
        ("Unique users", sum_data["unique_users"]),
        ("Visits", sum_data.get("total_visits", 0)),
        ("Searches", sum_data["total_searches"]),
        ("Q&As", sum_data["total_qa"]),
        ("Quiz gens", sum_data["total_quiz_gens"]),
        ("Submits", sum_data.get("total_submits", 0)),
    ]
    metric_cards = "".join(
        "<div class='admin-metric-card'>"
        f"<div class='admin-metric-label'>{html.escape(label)}</div>"
        f"<div class='admin-metric-value'>{value}</div>"
        "</div>"
        for label, value in metrics
    )
    st.markdown(f"<div class='admin-metrics-grid'>{metric_cards}</div>", unsafe_allow_html=True)

    # Charts & Top Users
    col_chart, col_users = st.columns([2, 1])

    with col_chart:
        st.markdown("<div class='admin-section-title'>Server resource history</div>", unsafe_allow_html=True)
        metrics_history = telemetry.get_recent_server_metrics(50)
        if metrics_history:
            cpu_vals = [m["cpu_percent"] for m in reversed(metrics_history)]
            ram_vals = [m["ram_percent"] for m in reversed(metrics_history)]
            sessions_vals = [m["active_sessions"] for m in reversed(metrics_history)]
            timestamps = [m["timestamp"].split("T")[-1][:5] for m in reversed(metrics_history)]
            df = pd.DataFrame(
                {"CPU %": cpu_vals, "RAM %": ram_vals, "Active Sessions": sessions_vals},
                index=timestamps
            )
            st.line_chart(df)
        else:
            st.caption("No history logged yet.")

    with col_users:
        st.markdown("<div class='admin-section-title'>Top active users</div>", unsafe_allow_html=True)
        top_users = telemetry.get_top_users(10)
        if top_users:
            formatted_top_users = []
            for r in top_users:
                formatted_top_users.append(
                    {
                        "Nume și prenume": r.get("random_username", "Unknown"),
                        "Last IP": format_ip(r.get("last_ip")),
                        "Events": r.get("total_activities", 0),
                        "Visits": r.get("visits", 0),
                    }
                )
            df_users = pd.DataFrame(formatted_top_users)
            st.dataframe(df_users, hide_index=True, width="stretch")
        else:
            st.caption("No user activity yet.")

    # Detailed activity logs
    st.markdown("<div class='admin-divider'></div>", unsafe_allow_html=True)
    st.markdown("<div class='admin-section-title'>Recent activity logs</div>", unsafe_allow_html=True)
    recent_logs = telemetry.get_recent_activity(200)
    if recent_logs:
        filtered_logs = recent_logs
        if selected_events:
            filtered_logs = [l for l in filtered_logs if l["event_type"].upper() in selected_events]
        if selected_users:
            filtered_logs = [l for l in filtered_logs if l["random_username"] in selected_users]
        if selected_ips:
            filtered_logs = [l for l in filtered_logs if l["ip"] in selected_ips]
        if search_query:
            q_lower = search_query.lower()
            filtered_logs = [
                l for l in filtered_logs
                if q_lower in l["query"].lower() or q_lower in json.dumps(l.get("details", {})).lower()
            ]

        st.markdown(
            f"<div class='admin-log-count'>Showing {len(filtered_logs)} of {len(recent_logs)} loaded logs.</div>",
            unsafe_allow_html=True,
        )

        if filtered_logs:
            table_rows = []
            for log in filtered_logs:
                ts = log["timestamp"].replace("T", " ")[:19]
                table_rows.append(
                    {
                        "Time": ts,
                        "Nume și prenume": log["random_username"],
                        "IP": format_ip(log["ip"]),
                        "Event": log["event_type"].upper(),
                        "Query": log["query"] or "-",
                    }
                )
            st.dataframe(pd.DataFrame(table_rows), hide_index=True, width="stretch")

            st.markdown("<div class='admin-filter-note'>Open a row below for raw input and system output details.</div>", unsafe_allow_html=True)
            for log in filtered_logs:
                ts = log["timestamp"].replace("T", " ")[:19]
                username = log["random_username"]
                ip = format_ip(log["ip"])
                event = log["event_type"].upper()
                query_text = log["query"]
                details = log.get("details", {})

                with st.expander(f"[{ts}] {username} ({ip}) — {event}"):
                    col_in, col_out = st.columns(2)
                    with col_in:
                        st.markdown("**User input**")
                        if event == "SEARCH":
                            st.info(f"Search concept: **{query_text}**")
                        elif event == "QA":
                            st.info(f"Question: **{query_text}**")
                        elif event == "QUIZ_GEN":
                            st.info(f"Quiz seed query: **{query_text}**")
                        elif event == "QUIZ_SUBMIT":
                            st.info(f"Submitted quiz: **{query_text}**")
                        elif event == "VISIT":
                            st.info("Direct Page Visit")
                    with col_out:
                        st.markdown("**System output**")
                        if event == "QA":
                            ans = details.get("answer", "No answer details logged.")
                            st.write(ans)
                            st.caption(f"Model: {details.get('model', 'unknown')} | Cached: {details.get('cached', False)}")
                        elif event == "SEARCH":
                            slides = details.get("top_slides", [])
                            if slides:
                                for idx, s in enumerate(slides, 1):
                                    st.write(f"{idx}. {s.get('source')} (p. {s.get('page')}) — {s.get('title')}")
                            else:
                                st.write(f"Matched {details.get('slides_count', 0)} slides.")
                        elif event == "QUIZ_GEN":
                            st.write(f"Generated {details.get('questions_count', 0)} questions.")
                            questions = details.get("questions", [])
                            if questions:
                                for idx, q in enumerate(questions, 1):
                                    if isinstance(q, dict):
                                        st.write(f"**Q{idx}:** {q.get('text')}")
                                        if q.get("code"):
                                            st.code(q.get("code"), language="prolog")
                                        if q.get("options"):
                                            st.write(f"Options: {', '.join(q.get('options'))}")
                                        st.write(f"Correct: `{q.get('correct')}`")
                                    else:
                                        st.write(f"{idx}. {q}")
                            else:
                                slides = details.get("slides_used", [])
                                if slides:
                                    st.write("Slides used for generation:")
                                    for s in slides[:3]:
                                        st.write(f"- {s.get('source')} (p. {s.get('page')})")
                        elif event == "QUIZ_SUBMIT":
                            st.write(f"Grade: **{details.get('score', 0)} / {details.get('total_questions', 0)}**")
                            attempts = details.get("attempts", [])
                            if attempts:
                                for idx, att in enumerate(attempts, 1):
                                    user_ans = att.get("user_answer", "Unanswered")
                                    correct_ans = att.get("correct_answer", "")
                                    is_correct = att.get("is_correct", False)
                                    icon = "✅" if is_correct else "❌"
                                    st.write(f"**Q{idx}:** {att.get('question_text')}")
                                    if att.get("code"):
                                        st.code(att.get("code"), language="prolog")
                                    if att.get("options"):
                                        st.write(f"Options: {', '.join(att.get('options'))}")
                                    st.write(f"{icon} **User answer:** `{user_ans}` | **Correct answer:** `{correct_ans}`")
                        elif event == "VISIT":
                            st.write("Visited the platform.")
                            st.caption(f"User Agent: {details.get('user_agent', 'unknown')}")
        else:
            st.caption("No logs match the selected filters.")
    else:
        st.caption("No recent logs found.")


def render_admin_dashboard() -> None:
    st.markdown(
        "<div class='admin-shell'>"
        "<div class='admin-kicker'>Admin console</div>"
        "<div class='admin-title'>Analytics and controls</div>"
        "<div class='admin-subtitle'>Monitor usage, filter telemetry, and run maintenance actions.</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    # Check if user session is already verified and valid
    user_id = get_user_id()
    if is_admin_session_valid(user_id):
        st.session_state.is_admin = True

    # Authentication check
    if not st.session_state.get("is_admin", False):
        render_admin_login(user_id, "Authenticate to monitor usage and run maintenance actions.")
        return

    # Layout: Reindex & Stats Summary
    col_btn, col_main = st.columns([1, 3])
    with col_btn:
        with st.container(border=True):
            st.markdown("<div class='admin-section-title'>System</div>", unsafe_allow_html=True)
            with st.form("admin_reindex_form"):
                reindex_confirm = st.text_input("Type REINDEX to re-index documents", key="admin_reindex_confirm")
                reindex_submit = st.form_submit_button("Re-index documents", type="primary", width="stretch")
                if reindex_submit:
                    if reindex_confirm != "REINDEX":
                        st.warning("Type REINDEX to confirm.")
                    else:
                        with st.spinner("Re-indexing..."):
                            result = run_indexing()
                        if result.returncode == 0:
                            st.success("Indexing completed successfully.")
                            st.cache_resource.clear()
                            st.cache_data.clear()
                        else:
                            st.error("Error during indexing:")
                            st.code(result.stderr)

            if st.button("Logout", width="stretch", key="admin_logout_btn"):
                st.session_state.is_admin = False
                user_id = get_user_id()
                clear_admin_session(user_id)
                try:
                    guest_name = telemetry.generate_random_username(user_id)
                    telemetry.update_user_username(user_id, guest_name)
                except Exception:
                    pass
                if st.session_state.get("username") == "Admin":
                    st.session_state.username = None
                st.rerun()

        with st.container(border=True):
            st.markdown("<div class='admin-section-title'>Connection Diagnostics</div>", unsafe_allow_html=True)
            with st.expander("Show headers and network details"):
                st.write("Resolved IP:", get_client_ip())
                st.write("st.context.ip_address:", st.context.ip_address if hasattr(st, "context") and hasattr(st.context, "ip_address") else "N/A")
                
                # Show headers from st.context.headers
                if hasattr(st, "context") and hasattr(st.context, "headers") and st.context.headers:
                    st.write("st.context.headers:")
                    clean_headers = {k: v for k, v in st.context.headers.items() if k.lower() not in ["cookie", "authorization", "sec-websocket-key"]}
                    st.json(clean_headers)
                else:
                    st.write("st.context.headers is empty or unavailable.")
                    
                # Show headers from WebSocket
                try:
                    from streamlit.web.server.websocket_headers import _get_websocket_headers
                    headers_ws = _get_websocket_headers()
                    if headers_ws:
                        st.write("WebSocket headers:")
                        clean_ws = {k: v for k, v in headers_ws.items() if k.lower() not in ["cookie", "authorization", "sec-websocket-key"]}
                        st.json(clean_ws)
                    else:
                        st.write("WebSocket headers are empty.")
                except Exception as e:
                    st.write("Error getting WebSocket headers:", str(e))

        with st.container(border=True):
            st.markdown(
                "<div class='admin-danger-title'>Danger zone</div>"
                "<div class='admin-danger-copy'>Destructive maintenance actions. Confirm each action explicitly.</div>",
                unsafe_allow_html=True,
            )
            st.markdown("<div class='admin-section-title'>Delete user</div>", unsafe_allow_html=True)
            with st.form("admin_delete_user_form"):
                del_username = st.text_input("Username to delete", placeholder="e.g. lloyd1515", key="delete_user_input")
                delete_confirm = st.text_input("Type DELETE <username> to confirm", key="delete_user_confirm")
                delete_submit = st.form_submit_button("Delete user", type="secondary", width="stretch")
                if delete_submit:
                    expected = f"DELETE {del_username}"
                    if not del_username:
                        st.warning("Please enter a username.")
                    elif delete_confirm != expected:
                        st.warning(f"Type {expected} to confirm.")
                    elif telemetry.delete_user_by_username(del_username):
                        st.success(f"User '{del_username}' deleted.")
                        st.rerun()
                    else:
                        st.error(f"User '{del_username}' not found.")

            st.markdown("<div class='admin-divider'></div>", unsafe_allow_html=True)
            st.markdown("<div class='admin-section-title'>Clean database</div>", unsafe_allow_html=True)
            with st.form("admin_delete_guests_form"):
                guests_confirm = st.text_input("Type DELETE GUESTS to confirm", key="delete_guests_confirm")
                guests_submit = st.form_submit_button("Delete all guests", type="secondary", width="stretch")
                if guests_submit:
                    if guests_confirm != "DELETE GUESTS":
                        st.warning("Type DELETE GUESTS to confirm.")
                    else:
                        deleted_count = telemetry.delete_guest_users()
                        st.success(f"Deleted {deleted_count} guest users and orphan logs.")
                        st.rerun()

    with col_main:
        st.markdown("<div class='admin-section-title'>Telemetry filters</div>", unsafe_allow_html=True)
        st.markdown("<div class='admin-filter-note'>Narrow the dashboard by event type, user, IP, or text inside queries and details.</div>", unsafe_allow_html=True)
        # Load recent activity logs once to populate filter choices
        recent_logs_for_filters = telemetry.get_recent_activity(200)
        
        all_events = sorted(list({log["event_type"].upper() for log in recent_logs_for_filters}))
        all_users = sorted(list({log["random_username"] for log in recent_logs_for_filters}))
        all_ips = sorted(list({log["ip"] for log in recent_logs_for_filters}))

        # Display filtering widget row
        with st.container(border=True):
            col_f1, col_f2, col_f3, col_f4 = st.columns(4)
            with col_f1:
                selected_events = st.multiselect("Event Type", options=all_events, placeholder="All", key="filter_event_type")
            with col_f2:
                selected_users = st.multiselect("Nume și prenume", options=all_users, placeholder="All", key="filter_user")
            with col_f3:
                selected_ips = st.multiselect("IP Address", options=all_ips, format_func=format_ip, placeholder="All", key="filter_ip")
            with col_f4:
                search_query = st.text_input("Search Input/Output Text", placeholder="Search query or details...", key="filter_search")

        # Invoke top-level fragment — auto-refreshes every 5 seconds
        render_live_data(selected_events, selected_users, selected_ips, search_query)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    # Fetch public IP client-side once per session using streamlit-javascript
    if "public_ip" not in st.session_state:
        try:
            from streamlit_javascript import st_javascript
            fetched_ip = st_javascript("await fetch('https://api.ipify.org?format=json').then(r => r.json()).then(d => d.ip)")
            if fetched_ip and isinstance(fetched_ip, str) and fetched_ip != "0" and len(fetched_ip) >= 7:
                st.session_state.public_ip = fetched_ip.strip()
                # Update the IP in telemetry
                user_id = get_user_id()
                try:
                    telemetry.get_or_create_user(user_id, st.session_state.public_ip)
                except Exception:
                    pass
        except Exception:
            pass

    # Log initial visit
    if "logged_visit" not in st.session_state:
        st.session_state.logged_visit = True
        try:
            telemetry.log_event(
                user_id=get_user_id(),
                ip=get_client_ip(),
                event_type="visit",
                query="Page load",
                details={
                    "user_agent": st.context.headers.get("User-Agent", "unknown") if (hasattr(st, "context") and st.context and st.context.headers) else "unknown"
                }
            )
        except Exception:
            pass

    cleanup_old_caches()
    render_header()

    # ── Client-side Cookie & User ID Sync ──
    user_id = get_user_id()
    controller = CookieController()

    # Ensure user_id cookie is saved
    try:
        raw_cookie = st.context.cookies.get("lp_user_id") if (hasattr(st, "context") and st.context and hasattr(st.context, "cookies")) else None
        cookie_user_id = verify_signed_value(raw_cookie)
        if not cookie_user_id:
            controller.set("lp_user_id", sign_value(user_id))
    except Exception:
        pass

    # Check if we are in admin mode (direct login URL or valid session)
    admin_requested = st.query_params.get("admin") == "1"
    has_admin_session = is_admin_session_valid(user_id) or st.session_state.get("is_admin", False)
    if has_admin_session:
        st.session_state.is_admin = True
        st.session_state.username = "Admin"
        try:
            db_username = telemetry.get_user_username(user_id)
            if db_username != "Admin":
                telemetry.get_or_create_user(user_id, get_client_ip())
                telemetry.update_user_username(user_id, "Admin")
        except Exception:
            pass
    elif admin_requested:
        render_admin_login(user_id, "Authenticate to monitor usage and run maintenance actions.")
        return
    else:
        # Check if they have a custom username (from session state, cookies or DB)
        has_custom = False
        if "username" in st.session_state and st.session_state.username and st.session_state.username != telemetry.generate_random_username(user_id):
            has_custom = True
        else:
            raw_cookie = st.context.cookies.get("lp_username") if (hasattr(st, "context") and st.context and hasattr(st.context, "cookies")) else None
            cookie_username = verify_signed_value(raw_cookie)
            # If they have a cookie username, check if we can automatically log them back in
            if cookie_username and is_valid_username(cookie_username) and cookie_username.lower() not in RESERVED_USERNAMES:
                existing_user_id = telemetry.get_user_id_by_username(cookie_username)
                if existing_user_id:
                    # Automatically adopt/restore the existing user ID!
                    user_id = existing_user_id
                    st.session_state.user_id = existing_user_id
                    st.session_state.username = cookie_username
                    # Sync session cookies
                    controller.set("lp_user_id", sign_value(existing_user_id))
                    controller.set("lp_username", sign_value(cookie_username))
                    has_custom = True

            if not has_custom:
                if cookie_username_is_usable(user_id, cookie_username):
                    st.session_state.username = cookie_username
                    has_custom = True
                    try:
                        db_username = telemetry.get_user_username(user_id)
                        if db_username != cookie_username:
                            telemetry.get_or_create_user(user_id, get_client_ip())
                            telemetry.update_user_username(user_id, cookie_username)
                    except Exception:
                        pass
                else:
                    try:
                        if telemetry.has_custom_username(user_id):
                            db_custom = telemetry.get_user_username(user_id)
                            st.session_state.username = db_custom
                            has_custom = True
                    except Exception:
                        pass

        # If they don't have a custom username, block them with the student login form
        if not has_custom:
            st.subheader("Welcome to Logic Programming Prolog Trainer! 👋")
            st.markdown("Please log in with your name and phone number to get started.")
            
            with st.form("student_login_form", clear_on_submit=False):
                nume_input = st.text_input("Nume de familie", help="Last name (Romanian diacritics are ignored)")
                prenume_input = st.text_input("Prenume", help="First name (Romanian diacritics are ignored)")
                phone_input = st.text_input("Număr de telefon", placeholder="07-- --- ---", help="Phone number (e.g. +40 755 991 124 or 0755991124)")
                submit = st.form_submit_button("Start Learning 🚀", type="primary")
                
                if submit:
                    cleaned_nume = nume_input.strip()
                    cleaned_prenume = prenume_input.strip()
                    cleaned_phone = phone_input.strip()
                    
                    if not cleaned_nume:
                        st.error("Please enter your Last Name (Nume de familie).")
                    elif not cleaned_prenume:
                        st.error("Please enter your First Name (Prenume).")
                    elif not cleaned_phone:
                        st.error("Please enter your Phone Number (Număr de telefon).")
                    elif len(clean_phone(cleaned_phone)) < 9:
                        st.error("The phone number must contain at least 9 digits (e.g., 07xx xxx xxx).")
                    else:
                        match = find_student_match(cleaned_nume, cleaned_prenume, cleaned_phone)
                        if match:
                            try:
                                telemetry.cleanup_inactive_users(hours=2.0)
                            except Exception:
                                pass
                            
                            student_user_id = generate_student_uuid(match["nume"], match["prenume"], match["telefon"])
                            username_clean = f"{match['nume']} {match['prenume']}"
                            
                            previous_user_id = st.session_state.get("user_id")
                            try:
                                telemetry.merge_user_identity(previous_user_id, student_user_id, username_clean, get_client_ip())
                                telemetry.scrub_sensitive_log_details()
                            except Exception:
                                pass
                            
                            st.session_state.user_id = student_user_id
                            st.session_state.username = username_clean
                            controller.set("lp_user_id", sign_value(student_user_id))
                            controller.set("lp_username", sign_value(username_clean))
                            st.success(f"Welcome, {username_clean}! Loading the platform...")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Credentials do not match our records. Please check your spelling and phone number.")
            
            st.markdown(
                "<hr><span style='font-size: 0.8em; color: gray;'>Privacy Notice: IP addresses and session telemetry are logged for usage statistics and security purposes.</span>",
                unsafe_allow_html=True
            )
            return

    collection = cached_collection(str(settings.DB_DIR), cached_db_fingerprint(str(settings.DB_DIR)))
    if collection is None:
        render_missing_database()
        return

    health = vector_store.collection_health(collection)
    if not health.is_current:
        for issue in health.issues:
            st.warning(issue)

    cache_dir = Path(tempfile.gettempdir()) / "prolog_trainer_cache"
    cache_collection = cached_cache_collection(str(cache_dir))

    api_key = os.environ.get("GEMINI_API_KEY", "")

    try:
        quizzes = cached_load_quizzes(
            str(settings.QUIZZES_PATH),
            settings.QUIZZES_PATH.stat().st_mtime if settings.QUIZZES_PATH.exists() else None,
        )
    except Exception:
        quizzes = []

    user_id = get_user_id()
    if is_admin_session_valid(user_id):
        st.session_state.is_admin = True

    is_admin_mode = st.session_state.get("is_admin", False)

    if is_admin_mode:
        tab_search, tab_quiz, tab_admin = st.tabs(["Search", "Quiz", "Admin"])
    else:
        tab_search, tab_quiz = st.tabs(["Search", "Quiz"])

    with tab_search:
        render_search_tab(collection, cache_collection, api_key, quizzes)
    with tab_quiz:
        render_quiz_tab(collection, api_key)
    if is_admin_mode:
        with tab_admin:
            render_admin_dashboard()

    _render_usage_tracker()

    st.markdown(
        "<div class='footer'>Logic Programming &copy; UTCN | ChromaDB · Streamlit · Gemini<br>"
        "<span style='font-size: 0.8em; color: gray;'>Privacy Notice: IP addresses and session telemetry are logged for usage statistics and security purposes.</span></div>",
        unsafe_allow_html=True,
    )


main()

