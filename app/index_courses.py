import os
import re
import sys
from pathlib import Path

import chromadb
import fitz  # PyMuPDF
from chromadb.utils import embedding_functions

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import settings
from app.vector_store import collection_metadata, ensure_collection_metadata


def clean_text(text):
    # Remove excessive control characters (excluding newlines and tabs)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\xff]', '', text)
    
    # Process line-by-line to preserve structure
    lines = []
    for line in text.splitlines():
        cleaned_line = re.sub(r'[ \t]+', ' ', line).strip()
        lines.append(cleaned_line)
    
    # Recombine and replace multiple blank lines with at most a double newline
    cleaned_text = "\n".join(lines)
    cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)
    return cleaned_text.strip()

def get_slide_title(text, page_num):
    lines = [line.strip() for line in text.split('\n') if line.strip()]

    # Skip lines that look like dates or numbers
    date_pattern = r'^\d{2}-[A-Za-z]{3}-\d{2}$|^\d{4}$|^\d{1,2}/\d{1,2}/\d{2,4}$'
    number_pattern = r'^\d+$'

    for line in lines:
        if re.match(date_pattern, line) or re.match(number_pattern, line) or len(line) < 3:
            continue
        # Check if it contains general lecture headers
        if (
            ("lecture" in line.lower() or "programare logic" in line.lower() or "logic programming" in line.lower())
            and len(lines) > 1
        ):
            continue
        return line[:100]  # Cap title length

    return f"Slide {page_num}"

def index_all_courses(curs_dir, db_dir):
    print(f"Initializing ChromaDB client at {db_dir}...")
    client = chromadb.PersistentClient(path=db_dir)

    # We will use the default embedding function (onnx-based MiniLM)
    # If the user doesn't have internet, this is loaded locally if already cached,
    # or will be fetched from chromadb's huggingface storage
    emb_fn = embedding_functions.DefaultEmbeddingFunction()

    # Create or get collection
    collection = client.get_or_create_collection(
        name=settings.COLLECTION_NAME,
        embedding_function=emb_fn,
        metadata=collection_metadata(),
    )
    ensure_collection_metadata(collection)

    # List all PDF files in the directory
    pdf_files = [f for f in os.listdir(curs_dir) if f.lower().endswith('.pdf')]
    pdf_files.sort()

    if not pdf_files:
        print(f"No PDF files found in {curs_dir}!")
        return

    print(f"Found {len(pdf_files)} PDF courses to index.")

    total_indexed = 0

    for pdf_file in pdf_files:
        pdf_path = os.path.join(curs_dir, pdf_file)
        print(f"\nProcessing {pdf_file}...")

        try:
            doc = fitz.open(pdf_path)
            num_pages = len(doc)
            print(f"  Pages found: {num_pages}")

            documents = []
            metadatas = []
            ids = []

            for page_idx in range(num_pages):
                page = doc[page_idx]
                raw_text = page.get_text()

                # Get the title before cleaning
                title = get_slide_title(raw_text, page_idx + 1)

                cleaned = clean_text(raw_text)

                # If slide is empty or has very little text, skip indexing or index minimal content
                if len(cleaned) < 10:
                    cleaned = f"[Slide representing diagram or image only] Title: {title}"

                doc_id = f"{pdf_file}_page_{page_idx + 1}"

                documents.append(cleaned)
                metadatas.append({
                    "source": pdf_file,
                    "page": page_idx + 1,
                    "title": title,
                    "length": len(cleaned)
                })
                ids.append(doc_id)

            # Batch upsert to ChromaDB
            if documents:
                collection.upsert(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids
                )
                total_indexed += len(documents)
                print(f"  Successfully indexed {len(documents)} slides from {pdf_file}")

        except Exception as e:
            print(f"  Error processing {pdf_file}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\nIndexing complete! Total slides indexed: {total_indexed}")
    print(f"Database saved at: {db_dir}")

if __name__ == "__main__":
    index_all_courses(str(settings.COURSES_DIR), str(settings.DB_DIR))
