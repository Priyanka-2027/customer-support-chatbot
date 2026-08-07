# chat.py
# ─────────────────────────────────────────────────────────────
# Responsibility:
#   Define the API route handlers (endpoints).
#   Each handler does exactly three things:
#     1. Accept and validate the incoming request
#     2. Call the appropriate business logic function
#     3. Return a typed, validated response
#
# Route handlers must not contain business logic.
# They are thin bridges between HTTP and the application core.
# All heavy lifting lives in chain.py, ingest.py, vectorstore.py.
# ─────────────────────────────────────────────────────────────

import logging
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.concurrency import run_in_threadpool

from app.chain import ask
from app.config import DOCUMENTS_DIR, ENVIRONMENT
from app.database import (
    create_conversation,
    delete_conversation,
    get_conversation,
    get_messages,
    list_conversations,
    save_message,
    update_conversation_timestamp,
)
from app.ingest import load_documents, split_documents
from app.schemas import (
    BatchUploadResponse,
    ChatRequestWithHistory,
    ChatResponse,
    ConversationSummary,
    CreateConversationResponse,
    FileUploadResult,
    HealthResponse,
    SourceDocument,
    StoredMessage,
    UploadResponse,
)
from app.security import get_current_user
from app.vectorstore import build_vectorstore, load_vectorstore, save_vectorstore

logger = logging.getLogger(__name__)

# ── APIRouter ─────────────────────────────────────────────────
# APIRouter is FastAPI's way of grouping related endpoints.
# We define routes here and register the router in main.py with
# a prefix. This keeps main.py clean and makes routes testable
# in isolation — you can mount this router in a test app without
# needing the full application.
router = APIRouter()


def _invalidate_retriever_cache() -> None:
    """
    Clear the cached retriever and vectorstore so the next request
    loads the updated FAISS index (or reconnects to Pinecone).
    Called after every successful document upload.
    """
    try:
        from app.retriever import _get_vectorstore, _get_pinecone_vectorstore, get_retriever
        from app.chain import _get_retriever_cached
        # Clear FAISS cache
        if hasattr(_get_vectorstore, 'cache_clear'):
            _get_vectorstore.cache_clear()
        # Clear Pinecone cache
        if hasattr(_get_pinecone_vectorstore, 'cache_clear'):
            _get_pinecone_vectorstore.cache_clear()
        # Clear chain's retriever cache
        if hasattr(_get_retriever_cached, 'cache_clear'):
            _get_retriever_cached.cache_clear()
        logger.info("Retriever cache invalidated — new documents will be searchable.")
    except Exception as e:
        logger.warning(f"Cache invalidation failed (non-critical): {e}")


# ─────────────────────────────────────────────────────────────
# GET /health
# ─────────────────────────────────────────────────────────────

@router.get(
    "/health",
    response_model=HealthResponse,
    # tags group endpoints together in the /docs Swagger UI.
    tags=["System"],
    summary="Health check",
    description="Verify the server is running and all dependencies are ready.",
)
async def health_check() -> HealthResponse:
    """
    Lightweight health check endpoint.

    Called by:
      - Render / Railway to verify the server started correctly
      - Uptime monitoring tools (UptimeRobot, Betterstack)
      - The frontend to check if the backend is reachable
      - You, to quickly verify the server is alive

    Returns a 200 OK with status info, or 503 if critical
    dependencies are unavailable.
    """

    # ── Check if the vector store is accessible ───────────────
    # We attempt to load the FAISS index. If ingestion hasn't
    # been run yet, this will fail — which is useful to know.
    # We catch the exception and report degraded status rather
    # than crashing the health check endpoint.
    vectorstore_loaded = False
    backend = "pinecone" if ENVIRONMENT == "production" else "faiss"

    if ENVIRONMENT == "production":
        try:
            from app.pinecone_store import get_pinecone_store
            from app.embeddings import get_embedding_model
            store = get_pinecone_store(get_embedding_model())
            stats = store._index.describe_index_stats()
            vectorstore_loaded = stats.get("total_vector_count", 0) > 0
        except Exception as e:
            logger.warning(f"Health check: Pinecone probe failed: {e}")
            vectorstore_loaded = False
    else:
        try:
            vs = load_vectorstore()
            vectorstore_loaded = vs.index.ntotal > 0
        except FileNotFoundError:
            logger.warning("Health check: vector store not found. Run ingestion first.")
        except Exception as e:
            logger.error(f"Health check: unexpected vector store error: {e}")

    return HealthResponse(
        status="ok" if vectorstore_loaded else "degraded",
        vectorstore_loaded=vectorstore_loaded,
        environment=ENVIRONMENT,
        backend=backend,
    )


