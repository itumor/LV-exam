const menu = document.querySelector("#menu");
const search = document.querySelector("#search");
const title = document.querySelector("#title");
const subtitle = document.querySelector("#subtitle");
const audio = document.querySelector("#audio");
const lvText = document.querySelector("#lvText");
const enText = document.querySelector("#enText");
const lvLink = document.querySelector("#lvLink");
const enLink = document.querySelector("#enLink");
const statusBadge = document.querySelector("#statusBadge");
const previousButton = document.querySelector("#prev");
const nextButton = document.querySelector("#next");

const tabTranscript = document.querySelector("#tab-transcript");
const tabShadowing = document.querySelector("#tab-shadowing");
const transcriptView = document.querySelector("#transcript-view");
const shadowingView = document.querySelector("#shadowing-view");
const currentSentence = document.querySelector("#currentSentence");
const currentTranslation = document.querySelector("#currentTranslation");
const sentenceCounter = document.querySelector("#sentenceCounter");
const showTranslation = document.querySelector("#showTranslation");
const shadowPrev = document.querySelector("#shadowPrev");
const shadowReplay = document.querySelector("#shadowReplay");
const shadowRecord = document.querySelector("#shadowRecord");
const shadowStop = document.querySelector("#shadowStop");
const shadowPlayRecording = document.querySelector("#shadowPlayRecording");
const shadowNext = document.querySelector("#shadowNext");
const waveformCanvas = document.querySelector("#waveformCanvas");
const recordingStatus = document.querySelector("#recordingStatus");
const pronunciationFeedback = document.querySelector("#pronunciationFeedback");

let sentences = [];
let currentSentenceIndex = 0;
let mediaRecorder = null;
let audioChunks = [];
let userAudioBlob = null;
let userAudioUrl = null;
let audioContext = null;
let analyser = null;
let animationId = null;
let recognition = null;
let isRecording = false;
let SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

const levelLabels = {
  A1: "A1 Klausīšanās",
  A2: "A2 Klausīšanās",
};

const visualLessons = [
  "Prieks iepazīties!",
  "No visas pasaules",
  "Pilsētā un laukos",
  "Mana māja un ģimene",
  "Kājām, ar trolejbusu, ar lidmašīnu",
  "Ikdienas darbi",
  "Iepirkšanās",
  "Labu apetīti!",
  "Brīvais laiks",
  "Es ceļoju",
  "Esi vesels!",
  "Mācības un darbs",
];

let catalog = [];
let filtered = [];
let selectedIndex = -1;

function badgeClass(status) {
  if (status === "completed") return "badge badge-completed";
  if (status === "transcribed only" || status === "translation failed") return "badge badge-transcribed";
  if (status === "failed") return "badge badge-failed";
  return "badge badge-muted";
}

function setText(node, value, fallback) {
  node.textContent = value && value.trim() ? value : fallback;
}

function renderMenu() {
  menu.textContent = "";
  for (const level of ["A1", "A2"]) {
    const items = filtered.filter((item) => item.level === level);
    const section = document.createElement("section");
    section.className = "level-section";

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "level-toggle";
    toggle.setAttribute("aria-expanded", "true");
    toggle.textContent = `${levelLabels[level]} (${items.length})`;
    const plus = document.createElement("span");
    plus.textContent = "−";
    toggle.appendChild(plus);

    const list = document.createElement("div");
    list.className = "item-list";

    for (const item of items) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "audio-item";
      if (filtered[selectedIndex] && filtered[selectedIndex].id === item.id) {
        button.classList.add("active");
      }
      button.addEventListener("click", () => selectItem(filtered.findIndex((candidate) => candidate.id === item.id)));

      const dot = document.createElement("span");
      dot.className = "play-dot";
      const label = document.createElement("span");
      label.textContent = item.title || item.original_filename || "Audio";
      const status = document.createElement("small");
      status.textContent = item.status || "unknown";
      button.append(dot, label, status);
      list.appendChild(button);
    }

    toggle.addEventListener("click", () => {
      const expanded = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!expanded));
      plus.textContent = expanded ? "+" : "−";
      list.hidden = expanded;
    });

    section.append(toggle, list);
    menu.appendChild(section);
  }

  if (filtered.length === 0) {
    visualLessons.forEach((lesson, index) => {
      const card = document.createElement("div");
      card.className = "lesson-card";
      card.textContent = `${index + 1}. ${lesson}`;
      menu.appendChild(card);
    });
  }
}

