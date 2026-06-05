import json
import unittest
from pathlib import Path

from app.index_courses import clean_text, get_slide_title
from app.quiz_logic import (
    blank_labels_for_quiz,
    clean_answer,
    compose_blank_answer,
    extract_blank_labels,
    few_shot_examples,
    few_shot_examples_diverse,
    is_answer_correct,
    option_letter,
    parse_model_json,
)
from app.telemetry import MAX_DETAIL_STRING_LENGTH, sanitize_details
from app.vector_store import (
    add_to_query_cache,
    build_source_filter,
    collection_health,
    collection_metadata,
    distance_to_similarity,
    ensure_collection_metadata,
    get_all_slides,
    get_cache_collection,
    search_query_cache,
    search_slides,
)


class CourseIndexingTests(unittest.TestCase):
    def test_clean_text_removes_control_chars_and_collapses_space(self):
        self.assertEqual(clean_text(" a\t\n b\x00 c  "), "a\nb c")

    def test_get_slide_title_skips_headers_and_numbers(self):
        text = "Programare Logica\n2026\nDifference Lists\nbody"
        self.assertEqual(get_slide_title(text, 3), "Difference Lists")


class QuizLogicTests(unittest.TestCase):
    def test_answer_normalization_matches_equivalent_forms(self):
        self.assertEqual(clean_answer(" Blank1: X ; Blank2: Y "), "blank1=x,blank2=y")

    def test_bracketed_prolog_term_matches_unbracketed(self):
        # User may write [New|R] but stored answer is New|R — both must normalise the same.
        self.assertEqual(clean_answer("[New|R]"), clean_answer("New|R"))

    def test_code_completion_quizzes_have_renderable_blanks(self):
        quiz_path = Path(__file__).resolve().parents[1] / "app" / "quizzes.json"
        quizzes = json.loads(quiz_path.read_text(encoding="utf-8"))
        missing = [
            (index, quiz.get("source"))
            for index, quiz in enumerate(quizzes)
            if quiz.get("type") == "code_completion" and not blank_labels_for_quiz(quiz)
        ]

        self.assertEqual(missing, [])

    def test_multiple_choice_accepts_letter_prefix(self):
        self.assertEqual(option_letter("b) Backtracking"), "b")
        self.assertTrue(is_answer_correct("b) Backtracking", "B", "multiple_choice"))

    def test_non_multiple_choice_requires_normalized_exact_match(self):
        self.assertFalse(is_answer_correct("a) value", "a", "code_completion"))

    def test_blank_labels_are_extracted_from_code_variants(self):
        code = "p(blank1, <blank_2>, [blank3])."
        self.assertEqual(extract_blank_labels(code), ["blank1", "blank_2", "blank3"])

    def test_blank_labels_prefer_declared_options(self):
        quiz = {"code": "p(blank1).", "blanks_or_options": ["[blank2]", "<blank_3>"]}
        self.assertEqual(blank_labels_for_quiz(quiz), ["blank2", "blank_3"])

    def test_composed_inline_blank_answer_matches_bracketed_barem(self):
        user_answer = compose_blank_answer({"blank1": "void", "blank2": "K"})
        self.assertTrue(is_answer_correct(user_answer, "[blank1] = void, [blank2] = K", "code_completion"))

    def test_parse_model_json_accepts_markdown_wrapped_json(self):
        self.assertEqual(parse_model_json('```json\n{"type": "multiple_choice"}\n```')["type"], "multiple_choice")

    def test_parse_model_json_accepts_json_list(self):
        self.assertEqual(parse_model_json('```json\n[{"type": "code_tracing"}]\n```')[0]["type"], "code_tracing")

    def test_example_graph_questions_have_visual_context(self):
        quiz_path = Path(__file__).resolve().parents[1] / "app" / "quizzes.json"
        quizzes = json.loads(quiz_path.read_text(encoding="utf-8"))
        missing = [
            (index, quiz.get("source"))
            for index, quiz in enumerate(quizzes)
            if "example graph" in quiz.get("question_text", "").lower() and not quiz.get("visual")
        ]

        self.assertEqual(missing, [])

    def test_few_shot_examples_preserve_visual_schema(self):
        examples = few_shot_examples(
            [
                {
                    "type": "multiple_choice",
                    "topic": "Graphs",
                    "question_text": "Use the graph.",
                    "code": None,
                    "visual": {"type": "graph", "nodes": ["a", "b"], "edges": [["a", "b"]]},
                    "blanks_or_options": ["a. yes", "b. no"],
                    "correct_answer": "a. yes",
                    "source": "ignored",
                }
            ],
            "multiple_choice",
            limit=1,
        )

        self.assertIn('"visual"', examples)
        self.assertNotIn('"source"', examples)

    def test_few_shot_examples_diverse(self):
        quizzes = [
            {"type": "multiple_choice", "topic": "T1", "question_text": "Q1", "code": None, "blanks_or_options": ["a", "b"], "correct_answer": "a"},
            {"type": "code_completion", "topic": "T2", "question_text": "Q2", "code": "c.", "blanks_or_options": ["blank1"], "correct_answer": "blank1 = 1"},
            {"type": "code_tracing", "topic": "T3", "question_text": "Q3", "code": "t.", "blanks_or_options": None, "correct_answer": "yes"},
        ]
        examples = few_shot_examples_diverse(quizzes)
        self.assertIn('"multiple_choice"', examples)
        self.assertIn('"code_completion"', examples)
        self.assertIn('"code_tracing"', examples)

    def test_lettered_options_are_multiple_choice_quizzes(self):
        quiz_path = Path(__file__).resolve().parents[1] / "app" / "quizzes.json"
        quizzes = json.loads(quiz_path.read_text(encoding="utf-8"))
        prefixes = ("a.", "b.", "c.", "d.", "e.", "f.", "a)", "b)", "c)", "d)", "e)", "f)")
        mismatches = []
        for index, quiz in enumerate(quizzes):
            options = quiz.get("blanks_or_options")
            if quiz.get("type") == "multiple_choice" or not isinstance(options, list):
                continue

            lettered_count = sum(
                isinstance(option, str) and option.strip().lower().startswith(prefixes)
                for option in options
            )
            blank_labels = all(
                isinstance(option, str) and option.strip().lower().replace("_", "").startswith("blank")
                for option in options
            )
            if lettered_count >= 2 and not blank_labels:
                mismatches.append((index, quiz.get("source"), quiz.get("question_text")))

        self.assertEqual(mismatches, [])

    def test_multiple_choice_answers_resolve_to_available_options(self):
        quiz_path = Path(__file__).resolve().parents[1] / "app" / "quizzes.json"
        quizzes = json.loads(quiz_path.read_text(encoding="utf-8"))
        mismatches = []
        for index, quiz in enumerate(quizzes):
            if quiz.get("type") != "multiple_choice":
                continue

            correct_answer = quiz.get("correct_answer")
            options = quiz.get("blanks_or_options") or []
            if "unresolved" in str(correct_answer).lower():
                mismatches.append((index, quiz.get("source"), correct_answer))
                continue

            correct_letter = option_letter(correct_answer)
            option_letters = {option_letter(option) for option in options}
            option_letters.discard(None)
            if correct_letter and option_letters and correct_letter not in option_letters:
                mismatches.append((index, quiz.get("source"), correct_answer))
                continue

            if correct_answer not in options and not any(
                is_answer_correct(option, correct_answer, "multiple_choice") for option in options
            ):
                mismatches.append((index, quiz.get("source"), correct_answer))

        self.assertEqual(mismatches, [])

    def test_known_quiz_barem_regressions_from_source_images(self):
        quiz_path = Path(__file__).resolve().parents[1] / "app" / "quizzes.json"
        quizzes = json.loads(quiz_path.read_text(encoding="utf-8"))

        expected_multiple_choice_answers = {
            "To make the predicate ins_sort/3 stable, we need to:": "a",
            "To make the predicate select_sort/3 stable, we need to: (corrected quiz view)": "c",
            "The predicate below verifies if the first argument (an element) is present in the second argument (a list). To have a non-deterministic call, we need to:": "b",
        }

        for question_text, expected_letter in expected_multiple_choice_answers.items():
            matches = [quiz for quiz in quizzes if quiz.get("question_text") == question_text]
            self.assertEqual(len(matches), 1, question_text)
            self.assertEqual(option_letter(matches[0]["correct_answer"]), expected_letter)

        expected_code_completion_answers = {
            "I want to write a predicate which replaces a given key in a BST with another key, specified as argument. The predicate should leave the tree unchanged if the searched key is not in the tree. Complete the partial implementation so that you get a correct predicate:": (
                "blank1 = _, blank2 = nil, nil, blank3 = t(L, NK, R), blank4 = !, "
                "blank5 = K, NK, R, NR"
            ),
        }

        for question_text, expected_answer in expected_code_completion_answers.items():
            matches = [quiz for quiz in quizzes if quiz.get("question_text") == question_text]
            self.assertEqual(len(matches), 1, question_text)
            self.assertEqual(clean_answer(matches[0]["correct_answer"]), clean_answer(expected_answer))