# ─────────────────────────────────────────────────────────────
# POST /chat
# ─────────────────────────────────────────────────────────────

@router.post(
    "/chat",
    response_model=ChatResponse,
    tags=["Chat"],
    summary="Ask a question",
    description="Send a customer question. Pass conversation_id to persist within an existing conversation, or omit it to auto-create one.",
    status_code=status.HTTP_200_OK,
)
async def chat(
    request: ChatRequestWithHistory,
    # Depends(get_current_user) extracts the JWT from the
    # Authorization: Bearer <token> header, validates it, and
    # returns the user dict. If the token is missing or invalid,
    # FastAPI returns 401 before this function body runs.
    current_user: dict = Depends(get_current_user),
) -> ChatResponse:
    """
    Main RAG endpoint — now persists every turn to SQLite.

    Flow:
      1. Validate the request
      2. Resolve or create the conversation in the DB
      3. Run the RAG pipeline (embed → retrieve → Gemini)
      4. Save the user message and bot response to the DB
      5. Return the response

    The conversation_id in the request body is optional.
    If omitted, a new conversation is created automatically and
    its id is included in the response so the frontend can use
    it for subsequent turns.
    """

    logger.info(f"POST /chat — question: '{request.question[:80]}'")

    # ── Step 1: Resolve the conversation ─────────────────────
    # If the client sent a conversation_id, verify it exists.
    # If not, create a new conversation using the question as
    # the title (truncated to 60 chars).
    conv_id: str

    if request.conversation_id:
        existing = await get_conversation(request.conversation_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversation '{request.conversation_id}' not found.",
            )
        # Security check: the conversation must belong to the requesting user.
        # Without this check, user A could send another user's conversation_id
        # and append their messages to it — a cross-user data pollution bug.
        if existing["user_id"] != current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have access to this conversation.",
            )
        conv_id = request.conversation_id
    else:
        conv_id = str(uuid.uuid4())
        title = request.question.strip()[:60]
        await create_conversation(conv_id, title, user_id=current_user["id"])

    # ── Step 2: Load conversation history from the database ──
    # History is loaded BEFORE saving the current user message so
    # the current turn is not included in what the LLM sees.
    history: list[dict] = []
    if request.conversation_id:
        try:
            raw_messages = await get_messages(conv_id)
            history = [
                {"role": msg["role"], "text": msg["text"]}
                for msg in raw_messages
            ]
        except Exception as e:
            logger.error(
                f"POST /chat — failed to load history for '{conv_id}': {e}",
                exc_info=True,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Chat history is temporarily unavailable. Please try again.",
            )

    # ── Step 3: Run the RAG chain ─────────────────────────────
    try:
        result: dict = await run_in_threadpool(ask, request.question, history)
    except ValueError as e:
        logger.warning(f"POST /chat — invalid input: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"POST /chat — internal error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The AI service is temporarily unavailable. Please try again.",
        )

    # ── Step 4: Build the typed response ─────────────────────
    sources_pydantic = [
        SourceDocument(
            filename=src["filename"],
            page=src["page"],
            chunk_text=src["chunk_text"],
            chunk_index=src["chunk_index"],
        )
        for src in result.get("sources", [])
    ]

    # ── Step 5: Persist both turns to the database ───────────
    # Save user message first (it happened first chronologically).
    await save_message(
        message_id=str(uuid.uuid4()),
        conversation_id=conv_id,
        role="user",
        text=request.question,
        sources=[],             # user messages never have sources
    )

    # Save bot response with its sources serialised as a list of dicts.
    # model_dump() converts a Pydantic model to a plain dict —
    # safe to pass to json.dumps() inside save_message().
    await save_message(
        message_id=str(uuid.uuid4()),
        conversation_id=conv_id,
        role="bot",
        text=result["answer"],
        sources=[s.model_dump() for s in sources_pydantic],
    )

    # Touch the conversation's updated_at so the sidebar
    # reorders correctly (most recently active at top).
    await update_conversation_timestamp(conv_id)

    logger.info(f"POST /chat — saved turn to conversation '{conv_id}'")

    # ── Step 6: Return the response ───────────────────────────
    # Include conversation_id in the response so the frontend
    # can store it and send it back in the next turn.
    return ChatResponse(
        answer=result["answer"],
        sources=sources_pydantic,
        conversation_id=conv_id,
    )


