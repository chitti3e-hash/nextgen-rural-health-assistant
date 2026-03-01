const askBtn = document.getElementById("askBtn");
const voiceBtn = document.getElementById("voiceBtn");
const speakBtn = document.getElementById("speakBtn");
const queryInput = document.getElementById("query");
const languageSelect = document.getElementById("language");
const ageYearsInput = document.getElementById("ageYears");
const locationInput = document.getElementById("locationInput");
const answerEl = document.getElementById("answer");
const disclaimerEl = document.getElementById("disclaimer");
const nextStepsEl = document.getElementById("nextSteps");
const sourcesEl = document.getElementById("sources");
const urgencyEl = document.getElementById("urgency");
const diseaseQueryInput = document.getElementById("diseaseQuery");
const diseaseBtn = document.getElementById("diseaseBtn");
const diseaseMetaEl = document.getElementById("diseaseMeta");
const diseaseResultEl = document.getElementById("diseaseResult");
const pincodeInput = document.getElementById("pincode");
const hospitalBtn = document.getElementById("hospitalBtn");
const hospitalMetaEl = document.getElementById("hospitalMeta");
const hospitalResultsEl = document.getElementById("hospitalResults");

const langMap = {
  en: "en-IN",
  hi: "hi-IN",
  ta: "ta-IN",
  te: "te-IN",
  bn: "bn-IN",
};

let lastAnswer = "";
let lastAnswerLanguage = "en";
let activeRecognition = null;
let isListening = false;

function detectLanguageFromText(text) {
  if (!text) {
    return null;
  }
  if (/[\u0B80-\u0BFF]/.test(text)) {
    return "ta";
  }
  if (/[\u0C00-\u0C7F]/.test(text)) {
    return "te";
  }
  if (/[\u0980-\u09FF]/.test(text)) {
    return "bn";
  }
  if (/[\u0900-\u097F]/.test(text)) {
    return "hi";
  }
  if (/[a-zA-Z]/.test(text)) {
    return "en";
  }
  return null;
}

function setVoiceButtonState(listening) {
  isListening = listening;
  voiceBtn.textContent = listening ? "⏹ Stop Listening" : "🎤 Voice Input";
}

function getVoiceErrorMessage(error) {
  const messageByCode = {
    "not-allowed": "Microphone permission denied. Allow mic access in browser settings.",
    "service-not-allowed": "Speech service is blocked. Enable speech recognition in browser settings.",
    "network": "Speech recognition network error. Check your internet connection.",
    "no-speech": "No speech detected. Please try again and speak clearly.",
    "audio-capture": "No microphone found. Connect or enable a microphone.",
    "aborted": "Voice capture stopped.",
  };
  return messageByCode[error] || "Voice capture failed. Please type your question.";
}

function renderList(container, items, formatter) {
  container.innerHTML = "";
  if (!items || items.length === 0) {
    const li = document.createElement("li");
    li.textContent = "No items.";
    container.appendChild(li);
    return;
  }

  items.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = formatter(item);
    container.appendChild(li);
  });
}

async function askAssistant(mode = "text") {
  const query = queryInput.value.trim();
  const selectedLanguage = languageSelect.value;
  const detectedLanguage = detectLanguageFromText(query);
  const language = detectedLanguage || selectedLanguage;
  const location = locationInput.value.trim();
  const ageValue = ageYearsInput.value.trim();
  const ageYears = ageValue === "" ? null : Number(ageValue);
  if (!query) {
    answerEl.textContent = "Please enter a question first.";
    return;
  }
  if (ageYears !== null && (Number.isNaN(ageYears) || ageYears < 0 || ageYears > 120)) {
    answerEl.textContent = "Please enter a valid age between 0 and 120.";
    return;
  }

  answerEl.textContent = "Getting grounded guidance...";
  nextStepsEl.innerHTML = "";
  sourcesEl.innerHTML = "";

  if (detectedLanguage && languageSelect.value !== detectedLanguage) {
    languageSelect.value = detectedLanguage;
  }

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        language,
        mode,
        age_years: ageYears,
        location: location || null,
      }),
    });

    if (!response.ok) {
      answerEl.textContent = "Request failed. Please try again.";
      return;
    }

    const payload = await response.json();
    lastAnswer = payload.answer;
    lastAnswerLanguage = payload.language || language;
    if (payload.language && languageSelect.value !== payload.language) {
      languageSelect.value = payload.language;
    }

    answerEl.textContent = payload.answer;
    disclaimerEl.textContent = payload.disclaimer;
    urgencyEl.textContent = `Status: ${payload.urgency.toUpperCase()} | Confidence: ${payload.confidence}`;
    urgencyEl.className = `badge ${payload.urgency}`;

    renderList(nextStepsEl, payload.next_steps, (step) => step);
    renderList(sourcesEl, payload.sources, (source) => `${source.title} (${source.source})`);
  } catch (error) {
    answerEl.textContent = "Network error. Please check server and try again.";
  }
}