function selectItem(index) {
  if (index < 0 || index >= filtered.length) return;
  selectedIndex = index;
  const item = filtered[index];
  setText(title, item.title || item.original_filename, "Untitled audio");
  setText(subtitle, `${levelLabels[item.level] || item.level} · ${item.original_filename || ""}`, "");
  audio.src = item.audio_url || "";
  setText(lvText, item.lv_text, "Latvian transcript is not available yet.");
  setText(enText, item.en_text, "English translation is not available yet.");
  lvLink.href = item.lv_markdown_url || "#";
  enLink.href = item.en_markdown_url || "#";
  statusBadge.textContent = item.status || "unknown";
  statusBadge.className = badgeClass(item.status);
  previousButton.disabled = selectedIndex <= 0;
  nextButton.disabled = selectedIndex >= filtered.length - 1;
  renderMenu();
  
  if (!tabShadowing.classList.contains("hidden")) {
    initShadowingMode();
  }
}

function applyFilter() {
  const query = search.value.trim().toLowerCase();
  filtered = catalog.filter((item) => {
    const haystack = [item.title, item.original_filename, item.level, item.status, item.lv_text, item.en_text]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(query);
  });
  selectedIndex = filtered.length ? 0 : -1;
  renderMenu();
  if (filtered.length) {
    selectItem(0);
  } else {
    setText(title, "No matching audio", "No matching audio");
    setText(subtitle, "Try another search or build the catalog after processing files.", "");
    audio.removeAttribute("src");
    setText(lvText, "", "No transcript selected.");
    setText(enText, "", "No translation selected.");
    statusBadge.textContent = "empty";
    statusBadge.className = "badge badge-muted";
  }
}

previousButton.addEventListener("click", () => selectItem(selectedIndex - 1));
nextButton.addEventListener("click", () => selectItem(selectedIndex + 1));
search.addEventListener("input", applyFilter);

tabTranscript.addEventListener("click", () => {
  tabTranscript.classList.add("active");
  tabShadowing.classList.remove("active");
  transcriptView.classList.remove("hidden");
  shadowingView.classList.add("hidden");
});

tabShadowing.addEventListener("click", () => {
  tabShadowing.classList.add("active");
  tabTranscript.classList.remove("active");
  transcriptView.classList.add("hidden");
  shadowingView.classList.remove("hidden");
  if (filtered[selectedIndex] && filtered[selectedIndex].lv_text) {
    initShadowingMode();
  }
});

showTranslation.addEventListener("change", () => {
  currentTranslation.classList.toggle("hidden", !showTranslation.checked);
});

function splitIntoSentences(text) {
  if (!text) return [];
  const sentenceRegex = /[^.!?]+[.!?]+/g;
  const matches = text.match(sentenceRegex);
  if (!matches) return text ? [text] : [];
  return matches.map(s => s.trim()).filter(s => s.length > 0);
}

function initShadowingMode() {
  const item = filtered[selectedIndex];
  if (!item || !item.lv_text) {
    currentSentence.textContent = "No transcript available for shadowing.";
    currentTranslation.textContent = "";
    sentenceCounter.textContent = "0 / 0";
    sentences = [];
    updateShadowingControls();
    return;
  }

  sentences = splitIntoSentences(item.lv_text);
  currentSentenceIndex = 0;
  userAudioBlob = null;
  userAudioUrl = null;
  recordingStatus.textContent = "";
  pronunciationFeedback.textContent = "";
  clearWaveform();

  if (sentences.length > 0) {
    displayCurrentSentence();
  } else {
    currentSentence.textContent = "No sentences found in transcript.";
    sentenceCounter.textContent = "0 / 0";
  }
  updateShadowingControls();
}

