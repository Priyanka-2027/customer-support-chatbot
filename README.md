# Customer Support Chatbot

An AI-powered customer support chatbot built with Retrieval-Augmented Generation (RAG). It answers questions using your own documentation as the knowledge base — no hallucinations, only grounded answers from your documents.

![Stack](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat) ![Stack](https://img.shields.io/badge/LLM-Google%20Gemini-4285F4?style=flat) ![Stack](https://img.shields.io/badge/VectorDB-FAISS%20%2F%20Pinecone-orange?style=flat) ![Stack](https://img.shields.io/badge/Frontend-React%20%2B%20Vite-61DAFB?style=flat)

---

## What it does

- Users register/login and chat with an AI assistant
- The assistant retrieves relevant passages from your uploaded PDF documents
- Google Gemini generates grounded answers using only those passages
- Full multi-turn conversation history is preserved per session
- Admins can upload new PDFs at runtime to expand the knowledge base

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   React Frontend                     │
│  AuthForm → ChatWindow → ChatInput → UploadPanel    │
└────────────────────┬────────────────────────────────┘
                     │ REST API (axios)
                     ▼
┌─────────────────────────────────────────────────────┐
│                  FastAPI Backend                     │
│                                                     │
│  /api/v1/auth/*   JWT authentication                │
│  /api/v1/chat     RAG pipeline                      │
│  /api/v1/upload   Document ingestion                │
│  /api/v1/health   Health check                      │
│                                                     │
│  RAG Pipeline:                                      │
│  Question → Embed → Retrieve → Prompt → Gemini      │
│                                                     │
│  Vector Store:                                      │
│  development  →  FAISS (local file)                 │
│  production   →  Pinecone (cloud)                   │
│                                                     │
│  History:  SQLite (aiosqlite)                       │
│  Auth:     JWT (access + refresh tokens)            │
└─────────────────────────────────────────────────────┘
```

---

## Tech Stack

### Backend
| Layer | Technology |
|---|---|
| Web framework | FastAPI 0.111 |
| LLM | Google Gemini (gemini-1.5-flash) |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| Vector store (dev) | FAISS |
| Vector store (prod) | Pinecone |
| RAG framework | LangChain |
| PDF parsing | PyPDF |
| Authentication | JWT (python-jose + passlib/bcrypt) |
| Database | SQLite via aiosqlite |
| Server | Uvicorn |

### Frontend
| Layer | Technology |
|---|---|
| Framework | React 19 |
| Build tool | Vite 8 |
| Language | TypeScript |
| Styling | Tailwind CSS v4 |
| HTTP client | Axios |
| Markdown rendering | react-markdown |
| Testing | Vitest + Testing Library |

---

## Project Structure

```
customer-support-chatbot/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app, CORS, startup/shutdown
│   │   ├── config.py        # All settings from .env
│   │   ├── auth.py          # /auth/* route handlers
│   │   ├── chat.py          # /chat, /upload route handlers
│   │   ├── chain.py         # RAG pipeline (retrieve → prompt → Gemini)
│   │   ├── retriever.py     # Vector store retriever (FAISS or Pinecone)
│   │   ├── embeddings.py    # Sentence-transformers embedding model
│   │   ├── ingest.py        # PDF loading and chunk splitting
│   │   ├── vectorstore.py   # FAISS index build/load/save
│   │   ├── pinecone_store.py# Pinecone index operations
│   │   ├── database.py      # SQLite schema and queries
│   │   ├── security.py      # JWT create/verify, password hashing
│   │   └── schemas.py       # Pydantic request/response models
│   ├── documents/           # Place your PDF/TXT files here
│   ├── vectorstore/         # FAISS index files (auto-generated)
│   ├── tests/               # pytest test suite
│   ├── Dockerfile           # Docker image for deployment
│   ├── requirements.txt     # Python dependencies (pinned)
│   ├── .env.example         # Environment variable template
│   └── history.db           # SQLite database (auto-created)
│
└── frontend/
    ├── src/
    │   ├── App.tsx           # Root component (auth → chat routing)
    │   ├── components/
    │   │   ├── AuthForm.tsx  # Login / register form
    │   │   ├── ChatHeader.tsx# Header with logout and upload button
    │   │   ├── ChatWindow.tsx# Message list with auto-scroll
    │   │   ├── ChatInput.tsx # Message input bar
    │   │   ├── MessageBubble.tsx # Individual message (markdown)
    │   │   └── UploadPanel.tsx   # PDF upload UI
    │   ├── hooks/
    │   │   ├── useAuth.ts    # Auth state (login/register/logout)
    │   │   ├── useChat.ts    # Chat state and message sending
    │   │   └── useUpload.ts  # File upload state
    │   ├── api/              # Axios API client functions
    │   └── types/            # TypeScript type definitions
    ├── vercel.json           # Vercel SPA routing config
    └── package.json
```

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- [Google AI Studio API key](https://aistudio.google.com/app/apikey) (free)
- (Production only) [Pinecone](https://www.pinecone.io/) account

---

## Local Development Setup

### 1. Clone the repo

```bash
git clone https://github.com/Priyanka-2027/customer-support-chatbot.git
cd customer-support-chatbot
```

### 2. Backend setup

```bash
cd backend

# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.example .env       # Windows
# cp .env.example .env       # macOS/Linux
```

Edit `.env` and fill in the required values (see Environment Variables section below).

### 3. Ingest your documents

Place your PDF or TXT files in `backend/documents/`, then run:

```bash
python -m app.ingest
```

This builds the FAISS vector store in `backend/vectorstore/`. You must do this before the chat endpoint will work.

### 4. Start the backend

```bash
uvicorn app.main:app --reload --port 8000
```

API is now at `http://localhost:8000`. Swagger UI at `http://localhost:8000/docs`.

### 5. Frontend setup

```bash
cd ../frontend
npm install
```

Create a `.env` file:
```
VITE_API_URL=http://localhost:8000
```

Start the dev server:
```bash
npm run dev
```

Frontend is now at `http://localhost:5173`.

---

## Environment Variables

All backend settings live in `backend/.env`. Copy from `.env.example` to get started.

| Variable | Required | Default | Description |
|---|---|---|---|
| `GOOGLE_API_KEY` | Yes | — | Gemini API key from Google AI Studio |
| `JWT_SECRET_KEY` | Yes | — | Secret for signing JWTs. Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `ENVIRONMENT` | No | `development` | `development` (FAISS) or `production` (Pinecone) |
| `GEMINI_MODEL` | No | `gemini-1.5-flash` | Gemini model name |
| `PINECONE_API_KEY` | Production | — | Pinecone API key |
| `PINECONE_INDEX_NAME` | Production | `support-chatbot` | Pinecone index name |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `15` | Access token lifetime in minutes |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | Refresh token lifetime in days |
| `CHUNK_SIZE` | No | `1000` | Document chunk size in characters |
| `CHUNK_OVERLAP` | No | `200` | Overlap between consecutive chunks |
| `RETRIEVER_K` | No | `4` | Number of chunks retrieved per query |
| `CHAT_HISTORY_WINDOW` | No | `10` | Number of prior message pairs included in LLM context |
| `FRONTEND_URL` | Production | — | Frontend URL for CORS allowlist |

---

## API Reference

All routes are prefixed with `/api/v1`.

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/auth/register` | Create a new account. Returns user info + sets HttpOnly cookies |
| `POST` | `/auth/login` | Login with email/password. Returns user info + sets HttpOnly cookies |
| `POST` | `/auth/refresh` | Exchange refresh token cookie for new access token |
| `POST` | `/auth/logout` | Clear auth cookies |
| `GET` | `/auth/me` | Get current user profile (requires auth) |

### Chat

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/chat` | Send a message, get a RAG-powered reply with sources |
| `GET` | `/chat/history` | Get conversation history |

**Chat request body:**
```json
{
  "question": "What is your return policy?",
  "conversation_id": "optional-existing-id"
}
```

**Chat response:**
```json
{
  "answer": "According to the return policy document...",
  "sources": [
    {
      "filename": "return-policy.pdf",
      "page": 2,
      "chunk_text": "Items can be returned within 30 days...",
      "chunk_index": 450
    }
  ],
  "conversation_id": "uuid-of-conversation"
}
```

### Documents

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/upload` | Upload a single PDF to the knowledge base |
| `POST` | `/upload/batch` | Upload up to 10 PDFs at once |

### System

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Returns server status and vector store state |
| `GET` | `/` | API info and links to docs |

---

## Authentication Flow

The app uses **JWT with HttpOnly cookies** for security:

1. **Register/Login** → server issues an access token (15 min) and refresh token (7 days) as HttpOnly cookies
2. **Every request** → access token is automatically sent via cookie
3. **Token expiry** → frontend silently calls `/auth/refresh` to get a new access token
4. **Logout** → server deletes both cookies

HttpOnly cookies prevent JavaScript from reading the tokens, protecting against XSS attacks.

---

## RAG Pipeline

```
User question
    │
    ▼
Embed with sentence-transformers (all-MiniLM-L6-v2)
    │
    ▼
Semantic search in FAISS / Pinecone (top-K chunks)
    │
    ▼
Build prompt:
  - System instructions (anti-hallucination rules)
  - Chat history (last N message pairs)
  - Retrieved context chunks
  - User question
    │
    ▼
Google Gemini generates answer grounded in context
    │
    ▼
Return answer + source citations
```

Key anti-hallucination rule in the prompt:
> "If the answer is not found in the context, respond with: I don't have information about that in the provided documents."

---

## Running Tests

**Backend:**
```bash
cd backend
pytest
```

**Frontend:**
```bash
cd frontend
npm test
```

---

## Deployment

### Backend → Google Cloud Run (free tier)

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and open Cloud Shell
2. Clone your repo and navigate to `backend/`
3. Deploy:

```bash
gcloud run deploy customer-support-chatbot \
  --source . \
  --port 7860 \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_API_KEY="...",JWT_SECRET_KEY="...",PINECONE_API_KEY="...",PINECONE_INDEX_NAME="support-chatbot",ENVIRONMENT="production",FRONTEND_URL="https://your-vercel-url.vercel.app"
```

4. After deploy, run ingestion once to populate Pinecone:
```bash
gcloud run jobs create ingest-job --image gcr.io/PROJECT/customer-support-chatbot --command "python" --args "-m,app.ingest"
```

### Frontend → Vercel

1. Go to [vercel.com](https://vercel.com) → **Add New Project** → import your GitHub repo
2. Set **Root Directory** to `frontend`
3. Set **Build Command** to `npm run build` and **Output Directory** to `dist`
4. Add environment variable: `VITE_API_URL=https://your-cloud-run-url`
5. Deploy

After both are deployed, update `FRONTEND_URL` on Cloud Run with the Vercel URL for CORS.

---

## Known Limitations

- FAISS vector store is in-memory / file-based — not suitable for multi-instance deployments (use Pinecone in production)
- SQLite history database is a single file — not suitable for multi-instance deployments (replace with Postgres for scale)
- Free tier deployments may have cold start latency (~10-30 seconds after inactivity)
- PDF ingestion requires selectable text — scanned image PDFs are not supported