class FakeCollection:
    metadata = collection_metadata()

    def modify(self, metadata):
        self.metadata = metadata

    def query(self, **kwargs):
        self.kwargs = kwargs
        return {
            "ids": [["LP1.pdf_page_1"]],
            "documents": [["cut prevents some backtracking"]],
            "metadatas": [[{"source": "LP1.pdf", "page": 1, "title": "The CUT"}]],
            "distances": [[0.5]],
        }

    def get(self, **kwargs):
        self.get_kwargs = kwargs
        return {
            "ids": ["LP1.pdf_page_1"],
            "documents": ["cut prevents some backtracking"],
            "metadatas": [{"source": "LP1.pdf", "page": 1, "title": "The CUT"}],
        }


class FakeCacheCollection:
    def __init__(self):
        self.data = []

    def add(self, ids, documents, metadatas):
        for doc, meta in zip(documents, metadatas, strict=False):
            self.data.append((doc, meta))

    def query(self, query_texts, n_results):
        results = {"ids": [[]], "distances": [[]], "metadatas": [[]], "documents": [[]]}
        for doc, meta in self.data:
            if query_texts[0] == doc:
                results["ids"][0].append("mock-id")
                results["distances"][0].append(0.1)  # similarity = 95%
                results["metadatas"][0].append(meta)
                results["documents"][0].append(doc)
            elif query_texts[0] in doc or doc in query_texts[0]:
                results["ids"][0].append("mock-id")
                results["distances"][0].append(0.2)  # similarity = 90%
                results["metadatas"][0].append(meta)
                results["documents"][0].append(doc)
        return results


