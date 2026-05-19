# Shristy — AI Companion with Live2D Avatar

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-8-646CFF.svg)](https://vitejs.dev/)
[![Groq](https://img.shields.io/badge/Powered%20By-Groq-F55036.svg)](https://groq.com/)

An expressive AI companion chatbot featuring an interactive **Live2D anime avatar** (`Hiyori`), real-time **audio-reactive lip-sync**, **BM25 semantic memory engine**, and low-latency inference powered by **Groq** and **Edge-TTS**.

---

## Features

- **Interactive Live2D Avatar**: Fully animated anime companion powered by PixiJS and Live2D Cubism SDK with natural idle animations and physics.
- **Real-time Audio-Reactive Lip-Sync**: Uses Web Audio API frequency analysis to drive avatar mouth movements during speech playback.
- **Dual Response Architecture**:
  - **Synchronized Chat (`/api/chat`)**: Completes Groq LLM inference and generates Edge-TTS speech in a unified payload for synced avatar animation.
  - **Live Token Streaming (`/api/chat/stream`)**: Server-Sent Events (SSE) token-by-token streaming from Groq for real-time text output.
- **Continuous BM25 Memory Engine**:
  - **Semantic Ranking**: Replaces basic keyword matching with Okapi BM25 scoring and contextual synonym expansion (e.g. matching "exhausted" with "burned out").
  - **Structured LLM Extraction**: Background task extracts lasting facts and preferences as structured JSON schemas with confidence filtering ($\ge 0.70$) while filtering out transient daily states.
  - **User-Controlled Memory Management**: Supports querying, adding, and deleting individual memories by ID (`DELETE /api/memory/{id}`).
- **Security & Hardening**:
  - **Server-Side Credential Priority**: Server-configured `GROQ_API_KEY` takes precedence over client inputs. Client keys can be completely disabled in production (`ALLOW_CLIENT_API_KEY=false`).
  - **Protected Memory Endpoints**: Administrative routes (`/api/memory`, `/api/memory/clear`) support authorization via `ADMIN_SECRET_KEY` (`Bearer` token or `X-Admin-Key`).
  - **Strict CORS Control**: Restricts allowed frontend origins via `ALLOWED_ORIGINS` instead of open wildcards.
- **Full Voice Pipeline**:
  - **Speech-to-Text**: Fast voice transcription via Groq Whisper (`whisper-large-v3-turbo`).
  - **Text-to-Speech**: High-fidelity natural voice synthesis via Edge-TTS with multi-voice selection.
- **Multi-Persona Modes & Responsible Safety**:
  - **Companion**: Warm, witty, casual friend who keeps chats grounded and brief (1-3 sentences) without unsolicited preaching.
  - **Emotional Support**: Compassionate, active-listening support clearly framed as a peer companion (not a medical/psychiatric substitute), equipped with international crisis guidance (US/Canada 988, UK 111, India 9152987821 / 1800-599-0019, International findahelpline.com).
  - **Mentor**: Direct, technical coding and machine learning assistance.

---

## Architecture

```
chatbot/
├── backend/                  # FastAPI Application
│   ├── main.py               # API endpoints, SSE streaming, Groq & Whisper STT
│   ├── memory_manager.py     # BM25 semantic ranker, structured schema & CRUD
│   ├── tts_manager.py        # Edge-TTS speech generation & cache management
│   ├── requirements.txt      # Python dependencies
│   ├── .env.example          # Environment variables template
│   └── static/audio/         # Generated speech audio cache
│
├── frontend/                 # React + Vite Application
│   ├── src/
│   │   ├── components/       # Live2D Avatar renderer & UI controls
│   │   ├── hooks/            # useAudioAnalyser for real-time lip-sync
│   │   ├── App.jsx           # Main chat interface and state management
│   │   └── main.jsx          # React DOM root
│   ├── public/
│   │   ├── model/hiyori/     # Live2D Cubism model assets & motions
│   │   └── live2dcubismcore  # Cubism Core runtime
│   ├── package.json
│   └── vite.config.js
```

---

## Getting Started

### Prerequisites

- **Python**: 3.10 or higher
- **Node.js**: 18.x or higher (npm / pnpm / yarn)
- **Groq API Key**: Obtain a free API key from [Groq Console](https://console.groq.com/)

---

### 1. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env and set GROQ_API_KEY and optional ADMIN_SECRET_KEY

# Start FastAPI server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The backend server runs at `http://localhost:8000`. You can inspect the interactive OpenAPI documentation at `http://localhost:8000/docs`.

---

### 2. Frontend Setup

```bash
# Open a new terminal and navigate to frontend
cd frontend

# Install dependencies
npm install

# Configure environment variables (optional, defaults to port 8000)
cp .env.example .env

# Start development server
npm run dev
```

Open `http://localhost:5173` in your browser.

---

## Environment Variables

### Backend (`backend/.env`)
| Variable | Description | Default |
| :--- | :--- | :--- |
| `GROQ_API_KEY` | Server-side Groq Cloud API key | *Required* |
| `ADMIN_SECRET_KEY` | Secret token to authenticate memory management endpoints | *None (open in dev)* |
| `ALLOW_CLIENT_API_KEY`| Allow clients to provide temporary API keys in requests | `true` (`false` in prod) |
| `ALLOWED_ORIGINS` | Comma-separated list of allowed CORS origins | `http://localhost:5173,http://localhost:3000` |
| `GROQ_MODEL` | Default model identifier | `llama-3.3-70b-versatile` |

### Frontend (`frontend/.env`)
| Variable | Description | Default |
| :--- | :--- | :--- |
| `VITE_API_URL` | Base URL of the FastAPI backend | `http://localhost:8000` |

---

## API Endpoints

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/chat` | Chat with synchronized TTS audio for avatar lip-sync | No |
| `POST` | `/api/chat/stream` | Server-Sent Events (SSE) token-by-token streaming | No |
| `POST` | `/api/transcribe` | Audio speech-to-text via Groq Whisper | No |
| `GET` | `/api/voices` | List available Edge-TTS voices | No |
| `GET` | `/api/memory` | Retrieve structured long-term memories | Optional (`ADMIN_SECRET_KEY`) |
| `POST` | `/api/memory` | Add an individual memory item | Optional (`ADMIN_SECRET_KEY`) |
| `DELETE`| `/api/memory/{id}` | Delete an individual memory by ID | Optional (`ADMIN_SECRET_KEY`) |
| `POST` | `/api/memory/clear` | Clear all long-term memories | Optional (`ADMIN_SECRET_KEY`) |
