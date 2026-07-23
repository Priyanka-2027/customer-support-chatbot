# ingest.py
# ─────────────────────────────────────────────────────────────
# Ingestion pipeline — Steps 1, 2 & 3:
#   1. Load PDFs from documents/ folder
#   2. Split pages into overlapping chunks
#   3. Embed chunks and confirm embedding shape
#
# Run manually from the backend/ directory:
#   python -m app.ingest
#
# NOT called by the API server — this is a one-time setup script.
# ─────────────────────────────────────────────────────────────

import logging
from pathlib import Path
from typing import List

from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import CHUNK_OVERLAP, CHUNK_SIZE, DOCUMENTS_DIR, ENVIRONMENT, PINECONE_INDEX_NAME
from app.embeddings import get_embedding_model
from app.vectorstore import build_vectorstore, save_vectorstore

# ── Logging setup ─────────────────────────────────────────────
# Standard logging gives us timestamps and log levels for free.
# Far more useful than print() once the project grows.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# STEP 1: load_documents()
# ─────────────────────────────────────────────────────────────
def load_documents() -> List[Document]:
    """
    Load all PDF files from the configured documents directory.

    Each page of each PDF becomes one LangChain Document object
    with the page text in `page_content` and the source filename
    and page number in `metadata`.

    Returns:
        List[Document]: One Document per PDF page.

    Raises:
        FileNotFoundError: If the documents directory does not exist.
        ValueError: If no PDFs are found or no text can be extracted.
    """

    # ── Guard: documents folder must exist ───────────────────
    if not DOCUMENTS_DIR.exists():
        raise FileNotFoundError(
            f"Documents directory not found: {DOCUMENTS_DIR}\n"
            "Create the folder and add PDF files to it."
        )

    # ── Guard: at least one PDF must be present ───────────────
    # glob() returns a generator — convert to list so we can
    # measure length and iterate over it more than once.
    pdf_files: List[Path] = list(DOCUMENTS_DIR.glob("*.pdf"))

    if not pdf_files:
        raise ValueError(
            f"No PDF files found in: {DOCUMENTS_DIR}\n"
            "Add at least one .pdf file and run ingestion again."
        )

    logger.info(f"Found {len(pdf_files)} PDF file(s) in '{DOCUMENTS_DIR}':")
    for pdf in pdf_files:
        logger.info(f"  • {pdf.name}")

    # ── Load with DirectoryLoader + PyPDFLoader ───────────────
    # DirectoryLoader scans the folder, PyPDFLoader handles each file.
    # use_multithreading=True loads files in parallel — faster for
    # large document sets.
    loader = DirectoryLoader(
        str(DOCUMENTS_DIR),          # must be str, not Path object
        glob="**/*.pdf",              # ** matches files in subdirectories too
        loader_cls=PyPDFLoader,       # one loader instance per PDF file
        show_progress=True,           # tqdm progress bar in terminal
        use_multithreading=True,      # parallel loading
    )

    # .load() returns one Document per page of each PDF.
    # A 5-page PDF → 5 Documents, each with metadata:
    #   {"source": "path/to/file.pdf", "page": 0}
    documents: List[Document] = loader.load()

    if not documents:
        raise ValueError(
            "PDF files were found but no text could be extracted.\n"
            "Make sure your PDFs contain actual selectable text.\n"
            "Scanned image PDFs require an OCR-based loader."
        )

    logger.info(f"Loaded {len(documents)} page(s) from {len(pdf_files)} file(s).")
    return documents


# ─────────────────────────────────────────────────────────────
# STEP 2: split_documents()
# ─────────────────────────────────────────────────────────────
def split_documents(documents: List[Document]) -> List[Document]:
    """
    Split a list of Documents into smaller, overlapping chunks.

    Uses RecursiveCharacterTextSplitter which tries to split on
    natural boundaries (paragraphs, sentences, words) before
    falling back to hard character splits.

    Args:
        documents: The raw pages returned by load_documents().

    Returns:
        List[Document]: A larger list of smaller Document chunks.
        Each chunk inherits the metadata of its parent document
        (source filename, page number).

    Raises:
        ValueError: If the input document list is empty.
    """

    if not documents:
        raise ValueError(
            "Cannot split an empty document list.\n"
            "Call load_documents() successfully before splitting."
        )

    # ── Build the text splitter ───────────────────────────────
    # RecursiveCharacterTextSplitter is the recommended default
    # for most RAG projects. It splits using a hierarchy of
    # separators, trying each one in order until chunks are
    # small enough:
    #
    #   1. "\n\n"  — paragraph breaks (preferred, most natural)
    #   2. "\n"    — line breaks
    #   3. " "     — word boundaries
    #   4. ""      — individual characters (last resort)
    #
    # This strategy preserves semantic units as much as possible
    # instead of blindly cutting at a fixed character position.
    splitter = RecursiveCharacterTextSplitter(
        # chunk_size: maximum characters allowed in one chunk.
        # Sourced from config.py (default: 1000).
        # ~150 words — enough for a full paragraph with context.
        chunk_size=CHUNK_SIZE,

        # chunk_overlap: characters shared between adjacent chunks.
        # Sourced from config.py (default: 200).
        # Prevents key sentences at chunk boundaries from being lost.
        chunk_overlap=CHUNK_OVERLAP,

        # length_function: the function used to measure chunk size.
        # len() counts characters. Some advanced setups use a
        # tokenizer here to count tokens instead of characters,
        # which is more accurate but slower.
        length_function=len,

        # add_start_index: adds a "start_index" key to each chunk's
        # metadata, recording where in the original document this
        # chunk begins. Useful for debugging and tracing.
        add_start_index=True,
    )

    # ── Perform the split ─────────────────────────────────────
    # split_documents() iterates over every Document, splits its
    # page_content into chunks, and copies the parent's metadata
    # into each child chunk — so source filename and page number
    # are preserved all the way through to the final response.
    chunks: List[Document] = splitter.split_documents(documents)

    # ── Log a detailed breakdown ──────────────────────────────
    logger.info(
        f"Split {len(documents)} page(s) into {len(chunks)} chunk(s) "
        f"[size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP}]"
    )

    # Compute character statistics across all chunks.
    # This helps you verify that chunks are the size you expect.
    chunk_lengths = [len(c.page_content) for c in chunks]
    avg_len = sum(chunk_lengths) / len(chunk_lengths)
    min_len = min(chunk_lengths)
    max_len = max(chunk_lengths)

    logger.info(
        f"Chunk length stats — "
        f"avg: {avg_len:.0f} | min: {min_len} | max: {max_len}"
    )

    # ── Show a sample chunk ───────────────────────────────────
    # Printing a sample lets you verify the split quality
    # and confirm that metadata is being carried over correctly.
    _log_sample_chunk(chunks)

    return chunks


