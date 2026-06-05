from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
COURSES_DIR = ROOT_DIR / "Curs"
DB_DIR = APP_DIR / "chroma_store"
QUIZZES_PATH = APP_DIR / "quizzes.json"
INDEX_SCRIPT = APP_DIR / "index_courses.py"
GEMINI_MODEL = "gemini-2.5-flash"
COLLECTION_NAME = "pl_courses"
VECTOR_SCHEMA_VERSION = "1"
EMBEDDING_FUNCTION = "chromadb-default"

# Model limits configuration for Gemini models
# RPD: Requests per day, RPM: Requests per minute, TPM: Tokens per minute, TPD: Tokens per day
MODEL_LIMITS = {
    "gemini-2.5-flash": {
        "name": "Gemini 2.5 Flash",
        "description": "Modelul implicit rapid și eficient.",
        "rpm": 1000,
        "tpm": 4_000_000,
        "rpd": 100000,
        "tpd": 100_000_000,
    }
}

# Quiz limits
MAX_QUIZ_PER_ATTEMPT = 24

# Batch generation
BATCH_SIZE_PER_CALL = 5
BATCH_DELAY_SECONDS = 0   # No delay needed on Paid API (2000+ RPM)
MAX_BATCH_TOTAL = 24
INPUT_TOKEN_LIMIT = 1_048_576  # Max tokens per single request

# Search context
SEARCH_CONTEXT_SLIDES = 15
