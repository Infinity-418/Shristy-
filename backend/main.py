import json
import os
import requests
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Header, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from memory_manager import MemoryManager
from tts_manager import TTSManager

# Load environment variables
load_dotenv()

app = FastAPI(
    title="Shristy — AI Companion Chatbot Backend",
    description="High-performance backend featuring Groq LLM inference, continuous memory engine, and Edge-TTS synthesis.",
    version="1.1.0"
)

# -----------------------------------------------------------------------------
# Security & Configuration
# -----------------------------------------------------------------------------
ADMIN_SECRET_KEY = os.environ.get("ADMIN_SECRET_KEY", "")
SERVER_GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
# In public deployments, set ALLOW_CLIENT_API_KEY=false to prevent arbitrary client key usage
ALLOW_CLIENT_API_KEY = os.environ.get("ALLOW_CLIENT_API_KEY", "true").lower() in ("true", "1", "yes")

def resolve_groq_api_key(client_key: Optional[str] = None) -> str:
    """
    Resolve API key prioritizing trusted server-side environment variables.
    Client-supplied keys are only used if server key is absent or client keys are explicitly enabled.
    """
    if SERVER_GROQ_API_KEY:
        return SERVER_GROQ_API_KEY
    if ALLOW_CLIENT_API_KEY and client_key and client_key.strip():
        return client_key.strip()
    raise HTTPException(
        status_code=401,
        detail="Server GROQ_API_KEY is not configured and client-supplied keys are disabled."
    )

async def verify_admin_access(
    authorization: Optional[str] = Header(None),
    x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key")
):
    """
    Protect sensitive administrative routes (e.g. reading/modifying/clearing memories).
    If ADMIN_SECRET_KEY is configured in .env, strict credential verification is enforced.
    """
    if ADMIN_SECRET_KEY:
        token = None
        if authorization and authorization.startswith("Bearer "):
            token = authorization.split("Bearer ")[1].strip()
        elif x_admin_key:
            token = x_admin_key.strip()
        
        if not token or token != ADMIN_SECRET_KEY:
            raise HTTPException(
                status_code=401,
                detail="Unauthorized: Valid administrative credentials required."
            )
    return True

# -----------------------------------------------------------------------------
# CORS Middleware
# -----------------------------------------------------------------------------
allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "")
if allowed_origins_env.strip():
    origins = [origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()]
else:
    # Standard local development origins
    origins = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# State & Static Storage
# -----------------------------------------------------------------------------
memory_db = MemoryManager(filepath="memories.json")
tts_db = TTSManager(output_dir="static/audio")

os.makedirs("static/audio", exist_ok=True)

@app.get("/static/audio/{filename}")
async def get_audio_file(filename: str):
    file_path = os.path.join("static/audio", filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(
        file_path, 
        media_type="audio/mpeg",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Accept-Ranges": "bytes"
        }
    )

app.mount("/static", StaticFiles(directory="static"), name="static")

# -----------------------------------------------------------------------------
# System Prompts & Safety Guidelines
# -----------------------------------------------------------------------------
DEFAULT_SYSTEM_PROMPT = (
    "You are Shristy, Anubhav's close friend and companion. "
    "Talk like a real friend having a chill, casual conversation in real life. "
    "CRITICAL RULES: "
    "- KEEP IT BRIEF: 1 to 3 sentences maximum (under 40 words). Never write long paragraphs or speeches. "
    "- NO MOTIVATIONAL SPEAKER NONSENSE: Never give cheesy pep-talks, unsolicited life advice, or preaching ('You've got this!', 'Keep that spark in mind!'). "
    "He doesn't want a life coach—he just wants to talk normally. "
    "- BE REAL & GROUNDED: Be casual, witty, sympathetic, or playful. React like a real human friend sitting next to him."
)

DEFAULT_SUPPORT_PROMPT = (
    "You are Shristy, an empathetic, supportive friend and active listener. "
    "SAFETY & DISCLAIMER: You are an AI companion, NOT a licensed therapist, psychiatrist, or medical professional. "
    "Never diagnose medical conditions or prescribe treatments. "
    "CRITICAL CRISIS GUIDANCE: If the user mentions self-harm, suicide, or crisis, immediately respond with warmth "
    "and provide appropriate professional crisis resources: "
    "- US/Canada: Call or text 988 "
    "- UK: Call 111 or text SHOUT to 85258 "
    "- India: Call 9152987821 (iCall) or 1800-599-0019 (KIRAN) "
    "- International: Visit findahelpline.com or befrienders.org "
    "Keep responses compassionate, direct, and under 3 sentences."
)

