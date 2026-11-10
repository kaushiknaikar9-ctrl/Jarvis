import os
import asyncio
import sys
import subprocess
import threading
import queue
import webbrowser
import random
from datetime import datetime
import socket
import json
import time

# Third-party imports
import speech_recognition as sr
import pywhatkit
import pyttsx3
from flask import Flask, request, jsonify, Response, stream_with_context, send_from_directory
from flask_cors import CORS
import requests

# Optional: Google Cloud TTS
try:
    from google.cloud import texttospeech
    GOOGLE_CLOUD_TTS_AVAILABLE = True
except ImportError:
    GOOGLE_CLOUD_TTS_AVAILABLE = False
    texttospeech = None

# Neural Network Engine
try:
    from llama_cpp import Llama
except ImportError:
    Llama = None

# Arete-19B Enhanced Reasoning Engine
try:
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from accelerate import Accelerator
    import torch
    ARETE_AVAILABLE = True
    print("[System] Arete-19B model integration available")
except ImportError:
    ARETE_AVAILABLE = False

# Project-specific modules
import updater
from api_manager import APIManager
from web_research import researcher

# Initialize API Manager
api_manager = APIManager()

# --- SYSTEM CONFIGURATION ---
CURRENT_VERSION = "3.4.0"  # Cloud-ready with Google Cloud TTS
SENSORS_ACTIVE = True
SYSTEM_STATUS = "OPTIMAL"
INTERNET_ACCESS = True
AWAITING_PASSWORD = False
SECRET_PASSWORD = "stark"

# Detect cloud deployment
CLOUD_DEPLOYMENT = os.environ.get("CLOUD_DEPLOYMENT", "false").lower() == "true"
GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "")

# Cloud API Configuration - Google Gemini (REST API)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AQ.Ab8RN6Lni8wdY71kQyjG56GPv4LIopB9ja5jaBZR3Rn80Sv3FQ")
GEMINI_MODEL = "gemini-flash-lite-latest"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
print(f"[System] Gemini REST API configured ({GEMINI_MODEL}).")
print(f"[System] Cloud deployment: {CLOUD_DEPLOYMENT}")

def call_gemini(prompt):
    """Call Gemini via REST API (faster, more reliable than SDK)."""
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY
    }
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        resp = requests.post(GEMINI_URL, headers=headers, json=data, timeout=30)
        if resp.status_code == 200:
            result = resp.json()
            candidates = result.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
        print(f"[Gemini Error] {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[Gemini Error] {e}")
    return None

if sys.platform == 'win32':
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

app = Flask(__name__)
CORS(app)

# --- CLOUD COGNITIVE ENGINE ---
llm_cache = {"instance": None}

def get_local_llm():
    """Lazy-loader for the LLM to ensure the system starts regardless of model status."""
    if llm_cache["instance"] is None:
        try:
            if Llama:
                print("[System] Initializing Neural Network Core...")
                # DISABLED for cooling - use cloud Gemini only
                # llm_cache["instance"] = Llama(
                #     model_path="C:/Users/kaushik/Downloads/Nemotron-3.5-Bolt-E4B-Q4_K_M.gguf",
                #     n_ctx=2048,
                #     n_gpu_layers=-1
                # )
                # print("[System] Neural Network Online.")
                print("[System] Cooling down — using cloud Gemini only")
            else:
                print("[Error] llama-cpp-python not found.")
        except Exception as e:
            print(f"[Error] Critical failure loading model: {e}")
    return llm_cache["instance"]

