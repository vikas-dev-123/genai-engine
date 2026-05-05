# GenAI Engine

**GenAI Engine** is a full-stack, production-ready AI assistant platform you can self-host. It pairs a **FastAPI** backend (Google **Gemini** + **LangChain** tool calling, **RAG**, memory, and optional voice) with a **React** web console styled as a dark HUD. Data remains under your control: **PostgreSQL** for accounts and chat history, **Redis** for caching and rate limits, and **FAISS** on disk for vector search.

---

## Table of contents

1. [What GenAI Engine does](#what-genai-engine-does)
2. [Key capabilities](#key-capabilities)
3. [Architecture](#architecture)
4. [Technology stack](#technology-stack)
5. [Repository layout](#repository-layout)
6. [Prerequisites](#prerequisites)
7. [Getting started (Docker — recommended)](#getting-started-docker--recommended)
8. [Getting started (local, without Docker)](#getting-started-local-without-docker)
9. [Using the application](#using-the-application)
10. [HTTP API reference](#http-api-reference)
11. [Streaming protocol (SSE)](#streaming-protocol-sse)
12. [Security and safety](#security-and-safety)
13. [Configuration](#configuration)
14. [Make targets](#make-targets)
15. [Troubleshooting](#troubleshooting)
16. [Extending GenAI Engine (adding a tool)](#extending-genai-engine-adding-a-tool)
17. [License](#license)

---

## What GenAI Engine does

GenAI Engine is designed to provide a flexible, self-hosted AI assistant platform with:

- **Multi-turn chat** with **server-sent events (SSE)** streaming so tokens appear as they are generated.
- **Retrieval-augmented generation (RAG)**: upload PDF, TXT, DOCX, or Markdown; chunks are embedded with **Gemini embeddings** and stored in a **per-user FAISS** index. Answers can cite document context.
- **Agent tools** the model can invoke: web search (DuckDuckGo), sandboxed file read/write, HTTP calls to an **allowlisted** domain set, and a **strictly allowlisted** set of shell commands.
- **Memory**: short-term context in **Redis** (with optional summarization when the buffer grows), plus **long-term** conversational snippets indexed in FAISS.
- **Optional voice**: **faster-whisper** (local) for speech-to-text; **ElevenLabs** for speech synthesis when an API key is present, with **pyttsx3** fallback.

The **web UI** supports authentication, conversation sidebar, document upload, RAG toggle, streaming markdown replies, tool-call cards, and a voice capture button.

---

## Key capabilities

| Area | Details |
|------|---------|
| **Auth** | Register/login; **JWT** access + refresh tokens; passwords hashed with **bcrypt** |
| **Chat** | Streaming replies; persisted **conversations** and **messages**; optional `tool_calls` on assistant messages |
| **RAG** | Ingest → chunk → embed → FAISS; keyword search-style **retrieve** API; MMR-style diversity in retrieval |
| **Tools** | `web_search`, `file_read` / `file_write` (per-user workspace), `api_call` (domain whitelist), `system_command` (command whitelist) |
| **Voice** | `POST /voice/transcribe`, `POST /voice/synthesize` |
| **Ops** | **Docker Compose** (Postgres, Redis, API, Nginx frontend); health check; structured logging; Redis rate limiting |

---

## Architecture

### High-level diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Client (Browser)                                │
│  React 18 · Vite · TypeScript · Tailwind · Zustand · SSE (EventSource/fetch) │
└─────────────────────────────────────────────────────────────────────────────┘
         │  HTTPS (dev: HTTP)
         │  REST JSON  ·  POST /api/v1/chat/stream (text/event-stream)
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Nginx (frontend container, :3000 → :80)                     │
│  · Serves SPA static assets                                                    │
│  · Proxies /api/ → backend (buffering OFF for SSE)                           │
└─────────────────────────────────────────────────────────────────────────────┘
         │  proxy /api/ …
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     FastAPI — GenAI Engine API (backend :8000)               │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  ┌─────────────────┐ │
│  │ Auth router │  │ Chat router  │  │ Voice router  │  │ RAG router      │ │
│  └──────┬──────┘  └──────┬───────┘  └───────┬───────┘  └────────┬────────┘ │
│         │                │                   │                    │           │
│         └────────────────┴─────────────────┴────────────────────┘           │
│                                    │                                          │
│  ┌─────────────────────────────────▼──────────────────────────────────────┐ │
│  │ LLMService — ChatGoogleGenerativeAI + LangChain AgentExecutor            │ │
│  │ · System prompt: user, time, RAG context, memories, rules              │ │
│  │ · Tools: search, files, api_call, system_command                        │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌─────────────────────┐ │
│  │ MemoryService         │  │ RAGService           │  │ VoiceService        │ │
│  │ · Redis short-term    │  │ · Ingest / retrieve  │  │ · Whisper / TTS     │ │
│  │ · FAISS long-term     │  │ · FAISS + metadata   │  │ · Redis TTS cache   │ │
│  └──────────────────────┘  └──────────────────────┘  └─────────────────────┘ │
│  Middleware: CORS · structured logging · Redis sliding-window rate limit        │
└─────────────────────────────────────────────────────────────────────────────┘
         │                              │                        │
         ▼                              ▼                        ▼
┌─────────────────┐          ┌─────────────────┐      ┌──────────────────────┐
│   PostgreSQL    │          │     Redis       │      │  FAISS + JSON meta   │
│ users, chats,   │          │ sessions, mem,  │      │  under FAISS_INDEX_  │
│ messages, docs  │          │ rate limit, TTS │      │  DIR (per user)      │
└─────────────────┘          └─────────────────┘      └──────────────────────┘
```

### Data flow (chat with RAG)

1. The client sends a **POST** to `/api/v1/chat/stream` with the user message and optional `conversation_id`.
2. The backend loads **short-term** and **long-term** memory, and if RAG is enabled, **retrieves** relevant chunks from the user’s document index.
3. **Gemini** runs inside an **agent** loop; tool calls and text stream out as **SSE** frames.
4. On completion, the backend **persists** user and assistant rows, updates **Redis** memory and **FAISS** long-term memory, and refreshes conversation metadata.

### External services

| Service | Role |
|---------|------|
| **Google Gemini** | Chat completions and text embeddings (API key required) |
| **DuckDuckGo** | Web search from the `web_search` tool (no API key) |
| **ElevenLabs** | Optional cloud TTS |
| **Internet** | Only where you allow it (`api_call` domains, `web_search`) |

---

## Technology stack

| Layer | Technologies |
|--------|--------------|
| **Backend** | Python 3.11, FastAPI, Uvicorn, SQLAlchemy 2 (async), asyncpg, Pydantic v2 |
| **AI** | `langchain`, `langchain-google-genai`, `langchain-core`, Google Generative AI SDK |
| **Vectors** | `faiss-cpu`, on-disk indexes; Gemini `text-embedding-004` |
| **Data** | PostgreSQL 16, Redis 7 |
| **Auth** | `python-jose[cryptography]`, `passlib[bcrypt]` |
| **Voice** | `faster-whisper`, `pydub`, `elevenlabs`, `pyttsx3` |
| **Frontend** | React 18, Vite 5, TypeScript (strict), Tailwind CSS, Zustand, Axios, react-markdown |
| **Containers** | Docker, Docker Compose; frontend image uses Nginx |

---

## Repository layout

```
genai-engine/
├── backend/                 # FastAPI application
│   ├── main.py              # App entry, lifespan, middleware, routers
│   ├── config.py            # Settings from .env
│   ├── dependencies.py      # DB session, Redis, current user
│   ├── models/              # SQLAlchemy models
│   ├── schemas/             # Pydantic request/response models
│   ├── routers/             # auth, chat, voice, rag
│   ├── services/            # auth, llm, memory, rag, voice
│   ├── tools/               # LangChain tools
│   ├── db/                  # engine, session, Base
│   ├── middleware/         # logging, rate limiting
│   └── utils/               # chunking, embeddings, SSE helpers
├── frontend/                # React SPA
│   └── src/                 # components, api, hooks, stores, styles
├── docker-compose.yml
├── .env.example
├── Makefile
└── README.md
```

---

## Prerequisites

- **Docker Desktop** (or Docker Engine + Compose v2) for the recommended path.
- A **Google AI Studio** API key for Gemini: [https://aistudio.google.com](https://aistudio.google.com)

Optional:

- **ElevenLabs** API key for higher-quality TTS (otherwise pyttsx3 WAV fallback is used when synthesizing).

---

## Getting started (Docker — recommended)

1. **Clone** the repository and enter the project root.

2. **Create environment file:**

   ```bash
   cp .env.example .env
   ```

3. **Edit `.env`** and set at minimum:

   - `GEMINI_API_KEY` — your Gemini key  
   - `JWT_SECRET_KEY` — long random secret (e.g. `openssl rand -hex 32` on Unix, or `make key` from the Makefile)

   Compose **overrides** `DATABASE_URL` and `REDIS_URL` for the backend container to point at the `postgres` and `redis` services. Other variables (Gemini, JWT, etc.) are read from `.env`.

4. **Start the stack:**

   ```bash
   make dev
   ```
   or: `docker compose up --build`

5. **Open the app:**

   | URL | Purpose |
   |-----|---------|
   | [http://localhost:3000](http://localhost:3000) | Web UI (Nginx → API) |
   | [http://localhost:8000/docs](http://localhost:8000/docs) | OpenAPI (Swagger) |
   | [http://localhost:8000/health](http://localhost:8000/health) | Health probe |

6. **First run:** register an account in the UI, then start chatting. Upload documents under **Knowledge Base** when you want RAG.

---

## Getting started (local, without Docker)

1. Install **PostgreSQL 16** and **Redis 7**. Create database `genai_engine` and user matching `.env.example` (or adjust `DATABASE_URL`).

2. **Backend:**

   ```bash
   cd backend
   python -m venv .venv
   .venv\Scripts\activate          # Windows
   # source .venv/bin/activate     # macOS/Linux
   pip install -r requirements.txt
   ```

   From `backend/`, with `.env` populated:

   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

3. **Frontend:**

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

   Vite serves on **port 3000** and proxies `/api` to `http://localhost:8000`.

### Windows note (native `pip install`)

Some dependencies may ship **source distributions** that require **Visual Studio Build Tools** (C++ workload) or **Rust** toolchain. If `pip install` fails building wheels (e.g. `av`, `pyreqwest-impersonate`), prefer **Docker** or **WSL2** for the backend, or install [Build Tools for Visual Studio](https://visualstudio.microsoft.com/visual-cpp-build-tools/).

**Dependency note:** `langchain-google-genai` expects `google-generativeai` in the **0.5.x** range; the pinned requirements follow that constraint.

---

## Using the application

### Web UI

1. **Sign in / Create account** — JWT access token is kept in memory; refresh token in `sessionStorage`.
2. **New Chat** — starts a thread; title updates from your first message.
3. **Sidebar** — switch conversations, delete threads, toggle **RAG**, upload/list documents.
4. **Composer** — type a message; **Enter** sends, **Shift+Enter** newline; **voice** button records via the microphone (browser permission required).
5. **Streaming** — assistant text streams in; **tool** cards show when the agent calls a tool.

### Developer API usage

- Obtain tokens via `POST /api/v1/auth/login` or `register`.
- Send `Authorization: Bearer <access_token>` on protected routes.
- For streaming, use a client that reads **SSE** lines starting with `data: ` (see below).

---

## HTTP API reference

Base path for versioned routes: **`/api/v1`**.  
**`GET /health`** is not under `/api/v1`.

### Auth (`/api/v1/auth`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/register` | Create account; returns tokens + user |
| POST | `/login` | JSON body: `email`, `password` |
| POST | `/refresh` | Body: `refresh_token` → new `access_token` |
| GET | `/me` | Current user (Bearer required) |

**Register example:**

```json
POST /api/v1/auth/register
Content-Type: application/json

{
  "email": "ada@example.com",
  "password": "minimum8chars",
  "name": "Ada Lovelace"
}
```

**Response (abbreviated):**

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "email": "ada@example.com",
    "name": "Ada Lovelace",
    "timezone": "UTC",
    "created_at": "2026-05-05T12:00:00Z"
  }
}
```

### Chat (`/api/v1/chat`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/stream` | SSE stream for assistant reply (Bearer, JSON body) |
| GET | `/conversations` | List conversations with message counts |
| GET | `/history/{conversation_id}` | Ordered messages |
| DELETE | `/conversation/{conversation_id}` | Delete thread and messages |

**Stream request body:**

```json
{
  "message": "What did I upload about the project timeline?",
  "conversation_id": null,
  "rag_enabled": true,
  "voice_mode": false
}
```

`conversation_id` may be omitted or `null` to start a **new** conversation.

### Voice (`/api/v1/voice`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/transcribe` | `multipart/form-data` field **`file`** (audio) |
| POST | `/synthesize` | JSON `{"text": "..."}` (max 2000 chars); returns audio bytes |

### RAG (`/api/v1/rag`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/upload` | Multipart **`file`** — PDF, TXT, DOCX, MD; max **50 MB** |
| GET | `/documents` | List user documents |
| DELETE | `/document/{doc_id}` | Remove document and vectors |
| GET | `/search?q=...` | Semantic search over ingested chunks |

### Health

**`GET /health`**

Example response shape:

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "model": "gemini-1.5-flash",
  "db": "connected",
  "redis": "connected"
}
```

`status` may reflect **degraded** if a dependency check fails.

---

## Streaming protocol (SSE)

The stream returns **`text/event-stream`**. Each event is a line:

```text
data: <JSON>\n\n
```

JSON envelope:

```json
{
  "type": "token | tool_call | tool_result | done | error",
  "data": "string or object"
}
```

| `type` | `data` meaning |
|--------|----------------|
| `token` | Partial assistant text (string) |
| `tool_call` | `{ "name": "...", "input": { ... } }` |
| `tool_result` | `{ "name": "...", "output": "..." }` (truncated in stream) |
| `done` | `{ "conversation_id": "...", "message_id": "..." }` |
| `error` | Error message string |

Clients should keep the connection open until `done` or `error`.

---

## Security and safety

- **Secrets** must live in `.env` or a secret manager — do not commit real keys.
- **JWT** access tokens are short-lived; refresh tokens should be stored with care.
- **Rate limiting** uses Redis (per user id from JWT when present, else IP).
- **File tools** are scoped to **`WORKSPACE_DIR/<user_id>`** with path sanitization.
- **`api_call`** only allows hostnames listed in **`ALLOWED_API_DOMAINS`**.
- **`system_command`** only allows a fixed whitelist (`ls`, `pwd`, `echo`, `date`, `whoami`, `df`, `du`).
- **CORS** is configurable via **`CORS_ORIGINS`**.

For production, also: TLS termination, strong Postgres/Redis passwords, secret rotation, and network policies appropriate for your environment.

---

## Configuration

All major settings are documented in **`.env.example`**. Summary:

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Required — Gemini API access |
| `GEMINI_MODEL` | Default `gemini-1.5-flash` |
| `EMBEDDING_MODEL` | Default `models/text-embedding-004` |
| `DATABASE_URL` | Async SQLAlchemy URL — use `postgresql+asyncpg://...` |
| `REDIS_URL` | Redis connection URL |
| `JWT_SECRET_KEY` | Required — signing key for JWTs |
| `JWT_ALGORITHM` | Default `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` / `REFRESH_TOKEN_EXPIRE_DAYS` | Token lifetimes |
| `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` | Optional TTS |
| `WHISPER_MODEL` | faster-whisper model id (e.g. `base.en`) |
| `FAISS_INDEX_DIR` | Vector index root |
| `WORKSPACE_DIR` | Per-user file tool sandbox root |
| `ALLOWED_API_DOMAINS` | Comma-separated hostnames for `api_call` |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` / `MAX_RAG_RESULTS` | RAG tuning |
| `CORS_ORIGINS` | Comma-separated allowed browser origins |
| `RATE_LIMIT_REQUESTS` / `RATE_LIMIT_WINDOW_SECONDS` | Throttling |
| `ENVIRONMENT` | e.g. `development` vs `production` (logging style) |
| `LOG_LEVEL` | e.g. `INFO` |

---

## Make targets

| Target | Command | Description |
|--------|---------|-------------|
| `make dev` | `docker compose up --build` | Run full stack |
| `make build` | `docker compose build` | Build images |
| `make down` | `docker compose down` | Stop stack |
| `make logs` | `docker compose logs -f backend` | Tail backend logs |
| `make test` | `pytest` in `backend/tests` | Run tests |
| `make shell-backend` | Exec shell in backend container | Debug |
| `make shell-db` | `psql` into Postgres | Debug |
| `make clean` | Down + volumes | **Destructive** — wipes DB/redis volumes |
| `make key` | Print random 32-byte hex | Suggested `JWT_SECRET_KEY` |
| `make format` | `black` + `isort` | Format backend |

---

## Troubleshooting

| Issue | Suggestion |
|-------|------------|
| UI loads but API errors | Check backend logs; verify `GEMINI_API_KEY` and DB/Redis from `/health`. |
| SSE stalls behind proxy | Ensure **proxy_buffering off** (Nginx config in `frontend/nginx.conf` does this for `/api/`). |
| Database connection refused in Docker | Wait for Postgres healthcheck; confirm Compose `DATABASE_URL` override for `backend`. |
| Windows `pip install` fails | Use Docker, or install MSVC Build Tools / use WSL2 (see [Getting started local](#getting-started-local-without-docker)). |
| RAG returns empty | Ensure documents show `ready`; embeddings need valid Gemini key; check `FAISS_INDEX_DIR` permissions and mounts. |

---

## Extending GenAI Engine (adding a tool)

1. Add a new **`BaseTool`** under `backend/tools/` with a clear **description** and **Pydantic `args_schema`** (so the model knows exact inputs).
2. Register the tool in **`LLMService._get_tools`** in `backend/services/llm_service.py` (respect per-user tools where needed).
3. **Sandbox** any filesystem or network access (reuse patterns from `file_ops.py` / `api_caller.py`).
4. **Update** this README if the tool is user-visible or needs new **environment variables**.
5. Rebuild/redeploy the backend; the UI **ToolCallCard** maps common tool names to icons — extend `frontend/src/components/ToolCallCard.tsx` if you want a dedicated icon/label.

---

## License

MIT

---

*GenAI Engine — local-first assistant with Gemini, RAG, and optional voice.*