# ─────────────────────────────────────────────────────────────
# POST /upload
# ─────────────────────────────────────────────────────────────

@router.post(
    "/upload",
    response_model=UploadResponse,
    tags=["Documents"],
    summary="Upload a PDF document",
    description="Upload a PDF to add to the knowledge base. The file is processed and added to the vector store immediately.",
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    # UploadFile is FastAPI's type for multipart/form-data file uploads.
    # File(...) marks it as required (no default).
    # The client sends: Content-Type: multipart/form-data with a
    # field named "file" containing the PDF binary.
    file: UploadFile = File(
        ...,
        description="A PDF file to add to the knowledge base.",
    ),
) -> UploadResponse:
    """
    Upload a PDF and immediately add it to the vector store.

    Flow:
      1. Validate the file is a PDF
      2. Save it to the documents/ folder
      3. Load + split + embed the new file
      4. Merge new vectors into the existing FAISS index
      5. Save the updated index to disk
      6. Return the number of chunks added

    This endpoint allows the knowledge base to be updated at
    runtime without restarting the server or re-running the
    full ingestion pipeline.
    """

    logger.info(f"POST /upload — filename: '{file.filename}'")

    # ── Validate file type ────────────────────────────────────
    # file.content_type is set by the client's HTTP headers.
    # We also check the filename extension as a second guard,
    # since content_type can be spoofed or absent.
    is_pdf_content_type = file.content_type == "application/pdf"
    is_pdf_extension = (
        file.filename is not None
        and file.filename.lower().endswith(".pdf")
    )

    if not (is_pdf_content_type or is_pdf_extension):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only PDF files are supported. Received: '{file.content_type}'",
        )

    # ── Sanitize the filename ─────────────────────────────────
    # file.filename comes from the client — never trust it directly.
    # Path(...).name extracts just the filename component, stripping
    # any path traversal attempts like "../../etc/passwd.pdf".
    safe_filename: str = Path(file.filename).name

    if not safe_filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename.",
        )

    # ── Save the file to the documents/ directory ─────────────
    # DOCUMENTS_DIR is defined in config.py and points to
    # backend/documents/. We save the file here so it becomes
    # part of the permanent knowledge base — future full
    # re-ingestions will pick it up.
    destination: Path = DOCUMENTS_DIR / safe_filename

    try:
        # run_in_threadpool wraps the synchronous file I/O.
        # shutil.copyfileobj reads from the upload stream and
        # writes to the destination file in chunks — memory efficient
        # for large files, doesn't load the whole PDF into RAM.
        await run_in_threadpool(_save_upload, file, destination)
    except Exception as e:
        logger.error(f"POST /upload — file save failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save the uploaded file.",
        )

    # ── Process the new file and update the vector store ──────
    try:
        chunks_added = await run_in_threadpool(
            _ingest_single_file, destination
        )
    except Exception as e:
        # If ingestion fails, remove the saved file to keep the
        # filesystem consistent — don't leave an unindexed PDF
        # in the documents folder.
        logger.error(f"POST /upload — ingestion failed: {e}", exc_info=True)
        if destination.exists():
            destination.unlink()    # unlink() deletes the file
        detail = (
            "Pinecone upsert failed. The file was not added to the knowledge base."
            if ENVIRONMENT == "production"
            else f"File was uploaded but could not be processed: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=detail,
        )

    logger.info(
        f"POST /upload — '{safe_filename}' processed, "
        f"{chunks_added} chunks added to vector store."
    )

    # Invalidate the retriever cache so the next query picks up the new document
    _invalidate_retriever_cache()

    return UploadResponse(
        message="Document uploaded and added to the knowledge base successfully.",
        filename=safe_filename,
        chunks_created=chunks_added,
    )


