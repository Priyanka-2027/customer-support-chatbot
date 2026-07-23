# chain.py
# ─────────────────────────────────────────────────────────────
# Responsibility:
#   Assemble and expose the complete RAG chain:
#
#   user question
#       → retrieve top-K chunks from FAISS
#       → inject chunks into a carefully designed prompt
#       → send prompt to Gemini
#       → return structured response (answer + sources)
#
# This module owns three things:
#   1. The Gemini LLM client
#   2. The prompt template (the core of hallucination prevention)
#   3. The RAG chain that wires everything together
#
# chat.py calls ask() — that's the only public interface needed.
# ─────────────────────────────────────────────────────────────

import logging
from functools import lru_cache
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableParallel

from app.config import CHAT_HISTORY_WINDOW, GEMINI_MODEL, GOOGLE_API_KEY
from app.retriever import get_retriever

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# format_history()  [public helper]
# ─────────────────────────────────────────────────────────────

def format_history(
    messages: list[dict],
    window: int = CHAT_HISTORY_WINDOW,
) -> str:
    """
    Convert a list of message dicts into a formatted prompt string.

    Takes the most recent `window` pairs (2*window messages) so the
    prompt doesn't grow unboundedly over long conversations.

    Args:
        messages: List of dicts with 'role' ("user" or "bot") and 'text'.
                  Ordered oldest → newest (as returned by get_messages()).
        window:   Max number of prior user+bot pairs to include.
                  Defaults to CHAT_HISTORY_WINDOW from config.

    Returns:
        Formatted string with one "Label: text" line per message,
        or "" for an empty list.

    Raises:
        ValueError: If any message has a role other than "user" or "bot".
    """
    if not messages:
        return ""

    _ROLE_LABELS: dict[str, str] = {
        "user": "Customer",
        "bot": "Support Agent",
    }
    _MAX_TEXT_LENGTH = 2000

    # Validate all roles eagerly before any formatting so we fail
    # fast with a clear error rather than producing a partial result.
    for msg in messages:
        role = msg.get("role")
        if role not in _ROLE_LABELS:
            raise ValueError(
                f"Invalid message role: '{role}'. Expected 'user' or 'bot'."
            )

    # Take only the most recent window*2 messages.
    max_messages = window * 2
    recent = messages[-max_messages:] if len(messages) > max_messages else messages

    lines = []
    for msg in recent:
        label = _ROLE_LABELS[msg["role"]]
        text = msg["text"]
        if len(text) > _MAX_TEXT_LENGTH:
            text = text[:_MAX_TEXT_LENGTH]
        lines.append(f"{label}: {text}")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# THE PROMPT TEMPLATE
# ─────────────────────────────────────────────────────────────
# This is the most important part of the entire RAG system.
# Every word here is deliberate. It controls:
#   - What role Gemini plays
#   - What it's allowed to do
#   - What it must do when it doesn't know
#   - How it formats its response
#
# Structure:
#   [system]  → persistent instructions, never changes
#   [human]   → the per-request content (context + question)
#
# The {context} placeholder is filled by LangChain with the
# retrieved chunks joined together as a single string.
# The {input} placeholder is filled with the user's question.
# ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a helpful and knowledgeable assistant that answers questions accurately using ONLY the information provided in the context below.

Rules you must follow:
1. Base your answer exclusively on the provided context. Do not use any outside knowledge or assumptions.
2. If the answer is not found in the context, respond with exactly:
   "I don't have information about that in the provided documents. Please check the original document or contact support for further assistance."
3. Be concise, direct, and thorough. Extract all relevant information from the context.
4. If the context contains partial information, share everything that is available.
5. Never fabricate information, policies, prices, timelines, or procedures.
6. Use the conversation history below (if any) to understand follow-up questions.
7. When listing items (like projects, features, policies), list ALL of them found in the context.

{chat_history_block}