class VectorStoreTests(unittest.TestCase):
    def test_source_filter_shape(self):
        self.assertIsNone(build_source_filter([]))
        self.assertEqual(build_source_filter(["LP1.pdf"]), {"source": "LP1.pdf"})
        self.assertEqual(
            build_source_filter(["LP1.pdf", "LP2.pdf"]),
            {"$or": [{"source": "LP1.pdf"}, {"source": "LP2.pdf"}]},
        )

    def test_distance_to_similarity(self):
        self.assertEqual(distance_to_similarity(0.0), 100.0)
        self.assertEqual(distance_to_similarity(2.0), 0.0)

    def test_search_slides_maps_chroma_result(self):
        collection = FakeCollection()
        slides = search_slides(collection, "cut", 1, ["LP1.pdf"])

        self.assertEqual(collection.kwargs["where"], {"source": "LP1.pdf"})
        self.assertEqual(slides[0].title, "The CUT")
        self.assertEqual(slides[0].similarity, 75.0)

    def test_get_all_slides_maps_chroma_result(self):
        collection = FakeCollection()
        slides = get_all_slides(collection, 1, ["LP1.pdf"])

        self.assertEqual(collection.get_kwargs["where"], {"source": "LP1.pdf"})
        self.assertEqual(slides[0].title, "The CUT")
        self.assertEqual(slides[0].similarity, 100.0)

    def test_collection_health_flags_stale_metadata(self):
        class StaleCollection:
            metadata = {"schema_version": "old"}

        health = collection_health(StaleCollection())

        self.assertFalse(health.is_current)
        self.assertTrue(any("schema" in issue for issue in health.issues))

    def test_ensure_collection_metadata_updates_existing_collection(self):
        collection = FakeCollection()
        collection.metadata = {}

        ensure_collection_metadata(collection)

        self.assertTrue(collection_health(collection).is_current)

    def test_semantic_cache_hit_returns_answer(self):
        cache_collection = FakeCacheCollection()
        add_to_query_cache(cache_collection, "What is unification?", "Unification is the process of...")
        
        hit = search_query_cache(cache_collection, "What is unification?")
        self.assertIsNotNone(hit)
        answer, similarity = hit
        self.assertEqual(answer, "Unification is the process of...")
        self.assertTrue(similarity >= 87.5)

    def test_semantic_cache_miss_returns_none(self):
        cache_collection = FakeCacheCollection()
        add_to_query_cache(cache_collection, "What is unification?", "Unification is the process of...")
        
        hit = search_query_cache(cache_collection, "How does recursion work?")
        self.assertIsNone(hit)

    def test_cache_collection_recovers_from_incompatible_chroma_db(self):
        import tempfile
        from unittest.mock import patch

        class FakeClient:
            attempts = 0

            def __init__(self, path):
                self.path = path

            def get_or_create_collection(self, name, embedding_function):
                FakeClient.attempts += 1
                if FakeClient.attempts == 1:
                    raise KeyError("_type")
                return FakeCacheCollection()

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "prolog_trainer_cache"
            cache_path.mkdir()
            stale_file = cache_path / "chroma.sqlite3"
            stale_file.write_text("old schema", encoding="utf-8")

            with patch("app.vector_store.chromadb.PersistentClient", FakeClient):
                collection = get_cache_collection(cache_path)

            self.assertIsInstance(collection, FakeCacheCollection)
            self.assertFalse(stale_file.exists())
            self.assertEqual(FakeClient.attempts, 2)


