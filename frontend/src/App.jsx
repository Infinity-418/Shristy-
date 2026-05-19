import React, { useState, useEffect, useRef } from "react";
import Avatar from "./components/Avatar";
import { useAudioAnalyser } from "./hooks/useAudioAnalyser";
import "./App.css";

const BACKEND_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function App() {
  const { analyserNode, audioContext, connectAudio, resumeAudioContext } = useAudioAnalyser();
  const [persona, setPersona] = useState(() => localStorage.getItem("shristy_persona") || "companion");
  const [messages, setMessages] = useState(() => {
    try {
      const saved = localStorage.getItem("shristy_chat_history");
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) {
          return parsed;
        }
      }
    } catch (e) {
      console.warn("Failed to load chat history:", e);
    }
    const savedPersona = localStorage.getItem("shristy_persona") || "companion";
    if (savedPersona === "psychiatrist") {
      return [{
        role: "assistant",
        content: "Hey Anubhav, I'm here with you. How are you feeling right now?"
      }];
    } else if (savedPersona === "mentor") {
      return [{
        role: "assistant",
        content: "Hey Anubhav! Ready to dive back into Codeforces, DSA, or ML models today?"
      }];
    } else {
      return [{
        role: "assistant",
        content: "Hey Anubhav! Good to chat with you again. How's everything going?"
      }];
    }
  });
  const [inputText, setInputText] = useState("");
  
  // Status states
  const [isThinking, setIsThinking] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");

  // Settings states (persisted in localStorage)
  const [apiKey, setApiKey] = useState(() => localStorage.getItem("shristy_api_key") || "");
  const [customPrompt, setCustomPrompt] = useState(() => localStorage.getItem("shristy_system_prompt") || "");
  const [selectedVoice, setSelectedVoice] = useState(() => localStorage.getItem("shristy_voice") || "en-US-AvaNeural");
  const [speechLanguage, setSpeechLanguage] = useState(() => localStorage.getItem("shristy_speech_lang") || "en-IN");
  
  // Modal & API data
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [voices, setVoices] = useState([]);
  const [memories, setMemories] = useState([]);
  const [testStatus, setTestStatus] = useState({ type: "", message: "" });

  const audioRef = useRef(null);
  const chatEndRef = useRef(null);
  const recognitionRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioStreamRef = useRef(null);
  const recognizedTextRef = useRef("");
  const silenceTimerRef = useRef(null);
  const sendChatRequestRef = useRef(null);
  const textareaRef = useRef(null);

  // Auto scroll to bottom of chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isThinking]);

  // Persist conversation history to localStorage
  useEffect(() => {
    try {
      localStorage.setItem("shristy_chat_history", JSON.stringify(messages));
    } catch (e) {
      console.warn("Failed to persist chat history:", e);
    }
  }, [messages]);

  // Auto resize input textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`;
    }
  }, [inputText]);

  const fetchVoices = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/voices`);
      if (response.ok) {
        const data = await response.json();
        setVoices(data.voices || []);
      }
    } catch (err) {
      console.error("Failed to fetch voices list:", err);
    }
  };

  // Fetch voices list on startup
  useEffect(() => {
    fetchVoices();
  }, []);

  // Fetch long term memories and fresh voices when settings are opened
  useEffect(() => {
    if (isSettingsOpen) {
      fetchMemories();
      fetchVoices();
    }
  }, [isSettingsOpen]);

  const fetchMemories = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/memory`);
      if (response.ok) {
        const data = await response.json();
        setMemories(data.memories || []);
      }
    } catch (err) {
      console.error("Failed to fetch memories:", err);
    }
  };

  const clearMemories = async () => {
    if (window.confirm("Are you sure you want to clear Shristy's long-term memory? She will forget everything about you.")) {
      try {
        const response = await fetch(`${BACKEND_URL}/api/memory/clear`, { method: "POST" });
        if (response.ok) {
          setMemories([]);
          alert("Memories cleared successfully.");
        }
      } catch (err) {
        console.error("Failed to clear memories:", err);
      }
    }
  };

  const deleteMemory = async (memId) => {
    try {
      const response = await fetch(`${BACKEND_URL}/api/memory/${encodeURIComponent(memId)}`, { method: "DELETE" });
      if (response.ok) {
        setMemories(prev => prev.filter(m => (typeof m === 'object' ? m.id !== memId && m.text !== memId : m !== memId)));
      }
    } catch (err) {
      console.error("Failed to delete memory:", err);
    }
  };

  const selectedVoiceObj = voices.find(v => v.ShortName === selectedVoice);
  const selectedLocale = selectedVoiceObj ? selectedVoiceObj.Locale : "en-US";

  // Robust Hybrid Speech Recognition & Whisper STT Fallback
  const stopListeningAndSend = async () => {
    setIsListening(false);
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }

    // Stop Web Speech Recognition if active
    if (recognitionRef.current) {
      try {
        recognitionRef.current.onresult = null;
        recognitionRef.current.onerror = null;
        recognitionRef.current.onend = null;
        recognitionRef.current.stop();
      } catch (_) {}
      recognitionRef.current = null;
    }

    const liveText = (recognizedTextRef.current || "").trim();

    // Stop MediaRecorder if recording
    const recorder = mediaRecorderRef.current;
    mediaRecorderRef.current = null;

    if (recorder && recorder.state !== "inactive") {
      recorder.onstop = async () => {
        // Stop microphone hardware tracks
        if (audioStreamRef.current) {
          audioStreamRef.current.getTracks().forEach((t) => t.stop());
          audioStreamRef.current = null;
        }

        // If Web Speech already captured high-confidence text, send immediately
        if (liveText && liveText.length > 1) {
          setInputText("");
          recognizedTextRef.current = "";
          setStatusMessage("");
          sendChatRequestRef.current?.(liveText);
          return;
        }

        // If browser speech recognition failed / heard nothing (very common in Safari), fallback to Groq Whisper
        if (audioChunksRef.current.length > 0) {
          setStatusMessage("Transcribing audio with Whisper...");
          try {
            const mimeType = recorder.mimeType || "audio/webm";
            const audioBlob = new Blob(audioChunksRef.current, { type: mimeType });
            const ext = mimeType.includes("mp4") ? "m4a" : "webm";
            const formData = new FormData();
            formData.append("file", audioBlob, `speech.${ext}`);
            if (speechLanguage) {
              formData.append("language", speechLanguage.split("-")[0]);
            }
            if (apiKey.trim()) {
              formData.append("apiKey", apiKey.trim());
            }

            const response = await fetch(`${BACKEND_URL}/api/transcribe`, {
              method: "POST",
              body: formData,
            });

            if (response.ok) {
              const data = await response.json();
              const whisperText = (data.text || "").trim();
              if (whisperText) {
                setInputText("");
                recognizedTextRef.current = "";
                setStatusMessage("");
                sendChatRequestRef.current?.(whisperText);
                return;
              }
            } else {
              const errData = await response.json().catch(() => ({}));
              console.warn("Whisper transcription response:", errData);
            }
          } catch (sttErr) {
            console.error("Transcription failed:", sttErr);
          }
        }

        setStatusMessage("Couldn't hear anything. Try speaking again.");
        setTimeout(() => setStatusMessage(""), 2500);
      };

      try {
        recorder.stop();
      } catch (_) {}
    } else {
      if (audioStreamRef.current) {
        audioStreamRef.current.getTracks().forEach((t) => t.stop());
        audioStreamRef.current = null;
      }
      if (liveText) {
        setInputText("");
        recognizedTextRef.current = "";
        setStatusMessage("");
        sendChatRequestRef.current?.(liveText);
      } else {
        setStatusMessage("");
      }
    }
  };

  const startListening = async () => {
    resumeAudioContext();
    // 1. Interrupt any playing TTS speech
    if (audioRef.current) {
      audioRef.current.pause();
      setIsSpeaking(false);
    }

    recognizedTextRef.current = "";
    audioChunksRef.current = [];
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }

    // 2. Request mic audio stream
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioStreamRef.current = stream;
    } catch (err) {
      console.error("Microphone access error:", err);
      setStatusMessage("Microphone permission denied.");
      alert("Microphone access was denied or is unavailable. Please check your browser's microphone permissions.");
      return;
    }

    // 3. Start MediaRecorder
    try {
      const mimeType = MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : MediaRecorder.isTypeSupported("audio/mp4")
        ? "audio/mp4"
        : "";
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          audioChunksRef.current.push(e.data);
        }
      };
      recorder.start(200);
      mediaRecorderRef.current = recorder;
    } catch (recErr) {
      console.warn("MediaRecorder start warning:", recErr);
    }

    // 4. Start Web Speech API for live transcription display
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      try {
        const rec = new SpeechRecognition();
        rec.continuous = true;
        rec.interimResults = true;
        rec.lang = speechLanguage || "en-IN";

        rec.onresult = (event) => {
          let fullText = "";
          for (let i = 0; i < event.results.length; i++) {
            fullText += event.results[i][0].transcript;
          }
          if (fullText.trim()) {
            setInputText(fullText);
            recognizedTextRef.current = fullText;

            // Auto-stop and submit 2 seconds after user stops speaking
            if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
            silenceTimerRef.current = setTimeout(() => {
              stopListeningAndSend();
            }, 2000);
          }
        };

        rec.onerror = (e) => {
          console.warn("Speech recognition warning:", e.error);
          if (e.error === "not-allowed" || e.error === "service-not-allowed") {
            setStatusMessage("Microphone permission denied.");
          }
        };

        rec.start();
        recognitionRef.current = rec;
      } catch (speechErr) {
        console.warn("SpeechRecognition error:", speechErr);
      }
    }

    setIsListening(true);
    setStatusMessage("Listening... Speak now (tap 🎤 to send)");
  };

  const toggleListening = () => {
    if (isListening) {
      stopListeningAndSend();
    } else {
      startListening();
    }
  };

  // Cleanup mic & recognition on unmount
  useEffect(() => {
    return () => {
      if (silenceTimerRef.current) clearTimeout(silenceTimerRef.current);
      if (recognitionRef.current) {
        try { recognitionRef.current.stop(); } catch (_) {}
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
        try { mediaRecorderRef.current.stop(); } catch (_) {}
      }
      if (audioStreamRef.current) {
        audioStreamRef.current.getTracks().forEach((t) => t.stop());
      }
    };
  }, []);

  const handlePersonaChange = (newPersona) => {
    if (newPersona === persona) return;
    
    let modeLabel = "AI Companion";
    if (newPersona === "psychiatrist") modeLabel = "Psychiatric Doctor";
    else if (newPersona === "mentor") modeLabel = "Coding & ML Mentor";

    if (window.confirm(`Switch to ${modeLabel} mode? This will switch persona while keeping your memories safe.`)) {
      setPersona(newPersona);
      localStorage.setItem("shristy_persona", newPersona);
      const greeting = newPersona === "psychiatrist"
        ? "Hey Anubhav, I'm here with you. How are you feeling right now?"
        : (newPersona === "mentor"
          ? "Hey Anubhav! Ready to dive back into Codeforces, DSA, or ML models today?"
          : "Hey Anubhav! Good to chat with you again. How's everything going?");
      const newMessages = [{ role: "assistant", content: greeting }];
      setMessages(newMessages);
      localStorage.setItem("shristy_chat_history", JSON.stringify(newMessages));

      if (audioRef.current) {
        audioRef.current.pause();
        setIsSpeaking(false);
      }
      setStatusMessage("");
    }
  };

  const handleResetChat = () => {
    if (window.confirm("Start a new chat session? (Your long-term memories with Shristy will be kept safe)")) {
      const greeting = persona === "psychiatrist"
        ? "Hey Anubhav, I'm here with you. How are you feeling right now?"
        : (persona === "mentor"
          ? "Hey Anubhav! Ready to dive back into Codeforces, DSA, or ML models today?"
          : "Hey Anubhav! Good to chat with you again. How's everything going?");
      const freshMessages = [{ role: "assistant", content: greeting }];
      setMessages(freshMessages);
      localStorage.setItem("shristy_chat_history", JSON.stringify(freshMessages));
      if (audioRef.current) {
        audioRef.current.pause();
        setIsSpeaking(false);
      }
      setStatusMessage("");
    }
  };

  const handleSendMessage = (e) => {
    e?.preventDefault?.();
    if (!inputText.trim()) return;
    resumeAudioContext();
    sendChatRequest(inputText);
    setInputText("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const sendChatRequest = async (text) => {
    if (isThinking) return;

    // Add user message to UI
    const newUserMessage = { role: "user", content: text };
    setMessages((prev) => [...prev, newUserMessage]);
    setIsThinking(true);
    setStatusMessage("Thinking...");

    try {
      // Build API request payload
      const chatHistory = messages.map(m => ({ role: m.role, content: m.content }));
      const response = await fetch(`${BACKEND_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          history: chatHistory,
          voice: selectedVoice,
          customPrompt: customPrompt.trim() ? customPrompt : null,
          apiKey: apiKey.trim() ? apiKey : null,
          persona: persona
        })
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || "Failed to communicate with LLM backend");
      }

      const data = await response.json();

      // Add assistant response to UI
      setMessages((prev) => [
        ...prev, 
        { 
          role: "assistant", 
          content: data.reply,
          memoriesUsed: data.memoriesUsed 
        }
      ]);
      setIsThinking(false);

      // Play audio response if available and not muted
      if (data.audioUrl && !isMuted) {
        const fullAudioUrl = `${BACKEND_URL}${data.audioUrl}`;
        setStatusMessage(
          persona === "psychiatrist" 
            ? "Dr. Shristy is speaking..." 
            : (persona === "mentor" ? "Shristy (Mentor) is speaking..." : "Shristy is speaking...")
        );

        resumeAudioContext();

        const el = audioRef.current;
        if (el) {
          el.crossOrigin = "anonymous";
          el.src = fullAudioUrl;

          try {
            connectAudio(el);
          } catch (_) {}

          el.play()
            .then(() => {
              setIsSpeaking(true);
            })
            .catch((playErr) => {
              console.warn("audio element play failed, trying direct fallback Audio instance:", playErr);
              const fallbackAudio = new Audio(fullAudioUrl);
              fallbackAudio.onplay = () => setIsSpeaking(true);
              fallbackAudio.onended = () => {
                setIsSpeaking(false);
                setStatusMessage("");
              };
              fallbackAudio.play().catch((fbErr) => {
                console.warn("Audio autoplay blocked by browser:", fbErr);
                setStatusMessage("Tap anywhere to hear Shristy speak 🔊");
                const onUserTap = () => {
                  fallbackAudio.play().catch(() => {});
                  resumeAudioContext();
                  window.removeEventListener("click", onUserTap);
                };
                window.addEventListener("click", onUserTap, { once: true });
              });
            });
        }
      } else {
        setStatusMessage("");
      }

    } catch (err) {
      console.error("Chat request failed:", err);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `⚠️ Error: ${err.message}. Please verify your API Key and backend connection.` }
      ]);
      setIsThinking(false);
      setStatusMessage("");
    }
  };
  sendChatRequestRef.current = sendChatRequest;

  // Save Settings Modal Handler
  const handleSaveSettings = (e) => {
    e.preventDefault();
    localStorage.setItem("shristy_api_key", apiKey);
    localStorage.setItem("shristy_system_prompt", customPrompt);
    localStorage.setItem("shristy_voice", selectedVoice);
    localStorage.setItem("shristy_speech_lang", speechLanguage);
    setIsSettingsOpen(false);
    setTestStatus({ type: "", message: "" });
  };

  // Test Groq API Key connectivity
  const testApiKey = async () => {
    setTestStatus({ type: "loading", message: "Testing connection..." });
    try {
      const response = await fetch(`${BACKEND_URL}/api/settings/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ apiKey: apiKey.trim() ? apiKey : null })
      });
      const data = await response.json();
      if (data.status === "ok") {
        setTestStatus({ type: "success", message: "Success! Groq API is reachable." });
      } else {
        setTestStatus({ type: "error", message: `Failed: ${data.message}` });
      }
    } catch (err) {
      setTestStatus({ type: "error", message: `Network error: ${err.message}` });
    }
  };

  return (
    <div className={`app-container ${persona}`}>
      {/* Invisible HTML5 Audio Tag */}
      <audio 
        ref={audioRef}
        onPlay={() => setIsSpeaking(true)}
        onPause={() => setIsSpeaking(false)}
        onEnded={() => {
          setIsSpeaking(false);
          setStatusMessage("");
        }}
        style={{ display: "none" }}
      />

      {/* Header Bar */}
      <header className="top-header">
        <div className="logo-section">
          <h1>
            <span className="pulse-dot"></span> 
            {persona === "psychiatrist" 
              ? "Dr. Shristy (Psychiatric Doctor)" 
              : (persona === "mentor" ? "Shristy (Coding & ML Mentor)" : "Shristy AI Companion")}
          </h1>
        </div>
        <div className="controls-section">
          <div className="persona-selector-container">
            <select 
              className="persona-select" 
              value={persona} 
              onChange={(e) => handlePersonaChange(e.target.value)}
              title="Change Companion Persona"
            >
              <option value="companion">❤️ Companion Mode</option>
              <option value="psychiatrist">🩺 Emotional Support Mode</option>
              <option value="mentor">💻 Coding/ML Mentor</option>
            </select>
          </div>
          <button 
            className={`icon-btn ${isMuted ? "active" : ""}`} 
            onClick={() => {
              setIsMuted(!isMuted);
              if (!isMuted && audioRef.current) {
                audioRef.current.pause();
                setIsSpeaking(false);
              }
            }}
            title={isMuted ? "Unmute Voice" : "Mute Voice"}
          >
            {isMuted ? "🔇" : "🔊"}
          </button>
          <button 
            className="icon-btn" 
            onClick={handleResetChat}
            title="Start Fresh Chat (Keeps Memories)"
          >
            🔄
          </button>
          <button 
            className="icon-btn" 
            onClick={() => setIsSettingsOpen(true)}
            title="Shristy Settings"
          >
            ⚙️
          </button>
        </div>
      </header>

      {/* Workspace Area */}
      <main className="main-workspace">
        
        {/* Left Side: Avatar and Audio Feedback */}
        <section className="avatar-panel">
          <Avatar 
            isSpeaking={isSpeaking}
            analyserNode={analyserNode}
            audioContext={audioContext}
            persona={persona}
          />
          {statusMessage && (
            <div className="avatar-status-badge">
              <span className={`status-dot ${isListening ? "listening" : isThinking ? "thinking" : isSpeaking ? "speaking" : "idle"}`} />
              <span className="status-text">{statusMessage}</span>
            </div>
          )}
        </section>

        {/* Right Side: Chat Transcript Logs */}
        <section className="chat-panel">
          <div className="chat-history">
            {messages.map((msg, index) => (
              <div 
                key={index} 
                className={`chat-bubble-wrapper ${msg.role}`}
              >
                <span className="chat-bubble-sender">
                  {msg.role === "user" 
                    ? "You" 
                    : (persona === "psychiatrist" 
                      ? "Dr. Shristy" 
                      : (persona === "mentor" ? "Shristy (Mentor)" : "Shristy"))}
                </span>
                <div className="chat-bubble">
                  {msg.content}
                </div>
                {msg.memoriesUsed && msg.memoriesUsed.length > 0 && (
                  <div className="memories-used-tag" title={msg.memoriesUsed.join(", ")}>
                    Recalled past fact
                  </div>
                )}
              </div>
            ))}
            
            {isThinking && (
              <div className="chat-bubble-wrapper assistant">
                <span className="chat-bubble-sender">
                  {persona === "psychiatrist" 
                    ? "Dr. Shristy" 
                    : (persona === "mentor" ? "Shristy (Mentor)" : "Shristy")}
                </span>
                <div className="chat-bubble" style={{ opacity: 0.6 }}>
                  Thinking...
                </div>
              </div>
            )}
            
            <div ref={chatEndRef} />
          </div>

          {/* User Chat Input Container */}
          <div className="chat-input-wrapper">
            {isListening && (
              <div className="listening-indicator-pill">
                <span className="listening-dot"></span>
                <span>Listening... Speak now (or tap ⏹️ to send)</span>
              </div>
            )}
            <form className="chat-input-container" onSubmit={handleSendMessage}>
              <button
                type="button"
                className={`icon-btn mic-btn ${isListening ? "active" : ""}`}
                onClick={toggleListening}
                title={isListening ? "Stop & Send Speech" : "Speak to Shristy (Hands-Free)"}
              >
                {isListening ? "⏹️" : "🎤"}
              </button>
              <div className="input-box-wrapper">
                <textarea
                  ref={textareaRef}
                  className="chat-input"
                  rows={1}
                  placeholder={isListening ? "Listening to your voice... speak now" : "Type your message here or press the mic..."}
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleSendMessage(e);
                    }
                  }}
                />
              </div>
              <button 
                type="submit" 
                className="send-btn" 
                disabled={isThinking || !inputText.trim()}
              >
                ➔
              </button>
            </form>
          </div>
        </section>
      </main>

      {/* Settings configuration Modal */}
      {isSettingsOpen && (
        <div className="modal-overlay">
          <div className="modal-content">
            <h2>
              Companion Settings
              <button 
                className="close-modal-btn" 
                onClick={() => {
                  setIsSettingsOpen(false);
                  setTestStatus({ type: "", message: "" });
                }}
              >
                ×
              </button>
            </h2>

            <form onSubmit={handleSaveSettings}>
              {/* API Key */}
              <div className="form-group">
                <label>Groq API Key</label>
                <input 
                  type="password" 
                  placeholder="paste your gsk_... key from console.groq.com" 
                  value={apiKey} 
                  onChange={(e) => setApiKey(e.target.value)}
                />
                <button 
                  type="button" 
                  className="test-connection-btn" 
                  onClick={testApiKey}
                >
                  Test Connection
                </button>
                {testStatus.message && (
                  <div className={`help-text ${testStatus.type === "success" ? "success" : "error"}`} style={{ 
                    color: testStatus.type === "success" ? "#2ecc71" : testStatus.type === "error" ? "#ff4081" : "#8e8eaf",
                    fontWeight: "500"
                  }}>
                    {testStatus.message}
                  </div>
                )}
                <span className="help-text">
                  Note: If empty, the backend will fallback to the key in <code>backend/.env</code>.
                </span>
              </div>

              {/* Voice Selection */}
              <div className="form-group">
                <label>Companion Voice</label>
                <select 
                  value={selectedVoice} 
                  onChange={(e) => setSelectedVoice(e.target.value)}
                >
                  {voices.map((v) => (
                    <option key={v.ShortName} value={v.ShortName}>
                      {v.FriendlyName} ({v.Gender}, {v.Locale})
                    </option>
                  ))}
                </select>
                <span className="help-text">
                  Microsoft Edge voices are free and require no account. en-US and en-IN voices work best.
                </span>
              </div>

              {/* Speech Recognition Input Language */}
              <div className="form-group">
                <label>Microphone Language (Voice Input)</label>
                <select 
                  value={speechLanguage} 
                  onChange={(e) => setSpeechLanguage(e.target.value)}
                >
                  <option value="en-IN">English (India) - Recommended</option>
                  <option value="en-US">English (US)</option>
                  <option value="hi-IN">Hindi (हिंदी)</option>
                </select>
                <span className="help-text">
                  Interprets your voice in English so your speech is never converted to Hindi text or Devanagari script.
                </span>
              </div>

              {/* Custom Persona */}
              <div className="form-group">
                <label>System Prompt (Personality)</label>
                <textarea 
                  rows="4" 
                  placeholder="Define Shristy's tone, traits, and backstory..."
                  value={customPrompt} 
                  onChange={(e) => setCustomPrompt(e.target.value)}
                />
                <span className="help-text">
                  Leave blank to use the default warm & conversational Shristy companion personality.
                </span>
              </div>

              {/* Memory Lock */}
              <div className="form-group">
                <label>Shristy's Long-Term Memories ({memories.length})</label>
                <div className="memory-list-container">
                  {memories.length === 0 ? (
                    <div className="help-text" style={{ padding: "6px" }}>Shristy has no memories stored yet. Talk to her to create some!</div>
                  ) : (
                    memories.map((m, idx) => {
                      const text = typeof m === "object" ? (m.text || m.fact) : m;
                      const id = typeof m === "object" ? m.id : m;
                      const category = typeof m === "object" && m.category ? m.category : null;
                      return (
                        <div key={id || idx} className="memory-item" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <span style={{ flex: 1, paddingRight: "8px" }}>
                            {category && (
                              <span style={{ 
                                fontSize: "10px", 
                                textTransform: "uppercase", 
                                letterSpacing: "0.5px",
                                padding: "2px 6px", 
                                borderRadius: "4px", 
                                background: "rgba(255, 255, 255, 0.12)", 
                                marginRight: "6px",
                                color: "#a5b4fc"
                              }}>
                                {category}
                              </span>
                            )}
                            {text}
                          </span>
                          <button 
                            type="button" 
                            onClick={() => deleteMemory(id)}
                            style={{ 
                              background: "transparent", 
                              border: "none", 
                              color: "#ff5252", 
                              cursor: "pointer", 
                              fontSize: "16px",
                              padding: "0 4px",
                              lineHeight: "1"
                            }}
                            title="Delete this memory"
                          >
                            ×
                          </button>
                        </div>
                      );
                    })
                  )}
                </div>
                {memories.length > 0 && (
                  <button 
                    type="button" 
                    className="clear-memories-btn" 
                    onClick={clearMemories}
                  >
                    Clear All Memories
                  </button>
                )}
              </div>

              <button type="submit" className="save-settings-btn">
                Apply & Save Settings
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
