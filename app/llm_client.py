"""
Gemini API client with full error handling.

Free Tier limits for gemini-2.5-flash (source: ai.google.dev/gemini-api/docs/rate-limits):
  RPM  : 10 requests/minute
  TPM  : 250,000 tokens/minute
  RPD  : 20 requests/day  ← the hard limit you hit
  TPD  : 1,000,000 tokens/day
  Input: 1,048,576 tokens max per request

The API does NOT expose X-RateLimit-Remaining headers.
Remaining quota is only visible in AI Studio: https://aistudio.google.com/rate-limit
Retry delay comes from error body: details[].retryDelay (e.g. "23s").
Token usage comes from response.usage_metadata (prompt_token_count, candidates_token_count).
"""
import re
import time
from dataclasses import dataclass

from app.quiz_logic import parse_model_json

# ── Error classification ────────────────────────────────────────────────────────

_RETRYABLE_CODES = {429, 500, 503, 504}

_QUOTA_IDS = {
    "GenerateRequestsPerDayPerProjectPerModel": "daily",
    "GenerateRequestsPerMinutePerProjectPerModel": "rpm",
    "GenerateTokensPerMinutePerProjectPerModel": "tpm",
}

_ERROR_MESSAGES = {
    400: "Invalid prompt — too long or wrong parameters.",
    401: "Invalid or expired API key. Check GEMINI_API_KEY in `.env`.",
    403: "Access denied — the API key does not have permissions for this model.",
    404: "Model not found. Check GEMINI_MODEL in settings.py.",
    429: {
        "daily": (
            "⛔ Daily quota exhausted (20 req/day, free tier). "
            "Please come back tomorrow or enable billing in Google AI Studio."
        ),
        "rpm": "⏱️ Too many requests per minute (max 10 RPM).",
        "tpm": "⏱️ Too many tokens per minute (max 250k TPM).",
        "default": "⏱️ Rate limit exceeded (free tier quota).",
    },
    500: "Gemini internal error. Please retry in a few seconds.",
    503: "Gemini service temporarily unavailable.",
    504: "Timeout — request took too long.",
}


@dataclass
class ApiError:
    code: int | None
    quota_type: str  # "daily" | "rpm" | "tpm" | "default" | ""
    retry_after: int | None  # seconds, from retryDelay in error body
    message: str
    is_retryable: bool


def parse_api_error(exc: Exception) -> tuple[str, int | None]:
    """Return (user_friendly_message, retry_after_seconds or None)."""
    err = _classify_error(exc)
    return err.message, err.retry_after


def is_retryable(exc: Exception) -> bool:
    return _classify_error(exc).is_retryable


def is_daily_limit(exc: Exception) -> bool:
    return _classify_error(exc).quota_type == "daily"


def _classify_error(exc: Exception) -> ApiError:
    raw = str(exc)

    # HTTP code
    code_match = re.search(r"\b(400|401|403|404|429|500|503|504)\b", raw)
    code = int(code_match.group(1)) if code_match else None

    # retryDelay from API body: 'retryDelay': '23s' or "retryDelay": "23.078s"
    retry_after: int | None = None
    delay_match = re.search(r"retryDelay['\"]?\s*[=:]\s*['\"](\d+)", raw, re.IGNORECASE)
    if delay_match:
        retry_after = int(delay_match.group(1)) + 2  # +2s buffer
    else:
        # Fallback: "retry in Xs" pattern
        fallback = re.search(r"retry[^0-9]*?(\d+)\s*s", raw, re.IGNORECASE)
        if fallback:
            retry_after = int(fallback.group(1)) + 2

    # Quota type from quotaId
    quota_type = "default"
    for quota_id, qtype in _QUOTA_IDS.items():
        if quota_id in raw:
            quota_type = qtype
            break

    # Build message
    if code == 429:
        base = _ERROR_MESSAGES[429]
        base_msg = base.get(quota_type, base["default"])
        if quota_type == "daily":
            msg = base_msg  # daily quota: no retry delay helps
            retry_after = None
        elif retry_after:
            msg = f"{base_msg} Retry in **{retry_after}s**."
        else:
            msg = f"{base_msg} Retry in a few seconds."
    elif code in _ERROR_MESSAGES:
        msg = _ERROR_MESSAGES[code]
    else:
        msg = f"API Error ({code or 'unknown'})."

    retryable = code in _RETRYABLE_CODES and quota_type != "daily"

    return ApiError(
        code=code,
        quota_type=quota_type,
        retry_after=retry_after,
        message=msg,
        is_retryable=retryable,
    )


