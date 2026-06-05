import json
import random
import re
from pathlib import Path
from typing import Any

ANSWER_LETTERS = {"a", "b", "c", "d", "e", "f"}
BLANK_PATTERN = re.compile(r"\[?\s*<?(blank_?\d+)>?\s*\]?", re.IGNORECASE)

# Token estimation constants (conservative estimates for free-tier planning)
_TOKENS_PER_CHAR = 0.25  # ~4 chars per token
_SYSTEM_PROMPT_TOKENS = 350
_EXAMPLES_TOKENS = 650
_RESPONSE_TOKENS_PER_Q = 180


def clean_answer(value: Any) -> str:
    if not value:
        return ""

    cleaned = "".join(str(value).split()).lower()
    cleaned = cleaned.replace('"', "").replace("'", "").replace(":", "=").replace(";", ",")
    # Strip [blank_N] notation (correct-answer barem format)
    cleaned = re.sub(r"\[(blank_?\d+)\]", r"\1", cleaned)
    # Strip outer brackets from individual blank values, e.g. [New|R] → New|R.
    # Only unwrap when there are no commas inside (a comma would indicate a real list).
    cleaned = re.sub(r"\[([^,\[\]]+)\]", r"\1", cleaned)
    return cleaned


def blank_label(value: Any) -> str | None:
    match = BLANK_PATTERN.fullmatch(str(value or "").strip())
    return match.group(1).lower() if match else None


def extract_blank_labels(code: str) -> list[str]:
    labels: list[str] = []
    for match in BLANK_PATTERN.finditer(code or ""):
        label = match.group(1).lower()
        if label not in labels:
            labels.append(label)
    return labels


def blank_labels_for_quiz(quiz: dict[str, Any]) -> list[str]:
    option_labels = [blank_label(option) for option in quiz.get("blanks_or_options") or []]
    labels = [label for label in option_labels if label]
    return labels or extract_blank_labels(quiz.get("code") or "")


def compose_blank_answer(values: dict[str, Any]) -> str:
    return ", ".join(f"{label} = {value}" for label, value in values.items())


def option_letter(text: Any) -> str | None:
    if not text:
        return None

    value = str(text).strip().lower()
    if len(value) == 1 and value in ANSWER_LETTERS:
        return value
    if len(value) > 1 and value[0] in ANSWER_LETTERS and value[1] in {".", ")", ":", "-", " "}:
        return value[0]
    return None


def is_answer_correct(user_answer: Any, correct_answer: Any, question_type: str) -> bool:
    if clean_answer(user_answer) == clean_answer(correct_answer):
        return True

    if question_type != "multiple_choice":
        return False

    user_letter = option_letter(user_answer)
    correct_letter = option_letter(correct_answer)
    return bool(user_letter and correct_letter and user_letter == correct_letter)


def parse_model_json(text: str) -> Any:
    value = text.strip()
    candidates = [value]

    for opener, closer in (("[", "]"), ("{", "}")):
        start_idx = value.find(opener)
        end_idx = value.rfind(closer)
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            candidates.append(value[start_idx : end_idx + 1])

    if "```" in value:
        for part in value.split("```"):
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if (part.startswith("{") and part.endswith("}")) or (part.startswith("[") and part.endswith("]")):
                candidates.append(part)

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    raise ValueError("Could not parse valid JSON from model response.")


def load_quizzes(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as quiz_file:
        data = json.load(quiz_file)

    if not isinstance(data, list):
        raise ValueError("Quiz database must contain a JSON list.")
    return data


def topics_for(quizzes: list[dict[str, Any]]) -> list[str]:
    return sorted({quiz.get("topic", "General") for quiz in quizzes})


def filter_by_topic(quizzes: list[dict[str, Any]], topic: str | None) -> list[dict[str, Any]]:
    if not topic or topic in ("Toate", "All"):
        return quizzes
    return [quiz for quiz in quizzes if quiz.get("topic") == topic]


def few_shot_examples(quizzes: list[dict[str, Any]], question_type: str, limit: int = 2) -> str:
    if not quizzes:
        return ""

    matched = [quiz for quiz in quizzes if quiz.get("type") == question_type]
    pool = matched or quizzes
    sample = random.sample(pool, min(limit, len(pool)))

    examples = "\nHere are 2 examples of real questions from the database to understand the difficulty and structure:\n"
    allowed_keys = {"type", "topic", "question_text", "code", "blanks_or_options", "correct_answer"}
    for idx, quiz in enumerate(sample, start=1):
        clean_quiz = {key: value for key, value in quiz.items() if key in allowed_keys}
        examples += f"Example {idx}:\n{json.dumps(clean_quiz, indent=2, ensure_ascii=False)}\n\n"
    return examples


def select_diverse_slides(slides: list[Any], n: int) -> list[Any]:
    """Pick n slides spread across as many different sources as possible."""
    if len(slides) <= n:
        return list(slides)

    by_source: dict[str, list] = {}
    for slide in slides:
        source = getattr(slide, "source", "unknown")
        by_source.setdefault(source, []).append(slide)

    selected: list[Any] = []
    sources = list(by_source.keys())
    random.shuffle(sources)
    while len(selected) < n:
        for source in sources:
            if len(selected) >= n:
                break
            pool = by_source[source]
            if pool:
                selected.append(pool.pop(random.randrange(len(pool))))
    return selected


def estimate_batch_tokens(slide_text: str, batch_size: int, num_calls: int) -> dict[str, int]:
    """Estimate token usage for a batch generation job (for UI display only)."""
    slide_tokens = max(1, int(len(slide_text) * _TOKENS_PER_CHAR))
    per_call_input = _SYSTEM_PROMPT_TOKENS + slide_tokens + _EXAMPLES_TOKENS
    per_call_output = _RESPONSE_TOKENS_PER_Q * batch_size
    total_input = per_call_input * num_calls
    total_output = per_call_output * num_calls
    return {
        "per_call_input": per_call_input,
        "per_call_output": per_call_output,
        "total_input": total_input,
        "total_output": total_output,
        "total": total_input + total_output,
        "num_calls": num_calls,
    }
