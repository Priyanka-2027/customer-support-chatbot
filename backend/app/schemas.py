# schemas.py — All Pydantic request/response models

from pydantic import BaseModel, Field


# ── Source document ───────────────────────────────────────────

class SourceDocument(BaseModel):
    filename: str = Field(..., examples=["refund-policy.pdf"])
    page: int = Field(..., ge=1, examples=[2])
    chunk_text: str = Field(..., examples=["Returns within 30 days."])
    chunk_index: int = Field(default=0, ge=0)


# ── Chat ──────────────────────────────────────────────────────

class ChatRequestWithHistory(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    conversation_id: str | None = Field(default=None)


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceDocument] = Field(default_factory=list)
    conversation_id: str | None = Field(default=None)


# ── Upload ────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    message: str
    filename: str
    chunks_created: int = Field(..., ge=0)


class FileUploadResult(BaseModel):
    filename: str
    success: bool
    chunks_created: int = Field(default=0, ge=0)
    error: str | None = Field(default=None)


class BatchUploadResponse(BaseModel):
    total_files: int = Field(..., ge=0)
    successful: int = Field(..., ge=0)
    failed: int = Field(..., ge=0)
    total_chunks_created: int = Field(..., ge=0)
    results: list[FileUploadResult] = Field(default_factory=list)


# ── Health ────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    vectorstore_loaded: bool
    environment: str
    backend: str  # "faiss" | "pinecone"


# ── Chat history ──────────────────────────────────────────────

class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = Field(default=0, ge=0)


class StoredMessage(BaseModel):
    id: str
    conversation_id: str
    role: str
    text: str
    sources: list[SourceDocument] = Field(default_factory=list)
    created_at: str


class CreateConversationResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


# ── Auth ──────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = Field(default="bearer")


class AuthSuccessResponse(BaseModel):
    message: str = "ok"


class LogoutResponse(BaseModel):
    message: str = "logged out"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    created_at: str
    access_token: str | None = None  # returned on login/register for cross-origin local dev