# --- TTS ENGINE (Hybrid: Local pyttsx3 + Google Cloud TTS) ---
class TTSEngine:
    """Unified TTS engine supporting both local (pyttsx3/SAPI5) and cloud (Google Cloud TTS)."""

    def __init__(self):
        self.local_engine = None
        self.cloud_client = None
        self.voices = []
        self.current_voice_id = None
        self._init_engines()

    def _init_engines(self):
        """Initialize available TTS engines."""
        # Try Google Cloud TTS first (for cloud deployment)
        if CLOUD_DEPLOYMENT and GOOGLE_CLOUD_TTS_AVAILABLE and GOOGLE_CLOUD_PROJECT:
            try:
                self.cloud_client = texttospeech.TextToSpeechClient()
                print("[TTS] Google Cloud TTS initialized.")
                self._load_cloud_voices()
            except Exception as e:
                print(f"[TTS] Google Cloud TTS init failed: {e}")
                self.cloud_client = None

        # Fallback to local pyttsx3 (for local development)
        if not self.cloud_client:
            self._init_local_engine()

    def _init_local_engine(self):
        """Initialize local pyttsx3 engine (Windows SAPI5)."""
        try:
            print("[TTS] Initializing pyttsx3 (SAPI5)...")
            self.local_engine = pyttsx3.init('sapi5')
            voices = self.local_engine.getProperty('voices')

            for i, v in enumerate(voices):
                print(f"[TTS] Local Voice {i}: {v.name} (id: {v.id})")

            # Select male voice (David/Mark) for JARVIS
            target_voice = voices[0].id
            for v in voices:
                if "David" in v.name or "Male" in v.name or "Mark" in v.name:
                    target_voice = v.id
                    print(f"[TTS] Selected optimal local voice: {v.name}")
                    break

            self.local_engine.setProperty('voice', target_voice)
            self.local_engine.setProperty('rate', 145)
            self.local_engine.setProperty('volume', 1.0)
            self.current_voice_id = target_voice
            print("[TTS] Local engine ready.")

            # Test beep
            try:
                import winsound
                winsound.Beep(880, 150)
                print("[TTS] Audio test beep played.")
            except:
                pass

            # Store voice list for API
            self.voices = [
                {"id": v.id, "name": v.name, "languages": getattr(v, 'languages', []), "source": "local"}
                for v in voices
            ]
        except Exception as e:
            print(f"[TTS] Local engine init failed: {e}")

    def _load_cloud_voices(self):
        """Load available Google Cloud TTS voices."""
        try:
            # List voices from Google Cloud
            response = self.cloud_client.list_voices()
            self.voices = []
            for voice in response.voices:
                for lang in voice.language_codes:
                    self.voices.append({
                        "id": voice.name,
                        "name": f"{voice.name} ({lang})",
                        "languages": [lang],
                        "source": "cloud",
                        "gender": voice.ssml_gender.name,
                        "natural_sample_rate_hertz": voice.natural_sample_rate_hertz
                    })
            print(f"[TTS] Loaded {len(self.voices)} Google Cloud voices.")

            # Select a good default (Neural2 or WaveNet male voice)
            preferred = [
                "en-US-Neural2-J", "en-US-Neural2-D",  # Male Neural2
                "en-US-Wavenet-D", "en-US-Wavenet-B",   # Male WaveNet
                "en-US-Standard-B", "en-US-Standard-D"  # Male Standard
            ]
            for pref in preferred:
                for v in self.voices:
                    if pref in v["id"]:
                        self.current_voice_id = v["id"]
                        print(f"[TTS] Selected cloud voice: {v['name']}")
                        return

            # Fallback to first voice
            if self.voices:
                self.current_voice_id = self.voices[0]["id"]
                print(f"[TTS] Using fallback cloud voice: {self.voices[0]['name']}")

        except Exception as e:
            print(f"[TTS] Failed to load cloud voices: {e}")
            self.voices = []

    def speak(self, text):
        """Speak text using the best available engine."""
        print(f"[Speak] {text[:100]}{'...' if len(text) > 100 else ''}")

        if self.cloud_client and self.current_voice_id:
            self._speak_cloud(text)
        elif self.local_engine:
            self._speak_local(text)
        else:
            print("[TTS] No TTS engine available!")

    def _speak_cloud(self, text):
        """Speak using Google Cloud TTS."""
        try:
            # Configure synthesis input
            synthesis_input = texttospeech.SynthesisInput(text=text)

            # Configure voice
            voice = texttospeech.VoiceSelectionParams(
                name=self.current_voice_id,
                language_code="en-US"
            )

            # Configure audio
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=1.0,
                pitch=0.0,
                volume_gain_db=0.0
            )

            # Synthesize
            response = self.cloud_client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config
            )

            # Save and play audio (in cloud, we return audio to client)
            # For local testing, play via system
            if not CLOUD_DEPLOYMENT:
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                    f.write(response.audio_content)
                    temp_path = f.name

                # Play based on platform
                if sys.platform == 'win32':
                    os.startfile(temp_path)
                elif sys.platform == 'darwin':
                    subprocess.run(['afplay', temp_path])
                else:
                    subprocess.run(['mpg123', '-q', temp_path])

                # Cleanup after a delay
                threading.Timer(5.0, lambda: os.unlink(temp_path) if os.path.exists(temp_path) else None).start()
            else:
                # In cloud deployment, audio is returned via API
                pass

            print(f"[TTS] Cloud synthesis complete ({len(response.audio_content)} bytes)")

        except Exception as e:
            print(f"[TTS] Cloud synthesis error: {e}")
            # Fallback to local
            if self.local_engine:
                self._speak_local(text)

    def _speak_local(self, text):
        """Speak using local pyttsx3 engine."""
        try:
            self.local_engine.say(text)
            self.local_engine.runAndWait()
            time.sleep(0.1)
        except Exception as e:
            print(f"[TTS] Local speak error: {e}")

    def set_voice(self, voice_id):
        """Change the active voice."""
        print(f"[TTS] Changing voice to: {voice_id}")
        self.current_voice_id = voice_id

        if self.local_engine:
            try:
                self.local_engine.setProperty('voice', voice_id)
                self.local_engine.say("Voice changed, sir.")
                self.local_engine.runAndWait()
            except Exception as e:
                print(f"[TTS] Local voice change failed: {e}")

    def get_voices(self):
        """Return list of available voices."""
        return self.voices

    def synthesize_for_client(self, text):
        """Synthesize speech and return audio data for client playback (cloud mode)."""
        if not self.cloud_client or not self.current_voice_id:
            return None

        try:
            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice = texttospeech.VoiceSelectionParams(
                name=self.current_voice_id,
                language_code="en-US"
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=1.0
            )
            response = self.cloud_client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config
            )
            return response.audio_content
        except Exception as e:
            print(f"[TTS] Client synthesis error: {e}")
            return None

