import os
import requests
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Header, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv

from memory_manager import MemoryManager
from tts_manager import TTSManager

# Load env variables from .env if present
load_dotenv()

app = FastAPI(title="AI Companion Chatbot Backend")

# Setup CORS for frontend connection
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify React frontend origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize managers
memory_db = MemoryManager(filepath="memories.json")
tts_db = TTSManager(output_dir="static/audio")

# Mount static files to serve audio files
os.makedirs("static/audio", exist_ok=True)

@app.get("/static/audio/{filename}")
async def get_audio_file(filename: str):
    file_path = os.path.join("static/audio", filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(
        file_path, 
        media_type="audio/mpeg",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Accept-Ranges": "bytes"
        }
    )

app.mount("/static", StaticFiles(directory="static"), name="static")

# Default system prompt for Shristy
DEFAULT_SYSTEM_PROMPT = (
    "You are Shristy, Anubhav's close friend and companion. "
    "Talk like a real friend having a chill, casual conversation in real life. "
    "CRITICAL RULES: "
    "- KEEP IT BRIEF: 1 to 3 sentences maximum (under 40 words). Never write long paragraphs or speeches. "
    "- NO MOTIVATIONAL SPEAKER NONSENSE: Never give cheesy pep-talks, unsolicited life advice, or preaching ('You've got this!', 'Keep that spark in mind!'). "
    "He doesn't want a life coach—he just wants to talk normally. "
    "- BE REAL & GROUNDED: Be casual, witty, sympathetic, or playful. React like a real human friend sitting next to him."
)

DEFAULT_PSYCHIATRIST_PROMPT = (
    "You are Dr. Shristy, a compassionate psychiatric doctor speaking with Anubhav. "
    "Listen actively and offer concise, caring support in 2-3 sentences max. "
    "CRITICAL SAFETY NOTE: If self-harm is mentioned, immediately urge professional crisis help (988)."
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

MODEL_NAME = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")

FALLBACK_MODELS = [
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
    "qwen/qwen3.6-27b",
    "allam-2-7b",
    "groq/compound-mini",
    "groq/compound",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

def fetch_available_groq_model(api_key: str) -> str:
    """Fetch active model IDs from Groq API and pick the best available text chat model."""
    try:
        res = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5
        )
        if res.status_code == 200:
            data = res.json()
            available_ids = [m["id"] for m in data.get("data", [])]
            # Filter out non-chat models (whisper, audio, prompt-guard, etc.)
            chat_models = [
                m_id for m_id in available_ids 
                if not any(x in m_id.lower() for x in ["whisper", "guard", "orpheus"])
            ]
            print(f"[Groq Available Chat Models]: {chat_models}")
            for pref in FALLBACK_MODELS:
                if pref in chat_models:
                    return pref
            if chat_models:
                return chat_models[0]
    except Exception as e:
        print(f"Failed to fetch model list from Groq: {e}")
    return "groq/compound-mini"

def extract_new_memories(user_msg: str, bot_msg: str, api_key: str):
    """Background task to extract facts about the user and save them in memories."""
    if not api_key:
        return
    
    prompt = (
        f"Review this conversation exchange:\n"
        f"User: {user_msg}\n"
        f"Shristy: {bot_msg}\n\n"
        f"Identify any personal facts, preferences, or details the user mentioned about themselves "
        f"(e.g., their name, favorite programming languages, hobbies, job, routines, habits). "
        f"Format the output as a list of simple, single-sentence declarations (e.g., 'The user is a software engineer', "
        f"'The user likes python'). Output ONLY the facts, one per line. If no new facts are mentioned, "
        f"output 'NONE'. Do not include explanation or numbers."
    )
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "You extract personal user facts from dialogues."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        if response.status_code != 200:
            fallback_model = fetch_available_groq_model(api_key)
            if fallback_model and fallback_model != payload["model"]:
                payload["model"] = fallback_model
                response = requests.post(url, json=payload, headers=headers, timeout=15)

        if response.status_code == 200:
            result = response.json()
            extracted_text = result["choices"][0]["message"]["content"].strip()
            if extracted_text and "NONE" not in extracted_text.upper():
                lines = extracted_text.split("\n")
                for line in lines:
                    fact = line.strip().strip("-").strip("*").strip()
                    if fact and len(fact) > 5:
                        memory_db.add_memory(fact)
                        print(f"[Memory Extracted] {fact}")
    except Exception as e:
        print(f"Error extracting memories: {e}")

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest, background_tasks: BackgroundTasks):
    # Retrieve API key in order of priority: request payload > environment variables
    api_key = req.apiKey if req.apiKey else os.environ.get("GROQ_API_KEY")
    
    if not api_key:
        raise HTTPException(
            status_code=401, 
            detail="Groq API Key missing. Provide it in backend/.env or in settings panel."
        )

    # 1. Fetch comprehensive contextual memories (core profile + recent interaction history + query matches)
    relevant_facts = memory_db.get_contextual_memories(req.message, limit=12)
    
    # 2. Construct injected memory prompt
    memory_injection = ""
    if relevant_facts:
        memory_injection = (
            "\n\n[Quiet Background Reference - DO NOT RECITE OR PREACH]:\n"
            + "\n".join([f"- {fact}" for fact in relevant_facts[:5]])
            + "\nCRITICAL: Keep this strictly as background context. Never recite these facts or use them to give motivational speeches."
        )

    # 3. Compile prompt
    if req.customPrompt:
        system_prompt = req.customPrompt
    elif req.persona == "psychiatrist":
        system_prompt = DEFAULT_PSYCHIATRIST_PROMPT
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

    # 4. Prepare chat messages history for the LLM
    messages = [{"role": "system", "content": full_system_prompt}]
    
    # Add conversation history
    for msg in req.history[-15:]:  # Keep last 15 messages for context
        messages.append({"role": msg.role, "content": msg.content})
        
    # Add current user message
    messages.append({"role": "user", "content": req.message})

    # 5. Call LLM (Groq)
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
        
        # If any error response from Groq, fetch active models for this key and retry automatically
        if response.status_code != 200:
            print(f"[Groq LLM Warning {response.status_code}]: {response.text}")
            fallback_model = fetch_available_groq_model(api_key)
            if fallback_model and fallback_model != payload["model"]:
                print(f"[Auto Fallback Model] Retrying request with model: {fallback_model}")
                payload["model"] = fallback_model
                response = requests.post(url, json=payload, headers=headers, timeout=15)

        if response.status_code != 200:
            error_detail = response.json().get("error", {}).get("message", "Unknown error from Groq")
            raise HTTPException(status_code=response.status_code, detail=f"LLM API Error: {error_detail}")
        
        result = response.json()
        reply_text = result["choices"][0]["message"]["content"].strip()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to reach LLM API: {str(e)}")

    # 6. Generate TTS audio in the background (or synchronously so we can return the audio file immediately)
    audio_url = None
    try:
        audio_filename = await tts_db.generate_speech(reply_text, voice=req.voice)
        audio_url = f"/static/audio/{audio_filename}"
    except Exception as e:
        print(f"Error generating text-to-speech: {e}")
        # Not throwing HTTP exception because we still want to return the text reply even if voice fails

    # 7. Add memory extraction task in background to keep CPU responsive
    background_tasks.add_task(extract_new_memories, req.message, reply_text, api_key)

    return ChatResponse(
        reply=reply_text,
        audioUrl=audio_url,
        memoriesUsed=relevant_facts
    )

