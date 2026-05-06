"""ChromaDB vectorstore for incident response knowledge base."""

from pathlib import Path
from typing import Optional

from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain.schema import Document

CHROMA_PERSIST_DIR = Path(__file__).parent.parent / "data" / "chroma_db"
KNOWLEDGE_BASE_DIR = Path(__file__).parent.parent / "data" / "knowledge_base"
COLLECTION_NAME = "incident_knowledge_base"


def get_vectorstore(embeddings: Optional[OpenAIEmbeddings] = None) -> Chroma:
    if embeddings is None:
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=str(CHROMA_PERSIST_DIR),
    )


def ingest_knowledge_base(
    embeddings: Optional[OpenAIEmbeddings] = None,
    force_reingest: bool = False,
) -> Chroma:
    if embeddings is None:
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

    vectorstore = get_vectorstore(embeddings)

    if not force_reingest:
        try:
            if vectorstore._collection.count() > 0:
                print(f"Knowledge base loaded: {vectorstore._collection.count()} chunks.")
                return vectorstore
        except Exception:
            pass

    print("Ingesting incident knowledge base...")
    documents = []

    category_dirs = {
        "runbooks": "runbook",
        "past_incidents": "past_incident",
        "system_docs": "system_doc",
        "nist_controls": "nist_control",
    }

    for subdir, category in category_dirs.items():
        subdir_path = KNOWLEDGE_BASE_DIR / subdir
        if not subdir_path.exists():
            continue
        for file_path in subdir_path.iterdir():
            if file_path.suffix.lower() not in (".txt", ".md"):
                continue
            try:
                text = file_path.read_text(encoding="utf-8")
                # Simple chunking
                chunk_size = 800
                overlap = 100
                chunks = []
                start = 0
                while start < len(text):
                    end = min(start + chunk_size, len(text))
                    chunks.append(text[start:end])
                    start = end - overlap
                for i, chunk in enumerate(chunks):
                    if len(chunk.strip()) > 50:
                        documents.append(Document(
                            page_content=chunk.strip(),
                            metadata={"source": file_path.name, "category": category, "chunk_index": i},
                        ))
                print(f"  Ingested {file_path.name}: {len(chunks)} chunks")
            except Exception as e:
                print(f"  WARNING: {file_path.name}: {e}")

    if documents:
        vectorstore.add_documents(documents)
        print(f"Total ingested: {len(documents)} chunks")

    return vectorstore