# Initialize TTS engine
tts_engine = TTSEngine()

def speak(text):
    """Queue text for speech synthesis."""
    # Log immediately
    print(f"[Speak Queue] Added: {text}")
    # For now, speak directly (thread-safe for cloud)
    # In production, could use a queue
    tts_engine.speak(text)

# --- Cloud Configuration ---
import os

def get_model_cache_dir():
    """Get model cache directory from environment or default."""
    return os.environ.get("MODEL_CACHE_DIR", "/app/models")

def is_cloud_deployment():
    """Check if running in cloud deployment."""
    return os.environ.get("CLOUD_DEPLOYMENT", "false").lower() == "true"

# --- ARETE-19B REASONING ENGINE ---
arete_model = None
arete_tokenizer = None

def load_arete_model():
    """Lazy-load the Arete-19B reasoning model on startup."""
    global arete_model, arete_tokenizer
    model_cache = get_model_cache_dir()

    # Check for local model in cloud cache (from Drive)
    snapshot_path = os.path.join(
        model_cache,
        "models--NousResearch--Arete-27B",
        "snapshots",
        "108f0afbdcfaa1ceeda4a635004304dfff6d4da2"
    )

    try:
        print(f"[System] Loading Arete-19B from: {snapshot_path}")

        if os.path.exists(snapshot_path) and os.path.exists(os.path.join(snapshot_path, "config.json")):
            print("[System] Using locally cached Arete-19B model")
            arete_tokenizer = AutoTokenizer.from_pretrained(
                snapshot_path, trust_remote_code=True, local_files_only=True
            )
            arete_model = AutoModelForCausalLM.from_pretrained(
                snapshot_path, device_map="auto", torch_dtype=torch.bfloat16,
                trust_remote_code=True, local_files_only=True
            )
        else:
            print("[System] Arete-19B not found locally, attempting download...")
            arete_tokenizer = AutoTokenizer.from_pretrained("NousResearch/Arete-19B", trust_remote_code=True)
            arete_model = AutoModelForCausalLM.from_pretrained(
                "NousResearch/Arete-19B", device_map="auto", torch_dtype=torch.bfloat16,
                trust_remote_code=True
            )

        print("[System] Arete-19B Neural Network Online.")
        return True
    except Exception as e:
        print(f"[Error] Arete-19B failed to load: {e}")
        return False

def generate_with_arete(query, system_prompt=""):
    """Generate a response using Arete-19B for enhanced reasoning."""
    if arete_model is None or arete_tokenizer is None:
        load_arete_model()
    if arete_model is None:
        return None

    full_prompt = f"{system_prompt}\n\n{query}" if system_prompt else query
    inputs = arete_tokenizer(full_prompt, return_tensors="pt").to(arete_model.device)

    with torch.no_grad():
        outputs = arete_model.generate(
            inputs.input_ids,
            max_new_tokens=200,
            temperature=0.7,
            top_p=0.9,
            pad_token_id=arete_tokenizer.eos_token_id
        )

    response = arete_tokenizer.decode(outputs[0][:, inputs.input_ids.shape[1]:], skip_special_tokens=True)
    return response.strip()

