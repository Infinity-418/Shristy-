import os
import uuid
import re
import edge_tts

def detect_language(text: str) -> str:
    # Check for Devanagari script (Hindi, Marathi, Nepali, Sanskrit)
    if re.search(r'[\u0900-\u097F]', text):
        return "hi"
    # Check for Bengali / Assamese
    if re.search(r'[\u0980-\u09FF]', text):
        return "bn"
    # Check for Tamil
    if re.search(r'[\u0B80-\u0BFF]', text):
        return "ta"
    # Check for Telugu
    if re.search(r'[\u0C00-\u0C7F]', text):
        return "te"
    # Check for Arabic / Urdu
    if re.search(r'[\u0600-\u06FF]', text):
        return "ur"
    # Check for Romanized Hindi / Hinglish keywords
    hinglish_markers = {
        "haan", "nahi", "kya", "kaise", "kyun", "accha", "theek", "bhai", "mera", 
        "meri", "hum", "aap", "tum", "samajh", "batao", "karo", "raha", "rahi",
        "hoga", "hogi", "bhi", "bahut", "yaar", "kuch", "shukriya", "dhanyawad"
    }
    words = set(re.findall(r'\b[a-z]+\b', text.lower()))
    if len(words.intersection(hinglish_markers)) >= 2:
        return "hinglish"
    return "en"

class TTSManager:
    def __init__(self, output_dir="static/audio"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        # Default voice (US female voice)
        self.default_voice = "en-US-AvaNeural"

    async def get_voices(self):
        try:
            # Get list of voices
            voices = await edge_tts.VoicesManager.create()
            # Sort voices for presentation
            voice_list = voices.voices
            return sorted(
                [
                    {
                        "Name": v["Name"],
                        "ShortName": v["ShortName"],
                        "Gender": v["Gender"],
                        "Locale": v["Locale"],
                        "FriendlyName": v.get("FriendlyName", v["ShortName"])
                    }
                    for v in voice_list
                ],
                key=lambda x: x["ShortName"]
            )
        except Exception as e:
            print(f"Error listing voices: {e}")
            # Fallback static list of common voices if API fails
            return [
                {"Name": "en-US-AvaNeural", "ShortName": "en-US-AvaNeural", "Gender": "Female", "Locale": "en-US", "FriendlyName": "Microsoft Ava (US)"},
                {"Name": "en-US-EmmaNeural", "ShortName": "en-US-EmmaNeural", "Gender": "Female", "Locale": "en-US", "FriendlyName": "Microsoft Emma (US)"},
                {"Name": "en-US-BrianNeural", "ShortName": "en-US-BrianNeural", "Gender": "Male", "Locale": "en-US", "FriendlyName": "Microsoft Brian (US)"},
                {"Name": "hi-IN-SwaraNeural", "ShortName": "hi-IN-SwaraNeural", "Gender": "Female", "Locale": "hi-IN", "FriendlyName": "Microsoft Swara (Hindi)"},
                {"Name": "hi-IN-MadhurNeural", "ShortName": "hi-IN-MadhurNeural", "Gender": "Male", "Locale": "hi-IN", "FriendlyName": "Microsoft Madhur (Hindi)"},
                {"Name": "en-IN-NeerjaNeural", "ShortName": "en-IN-NeerjaNeural", "Gender": "Female", "Locale": "en-IN", "FriendlyName": "Microsoft Neerja (India/Hinglish)"},
                {"Name": "en-IN-PrabhatNeural", "ShortName": "en-IN-PrabhatNeural", "Gender": "Male", "Locale": "en-IN", "FriendlyName": "Microsoft Prabhat (India)"},
                {"Name": "en-GB-SoniaNeural", "ShortName": "en-GB-SoniaNeural", "Gender": "Female", "Locale": "en-GB", "FriendlyName": "Microsoft Sonia (UK)"}
            ]

    async def generate_speech(self, text: str, voice: str = None) -> str:
        if not text:
            raise ValueError("Text cannot be empty")
        
        # Clean up text to avoid formatting issues
        cleaned_text = text.replace("**", "").replace("*", "").replace("`", "").replace("#", "")
        
        voice_to_use = voice if voice else self.default_voice
        lang = detect_language(cleaned_text)

        # Automatically select the best neural voice for the detected language
        if lang == "hi":
            # Devanagari Hindi text requires a Hindi neural voice
            if not voice_to_use.startswith("hi-"):
                voice_to_use = "hi-IN-SwaraNeural"
        elif lang == "hinglish":
            # Indian English voice pronounces Romanized Hindi (Hinglish) with native clarity
            if voice_to_use.startswith("en-US-") or voice_to_use.startswith("en-GB-"):
                voice_to_use = "en-IN-NeerjaNeural"
        elif lang == "bn" and not voice_to_use.startswith("bn-"):
            voice_to_use = "bn-IN-TanishaaNeural"
        elif lang == "ta" and not voice_to_use.startswith("ta-"):
            voice_to_use = "ta-IN-PallaviNeural"
        elif lang == "te" and not voice_to_use.startswith("te-"):
            voice_to_use = "te-IN-ShrutiNeural"
        elif lang == "ur" and not voice_to_use.startswith("ur-"):
            voice_to_use = "ur-PK-UzmaNeural"

        filename = f"{uuid.uuid4().hex}.mp3"
        filepath = os.path.join(self.output_dir, filename)
        
        try:
            communicate = edge_tts.Communicate(cleaned_text, voice_to_use)
            await communicate.save(filepath)
        except Exception as e:
            print(f"TTS with voice {voice_to_use} failed ({e}), falling back...")
            fallback_voice = "hi-IN-SwaraNeural" if lang == "hi" else self.default_voice
            communicate = edge_tts.Communicate(cleaned_text, fallback_voice)
            await communicate.save(filepath)
        
        return filename