# ── Usage tracking (session-level, approximate) ────────────────────────────────

@dataclass
class UsageRecord:
    input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


_session_usage = UsageRecord()
_session_usage_per_model: dict[str, UsageRecord] = {}


def get_session_usage() -> UsageRecord:
    return _session_usage


def get_session_usage_per_model(model_name: str) -> UsageRecord:
    if model_name not in _session_usage_per_model:
        _session_usage_per_model[model_name] = UsageRecord()
    return _session_usage_per_model[model_name]


def reset_session_usage() -> None:
    global _session_usage, _session_usage_per_model
    _session_usage = UsageRecord()
    _session_usage_per_model = {}


def _record_usage_for_model(model_name: str, response) -> None:
    """Extract usage_metadata from response and accumulate for a model and session."""
    global _session_usage
    rec = get_session_usage_per_model(model_name)
    meta = getattr(response, "usage_metadata", None)
    if meta:
        in_t = getattr(meta, "prompt_token_count", 0) or 0
        out_t = getattr(meta, "candidates_token_count", 0) or 0
        rec.input_tokens += in_t
        rec.output_tokens += out_t
        _session_usage.input_tokens += in_t
        _session_usage.output_tokens += out_t
    rec.requests += 1
    _session_usage.requests += 1


# ── Client helpers ─────────────────────────────────────────────────────────────

def create_client(api_key: str):
    from google import genai
    return genai.Client(api_key=api_key)


def generate_text(api_key: str, model_name: str, prompt: str, system_prompt: str, temperature: float) -> str:
    client = create_client(api_key)
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config={"system_instruction": system_prompt, "temperature": temperature},
    )
    _record_usage_for_model(model_name, response)
    return response.text


def generate_json(api_key: str, model_name: str, prompt: str, system_prompt: str, temperature: float):
    client = create_client(api_key)
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config={
            "system_instruction": system_prompt,
            "temperature": temperature,
            "response_mime_type": "application/json",
        },
    )
    _record_usage_for_model(model_name, response)
    return parse_model_json(response.text.strip())


# ── Public API functions ───────────────────────────────────────────────────────

def answer_from_slides(api_key: str, model_name: str, context_text: str, question: str) -> str:
    system_prompt = (
        "You are an active learning assistant for the Logic Programming (Prolog) course. "
        "Answer the user's question strictly based on the course slides/materials in the context. "
        "If the information is not present in the context, explicitly state this.\n"
        "Even if the source context slides are in Romanian, you MUST always output your response in English (translating the information correctly).\n\n"
        "CRITICAL response quality requirements:\n"
        "1. All generated Prolog code examples must be syntactically correct, fully functional in SWI-Prolog, and consistent in naming (if a predicate is called with N arguments, it must be defined with exactly N arguments).\n"
        "2. If you use dynamic predicates (assert/retract) to prevent loops, the code must contain an initialization/cleanup clause (e.g., retractall at the beginning of the main predicate) so it does not leave a dirty state during backtracking.\n"
        "3. The 'How it works' section must not be just an abstract block of text. Every explained point about a rule or predicate must be accompanied by a small Prolog code snippet (1-2 lines) showing the signature or call of that predicate.\n\n"
        "ALWAYS structure the response in this exact markdown format:\n\n"
        "## Short answer\n[1-2 clear and concise sentences in English]\n\n"
        "## How it works\n[Each of the maximum 5 points must contain a brief explanation followed directly by a small 1-2 line code snippet wrapped in a prolog code block, for example:\n"
        "- Explanation...\n"
        "```prolog\n"
        "rule(X) :- neighbor(X, Y), ...\n"
        "```]\n\n"
        "## Minimal example\n```prolog\n[Complete, functional, and testable Prolog code that runs in SWI-Prolog without predicate existence errors]\n```\n\n"
        "## ⚠️ Common pitfalls\n[List of typical errors, surprising behaviors of backtracking, or infinite loops in English]\n\n"
        "## 💡 What if...?\n[1-2 scenarios that clarify edge cases in English]\n\n"
        "If a section is not relevant, omit it. Answer in English. Do not invent information that is not in the context."
    )
    user_prompt = f"Course slides context:\n{context_text}\n\nQuestion: {question}"
    return generate_text(api_key, model_name, user_prompt, system_prompt, temperature=0.2)


