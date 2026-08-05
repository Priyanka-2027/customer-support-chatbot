# vectorstore.py
# ─────────────────────────────────────────────────────────────
# Responsibility:
#   1. Build a FAISS vector store from document chunks (ingestion)
#   2. Save the vector store to disk
#   3. Load the vector store from disk (used by the API server)
#
# This module is the bridge between the ingestion pipeline and
# the retriever. Ingestion writes the store, the retriever reads
# it. They share this module so the same paths and settings are
# always used on both sides.
# ─────────────────────────────────────────────────────────────

import logging
from typing import List

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from app.config import VECTORSTORE_DIR
from app.embeddings import get_embedding_model

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# build_vectorstore()
# ─────────────────────────────────────────────────────────────
def build_vectorstore(chunks: List[Document]) -> FAISS:
    """
    Embed all chunks and build a FAISS vector store in memory.

    This function does the heavy lifting of the ingestion pipeline:
    it takes every text chunk, converts it to a 384-dimensional
    vector using the embedding model, and loads all vectors into
    a FAISS index ready for similarity search.

    Args:
        chunks: The list of Document chunks from split_documents().

    Returns:
        FAISS: An in-memory FAISS vector store containing all
        embedded chunks, ready to be saved or queried.

    Raises:
        ValueError: If the chunks list is empty.
    """

    if not chunks:
        raise ValueError(
            "Cannot build a vector store from an empty chunk list.\n"
            "Run load_documents() and split_documents() first."
        )

    logger.info(f"Building FAISS vector store from {len(chunks)} chunks...")
    logger.info("Embedding all chunks — this may take a minute...")

    # ── Retrieve the shared embedding model ───────────────────
    # We call get_embedding_model() rather than instantiating a
    # new model here. The @lru_cache decorator on that function
    # ensures we always get the same model instance — no duplicate
    # loading, no extra 90MB of RAM.
    embedding_model = get_embedding_model()

    # ── FAISS.from_documents() ────────────────────────────────
    # This is the core operation. Under the hood it does three
    # things in one call:
    #
    #   1. Extracts page_content from each Document
    #   2. Calls embedding_model.embed_documents() on all of them
    #      in batches — producing a list of 384-dim float vectors
    #   3. Adds all vectors + their metadata into a new FAISS index
    #
    # The result is a FAISS object that holds:
    #   • The index (all vectors, searchable by L2 distance)
    #   • The docstore (mapping from vector ID → Document object)
    #   • The index_to_docstore_id map (integer index → string ID)
    #
    # All three are needed together to go from "similar vector"
    # back to "here is the original text chunk and its metadata."
    vectorstore: FAISS = FAISS.from_documents(
        documents=chunks,           # the chunked Documents to embed
        embedding=embedding_model,  # the model that produces vectors
    )

    logger.info("FAISS vector store built successfully in memory.")
    return vectorstore


# ─────────────────────────────────────────────────────────────
# save_vectorstore()
# ─────────────────────────────────────────────────────────────
def save_vectorstore(vectorstore: FAISS) -> None:
    """
    Persist the FAISS vector store to disk.

    Saves two files into the configured VECTORSTORE_DIR:
      - index.faiss : the binary vector index
      - index.pkl   : the metadata mapping (docstore)

    Both files are required to load the store back later.
    Neither is human-readable — they are binary formats.

    Args:
        vectorstore: The in-memory FAISS store to persist.
    """

    # ── Ensure the output directory exists ───────────────────
    # mkdir() with parents=True creates any missing parent
    # directories in the path.
    # exist_ok=True means no error is raised if the folder
    # already exists — safe to call multiple times.
    VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)

    logger.info(f"Saving vector store to: {VECTORSTORE_DIR}")

    # ── save_local() ──────────────────────────────────────────
    # Writes index.faiss and index.pkl to the specified folder.
    # str() conversion is needed because FAISS expects a string
    # path, not a pathlib.Path object.
    vectorstore.save_local(str(VECTORSTORE_DIR))

    # ── Verify the files were created ────────────────────────
    # We confirm the expected files exist before reporting success.
    # This catches edge cases where the save seemed to succeed
    # but the files aren't actually there.
    faiss_file = VECTORSTORE_DIR / "index.faiss"
    pkl_file = VECTORSTORE_DIR / "index.pkl"

    if not faiss_file.exists() or not pkl_file.exists():
        raise RuntimeError(
            f"Vector store save appeared to succeed but files are missing.\n"
            f"Expected: {faiss_file} and {pkl_file}"
        )

    # Log file sizes so you can see roughly how much data was stored.
    # faiss_size in KB, rounded to 1 decimal place.
    faiss_size_kb = faiss_file.stat().st_size / 1024
    pkl_size_kb = pkl_file.stat().st_size / 1024

    logger.info("Vector store saved successfully.")
    logger.info(f"  index.faiss : {faiss_size_kb:.1f} KB")
    logger.info(f"  index.pkl   : {pkl_size_kb:.1f} KB")


