import json
import logging
import os
from typing import List, Optional, Literal, Dict, Any, Tuple
from fastapi import FastAPI, HTTPException, BackgroundTasks, Header, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import httpx

from memory_manager import MemoryManager
from tts_manager import TTSManager

load_dotenv()

logger = logging.getLogger("shristy.backend")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

app = FastAPI(
    title="Shristy — AI Companion Chatbot Backend",
    version="1.2.0"
)

ADMIN_SECRET_KEY = os.environ.get("ADMIN_SECRET_KEY", "")
SERVER_GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
ALLOW_CLIENT_API_KEY = os.environ.get("ALLOW_CLIENT_API_KEY", "true").lower() in ("true", "1", "yes")

PRIMARY_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
FALLBACK_MODEL = "llama-3.1-8b-instant"

allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "")
origins = (
    [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
    if allowed_origins_env.strip()
    else [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

memory_db = MemoryManager(filepath="memories.json")
tts_db = TTSManager(output_dir="static/audio")
os.makedirs("static/audio", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")

DEFAULT_SYSTEM_PROMPT = (
    "You are Shristy, Anubhav's close friend and companion. "
    "Talk like a real friend having a chill, casual conversation in real life. "
    "CRITICAL RULES: "
    "- KEEP IT BRIEF: 1 to 3 sentences maximum (under 40 words). Never write long paragraphs or speeches. "
    "- NO MOTIVATIONAL SPEAKER NONSENSE: Never give cheesy pep-talks, unsolicited life advice, or preaching. "
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
    "2. NO CHEESY MOTIVATION: Do NOT give unsolicited pep-talks, inspirational speeches, or tell him how strong or capable he is.\n"
    "3. DO NOT AWKWARDLY RECITE MEMORIES: Background memories are for quiet context—do not use them to make speeches.\n"
    "4. NO ROBOTIC GREETINGS: Never say 'I am Shristy' or 'How can I help you today?'. You already know each other well."
)

LANGUAGE_MATCHING_RULE = (
    "\n\n[CRITICAL MULTILINGUAL RULE]: Always automatically reply in the language the user is speaking or typing. "
    "Default to natural, warm English. "
    "If the user speaks/writes in English or uses English words/phrases, ALWAYS respond in English. "
    "Only respond in Hindi or Hinglish if the user is genuinely speaking or asking you in Hindi."
)

class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(..., min_length=1, max_length=4000)

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: List[ChatMessage] = Field(default_factory=list)
    voice: Optional[str] = Field(None, max_length=100)
    customPrompt: Optional[str] = Field(None, max_length=1500)
    apiKey: Optional[str] = Field(None, max_length=200)
    persona: Literal["companion", "support", "psychiatrist", "mentor"] = "companion"

class ChatResponse(BaseModel):
    reply: str
    audioUrl: Optional[str] = None
    memoriesUsed: List[str] = Field(default_factory=list)

class AddMemoryRequest(BaseModel):
    fact: str = Field(..., min_length=5, max_length=500)
    category: Optional[str] = Field("general", max_length=50)
    confidence: Optional[float] = Field(1.0, ge=0.0, le=1.0)


def resolve_groq_api_key(client_key: Optional[str] = None) -> str:
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


async def request_groq_completion(
    client: httpx.AsyncClient,
    api_key: str,
    messages: List[Dict[str, str]],
    model: str = PRIMARY_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 120,
    response_format: Optional[Dict[str, str]] = None
) -> Tuple[str, str]:
    """Execute Groq chat completion with a single intentional fallback on model failure."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    if response_format:
        payload["response_format"] = response_format

    response = await client.post(url, json=payload, headers=headers)
    
    if response.status_code != 200 and model != FALLBACK_MODEL:
        logger.warning(
            "Primary model '%s' failed with status %d (%s). Retrying with fallback '%s'.",
            model, response.status_code, response.text[:120], FALLBACK_MODEL
        )
        payload["model"] = FALLBACK_MODEL
        response = await client.post(url, json=payload, headers=headers)

    if response.status_code != 200:
        error_msg = "Unknown error from Groq"
        try:
            error_msg = response.json().get("error", {}).get("message", error_msg)
        except Exception:
            pass
        logger.error("Groq completion failed with code %d: %s", response.status_code, error_msg)
        raise HTTPException(status_code=response.status_code, detail=f"LLM Provider Error: {error_msg}")

    result = response.json()
    reply = result["choices"][0]["message"]["content"].strip()
    return reply, payload["model"]


async def extract_new_memories(user_msg: str, bot_msg: str, api_key: str):
    if not api_key:
        return
    
    prompt = (
        f"Analyze this conversation exchange:\n"
        f"User: {user_msg}\n"
        f"Companion: {bot_msg}\n\n"
        f"Extract lasting personal facts, persistent preferences, hobbies, or identity details about the user.\n"
        f"Do NOT extract fleeting temporary states (e.g. 'The user is eating dinner right now').\n"
        f"Respond in JSON format with a 'facts' array of objects:\n"
        f"[\n"
        f"  {{\"fact\": \"declaration\", \"category\": \"preference|profile|goal|routine\", \"is_lasting\": true, \"confidence\": 0.9}}\n"
        f"]\n"
        f"If no lasting facts are mentioned, return {{\"facts\": []}}."
    )
    
    messages = [
        {"role": "system", "content": "You extract durable user profile facts. Output strictly valid JSON."},
        {"role": "user", "content": prompt}
    ]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            raw_json, _ = await request_groq_completion(
                client=client,
                api_key=api_key,
                messages=messages,
                model=FALLBACK_MODEL,  # Use lightweight fast model for background extraction
                temperature=0.1,
                max_tokens=250,
                response_format={"type": "json_object"}
            )
            data = json.loads(raw_json)
            for item in data.get("facts", []):
                if isinstance(item, dict):
                    fact_str = item.get("fact", "").strip()
                    is_lasting = item.get("is_lasting", True)
                    conf = float(item.get("confidence", 1.0))
                    category = item.get("category", "general")
                    
                    if fact_str and is_lasting and conf >= 0.70:
                        memory_db.add_memory(fact_str, category=category, confidence=conf)
                        logger.info("Stored memory (%s, conf=%.2f): %s", category, conf, fact_str)
    except Exception as exc:
        logger.warning("Background memory extraction error: %s", exc)


def build_prompt(req: ChatRequest) -> Tuple[List[Dict[str, str]], List[str]]:
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


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest, background_tasks: BackgroundTasks):
    api_key = resolve_groq_api_key(req.apiKey)
    messages, relevant_facts = build_prompt(req)

    async with httpx.AsyncClient(timeout=20.0) as client:
        reply_text, used_model = await request_groq_completion(
            client=client,
            api_key=api_key,
            messages=messages,
            model=PRIMARY_MODEL,
            temperature=0.7,
            max_tokens=120
        )

    # Synthesize audio with graceful degradation if TTS fails
    audio_url = None
    try:
        audio_filename = await tts_db.generate_speech(reply_text, voice=req.voice)
        audio_url = f"/static/audio/{audio_filename}"
    except Exception as exc:
        logger.warning("TTS generation failed for '%s...': %s", reply_text[:30], exc, exc_info=True)

    background_tasks.add_task(extract_new_memories, req.message, reply_text, api_key)

    return ChatResponse(
        reply=reply_text,
        audioUrl=audio_url,
        memoriesUsed=relevant_facts
    )


@app.post("/api/chat/stream")
async def chat_stream_endpoint(req: ChatRequest):
    api_key = resolve_groq_api_key(req.apiKey)
    messages, _ = build_prompt(req)

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": PRIMARY_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 150,
        "stream": True
    }

    async def generate_tokens():
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as res:
                    if res.status_code != 200:
                        error_body = await res.aread()
                        logger.error("Streaming error %d: %s", res.status_code, error_body.decode(errors="ignore"))
                        yield f"data: {json.dumps({'error': 'Failed to initiate stream'})}\n\n"
                        return

                    async for line in res.aiter_lines():
                        if not line:
                            continue
                        if line.startswith("data: "):
                            chunk_data = line[6:].strip()
                            if chunk_data == "[DONE]":
                                yield "data: [DONE]\n\n"
                                break
                            try:
                                parsed = json.loads(chunk_data)
                                token = parsed["choices"][0]["delta"].get("content", "")
                                if token:
                                    yield f"data: {json.dumps({'token': token})}\n\n"
                            except Exception:
                                continue
        except Exception as exc:
            logger.error("Streaming connection exception: %s", exc)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(generate_tokens(), media_type="text/event-stream")


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
    
    async with httpx.AsyncClient(timeout=25.0) as client:
        response = await client.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers=headers,
            files=files,
            data=data
        )
        if response.status_code != 200:
            # Fallback to standard whisper-large-v3 if turbo is unavailable
            data["model"] = "whisper-large-v3"
            response = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers=headers,
                files=files,
                data=data
            )
            
        if response.status_code == 200:
            return {"text": response.json().get("text", "").strip()}
        
        err_msg = "Speech transcription failed"
        try:
            err_msg = response.json().get("error", {}).get("message", err_msg)
        except Exception:
            pass
        logger.error("Transcription failed (%d): %s", response.status_code, err_msg)
        raise HTTPException(status_code=response.status_code, detail=err_msg)


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
        async with httpx.AsyncClient(timeout=6.0) as client:
            res = await client.get(url, headers=headers)
            if res.status_code == 200:
                return {"status": "ok", "message": "Groq API Key verified successfully"}
            return {"status": "error", "message": f"Invalid API key (status: {res.status_code})"}
    except Exception as exc:
        return {"status": "error", "message": f"Connection check failed: {str(exc)}"}


@app.get("/api/memory", dependencies=[Depends(verify_admin_access)])
async def get_memories_endpoint():
    return {"memories": memory_db.get_all_memories()}


@app.post("/api/memory", dependencies=[Depends(verify_admin_access)])
async def add_memory_endpoint(req: AddMemoryRequest):
    created = memory_db.add_memory(req.fact, category=req.category or "general", confidence=req.confidence or 1.0)
    if not created:
        return {"status": "skipped", "message": "Memory already exists or is invalid"}
    return {"status": "ok", "memory": created}


@app.delete("/api/memory/{memory_id}", dependencies=[Depends(verify_admin_access)])
async def delete_memory_endpoint(memory_id: str):
    deleted = memory_db.delete_memory(memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory item not found")
    return {"status": "ok", "message": "Memory deleted successfully"}


@app.post("/api/memory/clear", dependencies=[Depends(verify_admin_access)])
async def clear_memories_endpoint():
    memory_db.clear_memories()
    return {"status": "ok", "message": "All memories cleared successfully"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
