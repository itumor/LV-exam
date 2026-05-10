const container = document.querySelector("#microContainer");
const prevBtn = document.querySelector("#prevBtn");
const nextBtn = document.querySelector("#nextBtn");
const toast = document.querySelector("#toast");

let microClips = [];
let currentIndex = 0;
let hasAnswered = false;

async function loadMicroClips() {
  try {
    const response = await fetch("microClips.json");
    microClips = await response.json();
  } catch (error) {
    console.error("Failed to load micro clips:", error);
    microClips = getDefaultMicroClips();
  }
}

function getDefaultMicroClips() {
  return [
    {
      id: "micro-001",
      audio_url: "data/A1_klausisanas/audio/1_2.mp3",
      title: "Iepazīšanās",
      prompt: "Can you understand this Latvian?",
      prompt_lv: "Vai tu saproti šo latviešu valodu?",
      options: ["Labrīt!", "Labdien!", "Labvakar!"],
      answer: 0,
      answer_text: "Labrīt!",
      transcript: "Klausies un atkārto. Labrīt! Mani sauc Jānis.",
      translation: "Listen and repeat. Good morning! My name is Jānis.",
      difficulty: "A1",
      category: "greetings"
    },
    {
      id: "micro-002",
      audio_url: "data/A1_klausisanas/audio/1_3.mp3",
      title: "Vārds",
      prompt: "What name did you hear?",
      prompt_lv: "Kādu vārdu tu dzirdēji?",
      options: ["Maija", "Sāra", "Deivits"],
      answer: 2,
      answer_text: "Deivits",
      transcript: "Mani sauc Deivits, kā tevi sauc?",
      translation: "My name is Davit, what's your name?",
      difficulty: "A1",
      category: "people"
    },
    {
      id: "micro-003",
      audio_url: "data/A1_klausisanas/audio/2_1.mp3",
      title: "Karte",
      prompt: "Where is the speaker going?",
      prompt_lv: "Kur speakers dodas?",
      options: ["uz banku", "uzveikalu", "uz bibliotēku"],
      answer: 1,
      answer_text: "uz veikalu",
      transcript: "Es gāju uz veikalu pirkt maizi.",
      translation: "I went to the store to buy bread.",
      difficulty: "A1",
      category: "places"
    },
    {
      id: "micro-004",
      audio_url: "data/A1_klausisanas/audio/2_6.mp3",
      title: "Laiks",
      prompt: "What time was mentioned?",
      prompt_lv: "Kuru laiku pieminēja?",
      options: ["sešos", "septini", "astoņos"],
      answer: 0,
      answer_text: "sešos",
      transcript: "Es ceļosies sešos no rīta.",
      translation: "I wake up at six in the morning.",
      difficulty: "A1",
      category: "time"
    },
    {
      id: "micro-005",
      audio_url: "data/A1_klausisanas/audio/3_4.mp3",
      title: "Ēdiens",
      prompt: "Which word was missing?",
      prompt_lv: "Kurš vārds trūka?",
      options: ["ābols", "banāns", "apelsīns"],
      answer: 1,
      answer_text: "banāns",
      transcript: "Es gribu ēst ābolu un banānu.",
      translation: "I want to eat an apple and a banana.",
      difficulty: "A1",
      category: "food"
    },
    {
      id: "micro-006",
      audio_url: "data/A2_klausisanas/audio/1.nodalja.mp3",
      title: "Darbs",
      prompt: "What is the speaker's profession?",
      prompt_lv: "Kāda ir runātāja profesija?",
      options: ["pasniedzējs", "students", "ārsts"],
      answer: 0,
      answer_text: "pasniedzējs",
      transcript: "Es esmu pasniedzējs Latvijas Universitātē.",
      translation: "I am a teacher at the University of Latvia.",
      difficulty: "A2",
      category: "work"
    },
    {
      id: "micro-007",
      audio_url: "data/A2_klausisanas/audio/1_2.mp3",
      title: "Transport",
      prompt: "How does the speaker travel?",
      prompt_lv: "Kā ceļo runātājs?",
      options: ["ar autobusu", "ar riteni", "ar kājām"],
      answer: 0,
      answer_text: "ar autobusu",
      transcript: "Es braucu uz darbu ar autobusu katru dienu.",
      translation: "I go to work by bus every day.",
      difficulty: "A2",
      category: "transport"
    },
    {
      id: "micro-008",
      audio_url: "data/A2_klausisanas/audio/2_3.mp3",
      title: "Veselība",
      prompt: "Where should the person go?",
      prompt_lv: "Kur personai vajag iet?",
      options: ["uz slimnīcu", "uz aptieku", "uz sporta zāli"],
      answer: 1,
      answer_text: "uz aptieku",
      transcript: "Man vajag doties uz aptieku pēc zālēm.",
      translation: "I need to go to the pharmacy for medicine.",
      difficulty: "A2",
      category: "health"
    }
  ];
}

function getDifficultyClass(difficulty) {
  return difficulty === "A1" ? "tag-difficulty-a1" : "tag-difficulty-a2";
}