# ─────────────────────────────────────────────────────────────
# Helper: _log_sample_chunk()
# ─────────────────────────────────────────────────────────────
def _log_sample_chunk(chunks: List[Document]) -> None:
    """
    Log a sample chunk for visual inspection during development.

    Prefixed with underscore — this is a private helper intended
    only for use within this module.

    Args:
        chunks: The list of chunks to sample from.
    """
    if not chunks:
        return

    # Use the second chunk if available — the first is often a
    # title page with very little text, not representative.
    sample = chunks[1] if len(chunks) > 1 else chunks[0]

    logger.info("─" * 50)
    logger.info("Sample chunk:")
    logger.info(f"  source      : {sample.metadata.get('source', 'N/A')}")
    logger.info(f"  page        : {sample.metadata.get('page', 'N/A')}")
    logger.info(f"  start_index : {sample.metadata.get('start_index', 'N/A')}")
    logger.info(f"  length      : {len(sample.page_content)} chars")
    # Print first 200 characters of the chunk content, replacing
    # newlines with spaces for clean single-line log output.
    preview = sample.page_content[:200].replace("\n", " ")
    logger.info(f"  preview     : {preview}...")
    logger.info("─" * 50)


# ─────────────────────────────────────────────────────────────
# run_ingestion()  [public — callable by tests and __main__]
# ─────────────────────────────────────────────────────────────

def run_ingestion() -> dict:
    """
    Run the full ingestion pipeline for the configured environment.

    Development  (ENVIRONMENT="development"):
        Load PDFs → split → embed → save FAISS index to disk.

    Production   (ENVIRONMENT="production"):
        Load PDFs → split → embed → upsert into Pinecone.
        Pinecone imports are deferred so langchain-pinecone is
        never imported in development.

    Returns:
        dict: {"chunks": int, "docs": int} — counts for logging.

    Raises:
        ValueError: If ENVIRONMENT is not "development" or "production".
    """
    logger.info("═" * 50)
    logger.info(f"INGESTION PIPELINE — environment: {ENVIRONMENT}")
    logger.info("═" * 50)

    # Step 1: Load raw documents
    logger.info("\n[Step 1] Loading documents...")
    raw_docs = load_documents()

    # Step 2: Split into chunks
    logger.info("\n[Step 2] Splitting into chunks...")
    chunks = split_documents(raw_docs)

    # Step 3: Verify embedding model
    logger.info("\n[Step 3] Verifying embedding model...")
    embedding_model = get_embedding_model()

    # Step 4: Store based on environment
    logger.info(f"\n[Step 4] Storing vectors ({ENVIRONMENT} backend)...")

    if ENVIRONMENT == "development":
        vectorstore = build_vectorstore(chunks)
        save_vectorstore(vectorstore)
        logger.info(f"FAISS index saved — {len(chunks)} chunks.")

    elif ENVIRONMENT == "production":
        # Deferred imports — langchain-pinecone only loaded in production.
        from app.pinecone_store import build_pinecone_store, upsert_to_pinecone
        build_pinecone_store(chunks, embedding_model)
        upsert_to_pinecone(chunks, embedding_model)
        logger.info(
            f"Pinecone index '{PINECONE_INDEX_NAME}' updated — "
            f"{len(chunks)} chunks upserted."
        )

    else:
        raise ValueError(
            f"Invalid ENVIRONMENT value: '{ENVIRONMENT}'. "
            "Must be 'development' or 'production'."
        )

    logger.info("\n" + "═" * 50)
    logger.info("INGESTION COMPLETE")
    logger.info(f"  Raw pages loaded : {len(raw_docs)}")
    logger.info(f"  Chunks embedded  : {len(chunks)}")
    logger.info("═" * 50)

    return {"chunks": len(chunks), "docs": len(raw_docs)}


# ─────────────────────────────────────────────────────────────
# Entry point — run for manual testing
# python -m app.ingest
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    summary = run_ingestion()
    logger.info(
        f"Ingestion complete. "
        f"docs={summary['docs']}, chunks={summary['chunks']}"
    )