function displayCurrentSentence() {
  if (sentences.length === 0) return;
  currentSentence.textContent = sentences[currentSentenceIndex];
  sentenceCounter.textContent = `${currentSentenceIndex + 1} / ${sentences.length}`;
  
  const item = filtered[selectedIndex];
  if (item && item.en_text) {
    const enSentences = splitIntoSentences(item.en_text);
    currentTranslation.textContent = enSentences[currentSentenceIndex] || "";
  }
  
  updateShadowingControls();
}

function updateShadowingControls() {
  const hasSentences = sentences.length > 0;
  shadowPrev.disabled = !hasSentences || currentSentenceIndex === 0;
  shadowReplay.disabled = !hasSentences;
  shadowRecord.disabled = !hasSentences || isRecording;
  shadowStop.disabled = !isRecording;
  shadowPlayRecording.disabled = !hasSentences || !userAudioUrl;
  shadowNext.disabled = !hasSentences || currentSentenceIndex >= sentences.length - 1;
}

function playCurrentSentence() {
  if (sentences.length === 0) return;
  const sentenceText = sentences[currentSentenceIndex];
  const utterance = new SpeechSynthesisUtterance(sentenceText);
  utterance.lang = "lv-LV";
  utterance.rate = 0.8;
  speechSynthesis.speak(utterance);
}

shadowPrev.addEventListener("click", () => {
  if (currentSentenceIndex > 0) {
    currentSentenceIndex--;
    displayCurrentSentence();
    userAudioBlob = null;
    userAudioUrl = null;
    recordingStatus.textContent = "";
    pronunciationFeedback.textContent = "";
    clearWaveform();
  }
});

shadowReplay.addEventListener("click", playCurrentSentence);

shadowNext.addEventListener("click", () => {
  if (currentSentenceIndex < sentences.length - 1) {
    currentSentenceIndex++;
    displayCurrentSentence();
    userAudioBlob = null;
    userAudioUrl = null;
    recordingStatus.textContent = "";
    pronunciationFeedback.textContent = "";
    clearWaveform();
  }
});

shadowRecord.addEventListener("click", async () => {
  if (isRecording) return;

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];
    isRecording = true;

    mediaRecorder.ondataavailable = (event) => {
      audioChunks.push(event.data);
    };

    mediaRecorder.onstop = () => {
      userAudioBlob = new Blob(audioChunks, { type: "audio/webm" });
      if (userAudioUrl) URL.revokeObjectURL(userAudioUrl);
      userAudioUrl = URL.createObjectURL(userAudioBlob);
      recordingStatus.textContent = "Recording saved for self-review.";
      
      if (SpeechRecognition) {
        tryRecognition();
      }
      
      stream.getTracks().forEach(track => track.stop());
      updateShadowingControls();
    };

    mediaRecorder.start();
    recordingStatus.textContent = "Recording...";
    updateShadowingControls();
    visualizeAudio(stream);
  } catch (err) {
    console.error("Microphone error:", err);
    if (err.name === "NotAllowedError") {
      recordingStatus.textContent = "Microphone permission denied. Please allow access to record.";
    } else {
      recordingStatus.textContent = "Could not access microphone.";
    }
  }
});

shadowStop.addEventListener("click", () => {
  if (mediaRecorder && isRecording) {
    mediaRecorder.stop();
    isRecording = false;
    if (animationId) {
      cancelAnimationFrame(animationId);
      animationId = null;
    }
  }
});

shadowPlayRecording.addEventListener("click", () => {
  if (userAudioUrl) {
    const playAudio = new Audio(userAudioUrl);
    playAudio.play();
  }
});

