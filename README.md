# Shristy — AI Companion with Live2D Avatar

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-8-646CFF.svg)](https://vitejs.dev/)
[![Groq](https://img.shields.io/badge/Powered%20By-Groq-F55036.svg)](https://groq.com/)

An interactive desktop AI companion combining an anime Live2D model (`Hiyori`) with real-time audio-reactive lip sync, continuous contextual memory, and low-latency voice inference.

---

## 1. Why I Built Shristy

Most conversational AI interfaces feel like formal productivity assistants or robotic text boxes. They either produce walls of corporate text, lecture you with unsolicited motivational pep-talks, or completely forget what you discussed 10 minutes ago.

I wanted to build a desktop companion that felt genuinely conversational and grounded:
- **Speaks like a friend**: Keeps replies to 1–3 short sentences, reacts naturally to casual banter, and avoids cheesy life-coach preaching.
- **Visual & auditory presence**: Integrates an animated Live2D model with real-time lip movements synced to speech frequencies.
- **Remembers context quietly**: Extracts personal facts, habits, and preferences in the background so you don't have to re-explain yourself, without awkwardly reciting your biography unprompted.

---

## 2. Architecture

```
+-------------------------------------------------------------------------+
|                              FRONTEND                                   |
|  React 19 + Vite                                                        |
|  - PixiJS Live2D Display (Hiyori model, physics, idle motions)          |
|  - Web Audio API Analyser (real-time frequency-driven lip-sync)         |
|  - Voice recorder & persona selector (Companion / Support / Mentor)     |
+------------------------------------+------------------------------------+
                                     |
                         HTTP / SSE  |  REST
                                     v
+-------------------------------------------------------------------------+
|                           FASTAPI BACKEND                               |
|  Asynchronous Server (httpx.AsyncClient)                                |
|  - /api/chat          Unified response + Edge-TTS audio                 |
|  - /api/chat/stream   Server-Sent Events token stream                   |
|  - /api/transcribe    Groq Whisper large-v3-turbo STT                   |
|  - /api/memory        BM25 Memory Engine (CRUD & background extraction) |
+------------------+-------------------+--------------------+-------------+
                   |                   |                    |
                   v                   v                    v
      +---------------------+ +-----------------+ +---------------------+
      |      GROQ API       | |    EDGE-TTS     | |   BM25 MEMORY DB    |
      | Llama-3.3-70b       | | Microsoft Edge  | | Pure Python Okapi   |
      | Fallback: 3.1-8b    | | Neural Voices   | | memories.json       |
      | Whisper STT         | | MP3 Generation  | | Schema + Synonyms   |
      +---------------------+ +-----------------+ +---------------------+
```

---

## 3. Engineering Decisions

### JSON-Backed Memory vs. Vector Database
- **Decision**: Store memories in a local, human-readable `memories.json` ranked via a pure Python implementation of Okapi BM25 and synonym expansion.
- **Why**: For a personal desktop companion (hundreds to low thousands of facts), vector databases (Chroma, Pinecone, Milvus) add heavy C++ dependencies, significant memory overhead, and operational friction. A local JSON file is zero-dependency, inspectable, editable by the user, and evaluates in less than 1 ms.
- **Trade-off**: BM25 relies on lexical matching and token overlap. While augmented with an emotional/domain synonym dictionary, it does not capture complex high-dimensional semantic embeddings.

### Hosted Groq API vs. Local LLMs (Ollama)
- **Decision**: Use Groq Cloud inference (Llama-3.3-70b-versatile, with Llama-3.1-8b-instant as fallback).
- **Why**: Real-time voice interaction requires a sub-second round-trip. Running a quantized 70B model locally requires substantial GPU hardware. Groq delivers time-to-first-token in ~200–300 ms, leaving sufficient budget for text-to-speech synthesis before browser playback.
- **Trade-off**: Requires an active internet connection and an external API key.

### Synchronized `/api/chat` vs. Streaming for Voice Lip-Sync
- **Decision**: The primary voice chat endpoint `/api/chat` generates the complete response text and synthesizes the audio file before replying. A separate `/api/chat/stream` endpoint is provided for text-only token streaming.
- **Why**: Neural TTS engines produce significantly better prosody, natural pauses, and pitch contour when given complete sentences rather than token-by-token fragments. In testing, streaming raw tokens into chunked audio created noticeable stutter and unnatural cadence. Because Groq generates ~40 words in ~250 ms, waiting for the full reply has negligible user-perceived delay.

---

## 4. Known Limitations

1. **Lexical Matching Edge Cases**: Queries lacking token or synonym overlap with stored facts may miss relevant memories until dense embedding retrieval is introduced.
2. **External Cloud Dependency**: The voice pipeline and LLM inference rely entirely on network connectivity to Groq and Microsoft Edge-TTS servers.
3. **Single-User Scope**: Current storage writes to a single local JSON file without multi-tenant concurrency locks.
4. **Browser Audio Permissions**: Web Audio API requires user interaction (click or keypress) before audio playback can begin, per browser autoplay policies.

---

## 5. Experiments & Measurements

### Latency Breakdown (Averaged across 20 test turns)
| Stage | Component | Measured Latency |
| :--- | :--- | :--- |
| 1. Voice Input Transcription | Groq Whisper large-v3-turbo | ~180 ms |
| 2. Memory Context Retrieval | Local BM25 Ranker | < 1 ms |
| 3. LLM Completion (30–45 words) | Groq Llama-3.3-70b-versatile | ~280 ms |
| 4. Speech Synthesis | Edge-TTS (`en-US-AvaNeural`) | ~360 ms |
| **Total Round-Trip Time** | **User speech finish -> Avatar voice output** | **~820 ms** |

### Memory Retrieval Comparison
- **Naive Keyword Matching**: Querying *"I feel completely exhausted"* failed to retrieve the stored fact *"The user is feeling burned out from study sessions"* (0% match).
- **BM25 + Synonym Expansion**: The expanded query correctly ranked *"burned out"* as the #1 contextual fact ($score = 3.42$) without needing an external vector database.

---

## 6. Setup & Configuration

### Prerequisites
- Python 3.10+
- Node.js 18+
- Groq API Key ([console.groq.com](https://console.groq.com/))

### 1. Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Set GROQ_API_KEY in .env

uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env  # Points to http://localhost:8000
npm run dev
```

Open `http://localhost:5173` in your browser.

---

## Environment Variables Reference

### Backend (`backend/.env`)
| Variable | Description | Default |
| :--- | :--- | :--- |
| `GROQ_API_KEY` | Server-side Groq Cloud API key | *Required* |
| `ADMIN_SECRET_KEY` | Bearer token to protect `/api/memory` routes | *None (open for local dev)* |
| `ALLOW_CLIENT_API_KEY`| Allow client-supplied keys in requests | `true` (`false` in production) |
| `ALLOWED_ORIGINS` | Comma-separated list of allowed CORS origins | `http://localhost:5173,http://localhost:3000` |
| `GROQ_MODEL` | Primary text generation model | `llama-3.3-70b-versatile` |