def generate_quiz_batch(
    api_key: str,
    model_name: str,
    slides: list,
    examples_text: str,
) -> list[dict]:
    """Generate exactly one question per slide in a single API call."""
    slides_formatted = []
    for idx, slide in enumerate(slides, start=1):
        slides_formatted.append(
            f"Slide {idx} (Source: {slide.source}, Page: {slide.page}, Title: {slide.title}):\n{slide.text}\n"
        )
    slides_text = "\n-------------------\n".join(slides_formatted)

    system_prompt = (
        "You are a strict university professor drafting exam questions "
        "for a Logic Programming course (in Prolog).\n\n"
        f"Generate exactly {len(slides)} diverse questions (mix of multiple_choice, code_completion, code_tracing) "
        "based strictly on the slide chunks provided. For each slide chunk, generate exactly one question "
        "based exclusively on the technical contents of that slide chunk. Ensure the order of questions in the JSON array matches the order of slides (first question for Slide 1, second for Slide 2, etc.).\n\n"
        "CRITICAL RULES:\n"
        "1. NO GENERAL OR ABSTRACT THEORY QUESTIONS: Do not generate questions about definitions, history, or general principles (e.g., 'What is logic programming?', 'What is a query?', 'What is a fact?', 'How does backtracking work in theory?'). EVERY question must be practical, requiring the student to read, write, trace, complete, or debug concrete Prolog code.\n"
        "2. ALL QUESTIONS MUST CONTAIN CONCRETE CODE OR CONCRETE REASONING: Even for multiple-choice questions, the question must analyze a specific Prolog code block or a specific query execution trace.\n"
        "3. DIFFICULTY: Questions must be highly academic, challenging, and rigorous, matching the style of the provided exam examples. Test advanced concepts: cut semantics (green vs. red cuts), accumulator patterns, difference lists, DCGs, trees (BST, incomplete trees), backtracking order, database manipulation (assert/retract), negation as failure, and search algorithms (BFS, DFS, A*).\n"
        "4. QUESTION FORMATS AND SCHEMAS:\n"
        "   - 'code_completion': Provide a Prolog predicate with parts replaced by placeholders like 'blank1', 'blank2', 'blank3', etc. in the 'code' field. Set 'blanks_or_options' to the list of placeholder names: ['blank1', 'blank2', ...]. Set 'correct_answer' to the exact mappings: 'blank1 = <value>, blank2 = <value>, ...'.\n"
        "   - 'code_tracing': Provide a complete, syntactically correct Prolog program and a specific query (e.g., in the 'code' field: 'p(X, Y) :- ... \\n ?- p(a, Ans).'). Ask what the query returns/prints or what a variable binds to. Set 'blanks_or_options' to null. Set 'correct_answer' to the exact output/variable binding.\n"
        "   - 'multiple_choice': Provide 4 distinct options in 'blanks_or_options' (prefixed with 'a. ', 'b. ', 'c. ', 'd. '). The 'correct_answer' must be the exact text of the correct choice (or its letter prefix). The 'code' field must contain the relevant Prolog code block to analyze.\n"
        "5. SYNTAX AND LOGIC: All Prolog code snippets must be syntactically valid in SWI-Prolog. Predicate signatures, recursion, and variable bindings must be correct and logically sound.\n"
        "6. English Language: All questions, options, code comments, and correct answers must be written in English. Translate concepts from Romanian if the source slides are in Romanian.\n"
        "7. Self-contained: Questions must never refer to unseen images or diagrams. If a graph is required, include a visual object of type graph with explicit nodes and edges. Otherwise set visual to null.\n\n"
        f"Respond EXCLUSIVELY with a JSON array of exactly {len(slides)} objects, each containing:\n"
        "{\n"
        "  \"type\": \"multiple_choice\" | \"code_completion\" | \"code_tracing\",\n"
        "  \"topic\": \"Topic name (based on the technical concept of the slide)\",\n"
        "  \"question_text\": \"The question text in English\",\n"
        "  \"code\": \"Prolog code snippet or null (must be Prolog code for code_completion and code_tracing)\",\n"
        "  \"visual\": null or {\"type\": \"graph\", \"title\": \"Short title\", \"nodes\": [\"a\", \"b\"], \"edges\": [[\"a\", \"b\"]]},\n"
        "  \"blanks_or_options\": [\"a\", \"b\", \"c\", \"d\"] or null (required options list for multiple_choice, null for others),\n"
        "  \"correct_answer\": \"The correct answer\"\n"
        "}\nNo markdown formatting outside the JSON, no text before or after the JSON array."
    )
    user_prompt = f"Course slides (the {len(slides)} slides):\n{slides_text}\n\n{examples_text}"
    result = generate_json(api_key, model_name, user_prompt, system_prompt, temperature=0.7)
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        return [result]
    return []