# ─────────────────────────────────────────────────────────────
# load_vectorstore()
# ─────────────────────────────────────────────────────────────
def load_vectorstore() -> FAISS:
    """
    Load the FAISS vector store from disk into memory.

    Called by the API server at startup to make the vector store
    available for retrieval. The store stays in memory for the
    lifetime of the server process — no disk reads per request.

    Returns:
        FAISS: The loaded vector store, ready to be used as a
        retriever.

    Raises:
        FileNotFoundError: If the vector store files don't exist.
        RuntimeError: If loading fails for any other reason.
    """

    # ── Guard: vector store must have been built first ────────
    faiss_file = VECTORSTORE_DIR / "index.faiss"
    pkl_file = VECTORSTORE_DIR / "index.pkl"

    if not faiss_file.exists() or not pkl_file.exists():
        raise FileNotFoundError(
            f"Vector store not found at: {VECTORSTORE_DIR}\n"
            "Run the ingestion pipeline first:\n"
            "  python -m app.ingest"
        )

    logger.info(f"Loading vector store from: {VECTORSTORE_DIR}")

    # ── Retrieve the same embedding model used at ingestion ───
    # This is critical: the embedding model used to load the
    # store MUST be the same one used to build it.
    #
    # The FAISS index stores raw vectors. When a user query
    # comes in, it gets embedded using this same model to produce
    # a comparable vector. If you used a different model here,
    # the query vector would live in a completely different
    # mathematical space and similarity search would be meaningless.
    embedding_model = get_embedding_model()

    # ── load_local() ──────────────────────────────────────────
    # Reads index.faiss and index.pkl from disk and reconstructs
    # the full FAISS object (index + docstore + id mapping).
    #
    # allow_dangerous_deserialization=True is required because
    # index.pkl is loaded using Python's pickle module. LangChain
    # forces you to acknowledge this explicitly as a security
    # reminder: only load .pkl files that you created yourself.
    # Never load pickle files from untrusted sources.
    vectorstore: FAISS = FAISS.load_local(
        folder_path=str(VECTORSTORE_DIR),
        embeddings=embedding_model,
        allow_dangerous_deserialization=True,
    )

    logger.info("Vector store loaded successfully.")

    # ── Log index stats ───────────────────────────────────────
    # vectorstore.index.ntotal is a FAISS property that returns
    # the total number of vectors currently in the index.
    # This confirms the expected number of chunks are present.
    total_vectors = vectorstore.index.ntotal
    logger.info(f"  Vectors in index : {total_vectors}")

    return vectorstore


# ─────────────────────────────────────────────────────────────
# Manual test — run directly to verify the full save/load cycle
# python -m app.vectorstore
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    from langchain_core.documents import Document

    # ── Create minimal test chunks ────────────────────────────
    # We use synthetic chunks so this test runs without needing
    # real PDFs in the documents/ folder.
    test_chunks = [
        Document(
            page_content="Our return policy allows returns within 30 days of purchase.",
            metadata={"source": "refund-policy.pdf", "page": 0},
        ),
        Document(
            page_content="Free shipping is available on all orders over $50.",
            metadata={"source": "shipping-guide.pdf", "page": 0},
        ),
        Document(
            page_content="To reset your password, click Forgot Password on the login page.",
            metadata={"source": "account-help.pdf", "page": 1},
        ),
        Document(
            page_content="Refunds are processed within 5 to 7 business days.",
            metadata={"source": "refund-policy.pdf", "page": 1},
        ),
    ]

    # ── Build and save ────────────────────────────────────────
    logger.info("=== TEST: Build + Save ===")
    store = build_vectorstore(test_chunks)
    save_vectorstore(store)

    # ── Load back from disk ───────────────────────────────────
    logger.info("\n=== TEST: Load from disk ===")
    loaded_store = load_vectorstore()

    # ── Run a similarity search ───────────────────────────────
    # similarity_search() embeds the query string and returns the
    # K most similar Document objects from the store.
    # k=2 means return the 2 closest matches.
    logger.info("\n=== TEST: Similarity search ===")
    query = "Can I return a product and get a refund?"
    results = loaded_store.similarity_search(query, k=2)

    logger.info(f"Query : '{query}'")
    logger.info(f"Top {len(results)} results:")
    logger.info("─" * 50)

    for i, doc in enumerate(results, start=1):
        # doc.page_content is the original chunk text
        # doc.metadata holds source filename and page number
        logger.info(f"[{i}] Source : {doc.metadata.get('source')}")
        logger.info(f"    Page   : {doc.metadata.get('page')}")
        logger.info(f"    Text   : {doc.page_content}")
        logger.info("")

    logger.info("─" * 50)
    logger.info("Vector store is working correctly.")
