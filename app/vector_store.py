import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils import embedding_functions

from app import settings


@dataclass(frozen=True)
class SlideResult:
    title: str
    source: str
    page: Any
    similarity: float
    distance: float
    text: str


@dataclass(frozen=True)
class CollectionHealth:
    is_current: bool
    issues: tuple[str, ...]


def collection_metadata() -> dict[str, str]:
    return {
        "description": "Logic Programming Course Slides",
        "schema_version": settings.VECTOR_SCHEMA_VERSION,
        "embedding_function": settings.EMBEDDING_FUNCTION,
    }


def ensure_collection_metadata(collection) -> None:
    collection.modify(metadata=collection_metadata())


def db_fingerprint(db_path: Path) -> int:
    if not db_path.exists():
        return 0

    return max((path.stat().st_mtime_ns for path in db_path.rglob("*") if path.is_file()), default=0)


def get_collection(db_path: Path):
    if not db_path.exists():
        return None

    client = chromadb.PersistentClient(path=str(db_path))
    embedding_function = embedding_functions.DefaultEmbeddingFunction()
    return client.get_collection(name=settings.COLLECTION_NAME, embedding_function=embedding_function)


def _create_cache_collection(db_path: Path):
    db_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(db_path))
    embedding_function = embedding_functions.DefaultEmbeddingFunction()
    return client.get_or_create_collection(name="query_cache", embedding_function=embedding_function)


def get_cache_collection(db_path: Path):
    try:
        return _create_cache_collection(db_path)
    except Exception:
        try:
            if db_path.exists():
                shutil.rmtree(db_path)
            return _create_cache_collection(db_path)
        except Exception:
            return None


def search_query_cache(cache_collection, query: str) -> tuple[str, float] | None:
    if cache_collection is None:
        return None
    try:
        results = cache_collection.query(
            query_texts=[query],
            n_results=1
        )
        if not results or not results.get("ids") or not results["ids"][0]:
            return None
        
        distance = results["distances"][0][0]
        similarity = distance_to_similarity(distance)
        
        # Require high semantic similarity (e.g. distance < 0.25, i.e. similarity >= 87.5%)
        if similarity >= 87.5:
            metadata = results["metadatas"][0][0]
            if metadata and "answer" in metadata:
                return metadata["answer"], similarity
    except Exception:
        pass
    return None


def add_to_query_cache(cache_collection, query: str, answer: str) -> None:
    if cache_collection is None:
        return
    try:
        import uuid
        cache_collection.add(
            ids=[str(uuid.uuid4())],
            documents=[query],
            metadatas=[{"answer": answer, "query": query}]
        )
    except Exception:
        pass


def collection_health(collection) -> CollectionHealth:
    metadata = collection.metadata or {}
    issues: list[str] = []
    if metadata.get("schema_version") != settings.VECTOR_SCHEMA_VERSION:
        issues.append("The vector database schema version is out of date. Please run re-indexing.")
    if metadata.get("embedding_function") != settings.EMBEDDING_FUNCTION:
        issues.append("The vector database embedding function is not as expected. Please run re-indexing.")
    return CollectionHealth(is_current=not issues, issues=tuple(issues))



def build_source_filter(selected_sources: list[str] | None) -> dict[str, Any] | None:
    if not selected_sources:
        return None
    if len(selected_sources) == 1:
        return {"source": selected_sources[0]}
    return {"$or": [{"source": source} for source in selected_sources]}


def distance_to_similarity(distance: float) -> float:
    return max(0.0, 1.0 - (distance / 2.0)) * 100.0


def search_slides(collection, query: str, n_results: int, selected_sources: list[str] | None = None) -> list[SlideResult]:
    query_kwargs: dict[str, Any] = {
        "query_texts": [query],
        "n_results": n_results,
    }

    source_filter = build_source_filter(selected_sources)
    if source_filter:
        query_kwargs["where"] = source_filter

    results = collection.query(**query_kwargs)
    if not results or not results.get("ids") or not results["ids"][0]:
        return []

    slides: list[SlideResult] = []
    for idx, _doc_id in enumerate(results["ids"][0]):
        metadata = results["metadatas"][0][idx] or {}
        distance = results["distances"][0][idx]
        page = metadata.get("page", "?")
        slides.append(
            SlideResult(
                title=metadata.get("title", f"Slide {page}"),
                source=metadata.get("source", "Unknown"),
                page=page,
                similarity=distance_to_similarity(distance),
                distance=distance,
                text=results["documents"][0][idx],
            )
        )
    return slides


def slides_to_context(slides: list[SlideResult]) -> str:
    return "".join(
        f"\n--- Curs: {slide.source}, Pagina: {slide.page}, Slide: {slide.title} ---\n{slide.text}\n"
        for slide in slides
    )