# ─────────────────────────────────────────────────────────────
# POST /upload/batch
# ─────────────────────────────────────────────────────────────

@router.post(
    "/upload/batch",
    response_model=BatchUploadResponse,
    tags=["Documents"],
    summary="Upload multiple PDF documents",
    description=(
        "Upload up to 10 PDFs at once. Each file is validated, "
        "saved, and added to the vector store. Per-file results "
        "are returned so the client knows exactly which files "
        "succeeded or failed."
    ),
    # 207 Multi-Status: used when the response contains results
    # for multiple operations that may have mixed outcomes.
    # Some files may succeed while others fail — 207 signals
    # "I processed everything; check individual results."
    status_code=status.HTTP_207_MULTI_STATUS,
)
async def upload_documents_batch(
    # List[UploadFile] accepts multiple files under the same
    # form field name. The client sends them as:
    #   files=file1.pdf&files=file2.pdf (multipart/form-data)
    # FastAPI collects them all into this list automatically.
    files: list[UploadFile] = File(
        ...,
        description="One or more PDF files to add to the knowledge base.",
    ),
) -> BatchUploadResponse:
    """
    Upload multiple PDFs and add them all to the vector store.

    Processes files sequentially. If one file fails, processing
    continues with the remaining files — partial success is valid.

    Each file goes through:
      1. Type validation (must be PDF)
      2. Filename sanitization (path traversal prevention)
      3. Save to documents/ folder
      4. Load + split + embed
      5. Merge into FAISS index

    The FAISS index is saved to disk once after all files are
    processed, not after each file — this is more efficient
    and keeps the index consistent.
    """

    logger.info(f"POST /upload/batch — {len(files)} file(s) received")

    # ── Guard: enforce file count limit ──────────────────────
    # Prevent accidental or malicious uploads of hundreds of files
    # in a single request that would tie up the server.
    MAX_FILES = 10
    if len(files) > MAX_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum {MAX_FILES} files per request. Received {len(files)}.",
        )

    if len(files) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files received. Please attach at least one PDF.",
        )

    # ── Process each file and collect results ────────────────
    # We collect ALL results before saving the index.
    # This way, if file 3 of 5 fails, files 1, 2, 4, 5 still get
    # processed and the index is saved once with everything.
    results: list[FileUploadResult] = []

    # Accumulate all new chunks from ALL files.
    # We'll add them to the vector store in one batch at the end.
    all_new_chunks: list = []

    for file in files:
        filename_label = file.filename or "unknown"
        logger.info(f"  Processing: '{filename_label}'")

        # ── Per-file validation ───────────────────────────────
        is_pdf_content_type = file.content_type == "application/pdf"
        is_pdf_extension = (
            file.filename is not None
            and file.filename.lower().endswith(".pdf")
        )

        if not (is_pdf_content_type or is_pdf_extension):
            # Record failure for this file, continue to next file.
            # We don't raise HTTPException — that would abort the
            # entire batch. We record the per-file error instead.
            results.append(FileUploadResult(
                filename=filename_label,
                success=False,
                error=f"Not a PDF file (content_type='{file.content_type}').",
            ))
            continue

        # ── Filename sanitization ─────────────────────────────
        # Path(file.filename).name strips path components.
        # This prevents "../../sensitive/file.pdf" attacks.
        safe_filename = Path(file.filename).name
        if not safe_filename:
            results.append(FileUploadResult(
                filename=filename_label,
                success=False,
                error="Invalid or empty filename.",
            ))
            continue

        destination = DOCUMENTS_DIR / safe_filename

        # ── Save file to disk ─────────────────────────────────
        try:
            await run_in_threadpool(_save_upload, file, destination)
        except Exception as e:
            logger.error(f"  Save failed for '{safe_filename}': {e}")
            results.append(FileUploadResult(
                filename=safe_filename,
                success=False,
                error="Failed to save file to disk.",
            ))
            continue

        # ── Load and split (no embedding yet) ────────────────
        # We extract chunks here but defer embedding until all
        # files are loaded. This avoids partial index saves and
        # is more efficient for the embedding model.
        try:
            chunks = await run_in_threadpool(_load_and_split, destination)
            all_new_chunks.extend(chunks)

            # Record a temporary success entry — we'll confirm
            # chunk count after embedding succeeds.
            results.append(FileUploadResult(
                filename=safe_filename,
                success=True,
                chunks_created=len(chunks),
            ))
            logger.info(f"  '{safe_filename}' → {len(chunks)} chunks extracted")

        except Exception as e:
            logger.error(f"  Split failed for '{safe_filename}': {e}")
            # Clean up saved file — don't leave an unindexed PDF.
            if destination.exists():
                destination.unlink()
            results.append(FileUploadResult(
                filename=safe_filename,
                success=False,
                error=str(e),
            ))

    # ── Embed all chunks and update vector store once ─────────
    # Only run if at least one file was successfully chunked.
    if all_new_chunks:
        try:
            await run_in_threadpool(_merge_chunks_into_store, all_new_chunks)
            logger.info(
                f"Vector store updated: {len(all_new_chunks)} total chunks added."
            )
            # Invalidate retriever cache so next query uses the updated index
            _invalidate_retriever_cache()
        except Exception as e:
            # Embedding or vector store save failed.
            # Mark ALL previously-successful files as failed since
            # their chunks didn't make it into the index.
            logger.error(f"Vector store update failed: {e}", exc_info=True)
            error = (
                "Pinecone upsert failed. Please retry."
                if ENVIRONMENT == "production"
                else "Embedding failed. Please retry."
            )
            results = [
                FileUploadResult(
                    filename=r.filename,
                    success=False,
                    error=error,
                ) if r.success else r
                for r in results
            ]

    # ── Build summary statistics ──────────────────────────────
    successful = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)
    total_chunks = sum(r.chunks_created for r in results if r.success)

    logger.info(
        f"Batch upload complete: {successful} succeeded, "
        f"{failed} failed, {total_chunks} total chunks."
    )

    return BatchUploadResponse(
        total_files=len(files),
        successful=successful,
        failed=failed,
        total_chunks_created=total_chunks,
        results=results,
    )