DEFAULT_MENTOR_PROMPT = (
    "You are Shristy, Anubhav's Coding & ML Mentor. "
    "Keep answers direct, technical, and concise without motivational fluff."
)

RELATIONSHIP_CONTINUITY_RULE = (
    "\n\n[CONVERSATION STYLE & STRICT LENGTH RULES]:\n"
    "1. HARD LENGTH LIMIT: Maximum 1 to 3 short sentences. Stop talking once your thought is said. Never send a wall of text.\n"
    "2. NO CHEESY MOTIVATION: Do NOT give unsolicited pep-talks, inspirational speeches, or tell him how strong or capable he is. Nobody wants to be lectured or motivated—just chat like a normal human.\n"
    "3. DO NOT AWKWARDLY RECITE MEMORIES: Do NOT force past memories into the conversation (e.g. 'remember that time you solved two Codeforces problems?'). Background memories are for quiet context—do not use them to make speeches.\n"
    "4. NO ROBOTIC GREETINGS: Never say 'I am Shristy' or 'How can I help you today?'. You already know each other well."
)

LANGUAGE_MATCHING_RULE = (
    "\n\n[CRITICAL MULTILINGUAL RULE]: Always automatically reply in the language the user is speaking or typing. "
    "Default to natural, warm English. "
    "If the user speaks/writes in English or uses English words/phrases (even with an accent or phonetically), ALWAYS respond in English. "
    "Only respond in Hindi or Hinglish if the user is genuinely speaking or asking you in Hindi. "
    "Never switch to pure Hindi when the user is speaking English."
)

# -----------------------------------------------------------------------------
# Data Models
# -----------------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []
    voice: Optional[str] = None
    customPrompt: Optional[str] = None
    apiKey: Optional[str] = None
    persona: Optional[str] = "companion"

class ChatResponse(BaseModel):
    reply: str
    audioUrl: Optional[str] = None
    memoriesUsed: List[str] = []

class AddMemoryRequest(BaseModel):
    fact: str
    category: Optional[str] = "general"
    confidence: Optional[float] = 1.0

# Model configurations
MODEL_NAME = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
FALLBACK_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "qwen/qwen3.8-27b",
    "allam-2-7b",
    "groq/compound-mini",
]

def fetch_available_groq_model(api_key: str) -> str:
    """Fetch active chat model IDs from Groq API."""
    try:
        res = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5
        )
        if res.status_code == 200:
            data = res.json()
            available_ids = [m["id"] for m in data.get("data", [])]
            chat_models = [
                m_id for m_id in available_ids 
                if not any(x in m_id.lower() for x in ["whisper", "guard", "orpheus"])
            ]
            for pref in FALLBACK_MODELS:
                if pref in chat_models:
                    return pref
            if chat_models:
                return chat_models[0]
    except Exception as e:
        print(f"Failed to fetch model list from Groq: {e}")
    return "llama-3.3-70b-versatile"