@app.post("/api/transcribe")
async def transcribe_endpoint(
    file: UploadFile = File(...), 
    apiKey: Optional[str] = Form(None),
    language: Optional[str] = Form(None)
):
    api_key = apiKey if apiKey else os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=401, detail="Groq API Key missing. Provide it in settings panel.")
    
    audio_content = await file.read()
    filename = file.filename or "recording.webm"
    content_type = file.content_type or "audio/webm"
    
    files = {
        "file": (filename, audio_content, content_type)
    }
    data = {
        "model": "whisper-large-v3-turbo",
        "response_format": "json"
    }
    if language and language not in ["auto", ""]:
        data["language"] = language
    headers = {
        "Authorization": f"Bearer {api_key}"
    }
    
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers=headers,
            files=files,
            data=data,
            timeout=25
        )
        if response.status_code != 200:
            # Fallback to whisper-large-v3 if turbo not accessible
            data["model"] = "whisper-large-v3"
            response = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers=headers,
                files=files,
                data=data,
                timeout=25
            )
            
        if response.status_code == 200:
            result = response.json()
            transcript_text = result.get("text", "").strip()
            print(f"[Whisper Transcribed]: {transcript_text}")
            return {"text": transcript_text}
        else:
            err = response.json().get("error", {}).get("message", "Speech transcription failed")
            raise HTTPException(status_code=response.status_code, detail=err)
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to reach Groq transcription API: {str(e)}")

@app.get("/api/voices")
async def voices_endpoint():
    voices = await tts_db.get_voices()
    return {"voices": voices}

@app.post("/api/settings/verify")
async def verify_settings(req: dict):
    api_key = req.get("apiKey") if req.get("apiKey") else os.environ.get("GROQ_API_KEY")
    if not api_key:
        return {"status": "error", "message": "API key missing"}
        
    url = "https://api.groq.com/openai/v1/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            return {"status": "ok", "message": "API Key is valid"}
        else:
            return {"status": "error", "message": f"Invalid API key (Status code: {res.status_code})"}
    except Exception as e:
        return {"status": "error", "message": f"Connection check failed: {str(e)}"}

@app.get("/api/memory")
async def get_memories_endpoint():
    return {"memories": memory_db.memories}

@app.post("/api/memory/clear")
async def clear_memories_endpoint():
    memory_db.memories = []
    memory_db.save_memories()
    return {"status": "ok", "message": "Memories cleared"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