# ─────────────────────────────────────────────────────────────
# Private helpers for upload (sync, run in thread pool)
# ─────────────────────────────────────────────────────────────
def _save_upload(file: UploadFile, destination: Path) -> None:
    """
    Save an uploaded file to disk.

    Synchronous — must be called via run_in_threadpool().

    Args:
        file:        The FastAPI UploadFile object.
        destination: Full path where the file should be saved.
    """
    # Ensure the documents directory exists before writing.
    destination.parent.mkdir(parents=True, exist_ok=True)

    # Open the destination in write-binary mode.
    # "wb" = write, binary — required for PDF files which are
    # binary data, not text. Using text mode would corrupt the file.
    with open(destination, "wb") as buffer:
        # shutil.copyfileobj streams from source to destination
        # in chunks — avoids loading the entire PDF into memory.
        # file.file is the underlying SpooledTemporaryFile object
        # that FastAPI uses to buffer the upload.
        shutil.copyfileobj(file.file, buffer)


def _load_and_split(file_path: Path) -> list:
    """
    Load a single PDF and split it into chunks.
    Does NOT embed — embedding is deferred to _merge_chunks_into_store().

    Synchronous — must be called via run_in_threadpool().

    Args:
        file_path: Full path to the saved PDF file.

    Returns:
        List of LangChain Document chunks.

    Raises:
        ValueError: If no text can be extracted from the PDF.
    """
    from langchain_community.document_loaders import PyPDFLoader

    loader = PyPDFLoader(str(file_path))
    pages = loader.load()

    if not pages:
        raise ValueError(
            f"No text could be extracted from '{file_path.name}'. "
            "Ensure the PDF contains selectable text, not scanned images."
        )

    # split_documents() is imported from ingest.py.
    # Re-using it ensures consistent chunk_size and chunk_overlap
    # settings for all files, whether uploaded one-by-one or in batch.
    return split_documents(pages)