def is_complex_query(query):
    """Determine if a query requires Arete-19B enhanced reasoning."""
    complex_keywords = [
        "explain", "analyze", "solve", "calculate", "debug",
        "architecture", "logic", "reasoning", "complex", "technical",
        "compare", "evaluate", "determine", "assess", "derive",
        "explain how", "how does", "why does", "what is the rationale"
    ]
    lower = query.lower()
    return any(kw in lower for kw in complex_keywords)

# --- SPEECH RECOGNITION (Local only) ---
def listen():
    """High-fidelity sonic capture with extreme sensitivity."""
    print("[Microphone] Attempting to access microphone...")
    try:
        r = sr.Recognizer()
        r.dynamic_energy_threshold = False
        r.energy_threshold = 30

        with sr.Microphone() as source:
            print("[Microphone] Adjusting for ambient noise...")
            r.adjust_for_ambient_noise(source, duration=0.05)
            r.pause_threshold = 0.5
            r.non_speaking_duration = 0.5

            try:
                audio = r.listen(source, timeout=3, phrase_time_limit=5)
            except sr.WaitTimeoutError:
                print("[Microphone] Listening timed out.")
                return 'none'

        try:
            query = r.recognize_google(audio, language='en-US')
            print(f"User said: {query}")
            return query.lower()
        except sr.UnknownValueError:
            print("[Microphone] Could not understand audio.")
            return 'none'
        except sr.RequestError as e:
            print(f'[Microphone] API Error: {e}')
            return 'none'
    except Exception as e:
        import traceback
        print(f'[Microphone] CRITICAL SYSTEM ERROR: {e}')
        traceback.print_exc()
        return 'pyaudio_error'

# --- ROUTES ---

