# Shristy — AI Companion with Live2D Avatar

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-8-646CFF.svg)](https://vitejs.dev/)
[![Groq](https://img.shields.io/badge/Powered%20By-Groq-F55036.svg)](https://groq.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An intelligent, expressive AI companion chatbot featuring an interactive **Live2D anime avatar** (`Hiyori`), real-time **audio-reactive lip-sync**, **persistent contextual memory**, and ultra-low latency voice responses powered by **Groq** and **Edge-TTS**.

---

##  Features

- ** Interactive Live2D Avatar**: Fully animated anime companion powered by PixiJS and Live2D Cubism SDK with natural idle animations and physics.
- ** Real-time Audio-Reactive Lip-Sync**: Uses the Web Audio API to analyze output speech frequencies in real time, driving realistic avatar mouth movements.
- ** Ultra-Fast Streaming**: Powered by Groq LLMs (Llama 3, Qwen, Mixtral) for lightning-fast sub-second response times.
- ** Continuous Memory Architecture**:
  - Automatically extracts and indexes personal facts, preferences, and details from conversations in the background.
  - Contextual retrieval using TF-IDF similarity to recall relevant memories without awkward robotic recitations.
- ** Full Voice Pipeline**:
  - **Speech-to-Text**: Fast voice input via Groq Whisper (`whisper-large-v3-turbo`).
  - **Text-to-Speech**: High-fidelity natural voice synthesis via Edge-TTS with multi-voice selection.
- ** Multi-Persona Modes**:
  - **Companion**: Warm, witty, casual friend who keeps chats grounded and brief without cheesy motivational clichés.
  - **Psychiatrist**: Compassionate, active-listening support with built-in safety boundaries.
  - **Mentor**: Direct, technical coding and machine learning assistance.

---

##  Architecture

```
chatbot/
├── backend/                  # FastAPI Application
│   ├── main.py               # API endpoints, Groq integration, Whisper STT
│   ├── memory_manager.py     # Persistent memory storage & TF-IDF similarity search
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
│
└── AI_Companion_Roadmap.pdf  # Project architecture & product roadmap
```

---

##  Getting Started

### Prerequisites

- **Python**: 3.10 or higher
- **Node.js**: 18.x or higher (npm / pnpm / yarn)
- **Groq API Key**: Get a free API key from [Groq Console](https://console.groq.com/)

---

### 1. Backend Setup

```bash
# Navigate to the backend directory
cd backend

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Open .env and add your GROQ_API_KEY:
# GROQ_API_KEY=gsk_...

# Start the FastAPI server
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

## ⚙️ Environment Variables

### Backend (`backend/.env`)
| Variable | Description | Default |
| :--- | :--- | :--- |
| `GROQ_API_KEY` | Your Groq Cloud API key | *Required* |
| `GROQ_MODEL` | Default model identifier | `llama-3.3-70b-versatile` |

### Frontend (`frontend/.env`)
| Variable | Description | Default |
| :--- | :--- | :--- |
| `VITE_API_URL` | Base URL of the FastAPI backend | `http://localhost:8000` |

---