def _ingest_single_file(file_path: Path) -> int:
    """
    Load, split, and embed a single PDF into the active vector store.

    Convenience wrapper used by upload_document() — combines
    _load_and_split() and _merge_chunks_into_store() in one call.

    Synchronous — must be called via run_in_threadpool().

    Args:
        file_path: Full path to the saved PDF file.

    Returns:
        int: Number of chunks added to the vector store.
    """
    chunks = _load_and_split(file_path)
    _merge_chunks_into_store(chunks)
    return len(chunks)


def _merge_chunks_into_store(chunks: list) -> None:
    """
    Embed a list of chunks and merge them into the active vector store.

    Routes to FAISS (development) or Pinecone (production) based on
    ENVIRONMENT. Saves the updated FAISS index to disk when in development.

    Synchronous — must be called via run_in_threadpool().

    Args:
        chunks: List of Document chunks from one or more files.
    """
    if ENVIRONMENT == "production":
        # Deferred import — langchain-pinecone is not installed in dev.
        from app.pinecone_store import upsert_to_pinecone
        try:
            upsert_to_pinecone(chunks)
        except Exception:
            logger.error(
                f"Pinecone upsert failed for {len(chunks)} chunks.",
                exc_info=True,
            )
            raise

    elif ENVIRONMENT == "development":
        try:
            existing_store = load_vectorstore()
            existing_store.add_documents(chunks)
            save_vectorstore(existing_store)
        except FileNotFoundError:
            logger.info("No existing vector store found. Creating new one from uploaded files.")
            new_store = build_vectorstore(chunks)
            save_vectorstore(new_store)

    else:
        raise ValueError(
            f"Invalid ENVIRONMENT value: '{ENVIRONMENT}'. "
            "Must be 'development' or 'production'."
        )

# ─────────────────────────────────────────────────────────────
# POST /admin/ingest
# ─────────────────────────────────────────────────────────────
# One-time endpoint to trigger document ingestion on the server.
# Protected by a secret key passed as a query parameter.
# Call once to populate Pinecone, then it's done permanently.

@router.get(
    "/admin/ingest",
    tags=["Admin"],
    summary="Trigger document ingestion",
)
async def trigger_ingestion(secret: str) -> dict:
    """
    Trigger the full ingestion pipeline on the server.
    Protected by ADMIN_SECRET env var.
    """
    import os
    admin_secret = os.getenv("ADMIN_SECRET", "")
    if not admin_secret or secret != admin_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing admin secret.",
        )

    try:
        result = await run_in_threadpool(_run_ingestion)
        return {"status": "ok", "chunks": result}
    except Exception as e:
        logger.error(f"Admin ingestion failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {str(e)}",
        )


def _run_ingestion() -> int:
    """Run the full ingestion pipeline synchronously."""
    from app.ingest import load_documents, split_documents
    from app.embeddings import get_embedding_model

    docs = load_documents()
    chunks = split_documents(docs)

    if ENVIRONMENT == "production":
        from app.pinecone_store import build_pinecone_store
        get_embedding_model()  # warm up
        build_pinecone_store(chunks, get_embedding_model())
    else:
        store = build_vectorstore(chunks)
        save_vectorstore(store)

    return len(chunks)