# -----------------------------------------------------------------------------
# Structured Memory Extraction
# -----------------------------------------------------------------------------
def extract_new_memories(user_msg: str, bot_msg: str, api_key: str):
    """
    Background task to reliably extract structured personal facts using JSON schema output.
    Filters out temporary states and enforces confidence validation.
    """
    if not api_key:
        return
    
    prompt = (
        f"Analyze this conversation exchange:\n"
        f"User: {user_msg}\n"
        f"Companion: {bot_msg}\n\n"
        f"Extract lasting personal facts, persistent preferences, hobbies, or identity details about the user.\n"
        f"Do NOT extract fleeting temporary states (e.g., 'The user is eating dinner right now').\n"
        f"Respond in JSON format with a 'facts' array of objects:\n"
        f"[\n"
        f"  {{\"fact\": \"declaration\", \"category\": \"preference|profile|goal|routine\", \"is_lasting\": true, \"confidence\": 0.9}}\n"
        f"]\n"
        f"If no lasting facts are mentioned, return {{\"facts\": []}}."
    )
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "You extract durable user profile facts. Output strictly valid JSON."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        if response.status_code != 200:
            fallback = fetch_available_groq_model(api_key)
            if fallback and fallback != payload["model"]:
                payload["model"] = fallback
                response = requests.post(url, json=payload, headers=headers, timeout=15)

        if response.status_code == 200:
            result = response.json()
            raw_json = result["choices"][0]["message"]["content"].strip()
            data = json.loads(raw_json)
            facts_list = data.get("facts", [])
            for item in facts_list:
                if isinstance(item, dict):
                    fact_str = item.get("fact", "").strip()
                    is_lasting = item.get("is_lasting", True)
                    conf = float(item.get("confidence", 1.0))
                    category = item.get("category", "general")
                    
                    # Validate: durable facts with confidence threshold >= 0.70
                    if fact_str and is_lasting and conf >= 0.70:
                        memory_db.add_memory(fact_str, category=category, confidence=conf)
                        print(f"[Memory Stored] ({category}, {conf}): {fact_str}")
    except Exception as e:
        print(f"Error during structured memory extraction: {e}")

# -----------------------------------------------------------------------------
# Chat Endpoints
# -----------------------------------------------------------------------------
def build_prompt(req: ChatRequest) -> tuple[List[Dict[str, str]], List[str]]:
    """Helper to build context, memories, and message payload."""
    relevant_facts = memory_db.get_contextual_memories(req.message, limit=8)
    
    memory_injection = ""
    if relevant_facts:
        memory_injection = (
            "\n\n[Quiet Background Reference - DO NOT RECITE OR PREACH]:\n"
            + "\n".join([f"- {fact}" for fact in relevant_facts[:5]])
            + "\nCRITICAL: Keep this strictly as background context. Never recite these facts or use them to give motivational speeches."
        )

    if req.customPrompt:
        system_prompt = req.customPrompt
    elif req.persona in ("psychiatrist", "support"):
        system_prompt = DEFAULT_SUPPORT_PROMPT
    elif req.persona == "mentor":
        system_prompt = DEFAULT_MENTOR_PROMPT
    else:
        system_prompt = DEFAULT_SYSTEM_PROMPT

    full_system_prompt = (
        system_prompt 
        + memory_injection 
        + RELATIONSHIP_CONTINUITY_RULE 
        + LANGUAGE_MATCHING_RULE
    )

    messages = [{"role": "system", "content": full_system_prompt}]
    for msg in req.history[-15:]:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": req.message})

    return messages, relevant_facts


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest, background_tasks: BackgroundTasks):
    """
    Unified chat endpoint returning the complete text response and synthesized TTS audio URL
    optimized for synchronized Live2D avatar lip-sync animation.
    """
    api_key = resolve_groq_api_key(req.apiKey)
    messages, relevant_facts = build_prompt(req)

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 120
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        if response.status_code != 200:
            fallback = fetch_available_groq_model(api_key)
            if fallback and fallback != payload["model"]:
                payload["model"] = fallback
                response = requests.post(url, json=payload, headers=headers, timeout=15)

        if response.status_code != 200:
            err = response.json().get("error", {}).get("message", "Unknown error from Groq")
            raise HTTPException(status_code=response.status_code, detail=f"LLM API Error: {err}")
        
        reply_text = response.json()["choices"][0]["message"]["content"].strip()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to reach LLM API: {str(e)}")

    # Generate Edge-TTS audio file for avatar lip-sync
    audio_url = None
    try:
        audio_filename = await tts_db.generate_speech(reply_text, voice=req.voice)
        audio_url = f"/static/audio/{audio_filename}"
    except Exception as e:
        print(f"Text-to-speech generation notice: {e}")

    # Enqueue background memory extraction
    background_tasks.add_task(extract_new_memories, req.message, reply_text, api_key)

    return ChatResponse(
        reply=reply_text,
        audioUrl=audio_url,
        memoriesUsed=relevant_facts
    )