@app.route('/command', methods=['POST'])
def handle_command():
    """Handle voice command from local client (uses local microphone)."""
    print("\n[Server] Request received!")
    try:
        data = request.json
        action = data.get("action")
        print(f"[Server] Action requested: {action}")

        if action == "listen":
            # Only works locally (requires microphone)
            if CLOUD_DEPLOYMENT:
                return jsonify({
                    "status": "error",
                    "message": "Voice input not available in cloud mode. Use /brain endpoint with text input."
                }), 400

            query = listen()
            if query == "none":
                speak("I'm sorry sir, I didn't catch that. Could you repeat?")
                return jsonify({"status": "error", "message": "Could not hear you"})
            if query == "pyaudio_error":
                speak("Sir, I'm having trouble accessing the microphone hardware.")
                return jsonify({"status": "error", "message": "Microphone hardware error"})

            is_ai = True
            response_text = ""
            query_lower = query.lower().strip()
            intents = {
                "open": handle_open,
                "close": handle_close,
                "wifi": handle_wifi,
                "update": handle_update,
                "youtube": handle_youtube,
                "time": handle_time,
                "hello": handle_greeting,
                "exit": handle_exit,
                "status": handle_status
            }

            for key, handler in intents.items():
                if key in query_lower:
                    if any(q_word in query_lower for q_word in ["who", "what", "where", "when", "why", "how"]):
                        continue
                    if key in ["open", "update", "youtube"] and not INTERNET_ACCESS:
                        response_text = "I am sorry sir, but internet access is currently disabled."
                        is_ai = False
                    else:
                        response_text = handler(query)
                        is_ai = False
                    break

            api_response = api_manager.handle_api_request(query_lower)
            if api_response:
                speak(api_response)
                return jsonify({"status": "success", "query": query, "response": api_response, "streaming": False})

            if not is_ai:
                speak(response_text)
                return jsonify({"status": "success", "query": query, "response": response_text, "streaming": False})

            return Response(stream_with_context(generate_ai_stream(query, speak_on_laptop=True)), mimetype='text/event-stream')
    except Exception as e:
        print(f"[Server Error] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/brain', methods=['POST'])
def handle_brain():
    """Handle text query from any client (local or cloud)."""
    try:
        data = request.json or {}
        query = (data.get("query") or "").strip()
        if not query:
            return jsonify({"status": "error", "message": "Empty query"}), 400

        # speak_on_laptop: only applies to local deployment
        speak_on_laptop = bool(data.get("speak_on_laptop", True)) and not CLOUD_DEPLOYMENT

        # For cloud: return audio data for client to play
        return Response(stream_with_context(generate_ai_stream(query, speak_on_laptop)), mimetype='text/event-stream')
    except Exception as e:
        print(f"[Brain Error] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/tts', methods=['POST'])
def handle_tts():
    """Synthesize speech for client playback (cloud mode)."""
    try:
        data = request.json or {}
        text = (data.get("text") or "").strip()
        if not text:
            return jsonify({"status": "error", "message": "Empty text"}), 400

        if not CLOUD_DEPLOYMENT:
            # Local mode: just speak locally
            speak(text)
            return jsonify({"status": "success", "message": "Spoken locally"})

        # Cloud mode: return audio data
        audio_content = tts_engine.synthesize_for_client(text)
        if audio_content:
            import base64
            return jsonify({
                "status": "success",
                "audio": base64.b64encode(audio_content).decode('utf-8'),
                "format": "mp3"
            })
        else:
            return jsonify({"status": "error", "message": "TTS synthesis failed"}), 500
    except Exception as e:
        print(f"[TTS Error] {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


def generate_ai_stream(query, speak_on_laptop=True):
    """Generate AI response with streaming and Arete-19B enhanced reasoning."""
    def _say(text):
        if speak_on_laptop:
            speak(text)

    print(f"Processing request: {query}...")
    try:
        is_factual = any(word in query.lower() for word in ["what is", "who is", "where is", "how to", "current", "price of", "tell me about"])

        web_context = ""
        if is_factual:
            _say("Searching the archives for you, sir.")
            search_query = query.replace("jarvis", "").strip()
            web_data = researcher.fast_search(search_query)
            web_context = f" [Web Data: {web_data}] "
            print(f"Web context retrieved: {web_data[:50]}...")

        system_prompt = ("You are JARVIS, the sophisticated AI from Iron Man. "
                         "Use the provided Web Data to answer accurately, but keep your tone "
                         "loyal, professional, and slightly sarcastic. Be concise. "
                         "Refer to the user as 'sir'. If no web data is provided, use your own knowledge.")

        full_prompt = f"{system_prompt}\n\n{web_context} {query}"

        # Smart model selection: use Arete-19B for complex reasoning queries
        use_arete = is_complex_query(query)

        full_response = ""
        if use_arete:
            print("[System] Complex query detected - using Arete-19B for enhanced reasoning")
            arete_response = generate_with_arete(query, system_prompt)
            if arete_response and len(arete_response.strip()) > 10:
                full_response = arete_response
                print(f"[Arete-19B Response] {full_response[:100]}...")
            else:
                print("[System] Arete-19B returned insufficient response, falling back to Gemini")
        else:
            print("[System] Using Gemini API for general query")

        # Get response from selected model
        if full_response == "":
            response_text = call_gemini(full_prompt)
        else:
            response_text = full_response

        if response_text:
            full_response = response_text
        else:
            print("[System] Gemini API is overloaded — using fallback is disabled during cooling phase.")
            # FALLBACK DISABLED: let user know cloud services are overloaded
            fallback = "The cloud brain is experiencing high load, sir. Please try again shortly."
            _say(fallback)
            yield f"data: {json.dumps({'token': fallback})}\n\n"

        if full_response.strip():
            words = full_response.split()
            for i, word in enumerate(words):
                token = word + (" " if i < len(words) - 1 else "")
                yield f"data: {json.dumps({'token': token})}\n\n"
            _say(full_response)
        else:
            fallback = "I've processed the data, sir, but produced no output."
            _say(fallback)
            yield f"data: {json.dumps({'token': fallback})}\n\n"

    except Exception as e:
        print(f"System Error: {e}")
        error_msg = "A glitch occurred in my processing unit, sir."
        _say(error_msg)
        yield f"data: {json.dumps({'token': error_msg})}\n\n"


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def static_file(path):
    if path.endswith(('.css', '.js', '.jpg', '.png', '.json', '.mp3', '.wav')):
        return send_from_directory('.', path)
    return "Forbidden", 403


@app.route('/status', methods=['GET'])
def handle_status():
    return jsonify({
        "status": "online",
        "version": CURRENT_VERSION,
        "local_llm": llm_cache["instance"] is not None,
        "gemini": True,
        "arete_19b": arete_model is not None if ARETE_AVAILABLE else False,
        "arete_available": ARETE_AVAILABLE,
        "system": SYSTEM_STATUS,
        "cloud_deployment": CLOUD_DEPLOYMENT,
        "tts_engine": "google-cloud" if (CLOUD_DEPLOYMENT and tts_engine.cloud_client) else "local"
    })


@app.route('/voices', methods=['GET'])
def handle_voices():
    """List available TTS voices."""
    voices = tts_engine.get_voices()
    return jsonify({"voices": voices})


@app.route('/set-voice', methods=['POST'])
def handle_set_voice():
    """Change the active TTS voice."""
    data = request.json or {}
    voice_id = data.get('voice_id')
    if not voice_id:
        return jsonify({"status": "error", "message": "voice_id required"}), 400
    tts_engine.set_voice(voice_id)
    return jsonify({"status": "success", "message": f"Voice changed to: {voice_id}"})


# --- HANDLER FUNCTIONS ---

def handle_open(query):
    target = query.replace("open", "").strip()
    if any(ext in target for ext in [".com", ".in", ".org", ".net", "http"]) or "google" in target:
        url = target if target.startswith("http") else f"https://www.google.com/search?q={target}"
        webbrowser.open(url)
        return f"Accessing the global network for {target}, sir. Seamlessly delivered."
    subprocess.Popen(f"start shell:AppsFolder\\{target}", shell=True)
    subprocess.Popen(f"start {target}", shell=True)
    return f"Initializing {target}. System access granted."

def handle_close(query):
    target = query.replace("close", "").replace("kill", "").strip()
    os.system(f"taskkill /f /im {target}.exe")
    return f"Terminating {target} process. System cleaned, sir."

def handle_wifi(query):
    try:
        result = subprocess.check_output("netsh interface show interface", shell=True).decode()
        if "Wi-Fi" in result and "Connected" in result:
            return "Wireless connection is stable and operating at peak efficiency, sir."
        return "Wireless interface is active, but no network connection detected."
    except:
        return "I encountered a glitch checking the network status, sir."

def handle_update(query):
    speak("Scanning encrypted servers for updates, sir.")
    latest = updater.check_for_updates(CURRENT_VERSION)
    if latest:
        speak(f"Version {latest} detected. Overwriting legacy code.")
        if updater.apply_updates(["backend.py", "main.js", "script.js", "styles.css"]):
            speak("System evolved. Rebooting.")
            updater.restart_jarvis()
        return "Update synchronization failed."
    return "All systems are current. No updates found in the archives."

def handle_youtube(query):
    video = query.replace("play", "").replace("on youtube", "").replace("youtube", "").strip()
    pywhatkit.playonyt(video)
    return f"Searching YouTube archives for {video}. Enjoy the data stream, sir."

def handle_time(query):
    return f"The current temporal coordinate is {datetime.now().strftime('%H:%M')}, sir."

def handle_greeting(query):
    return random.choice([
        "Hello sir. All systems are nominal. I am ready for your command.",
        "Systems at 100%. I was just optimizing your background processes, sir.",
        "At your service, sir. The HUD is online and synchronized."
    ])

def handle_exit(query):
    return "Shutting down all systems. Powering off the Arc Reactor. Goodbye, sir."

def handle_status(query):
    return f"Current Status: {SYSTEM_STATUS}. Core Temperature: Nominal. Security: Encrypted."


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


if __name__ == "__main__":
    local_ip = get_local_ip()
    print(f"JARVIS NEURAL NETWORK v{CURRENT_VERSION} Online | http://127.0.0.1:5000")
    print(f"JARVIS NEURAL NETWORK v{CURRENT_VERSION} ONLINE FOR MOBILE | http://{local_ip}:5000")
    print(f"Cloud mode: {CLOUD_DEPLOYMENT}")

    def startup_arete():
        """Load Arete-19B model in background thread to avoid blocking startup."""
        if ARETE_AVAILABLE:
            load_arete_model()
        else:
            print("[System] Arete-19B not available - using cloud Gemini only")

    def startup_intro():
        import time
        time.sleep(3)
        full_intro = (
            "Systems online. I am JARVIS, your personal AI assistant. "
            "My core is synchronized and I am ready to assist you, sir."
        )
        print(f"Intro: {full_intro}")
        speak(full_intro)

    threading.Thread(target=startup_arete, daemon=True).start()
    threading.Thread(target=startup_intro, daemon=True).start()

    try:
        port = int(os.environ.get("PORT", 5000))
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, threaded=True)
    except Exception as e:
        print(f"[Critical] Flask Server Crash: {e}")