async function lookupHospitals() {
  const pincode = pincodeInput.value.trim();
  if (!/^\d{6}$/.test(pincode)) {
    hospitalMetaEl.textContent = "Please enter a valid 6-digit pincode.";
    renderList(hospitalResultsEl, [], (item) => item);
    return;
  }

  hospitalMetaEl.textContent = "Fetching nearest hospitals...";
  renderList(hospitalResultsEl, [], (item) => item);

  const response = await fetch(`/hospitals/nearest?pincode=${encodeURIComponent(pincode)}&limit=5`);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    hospitalMetaEl.textContent = payload.detail || "Hospital lookup failed. Please try again.";
    return;
  }

  const payload = await response.json();
  const freshness = payload.cached ? "cached" : "live";
  hospitalMetaEl.textContent = `Location: ${payload.location} | Source: ${payload.source} (${freshness})`;

  renderList(
    hospitalResultsEl,
    payload.hospitals,
    (hospital) => `${hospital.name} - ${hospital.distance_km} km - ${hospital.address}`
  );
}

async function lookupDiseaseInfo() {
  const query = diseaseQueryInput.value.trim();
  if (query.length < 2) {
    diseaseMetaEl.textContent = "Please enter at least 2 characters.";
    diseaseResultEl.textContent = "No disease selected yet.";
    return;
  }

  diseaseMetaEl.textContent = "Fetching disease treatment guidance...";
  diseaseResultEl.textContent = "Loading...";

  const response = await fetch(`/diseases/search?q=${encodeURIComponent(query)}&limit=1`);
  if (!response.ok) {
    diseaseMetaEl.textContent = "Disease lookup failed. Please try again.";
    diseaseResultEl.textContent = "No disease data found.";
    return;
  }

  const payload = await response.json();
  if (!payload.matches || payload.matches.length === 0) {
    diseaseMetaEl.textContent = "No close disease match found.";
    diseaseResultEl.textContent = "Try a common disease name like dengue, diabetes, asthma, migraine.";
    return;
  }

  const disease = payload.matches[0];
  diseaseMetaEl.textContent = `Matched: ${disease.name} | Category: ${disease.category} | Confidence: ${disease.score}`;

  const sections = [
    `${disease.name}`,
    `Overview: ${disease.overview}`,
    `Treatment: ${disease.treatment_summary}`,
    "Medicines (doctor-guided):",
    ...disease.medicine_guidance.map((item) => `- ${item}`),
    "Home remedies/care:",
    ...disease.home_care.map((item) => `- ${item}`),
    "Urgent red flags:",
    ...disease.red_flags.map((item) => `- ${item}`),
    `Source: ${disease.source}`,
    "Safety: Do not self-start prescription medicines without doctor advice.",
  ];

  diseaseResultEl.textContent = sections.join("\n");
}

askBtn.addEventListener("click", () => askAssistant("text"));
diseaseBtn.addEventListener("click", lookupDiseaseInfo);
hospitalBtn.addEventListener("click", lookupHospitals);

voiceBtn.addEventListener("click", () => {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    answerEl.textContent = "Voice input is not supported in this browser.";
    return;
  }
  const runningOnLocalhost = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
  if (!window.isSecureContext && !runningOnLocalhost) {
    answerEl.textContent = "Voice input needs HTTPS. Open the secure site URL, then try again.";
    return;
  }

  if (isListening && activeRecognition) {
    activeRecognition.stop();
    setVoiceButtonState(false);
    return;
  }

  const recognition = new SpeechRecognition();
  activeRecognition = recognition;
  recognition.lang = langMap[languageSelect.value] || "en-IN";
  recognition.interimResults = false;
  recognition.continuous = false;
  recognition.maxAlternatives = 1;

  recognition.onstart = () => {
    setVoiceButtonState(true);
    answerEl.textContent = "Listening...";
  };

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript.trim();
    queryInput.value = transcript;
    const detectedLanguage = detectLanguageFromText(transcript);
    if (detectedLanguage && languageSelect.value !== detectedLanguage) {
      languageSelect.value = detectedLanguage;
    }
    askAssistant("voice");
  };

  recognition.onerror = (event) => {
    answerEl.textContent = getVoiceErrorMessage(event.error);
  };

  recognition.onend = () => {
    setVoiceButtonState(false);
    activeRecognition = null;
  };

  try {
    recognition.start();
  } catch (error) {
    setVoiceButtonState(false);
    activeRecognition = null;
    answerEl.textContent = "Could not start voice input. Refresh and try again.";
  }
});

speakBtn.addEventListener("click", () => {
  if (!lastAnswer) {
    return;
  }
  const utterance = new SpeechSynthesisUtterance(lastAnswer);
  utterance.lang = langMap[lastAnswerLanguage] || "en-IN";
  window.speechSynthesis.speak(utterance);
});
