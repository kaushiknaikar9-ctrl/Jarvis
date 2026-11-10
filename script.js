// Window Control Function
function windowControl(action) {
    try {
        const { ipcRenderer } = require('electron');
        ipcRenderer.send('window-control', action);
    } catch (e) {
        console.error("Electron IPC error:", e);
    }
}

// --- CONFIGURATION ---
const CONFIG = {
    // Cloud backend URL (set after deployment, can be overridden via localStorage)
    CLOUD_BACKEND_URL: localStorage.getItem('jarvis_cloud_url') || '',

    // Local backend (default)
    LOCAL_BACKEND_URL: 'http://127.0.0.1:5000',

    // Auto-detect cloud vs local
    AUTO_DETECT: true
};

// --- DYNAMIC BACKEND URL ---
function getBackendUrl() {
    // If cloud URL is configured and we're not on localhost, use cloud
    if (CONFIG.CLOUD_BACKEND_URL && CONFIG.AUTO_DETECT) {
        const isLocalhost = window.location.hostname === 'localhost' ||
                           window.location.hostname === '127.0.0.1' ||
                           window.location.hostname === '';
        if (!isLocalhost) {
            return CONFIG.CLOUD_BACKEND_URL;
        }
    }

    // Check if manually set to cloud mode
    if (localStorage.getItem('jarvis_use_cloud') === 'true' && CONFIG.CLOUD_BACKEND_URL) {
        return CONFIG.CLOUD_BACKEND_URL;
    }

    // Default to local
    const host = window.location.hostname || '127.0.0.1';
    const port = window.location.port || '5000';
    return `http://${host}:${port}`;
}

function setCloudMode(enabled) {
    localStorage.setItem('jarvis_use_cloud', enabled ? 'true' : 'false');
    updateBackendIndicator();
}

function isCloudMode() {
    const url = getBackendUrl();
    return url !== CONFIG.LOCAL_BACKEND_URL && url.startsWith('https://');
}

function updateBackendIndicator() {
    const indicator = document.getElementById('backend-indicator');
    if (indicator) {
        const isCloud = isCloudMode();
        indicator.textContent = isCloud ? '☁️ CLOUD' : '💻 LOCAL';
        indicator.className = 'backend-indicator ' + (isCloud ? 'cloud' : 'local');
    }
}

// --- STARTUP SEQUENCE ---
async function runStartupSequence() {
    const overlay = document.getElementById('startup-overlay');
    const progressBar = document.getElementById('startup-progress-bar');
    const statusEl = document.getElementById('startup-status');
    const mainHud = document.getElementById('main-hud');

    const steps = [
        { progress: 25, status: 'Loading...', delay: 200 },
        { progress: 50, status: 'Initializing...', delay: 200 },
        { progress: 100, status: 'Systems online', delay: 100 }
    ];

    for (const step of steps) {
        progressBar.style.width = `${step.progress}%`;
        statusEl.textContent = step.status;
        await new Promise(r => setTimeout(r, step.delay));
    }

    // Fade out overlay
    overlay.classList.add('hidden');
    mainHud.style.opacity = '0';
    mainHud.style.transition = 'opacity 600ms ease';

    await new Promise(r => setTimeout(r, 100));
    mainHud.style.opacity = '1';

    // Clean up overlay after transition
    setTimeout(() => {
        overlay.style.display = 'none';
    }, 800);

    // Update backend indicator
    updateBackendIndicator();

    // Test backend connection
    testBackendConnection();
}

async function testBackendConnection() {
    const addLog = window.addLog; // Will be defined later
    try {
        const response = await fetch(`${getBackendUrl()}/status`);
        const data = await response.json();
        if (addLog) addLog(`Connected to ${data.cloud_deployment ? 'Cloud' : 'Local'} backend v${data.version}`);
        if (data.tts_engine) {
            if (addLog) addLog(`TTS Engine: ${data.tts_engine}`);
        }
    } catch (e) {
        if (addLog) addLog('Backend connection failed - check server');
        console.error('Backend connection test failed:', e);
    }
}

// --- AUDIO PLAYBACK (for cloud TTS) ---
const audioContext = new (window.AudioContext || window.webkitAudioContext)();
let audioQueue = [];
let isPlayingAudio = false;