Context:
{context}"""

# ChatPromptTemplate.from_messages() builds a structured prompt
# that separates the system instruction from the user's input.
# This two-message structure is how chat models like Gemini
# are designed to be used — system sets the behaviour,
# human provides the per-turn content.
PROMPT_TEMPLATE = ChatPromptTemplate.from_messages(
    [
        # ("system", ...) → the SystemMessage — persistent instructions
        # Gemini receives this as context about how to behave.
        # It does not change between requests.
        ("system", SYSTEM_PROMPT),

        # ("human", ...) → the HumanMessage — the actual user question.
        # {input} is a LangChain placeholder that gets filled with
        # the user's question string at runtime.
        ("human", "{input}"),
    ]
)


# ─────────────────────────────────────────────────────────────
# _get_gemini_client()  [private, cached]
# ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_gemini_client():
    """
    Create and cache the Google Gemini client.

    Uses the google-genai SDK directly — more reliable than
    langchain-google-genai on Python 3.14.
    """
    if not GOOGLE_API_KEY:
        raise ValueError(
            "GOOGLE_API_KEY is not set.\n"
            "Add it to your .env file:\n"
            "  GOOGLE_API_KEY=your_key_here\n"
            "Get a free key at: https://aistudio.google.com/app/apikey"
        )
    from google import genai
    import os as _os
    _os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY
    client = genai.Client()
    logger.info(f"Gemini client initialized (model: {GEMINI_MODEL})")
    return client


def _call_gemini(prompt: str) -> str:
    """
    Call the Gemini API directly using the google-genai SDK.

    Args:
        prompt: The full prompt string to send.

    Returns:
        The generated text response.
    """
    client = _get_gemini_client()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    return response.text


# ─────────────────────────────────────────────────────────────
# _get_retriever_cached()  [private, cached]
# ─────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_retriever_cached():
    """Cache the retriever so we don't reconnect on every call."""
    return get_retriever()


# ─────────────────────────────────────────────────────────────
# ask()  [public interface]
# ─────────────────────────────────────────────────────────────

def ask(question: str, history: list[dict] | None = None) -> dict:
    """
    Run the full RAG pipeline for a user question.

    This is the only function chat.py needs to call.
    Everything — retrieval, prompt construction, LLM call,
    response formatting — happens inside this function.

    Args:
        question: The user's natural language question string.
        history:  Optional list of prior message dicts, each with
                  'role' ("user" or "bot") and 'text'.
                  Defaults to [] (single-turn / backward-compatible mode).

    Returns:
        dict with keys:
            "answer"  (str)        — Gemini's grounded response
            "sources" (List[dict]) — list of source documents used,
                                     each with "filename" and "page"

    Raises:
        ValueError: If the question is empty or any history message
                    has an invalid role.
        Exception:  Re-raises any Gemini API errors with context.
    """
    if history is None:
        history = []

    # ── Input validation ──────────────────────────────────────
    if not question or not question.strip():
        raise ValueError("Question cannot be empty.")

    # Normalize whitespace — collapse multiple spaces/newlines
    # into a single space. This prevents embedding artifacts from
    # poorly formatted user input.
    question = " ".join(question.split())

    logger.info(f"Processing question: '{question[:100]}' with {len(history)} history message(s).")

    # ── Build the chat history block ──────────────────────────
    # format_history raises ValueError on invalid roles — surfaces
    # as a 422 in the chat endpoint.
    history_str = format_history(history)
    chat_history_block = (
        f"Prior conversation:\n{history_str}" if history_str else ""
    )

    # ── Retrieve relevant chunks ──────────────────────────────
    retriever = _get_retriever_cached()
    try:
        raw_sources = retriever.invoke(question)
    except Exception as e:
        logger.error(f"Retrieval failed: {e}")
        raise

    context_text = "\n\n".join(doc.page_content for doc in raw_sources)

    # ── Build the full prompt ─────────────────────────────────
    system_filled = SYSTEM_PROMPT.format(
        chat_history_block=chat_history_block,
        context=context_text,
    )
    full_prompt = f"{system_filled}\n\nCustomer question: {question}"

    # ── Call Gemini directly (google-genai SDK) ───────────────
    try:
        answer = _call_gemini(full_prompt).strip()
    except Exception as e:
        logger.error(f"Gemini API call failed: {e}")
        raise

    # ── Format sources ────────────────────────────────────────
    sources = _format_sources(raw_sources)

    logger.info(f"Answer generated ({len(answer)} chars) from {len(sources)} source(s).")

    return {
        "answer": answer,
        "sources": sources,
    }


# ─────────────────────────────────────────────────────────────
# _format_sources()  [private helper]
# ─────────────────────────────────────────────────────────────