class TelemetryTests(unittest.TestCase):
    def test_sanitize_details_removes_sensitive_header_payloads(self):
        details = {
            "request_headers": {"cookie": "secret"},
            "nested": {
                "Authorization": "bearer token",
                "Sec-Websocket-Key": "socket-secret",
                "safe": "ok",
            },
        }

        sanitized = sanitize_details(details)

        self.assertNotIn("request_headers", sanitized)
        self.assertNotIn("Authorization", sanitized["nested"])
        self.assertNotIn("Sec-Websocket-Key", sanitized["nested"])
        self.assertEqual(sanitized["nested"]["safe"], "ok")

    def test_merge_user_identity_moves_guest_logs_to_student(self):
        import tempfile
        from pathlib import Path

        import app.telemetry as telemetry

        original_db_path = telemetry.DB_PATH
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                telemetry.DB_PATH = Path(tmpdir) / "telemetry.db"
                telemetry.init_db()
                telemetry.log_event("guest-id", "127.0.0.1", "visit", "Page load", {"safe": "ok"})

                telemetry.merge_user_identity("guest-id", "student-id", "Popescu Ana", "127.0.0.1")

                logs = telemetry.get_recent_activity(10)
                self.assertEqual(logs[0]["random_username"], "Popescu Ana")
                self.assertEqual(telemetry.get_user_username("student-id"), "Popescu Ana")
                self.assertIsNone(telemetry.get_user_username("guest-id"))
        finally:
            telemetry.DB_PATH = original_db_path

    def test_sanitize_details_caps_large_payloads(self):
        sanitized = sanitize_details({
            "answer": "x" * (MAX_DETAIL_STRING_LENGTH + 10),
            "items": list(range(30)),
        })

        self.assertEqual(len(sanitized["answer"]), MAX_DETAIL_STRING_LENGTH)
        self.assertEqual(len(sanitized["items"]), 25)


class QuizNavigationTests(unittest.TestCase):
    def test_quiz_nav_label_marks_answered_and_keeps_empty_plain(self):
        from app.app import quiz_nav_label

        self.assertEqual(quiz_nav_label(0, True), "✅ 1")
        self.assertEqual(quiz_nav_label(1, False), "2")
        self.assertEqual(quiz_nav_label(2, True, flagged=True), "✅ 3 ⚑")


class StudentLoginTests(unittest.TestCase):
    def test_normalize_text_removes_diacritics_and_spaces(self):
        from app.app import normalize_text
        self.assertEqual(normalize_text("Drăghici"), "draghici")
        self.assertEqual(normalize_text("Popescu-Florian"), "popescuflorian")
        self.assertEqual(normalize_text("  Cîrneală  "), "cirneala")
        self.assertEqual(normalize_text("șțâîăşţã"), "staiasta")

    def test_clean_phone_extracts_last_9_digits(self):
        from app.app import clean_phone
        self.assertEqual(clean_phone("+40 755 991 124"), "755991124")
        self.assertEqual(clean_phone("0755-991-124"), "755991124")
        self.assertEqual(clean_phone("755991124"), "755991124")
        self.assertEqual(clean_phone("123"), "123")

    def test_generate_student_uuid_is_deterministic(self):
        from app.app import generate_student_uuid
        uuid1 = generate_student_uuid("Drăghici", "Alexandru", "0755 991 124")
        uuid2 = generate_student_uuid("draghici", "alexandru", "+40755991124")
        self.assertEqual(uuid1, uuid2)

    def test_find_student_match_matches_correctly(self):
        from app.app import find_student_match
        match = find_student_match("Drăghici", "Alexandru", "0755 991 124")
        self.assertIsNotNone(match)
        self.assertEqual(match["nume"], "Drăghici")
        
        match_invalid = find_student_match("Draghici", "Alexandru", "0755 000 000")
        self.assertIsNone(match_invalid)


if __name__ == "__main__":
    unittest.main()
