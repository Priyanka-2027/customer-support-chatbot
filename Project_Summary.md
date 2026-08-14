# Customer Support Chatbot — Project Summary

## Overview

An AI-powered customer support chatbot built using Retrieval-Augmented Generation (RAG). The system answers user questions by retrieving relevant passages from uploaded PDF documents and generating grounded, accurate responses using Google Gemini — eliminating hallucinations by grounding every answer in real documentation.

**Live Demo:** https://customer-support-chatbot-using-rag.vercel.app  
**Backend API:** https://customer-support-chatbot-b1s0.onrender.com/docs

---

## Problem Statement

Traditional customer support chatbots either hallucinate answers or require expensive manual scripting of every possible question. This project solves that by letting businesses upload their own documentation and instantly get an AI assistant that answers questions accurately from those documents.

---

## Architecture

```
React Frontend (Vercel)
       ↓ REST API
FastAPI Backend (Render)
       ↓
RAG Pipeline:
  User Question → Embed → Pinecone Search → Top-K Chunks → Gemini LLM → Answer + Sources
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 19, Vite, TypeScript, Tailwind CSS |
| Backend | FastAPI (Python), Uvicorn |
| LLM | Google Gemini (gemini-1.5-flash) |
| Embeddings | Google Gemini Embedding API |
| Vector Store | Pinecone (production), FAISS (development) |
| RAG Framework | LangChain |
| Authentication | JWT (HttpOnly cookies, access + refresh tokens) |
| Database | SQLite via aiosqlite (chat history) |
| Deployment | Render (backend), Vercel (frontend) |

---

## Key Features

- **Secure Authentication** — JWT-based login/register with HttpOnly cookies to prevent XSS attacks
- **RAG Pipeline** — Embeds user questions, retrieves top-4 relevant chunks from Pinecone, feeds them to Gemini
- **Source Citations** — Every answer includes the source document, page number, and relevant text chunk
- **Multi-turn Conversations** — Full conversation history preserved per user session in SQLite
- **Document Upload** — Admins can upload PDFs at runtime to expand the knowledge base without restarting
- **Anti-hallucination** — If the answer isn't in the documents, the bot explicitly says so

---

## RAG Pipeline Flow

1. User submits a question
2. Question is embedded using Google Gemini Embedding API (768 dimensions)
3. Pinecone semantic search retrieves the 4 most relevant document chunks
4. Gemini generates an answer grounded only in those chunks
5. Answer + source citations returned to the frontend

---

## Deployment

- **Backend** deployed on Render (free tier, Python 3.11, Docker)
- **Frontend** deployed on Vercel (free tier, Vite/React SPA)
- **Vector Store** hosted on Pinecone (free tier, cloud-managed)
- CORS configured to allow only the Vercel frontend domain
- Environment variables managed via Render dashboard (API keys, JWT secret, Pinecone credentials)

---

## Project Structure

```
customer-support-chatbot/
├── backend/
│   ├── app/
│   │   ├── main.py       # FastAPI app, CORS, startup
│   │   ├── auth.py       # JWT authentication endpoints
│   │   ├── chat.py       # Chat, upload, health endpoints
│   │   ├── chain.py      # RAG pipeline (LangChain + Gemini)
│   │   ├── embeddings.py # Google embedding model wrapper
│   │   ├── retriever.py  # Pinecone / FAISS retriever
│   │   └── database.py   # SQLite chat history
│   └── documents/        # PDF knowledge base files
└── frontend/
    └── src/
        ├── components/   # React UI components
        ├── hooks/        # useAuth, useChat, useUpload
        └── api/          # Axios API client
```

---

*Built by Priyanka Jakkampudi — August 2026*