function renderCard(clip) {
  hasAnswered = false;
  
  const card = document.createElement("article");
  card.className = "micro-card";
  card.dataset.id = clip.id;

  card.innerHTML = `
    <div class="micro-meta">
      <span class="micro-tag ${getDifficultyClass(clip.difficulty)}">${clip.difficulty}</span>
      <span class="micro-tag tag-category">${clip.category}</span>
    </div>
    
    <h2 class="micro-prompt">${clip.prompt_lv}</h2>
    <p style="color: var(--muted); margin-bottom: 16px; font-size: 0.9rem;">${clip.prompt}</p>

    <audio class="micro-audio" controls preload="metadata">
      <source src="${clip.audio_url}" type="audio/mpeg">
      Your browser does not support audio.
    </audio>

    <div class="micro-options">
      ${clip.options.map((opt, idx) => `
        <button class="micro-option" data-index="${idx}">${opt}</button>
      `).join("")}
    </div>

    <div class="micro-feedback" id="feedback">
      <div class="feedback-title"></div>
      <div class="feedback-explanation"></div>
    </div>

    <div class="micro-transcript" id="transcript">
      <div class="micro-transcript-label">Transcript</div>
      <div class="micro-transcript-text">
        <strong>LV:</strong> ${clip.transcript}<br>
        <strong>EN:</strong> ${clip.translation}
      </div>
    </div>

    <div class="micro-actions">
      <button class="micro-btn btn-reveal" id="revealBtn">Rādīt transkriptu</button>
      <button class="micro-btn btn-save" id="saveBtn">Saglabāt vārdus</button>
      <button class="micro-btn btn-copy" id="copyBtn">Kopēt saiti</button>
    </div>
  `;

  container.innerHTML = "";
  container.appendChild(card);

  const options = card.querySelectorAll(".micro-option");
  options.forEach((btn, idx) => {
    btn.addEventListener("click", () => handleAnswer(idx, clip, options));
  });

  const revealBtn = card.querySelector("#revealBtn");
  const transcriptDiv = card.querySelector("#transcript");
  revealBtn.addEventListener("click", () => {
    transcriptDiv.classList.toggle("visible");
    revealBtn.textContent = transcriptDiv.classList.contains("visible") ? "Slēpt transkriptu" : "Rādīt transkriptu";
  });

  const saveBtn = card.querySelector("#saveBtn");
  saveBtn.addEventListener("click", () => {
    showToast("Vārdi saglabāti!");
  });

  const copyBtn = card.querySelector("#copyBtn");
  copyBtn.addEventListener("click", () => {
    const url = `${window.location.origin}${window.location.pathname.replace("micro.html", "micro.html")}?id=${clip.id}`;
    navigator.clipboard.writeText(url).then(() => {
      showToast("Saite nokopēta!");
    });
  });

  updateNavButtons();
}

function handleAnswer(selectedIndex, clip, options) {
  if (hasAnswered) return;
  hasAnswered = true;

  const correctIndex = clip.answer;
  const feedback = document.querySelector("#feedback");

  options.forEach((opt, idx) => {
    if (idx === correctIndex) {
      opt.classList.add("correct");
    } else if (idx === selectedIndex) {
      opt.classList.add("incorrect");
    }
    opt.disabled = true;
  });

  const isCorrect = selectedIndex === correctIndex;
  feedback.classList.add("visible");
  feedback.classList.add(isCorrect ? "feedback-correct" : "feedback-incorrect");
  
  feedback.querySelector(".feedback-title").textContent = isCorrect ? "Pareizi! ✓" : "Nepareizi!";
  feedback.querySelector(".feedback-explanation").textContent = isCorrect 
    ? `Pareizā atbilde: ${clip.answer_text}`
    : `Pareizā atbilde bija: ${clip.answer_text}. ${clip.translation}`;

  const audio = document.querySelector(".micro-audio");
  audio.play();
}

function updateNavButtons() {
  prevBtn.disabled = currentIndex <= 0;
  nextBtn.disabled = currentIndex >= microClips.length - 1;
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("visible");
  setTimeout(() => {
    toast.classList.remove("visible");
  }, 2500);
}

function navigate(direction) {
  const newIndex = currentIndex + direction;
  if (newIndex >= 0 && newIndex < microClips.length) {
    currentIndex = newIndex;
    renderCard(microClips[currentIndex]);
    window.history.replaceState(null, "", `?id=${microClips[currentIndex].id}`);
  }
}

prevBtn.addEventListener("click", () => navigate(-1));
nextBtn.addEventListener("click", () => navigate(1));

document.addEventListener("keydown", (e) => {
  if (e.key === "ArrowLeft") navigate(-1);
  if (e.key === "ArrowRight") navigate(1);
});

let touchStartX = 0;
document.addEventListener("touchstart", (e) => {
  touchStartX = e.touches[0].clientX;
});

document.addEventListener("touchend", (e) => {
  const touchEndX = e.changedTouches[0].clientX;
  const diff = touchStartX - touchEndX;
  if (Math.abs(diff) > 50) {
    if (diff > 0) navigate(1);
    else navigate(-1);
  }
});

async function init() {
  await loadMicroClips();

  const params = new URLSearchParams(window.location.search);
  const clipId = params.get("id");
  
  if (clipId) {
    const foundIndex = microClips.findIndex(c => c.id === clipId);
    if (foundIndex !== -1) {
      currentIndex = foundIndex;
    }
  }

  if (microClips.length > 0) {
    renderCard(microClips[currentIndex]);
  }
}

init();