function visualizeAudio(stream) {
  if (!audioContext) {
    audioContext = new (window.AudioContext || window.webkitAudioContext)();
  }
  analyser = audioContext.createAnalyser();
  const source = audioContext.createMediaStreamSource(stream);
  source.connect(analyser);
  analyser.fftSize = 256;
  
  const bufferLength = analyser.frequencyBinCount;
  const dataArray = new Uint8Array(bufferLength);
  const ctx = waveformCanvas.getContext("2d");
  
  function draw() {
    if (!isRecording) return;
    animationId = requestAnimationFrame(draw);
    analyser.getByteFrequencyData(dataArray);
    
    ctx.fillStyle = "#e7eff3";
    ctx.fillRect(0, 0, waveformCanvas.width, waveformCanvas.height);
    
    const barWidth = (waveformCanvas.width / bufferLength) * 2.5;
    let x = 0;
    for (let i = 0; i < bufferLength; i++) {
      const barHeight = (dataArray[i] / 255) * waveformCanvas.height;
      ctx.fillStyle = `rgb(214, 10, 79)`;
      ctx.fillRect(x, waveformCanvas.height - barHeight, barWidth, barHeight);
      x += barWidth + 1;
    }
  }
  
  draw();
}

function clearWaveform() {
  const ctx = waveformCanvas.getContext("2d");
  ctx.fillStyle = "#e7eff3";
  ctx.fillRect(0, 0, waveformCanvas.width, waveformCanvas.height);
}

function tryRecognition() {
  if (!SpeechRecognition) {
    pronunciationFeedback.textContent = "";
    return;
  }

  recognition = new SpeechRecognition();
  recognition.lang = "lv-LV";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    const targetSentence = sentences[currentSentenceIndex];
    const similarity = calculateSimilarity(transcript.toLowerCase(), targetSentence.toLowerCase());
    
    let feedback = `You said: "${transcript}"<br>`;
    if (similarity > 0.7) {
      feedback += `<span class="feedback-good">Great match! (${Math.round(similarity * 100)}%)</span>`;
    } else if (similarity > 0.4) {
      feedback += `<span class="feedback-ok">Partial match (${Math.round(similarity * 100)}%). Try again!</span>`;
    } else {
      feedback += `<span class="feedback-low">Keep practicing! (${Math.round(similarity * 100)}%)</span>`;
    }
    pronunciationFeedback.innerHTML = feedback;
  };

  recognition.onerror = (event) => {
    console.error("Speech recognition error:", event.error);
    pronunciationFeedback.innerHTML = "Speech recognition unavailable. Recording saved for self-review.";
  };

  if (userAudioBlob) {
    recognition.start();
  }
}

function calculateSimilarity(str1, str2) {
  const words1 = str1.replace(/[^\w\s]/g, "").toLowerCase().split(/\s+/).filter(w => w);
  const words2 = str2.replace(/[^\w\s]/g, "").toLowerCase().split(/\s+/).filter(w => w);
  
  if (words1.length === 0 || words2.length === 0) return 0;
  
  const set2 = new Set(words2);
  let matches = 0;
  for (const word of words1) {
    if (set2.has(word)) matches++;
  }
  
  return (2 * matches) / (words1.length + words2.length);
}

fetch("catalog.json", { cache: "no-store" })
  .then((response) => {
    if (!response.ok) throw new Error(`Catalog request failed: ${response.status}`);
    return response.json();
  })
  .then((items) => {
    catalog = Array.isArray(items) ? items : [];
    filtered = catalog.slice();
    renderMenu();
    if (filtered.length) {
      selectItem(0);
    }
  })
  .catch((error) => {
    console.error(error);
    filtered = [];
    renderMenu();
    setText(title, "Catalog not ready", "Catalog not ready");
    setText(subtitle, "Run scripts/build_catalog.py after processing audio.", "");
  });