async function playAudioBase64(base64Audio) {
    try {
        const binaryString = atob(base64Audio);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }

        const audioBuffer = await audioContext.decodeAudioData(bytes.buffer);
        const source = audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(audioContext.destination);
        source.start(0);

        return new Promise(resolve => {
            source.onended = resolve;
        });
    } catch (e) {
        console.error('Audio playback error:', e);
    }
}

async function playAudioQueue() {
    if (isPlayingAudio || audioQueue.length === 0) return;
    isPlayingAudio = true;

    while (audioQueue.length > 0) {
        const audioData = audioQueue.shift();
        await playAudioBase64(audioData);
    }

    isPlayingAudio = false;
}

function queueAudio(base64Audio) {
    audioQueue.push(base64Audio);
    playAudioQueue();
}

// --- TTS HELPER ---
async function speakText(text) {
    if (!isCloudMode()) {
        // Local mode - backend handles TTS
        return;
    }

    try {
        const response = await fetch(`${getBackendUrl()}/tts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });

        const data = await response.json();
        if (data.status === 'success' && data.audio) {
            queueAudio(data.audio);
        }
    } catch (e) {
        console.error('TTS request failed:', e);
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    console.log("JARVIS HUD: DOM fully loaded. Initializing systems...");

    // Run startup sequence
    await runStartupSequence();

    // Element Selectors
    const clockEl = document.getElementById('clock');
    const coreEl = document.getElementById('jarvis-core');
    const listenBtn = document.getElementById('listen-btn');
    const displayText = document.getElementById('display-text');
    const logContainer = document.getElementById('system-logs');
    const cpuProgress = document.getElementById('cpu-progress');
    const cpuValue = document.getElementById('cpu-value');
    const uptimeEl = document.getElementById('uptime');

    // --- LOGGING SYSTEM ---
    window.addLog = function addLog(message) {
        console.log("Log:", message);
        if (!logContainer) return;
        const entry = document.createElement('div');
        entry.className = 'log-entry';
        entry.textContent = `> ${message}`;
        logContainer.appendChild(entry);
        if (logContainer.children.length > 6) {
            logContainer.removeChild(logContainer.firstChild);
        }
    };

    // --- CLOCK SYSTEM ---
    function updateClock() {
        if (clockEl) {
            const now = new Date();
            clockEl.textContent = now.toLocaleTimeString('en-US', { hour12: false });
        }
    }
    setInterval(updateClock, 1000);
    updateClock();

    // --- UPTIME SYSTEM ---
    let uptimeSeconds = 0;
    function updateUptime() {
        uptimeSeconds++;
        const h = Math.floor(uptimeSeconds / 3600).toString().padStart(2, '0');
        const m = Math.floor((uptimeSeconds % 3600) / 60).toString().padStart(2, '0');
        const s = (uptimeSeconds % 60).toString().padStart(2, '0');
        if (uptimeEl) uptimeEl.textContent = `${h}:${m}:${s}`;
    }
    setInterval(updateUptime, 1000);
    updateUptime();

    // --- CORE VISUALS ---
    function triggerCorePulse(intensity = 'normal') {
        if (!coreEl) return;
        coreEl.classList.add('active');
        setTimeout(() => {
            coreEl.classList.remove('active');
        }, 1200);
    }

    if (coreEl) {
        coreEl.addEventListener('click', () => {
            coreEl.classList.toggle('active');
            addLog(coreEl.classList.contains('active') ? "Core Overdrive Engaged" : "Core Stabilized");
        });
    }

    // --- VOICE INTERACTION (Local only) ---
    if (!listenBtn) {
        console.error("CRITICAL ERROR: Button with id 'listen-btn' not found!");
    } else {
        let listenCooldown = false;

        listenBtn.addEventListener('click', async () => {
            if (listenCooldown) return;

            // Check if cloud mode - voice input not supported
            if (isCloudMode()) {
                addLog("Voice input unavailable in cloud mode. Use text input.");
                listenBtn.textContent = 'CLOUD MODE';
                setTimeout(() => { listenBtn.textContent = 'INITIALIZE VOICE'; }, 2000);
                return;
            }

            listenCooldown = true;
            listenBtn.disabled = true;
            listenBtn.textContent = 'LISTENING...';

            console.log("Button clicked! Sending request to backend...");

            // Visual Feedback
            triggerCorePulse('high');
            if (coreEl) coreEl.classList.add('core-listening');
            if (displayText) {
                displayText.textContent = "Listening...";
                displayText.classList.add('active');
            }
            addLog("Voice Input Active...");

            try {
                const response = await fetch(`${getBackendUrl()}/command`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: 'listen' })
                });

                const contentType = response.headers.get('Content-Type');

                if (contentType && contentType.includes('text/event-stream')) {
                    if (displayText) displayText.textContent = "";
                    const reader = response.body.getReader();
                    const decoder = new TextDecoder();
                    let fullResponse = "";

                    while (true) {
                        const { value, done } = await reader.read();
                        if (done) break;
                        const chunk = decoder.decode(value);
                        const lines = chunk.split('\n');
                        for (const line of lines) {
                            if (line.startsWith('data: ')) {
                                try {
                                    const data = JSON.parse(line.substring(6));
                                    const token = data.token;
                                    if (displayText) displayText.textContent += token;
                                    fullResponse += token;
                                } catch (e) {
                                    console.error("Error parsing stream token", e);
                                }
                            }
                        }
                    }
                    addLog(`Jarvis: ${fullResponse}`);
                    triggerCorePulse('normal');
                } else {
                    const data = await response.json();
                    if (data.status === 'success') {
                        if (displayText) displayText.textContent = data.response;
                        addLog(`User: ${data.query}`);
                        addLog(`Jarvis: ${data.response}`);
                        triggerCorePulse('normal');
                    } else {
                        if (displayText) displayText.textContent = "Could not hear you, sir.";
                        addLog("Listening error: " + data.message);
                    }
                }
            } catch (error) {
                console.error("Connection Error:", error);
                if (displayText) displayText.textContent = "Backend offline, sir.";
                addLog("Connection Error: Backend not running.");
            } finally {
                if (coreEl) coreEl.classList.remove('core-listening');
                if (displayText) displayText.classList.remove('active');
                listenBtn.disabled = false;
                listenBtn.textContent = 'INITIALIZE VOICE';
                setTimeout(() => { listenCooldown = false; }, 2000);
            }
        });
    }

    // --- TEXT INPUT INTERACTION (Works both local and cloud) ---
    const textInputGroup = document.getElementById('text-input-group');
    const textInput = document.getElementById('text-input');
    const sendBtn = document.getElementById('send-btn');

    if (textInputGroup && textInput && sendBtn) {
        textInputGroup.style.display = 'flex';

        async function sendTextQuery() {
            const query = textInput.value.trim();
            if (!query) return;

            triggerCorePulse('high');
            if (coreEl) coreEl.classList.add('core-listening');
            if (displayText) {
                displayText.textContent = "Thinking...";
                displayText.classList.add('active');
            }
            addLog(`> User typed: ${query}`);
            textInput.value = "";

            try {
                // In cloud mode, we don't want laptop to speak
                const speakOnLaptop = !isCloudMode();

                const response = await fetch(`${getBackendUrl()}/brain`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query, speak_on_laptop: speakOnLaptop })
                });

                const contentType = response.headers.get('Content-Type');

                if (contentType && contentType.includes('text/event-stream')) {
                    if (displayText) displayText.textContent = "";
                    const reader = response.body.getReader();
                    const decoder = new TextDecoder();
                    let fullResponse = "";

                    while (true) {
                        const { value, done } = await reader.read();
                        if (done) break;
                        const chunk = decoder.decode(value);
                        const lines = chunk.split('\n');
                        for (const line of lines) {
                            if (line.startsWith('data: ')) {
                                try {
                                    const data = JSON.parse(line.substring(6));
                                    const token = data.token;
                                    if (displayText) displayText.textContent += token;
                                    fullResponse += token;
                                } catch (e) {
                                    console.error("Error parsing stream token", e);
                                }
                            }
                        }
                    }
                    addLog(`Jarvis: ${fullResponse}`);
                    triggerCorePulse('normal');

                    // In cloud mode, request TTS playback
                    if (isCloudMode() && fullResponse.trim()) {
                        await speakText(fullResponse);
                    }
                } else {
                    const data = await response.json();
                    if (data.status === 'success') {
                        if (displayText) displayText.textContent = data.response;
                        addLog(`Jarvis: ${data.response}`);
                        triggerCorePulse('normal');

                        if (isCloudMode() && data.response) {
                            await speakText(data.response);
                        }
                    } else {
                        if (displayText) displayText.textContent = "Could not process command, sir.";
                        addLog("Text input error: " + data.message);
                    }
                }
            } catch (error) {
                console.error("Connection Error:", error);
                if (displayText) displayText.textContent = "Backend offline, sir.";
                addLog("Connection Error: Backend not running.");
            } finally {
                if (coreEl) coreEl.classList.remove('core-listening');
                if (displayText) displayText.classList.remove('active');
            }
        }

        sendBtn.addEventListener('click', sendTextQuery);

        textInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendTextQuery();
        });
    }

    // --- VOICE SELECTOR ---
    const voiceSelector = document.getElementById('voice-selector');
    const voiceSelect = document.getElementById('voice-select');
    const voiceTest = document.getElementById('voice-test');

    let voiceChangeCooldown = false;

    // Define loadVoices at module scope so cloud toggle can call it
    async function loadVoices() {
        try {
            const response = await fetch(`${getBackendUrl()}/voices`);
            const data = await response.json();
            if (data.voices && data.voices.length > 0) {
                if (voiceSelect) {
                    voiceSelect.innerHTML = '';
                    data.voices.forEach(v => {
                        const opt = document.createElement('option');
                        opt.value = v.id;
                        const sourceLabel = v.source === 'cloud' ? '☁️' : '💻';
                        opt.textContent = `${sourceLabel} ${v.name}`;
                        voiceSelect.appendChild(opt);
                    });
                }
                addLog(`Loaded ${data.voices.length} voices`);
            }
        } catch (e) {
            console.error("Voice load error:", e);
        }
    }

    if (voiceSelector && voiceSelect && voiceTest) {
        voiceSelector.style.display = 'flex';

        voiceTest.addEventListener('click', async () => {
            if (voiceChangeCooldown) return;
            const voiceId = voiceSelect.value;
            if (!voiceId) return;
            voiceChangeCooldown = true;
            voiceTest.disabled = true;
            voiceTest.textContent = 'TESTING...';
            try {
                const response = await fetch(`${getBackendUrl()}/set-voice`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ voice_id: voiceId })
                });
                const data = await response.json();
                addLog(data.message || "Voice test queued");

                // Test the voice
                if (isCloudMode()) {
                    await speakText("Voice test successful, sir.");
                }
            } catch (e) {
                console.error("Voice test error:", e);
            } finally {
                voiceTest.disabled = false;
                voiceTest.textContent = 'TEST';
                setTimeout(() => { voiceChangeCooldown = false; }, 2000);
            }
        });

        loadVoices();
    }

    // --- CLOUD MODE TOGGLE ---
    const cloudToggle = document.getElementById('cloud-toggle');
    if (cloudToggle) {
        cloudToggle.addEventListener('click', async () => {
            const newMode = !isCloudMode();
            if (newMode) {
                // Prompt for cloud URL if not configured
                if (!CONFIG.CLOUD_BACKEND_URL) {
                    const url = prompt('Enter Cloud Run backend URL:', 'https://');
                    if (url && url.startsWith('http')) {
                        CONFIG.CLOUD_BACKEND_URL = url;
                        localStorage.setItem('jarvis_cloud_url', url);
                    } else {
                        addLog('Cloud URL not provided. Staying in local mode.');
                        cloudToggle.checked = false;
                        return;
                    }
                }
                setCloudMode(true);
                addLog(`Switched to Cloud mode: ${CONFIG.CLOUD_BACKEND_URL}`);
            } else {
                setCloudMode(false);
                addLog('Switched to Local mode');
            }
            // Reload voices for new backend
            loadVoices();
            testBackendConnection();
        });
        // Set initial state
        cloudToggle.checked = isCloudMode();
    }

    // --- STATS SYSTEM ---
    function updateStats() {
        if (cpuProgress) {
            const cpu = Math.floor(Math.random() * 100);
            const offset = 283 - (283 * cpu / 100);
            cpuProgress.style.strokeDashoffset = offset;
        }
        if (cpuValue) {
            cpuValue.textContent = `${Math.floor(Math.random() * 50)}%`;
        }
        const tempEl = document.getElementById('core-temp');
        if (tempEl) tempEl.textContent = `${40 + Math.floor(Math.random() * 5)}°C`;
    }
    setInterval(updateStats, 5000);
    updateStats();
});