def _format_sources(documents: list) -> list[dict]:
    """
    Convert raw LangChain Document objects into serializable dicts.

    Includes:
      - filename  : bare filename extracted from the full path
      - page      : 1-indexed page number
      - chunk_text: first 300 chars of the retrieved passage
      - chunk_index: character start offset within the page

    Deduplication logic: if two chunks came from the exact same
    (filename, page, start_index) triplet — which can happen when
    chunk overlap causes nearly identical passages to be retrieved
    twice — only the first occurrence is kept.

    Args:
        documents: List of LangChain Document objects from
                   result["context"] in the RAG chain output.

    Returns:
        List of dicts ready for Pydantic SourceDocument validation.
    """

    # seen tracks (filename, page, chunk_index) triplets.
    # Using chunk_index in the key (not just filename+page) means
    # two different chunks from the same page are kept as separate
    # source entries — they cover different passages.
    seen: set = set()
    sources: list = []

    for doc in documents:
        # ── Extract metadata ─────────────────────────────────
        raw_source: str = doc.metadata.get("source", "")
        raw_page: int = doc.metadata.get("page", 0)

        # start_index was added by RecursiveCharacterTextSplitter
        # when add_start_index=True was set in ingest.py.
        # It records the character offset of this chunk within
        # the original page text. Default 0 if not present
        # (e.g. for manually constructed documents).
        chunk_index: int = int(doc.metadata.get("start_index", 0))

        # ── Normalise filename ────────────────────────────────
        # raw_source is the full filesystem path written by
        # PyPDFLoader, e.g.:
        #   C:\Users\...\backend\documents\refund-policy.pdf
        # We want just:
        #   refund-policy.pdf
        # Replace backslashes first so the split works on Windows.
        filename: str = raw_source.replace("\\", "/").split("/")[-1]

        # ── Convert page to 1-indexed ─────────────────────────
        # PyPDFLoader uses 0-based page numbers internally.
        # Users read PDFs with 1-based page numbers — add 1.
        page: int = int(raw_page) + 1

        # ── Build the chunk text preview ──────────────────────
        # doc.page_content is the raw text of this chunk as it
        # was stored in FAISS and passed to the LLM prompt.
        # We truncate to 300 characters for the API response —
        # enough to show the key passage without bloating the payload.
        #
        # .strip() removes leading/trailing whitespace that PDFs
        # often introduce (header/footer artifacts, extra newlines).
        #
        # .replace("\n", " ") collapses newlines into spaces so
        # the preview reads as a flowing sentence in the UI.
        raw_text: str = doc.page_content.strip().replace("\n", " ")

        # Collapse multiple consecutive spaces into one.
        # PDF text extraction often produces "word  word" with
        # double spaces where the original had formatting.
        import re
        cleaned_text: str = re.sub(r" {2,}", " ", raw_text)

        # Truncate to 300 chars. If the chunk is longer, add "…"
        # so the user knows there's more text in the full document.
        PREVIEW_LENGTH = 300
        chunk_text: str = (
            cleaned_text[:PREVIEW_LENGTH] + "…"
            if len(cleaned_text) > PREVIEW_LENGTH
            else cleaned_text
        )

        # ── Deduplication ─────────────────────────────────────
        # Use (filename, page, chunk_index) as the unique key.
        # Two chunks with the same key are truly identical
        # (same file, same page, same start offset) and only
        # the first one should appear in the response.
        key = (filename, page, chunk_index)
        if key in seen:
            continue

        seen.add(key)
        sources.append({
            "filename": filename,
            "page": page,
            "chunk_text": chunk_text,
            "chunk_index": chunk_index,
        })

    return sources


# ─────────────────────────────────────────────────────────────
# Manual test — run directly to verify the full RAG chain
# python -m app.chain
#
# Requires:
#   1. GOOGLE_API_KEY set in .env
#   2. Vector store built (run python -m app.ingest first)
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    test_questions = [
        "What is your return policy?",
        "How long does a refund take?",
        "Do you offer free shipping?",
        "What is the meaning of life?",   # out of scope — tests "I don't know"
    ]

    logger.info("═" * 60)
    logger.info("RAG CHAIN TEST — Gemini + FAISS")
    logger.info("═" * 60)

    for question in test_questions:
        logger.info(f"\nQ: {question}")
        logger.info("─" * 60)

        response = ask(question)

        # Print the answer
        print(f"\nA: {response['answer']}")

        # Print the sources
        if response["sources"]:
            print("\nSources:")
            for src in response["sources"]:
                # page is already 1-indexed from _format_sources()
                print(f"  • {src['filename']} — page {src['page']}")
        else:
            print("  (no sources)")

        logger.info("─" * 60)

    logger.info("\nRAG chain test complete.")