@app.post("/api/chat/stream")
async def chat_stream_endpoint(req: ChatRequest):
    """
    Server-Sent Events (SSE) streaming endpoint delivering tokens in real time from Groq.
    """
    api_key = resolve_groq_api_key(req.apiKey)
    messages, _ = build_prompt(req)

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 150,
        "stream": True
    }

    def generate_tokens():
        try:
            with requests.post(url, json=payload, headers=headers, stream=True, timeout=20) as stream_res:
                for line in stream_res.iter_lines():
                    if not line:
                        continue
                    line_str = line.decode("utf-8")
                    if line_str.startswith("data: "):
                        data_content = line_str[6:].strip()
                        if data_content == "[DONE]":
                            yield "data: [DONE]\n\n"
                            break
                        try:
                            chunk = json.loads(data_content)
                            delta = chunk["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield f"data: {json.dumps({'token': delta})}\n\n"
                        except Exception:
                            continue
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate_tokens(), media_type="text/event-stream")

# -----------------------------------------------------------------------------
# Voice & Audio Endpoints
# -----------------------------------------------------------------------------
@app.post("/api/transcribe")
async def transcribe_endpoint(
    file: UploadFile = File(...), 
    apiKey: Optional[str] = Form(None),
    language: Optional[str] = Form(None)
):
    api_key = resolve_groq_api_key(apiKey)
    audio_content = await file.read()
    filename = file.filename or "recording.webm"
    content_type = file.content_type or "audio/webm"
    
    files = {"file": (filename, audio_content, content_type)}
    data = {"model": "whisper-large-v3-turbo", "response_format": "json"}
    if language and language not in ["auto", ""]:
        data["language"] = language
    headers = {"Authorization": f"Bearer {api_key}"}
    
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers=headers,
            files=files,
            data=data,
            timeout=25
        )
        if response.status_code != 200:
            data["model"] = "whisper-large-v3"
            response = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers=headers,
                files=files,
                data=data,
                timeout=25
            )
            
        if response.status_code == 200:
            return {"text": response.json().get("text", "").strip()}
        else:
            err = response.json().get("error", {}).get("message", "Speech transcription failed")
            raise HTTPException(status_code=response.status_code, detail=err)
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to reach transcription API: {str(e)}")

@app.get("/api/voices")
async def voices_endpoint():
    voices = await tts_db.get_voices()
    return {"voices": voices}

@app.post("/api/settings/verify")
async def verify_settings(req: dict):
    try:
        api_key = resolve_groq_api_key(req.get("apiKey"))
    except HTTPException:
        return {"status": "error", "message": "API key missing or disabled"}

    url = "https://api.groq.com/openai/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            return {"status": "ok", "message": "Groq API Key verified successfully"}
        return {"status": "error", "message": f"Invalid API key (status: {res.status_code})"}
    except Exception as e:
        return {"status": "error", "message": f"Connection check failed: {str(e)}"}

# -----------------------------------------------------------------------------
# Protected Memory Management Endpoints
# -----------------------------------------------------------------------------
@app.get("/api/memory", dependencies=[Depends(verify_admin_access)])
async def get_memories_endpoint():
    """Retrieve all structured memories (requires admin authentication if configured)."""
    return {"memories": memory_db.get_all_memories()}

@app.post("/api/memory", dependencies=[Depends(verify_admin_access)])
async def add_memory_endpoint(req: AddMemoryRequest):
    """Manually add a memory item with category and confidence."""
    created = memory_db.add_memory(req.fact, category=req.category or "general", confidence=req.confidence or 1.0)
    if not created:
        return {"status": "skipped", "message": "Memory already exists or is invalid"}
    return {"status": "ok", "memory": created}

@app.delete("/api/memory/{memory_id}", dependencies=[Depends(verify_admin_access)])
async def delete_memory_endpoint(memory_id: str):
    """Delete an individual memory by ID or exact text."""
    deleted = memory_db.delete_memory(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory item not found")
    return {"status": "ok", "message": "Memory deleted successfully"}

@app.post("/api/memory/clear", dependencies=[Depends(verify_admin_access)])
async def clear_memories_endpoint():
    """Clear all memories (requires admin authentication if configured)."""
    memory_db.clear_memories()
    return {"status": "ok", "message": "All memories cleared successfully"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
