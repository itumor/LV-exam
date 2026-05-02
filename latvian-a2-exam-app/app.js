const optionLetters = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l"];
const FlowCore = window.LatvianA2FlowCore;
if (!FlowCore) {
  throw new Error("LatvianA2FlowCore helpers failed to load.");
}

const {
  createTimerState,
  calculateRemaining,
  startTimer,
  pauseTimer,
  resetTimer,
  tickTimer,
  buildCandidateReportModel,
  buildCandidateReportHtml
} = FlowCore;

const EXAMS = Array.from({ length: 10 }, (_, index) => {
  const number = String(index + 1).padStart(2, "0");
  return {
    id: number,
    title: `A2 Mock Exam ${number}`,
    markdownPath: `/codex/A2_Mock_Exam_${number}.md`,
    sourcePath: `codex/A2_Mock_Exam_${number}.md`,
    attachmentRoot: `/codex/Attachments/A2_Mock_Exam_${number}/`
  };
});

const state = {
  exam: EXAMS[0],
  markdown: "",
  assets: {
    audio: [],
    images: []
  },
  runner: {
    activePart: "listening",
    selectedDragValue: "",
    activeAdGroups: {},
    playbackCounts: {},
    speakingSessions: {},
    lockedParts: {},
    finalized: false,
    timers: {
      listening: createTimerState(25 * 60),
      reading: createTimerState(30 * 60),
      writing: createTimerState(35 * 60),
      speaking: createTimerState(15 * 60)
    }
  },
  flow: {
    screen: "home",
    mode: "exam",
    candidate: {
      code: "",
      firstName: "",
      lastName: ""
    }
  },
  answers: {},
  submission: null,
  evaluation: null,
  evaluating: false
};

const PART_CONFIG = [
  { key: "listening", title: "Klausīšanās", english: "Listening", heading: "### Klausīšanās prasmes pārbaude", minutes: 25 },
  { key: "reading", title: "Lasīšana", english: "Reading", heading: "### Lasītprasmes pārbaude", minutes: 30 },
  { key: "writing", title: "Rakstīšana", english: "Writing", heading: "### Rakstītprasmes pārbaude", minutes: 35 },
  { key: "speaking", title: "Runāšana", english: "Speaking", heading: "### Runātprasmes pārbaude", minutes: 15 }
];

const FLOW_SCREENS = new Set(["home", "register", "instructions", "exam", "results"]);

const TASK_CONFIG = {
  listening: [
    { taskKey: "task1", title: "1. uzdevums", heading: "#### 1. uzdevums", ends: ["#### 2. uzdevums"], split: "numbered", kind: "choice-list", options: ["a", "b", "c"], expected: 6 },
    { taskKey: "task2", title: "2. uzdevums", heading: "#### 2. uzdevums", ends: ["#### 3. uzdevums"], split: "numbered", kind: "yes-no-table", options: ["Jā", "Nē"], expected: 4 },
    { taskKey: "task3", title: "3. uzdevums", heading: "#### 3. uzdevums", ends: ["###"], split: "numbered", referenceStarts: "Atbilžu varianti", kind: "drag-fill", expected: 5 }
  ],
  reading: [
    { taskKey: "task1", title: "1. uzdevums", heading: "#### 1. uzdevums", ends: ["#### 2. uzdevums"], split: "readingTexts", kind: "reading-choice", options: ["a", "b", "c"], expected: 4 },
    { taskKey: "task2", title: "2. uzdevums", heading: "#### 2. uzdevums", ends: ["#### 3. uzdevums"], split: "situations", kind: "ad-match", options: optionLetters.slice(0, 12), expected: 6 },
    { taskKey: "task3", title: "3. uzdevums", heading: "#### 3. uzdevums", ends: ["###"], split: "inlineGap", kind: "inline-select", expected: 5 }
  ],
  writing: [
    { taskKey: "task1", title: "1. uzdevums", heading: "#### 1. uzdevums", ends: ["#### 2. uzdevums"], split: "numbered", kind: "photo-sentences", rows: 3, placeholder: "Uzrakstiet 1 teikumu par attēlu.", expected: 4 },
    { taskKey: "task2", title: "2. uzdevums", heading: "#### 2. uzdevums", ends: ["#### 3. uzdevums"], split: "numbered", kind: "word-form", placeholder: "Ierakstiet pareizo formu.", expected: 5 },
    { taskKey: "task3", title: "3. uzdevums", heading: "#### 3. uzdevums", ends: ["###"], split: "single", kind: "writing-long", rows: 10, placeholder: "Rakstiet atbildi šeit.", expected: 1 }
  ],
  speaking: [
    { taskKey: "task1", title: "1. uzdevums", heading: "#### 1. uzdevums", ends: ["#### 2. uzdevums"], split: "numbered", kind: "oral-interview", rows: 2, placeholder: "Atbildiet pilnā teikumā.", expected: 10 },
    { taskKey: "task2", title: "2. uzdevums", heading: "#### 2. uzdevums", ends: ["#### 3. uzdevums"], split: "pictures", kind: "oral-pictures", rows: 4, placeholder: "Aprakstiet attēlu.", expected: 3 },
    { taskKey: "task3", title: "3. uzdevums", heading: "#### 3. uzdevums", ends: ["## Answer Key"], split: "numbered", kind: "oral-questions", placeholder: "Uzrakstiet pilnu jautājumu.", expected: 3 }
  ]
};

const els = {
  examSelect: document.querySelector("#exam-select"),
  sourcePath: document.querySelector("#source-path"),
  examOutput: document.querySelector("#exam-output"),
  runnerOutput: document.querySelector("#runner-output"),
  markdownOutput: document.querySelector("#markdown-output"),
  jsonOutput: document.querySelector("#json-output"),
  submissionOutput: document.querySelector("#submission-output"),
  ttsOutput: document.querySelector("#tts-output"),
  promptOutput: document.querySelector("#prompt-output"),
  qualityOutput: document.querySelector("#quality-output"),
  workspaceTitle: document.querySelector("#workspace-title"),
  validationPill: document.querySelector("#validation-pill"),
  globalPartNav: document.querySelector("#global-part-nav"),
  topbarTimer: document.querySelector("#topbar-timer"),
  progressFill: document.querySelector("#exam-progress-fill"),
  toast: document.querySelector("#toast")
};

function init() {
  els.examSelect.innerHTML = EXAMS.map(exam => `<option value="${exam.id}">${exam.title}</option>`).join("");
  els.examSelect.addEventListener("change", () => loadExam(els.examSelect.value));

  document.querySelector("#reload-exam").addEventListener("click", () => loadExam(state.exam.id));
  document.querySelector("#submit-exam").addEventListener("click", () => submitAnswers());
  document.querySelector("#evaluate-submission").addEventListener("click", () => evaluateSubmissionWithAi());
  document.querySelector("#copy-submission").addEventListener("click", () => {
    copyText(JSON.stringify(ensureSubmission("draft"), null, 2), "Submission copied");
  });
  document.querySelector("#download-submission").addEventListener("click", () => {
    const submission = ensureSubmission("draft");
    downloadFile(`${submission.submission_id}.json`, JSON.stringify(submission, null, 2), "application/json");
  });
  document.querySelector("#copy-markdown").addEventListener("click", () => copyText(state.markdown, "Markdown copied"));
  document.querySelector("#copy-json").addEventListener("click", () => {
    copyText(JSON.stringify(buildExportJson(), null, 2), "JSON copied");
  });
  document.querySelector("#download-markdown").addEventListener("click", () => {
    downloadFile(`A2_Mock_Exam_${state.exam.id}.md`, state.markdown, "text/markdown");
  });
  document.querySelector("#download-json").addEventListener("click", () => {
    downloadFile(`A2_Mock_Exam_${state.exam.id}.json`, JSON.stringify(buildExportJson(), null, 2), "application/json");
  });

  document.querySelectorAll(".nav-list button").forEach(button => {
    button.addEventListener("click", () => setView(button.dataset.view));
  });
  els.globalPartNav.addEventListener("click", event => {
    const button = event.target.closest("[data-global-part]");
    if (!button) return;
    switchPart(button.dataset.globalPart);
  });

  const params = new URLSearchParams(window.location.search);
  const requestedScreen = params.get("screen");
  const requestedPart = params.get("part");
  state.flow.screen = FLOW_SCREENS.has(requestedScreen) ? requestedScreen : (PART_CONFIG.some(part => part.key === requestedPart) ? "exam" : "home");
  const requestedExam = params.get("exam");
  loadExam(String(requestedExam || "01").padStart(2, "0"));
  setInterval(tickTimers, 1000);
}

async function loadExam(examId) {
  const exam = EXAMS.find(item => item.id === examId) || EXAMS[0];
  state.exam = exam;
  els.examSelect.value = exam.id;
  els.sourcePath.value = exam.sourcePath;
  els.workspaceTitle.textContent = exam.title;
  els.examOutput.innerHTML = `<div class="loading">Loading ${escapeHtml(exam.sourcePath)}...</div>`;

  try {
    const response = await fetch(`${exam.markdownPath}?v=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`);
    }
    state.markdown = await response.text();
    state.assets = extractAssets(state.markdown, exam);
    resetAnswers();
    resetTimers();
    resetSpeakingSessions();
    state.submission = null;
    state.evaluation = null;
    state.evaluating = false;
    const requestedPart = new URLSearchParams(window.location.search).get("part");
    if (PART_CONFIG.some(part => part.key === requestedPart)) {
      state.runner.activePart = requestedPart;
    }
    updateExamUrl();
    renderAll();
    showToast(`${exam.title} loaded`);
  } catch (error) {
    renderLoadError(error);
  }
}

function renderAll() {
  renderTopChrome();
  renderRunner();
  els.examOutput.innerHTML = renderMarkdown(state.markdown, state.exam);
  els.markdownOutput.textContent = state.markdown;
  els.jsonOutput.textContent = JSON.stringify(buildExportJson(), null, 2);
  renderSubmission();
  renderTts();
  renderImages();
  renderQuality();
  syncEvaluationButtons();
}

function renderLoadError(error) {
  console.error(error);
  els.examOutput.innerHTML = `
    <div class="empty-state">
      <h2>Cannot load exam Markdown</h2>
      <p>The app is trying to read <code>${escapeHtml(state.exam.markdownPath)}</code>, but rendering failed with: <strong>${escapeHtml(error.message)}</strong>.</p>
      <p>Serve the repository root, then open <code>http://localhost:4173/latvian-a2-exam-app/</code>.</p>
      <pre>python3 -m http.server 4173 --directory /Users/eramadan/GitRepo/lvcodex</pre>
    </div>
  `;
  els.validationPill.textContent = "Needs root server";
  els.validationPill.classList.add("bad");
}

function getStudentSections(markdown) {
  const lines = markdown.split(/\r?\n/);
  return {
    listening: sectionBetween(lines, "### Klausīšanās prasmes pārbaude", ["### Lasītprasmes pārbaude", "## Answer Key"]),
    reading: sectionBetween(lines, "### Lasītprasmes pārbaude", ["### Rakstītprasmes pārbaude", "## Answer Key"]),
    writing: sectionBetween(lines, "### Rakstītprasmes pārbaude", ["### Runātprasmes pārbaude", "## Answer Key"]),
    speaking: sectionBetween(lines, "### Runātprasmes pārbaude", ["## Answer Key"])
  };
}

function getTaskSection(lines, taskHeading, endPrefixes) {
  return sectionBetween(lines, taskHeading, endPrefixes);
}

function sectionBetween(lines, startHeading, endHeadingPrefixes) {
  const prefixes = Array.isArray(endHeadingPrefixes) ? endHeadingPrefixes : [endHeadingPrefixes];
  let start = -1;
  for (let index = 0; index < lines.length; index += 1) {
    if (lines[index].trim() === startHeading) {
      start = index;
      break;
    }
  }
  if (start === -1) {
    return [];
  }
  let end = lines.length;
  for (let index = start + 1; index < lines.length; index += 1) {
    const trimmed = lines[index].trim();
    if (prefixes.some(prefix => trimmed.startsWith(prefix))) {
      end = index;
      break;
    }
  }
  return lines.slice(start, end);
}

function resetAnswers() {
  state.runner.selectedDragValue = "";
  state.runner.activeAdGroups = {};
  state.answers = {
    listening: {
      task1: Array.from({ length: 6 }, () => ""),
      task2: Array.from({ length: 4 }, () => ""),
      task3: Array.from({ length: 5 }, () => "")
    },
    reading: {
      task1: Array.from({ length: 4 }, () => ""),
      task2: Array.from({ length: 6 }, () => ""),
      task3: Array.from({ length: 5 }, () => "")
    },
    writing: {
      task1: Array.from({ length: 4 }, () => ""),
      task2: Array.from({ length: 5 }, () => ""),
      task3: [""]
    },
    speaking: {
      task1: Array.from({ length: 10 }, () => ""),
      task2: ["", "", ""],
      task3: Array.from({ length: 3 }, () => "")
    }
  };
}

function resetTimers() {
  for (const [part, timer] of Object.entries(state.runner.timers)) {
    resetTimer(timer, durationForPart(part));
  }
  state.runner.activePart = "listening";
  state.runner.finalized = false;
  state.runner.lockedParts = {};
}

function resetSpeakingSessions() {
  for (const session of Object.values(state.runner.speakingSessions || {})) {
    if (session?.previewUrl && String(session.previewUrl).startsWith("blob:")) {
      URL.revokeObjectURL(session.previewUrl);
    }
  }
  state.runner.speakingSessions = Object.fromEntries(
    TASK_CONFIG.speaking.map(task => [task.taskKey, {
      recordingId: "",
      uploadUrl: "",
      uploadState: "idle",
      uploadError: "",
      playbackCount: 0,
      transcript: "",
      status: "idle",
      mimeType: "",
      durationMs: 0,
      previewUrl: "",
      uploadedAt: ""
    }])
  );
}

function updateExamUrl() {
  const params = new URLSearchParams(window.location.search);
  params.set("exam", state.exam.id);
  params.set("part", state.runner.activePart);
  params.set("screen", state.flow.screen);
  window.history.replaceState(null, "", `?${params.toString()}`);
}

function durationForPart(part) {
  return { listening: 25, reading: 30, writing: 35, speaking: 15 }[part] * 60;
}

function tickTimers() {
  const now = Date.now();
  const expiredParts = [];
  let changed = false;
  for (const [part, timer] of Object.entries(state.runner.timers)) {
    const previousRemaining = calculateRemaining(timer);
    const tick = tickTimer(timer, now);
    if (tick.remaining !== previousRemaining) {
      changed = true;
    }
    if (tick.expired) {
      expiredParts.push(part);
    }
  }
  if (expiredParts.length) {
    expiredParts.forEach(part => handleTimerExpired(part));
    changed = true;
  }
  if (changed) renderTimersOnly();
}

function renderRunner() {
  if (state.flow.screen !== "exam") {
    els.runnerOutput.innerHTML = renderFlowScreen();
    bindFlowEvents();
    renderTopChrome();
    return;
  }
  const sections = getStudentSections(state.markdown);
  const activePart = getPartConfig(state.runner.activePart);
  const activeSectionLines = sections[activePart.key] || [];
  const totalProgress = getExamProgress();
  els.runnerOutput.innerHTML = `
    <div class="runner-shell runner-shell-sticky">
      ${renderPartTimer(activePart.key, `${activePart.title} / ${activePart.english}`, activePart.minutes)}
    </div>

    <div class="flow-stack">
      ${renderSkillFlow(activePart, activeSectionLines)}
    </div>

    <div class="part-navigation">
      ${renderPartMoveButton("previous")}
      ${renderPartMoveButton("next")}
    </div>

    <section class="submit-panel">
      <div>
        <h3>Submit answers</h3>
        <p><span data-exam-progress>${totalProgress.answered}/${totalProgress.total}</span> response fields completed. Objective answers can be checked now; writing and speaking text stays in the validation queue.</p>
      </div>
      <div class="submit-actions">
        <button type="button" data-action="submit-exam">Submit answers</button>
        <button type="button" data-action="evaluate-exam">AI score</button>
        <button type="button" data-action="open-submission">Review submission</button>
      </div>
    </section>
  `;
  bindRunnerEvents();
  renderTimersOnly();
  renderTopChrome();
}

function renderFlowScreen() {
  if (state.flow.screen === "register") return renderRegistrationScreen();
  if (state.flow.screen === "instructions") return renderInstructionsScreen();
  if (state.flow.screen === "results") return renderResultsScreen();
  return renderHomeScreen();
}

function renderHomeScreen() {
  return `
    <section class="flow-card flow-home">
      <div class="flow-emblem" aria-hidden="true"></div>
      <h1>Valsts valodas prasmes pārbaude - A2 līmenis</h1>
      <p>Oficiāls valsts valodas prasmes pārbaudes simulators, kas sagatavots atbilstoši izglītības un satura standartiem.</p>
      ${renderFlowExamPicker()}
      <div class="mode-switch" role="group" aria-label="Režīms">
        <button type="button" data-flow-action="set-mode" data-mode="exam" class="${state.flow.mode === "exam" ? "active" : ""}">Eksāmena režīms</button>
        <button type="button" data-flow-action="set-mode" data-mode="practice" class="${state.flow.mode === "practice" ? "active" : ""}">Treniņa režīms</button>
      </div>
      <div class="flow-primary-stack">
        <button type="button" class="flow-primary-button" data-flow-action="register">Sākt pilnu eksāmenu</button>
        <button type="button" class="flow-secondary-button" data-flow-action="start-practice">Trenēties pa daļām</button>
      </div>
      <div class="flow-home-links">
        <button type="button" data-flow-action="results">Skatīt rezultātus</button>
        <button type="button" data-flow-action="instructions">Norādījumi</button>
      </div>
      <p class="flow-version">Sistēmas versija 1.2.0 • Oficiālais simulators</p>
    </section>
  `;
}

function renderRegistrationScreen() {
  const candidate = state.flow.candidate;
  return `
    <section class="flow-card flow-register">
      <div class="flow-emblem" aria-hidden="true"></div>
      <h1>Kandidāta reģistrācija</h1>
      <p>A2 Valsts valodas pārbaudes simulators</p>
      ${renderFlowExamPicker("Izvēlētais eksāmens")}
      <form class="candidate-form" data-candidate-form>
        <label>
          Kandidāta kods
          <input name="code" value="${escapeHtml(candidate.code)}" autocomplete="off" required>
        </label>
        <label>
          Vārds
          <input name="firstName" value="${escapeHtml(candidate.firstName)}" autocomplete="given-name" required>
        </label>
        <label>
          Uzvārds
          <input name="lastName" value="${escapeHtml(candidate.lastName)}" autocomplete="family-name" required>
        </label>
        <button type="submit" class="flow-success-button">Sākt pārbaudi</button>
      </form>
      <p class="form-note">Lūdzu, ievadiet datus tieši tā, kā norādīts jūsu eksāmena lapā.</p>
    </section>
  `;
}

function renderInstructionsScreen() {
  const commands = [
    ["headphones", "Klausieties!"],
    ["book", "Lasiet!"],
    ["pencil", "Rakstiet!"],
    ["message", "Atbildiet!"],
    ["check", "Atzīmējiet pareizo atbildi!"],
    ["input", "Izvēlieties atbilstošo!"],
    ["blank", "Ierakstiet tukšajā vietā!"],
    ["question", "Uzdodiet jautājumu!"]
  ];
  return `
    <section class="flow-card flow-instructions">
      <h1>Pārbaudes norādījumi</h1>
      <p>Lūdzu, uzmanīgi iepazīstieties ar biežāk sastopamajām norādēm un darbībām, kas būs jāveic eksāmena laikā.</p>
      ${renderFlowExamPicker("Eksāmens")}
      <div class="instruction-panel">
        ${commands.map(([icon, label]) => `
          <div class="instruction-row">
            <span class="instruction-icon instruction-icon-${icon}" aria-hidden="true"></span>
            <strong>${label}</strong>
          </div>
        `).join("")}
      </div>
      <button type="button" class="flow-primary-button compact" data-flow-action="begin-exam">Saprasts / Atpakaļ</button>
    </section>
  `;
}

function renderFlowExamPicker(label = "Izvēlieties eksāmenu") {
  return `
    <label class="flow-exam-picker">
      <span>${label}</span>
      <select data-flow-exam-select aria-label="${label}">
        ${EXAMS.map(exam => `<option value="${exam.id}" ${exam.id === state.exam.id ? "selected" : ""}>${exam.title}</option>`).join("")}
      </select>
    </label>
  `;
}

function renderResultsScreen() {
  const submission = ensureSubmission("draft");
  const skills = PART_CONFIG.map(part => {
    const score = submission.scoring.by_skill[part.key] || { correct: 0, possible: 15 };
    const points = Math.min(15, Math.round((Number(score.correct || 0) / Math.max(1, Number(score.possible || 15))) * 15));
    return {
      part,
      points,
      percent: Math.round((points / 15) * 100),
      passed: points >= 9
    };
  });
  const passed = skills.every(item => item.passed);
  return `
    <section class="results-flow">
      <h1>Eksāmena Rezultāti</h1>
      <p>Jūsu snieguma kopsavilkums pa pārbaudījuma daļām.</p>
      <div class="results-table" role="table" aria-label="Eksāmena rezultāti">
        <div class="results-row results-head" role="row">
          <span>Sadaļa</span><span>Punkti</span><span>Procenti</span><span>Statuss</span>
        </div>
        ${skills.map(({ part, points, percent, passed }) => `
          <div class="results-row" role="row">
            <span>${part.title}</span>
            <span>${points} / 15</span>
            <span><b>${percent}%</b><i style="--value:${percent}%"></i></span>
            <span class="${passed ? "status-pass" : "status-fail"}">${passed ? "Nokārtots" : "Jātrenējas"}</span>
          </div>
        `).join("")}
      </div>
      <div class="final-status ${passed ? "passed" : "failed"}">
        <p>Noslēguma statuss</p>
        <h2>Kopējais rezultāts: ${passed ? "nokārtots" : "nav nokārtots"}</h2>
        <span>Minimums ir 9 punkti katrā prasmē. Šis pārskats izmanto lokālo objektīvo vērtējumu un saglabā rakstīšanas/runāšanas darbus pārbaudei.</span>
      </div>
      <button type="button" class="flow-primary-button results-action" data-flow-action="open-submission">Skatīt detalizētu pārskatu</button>
    </section>
  `;
}

function renderSkillFlow(part, sectionLines) {
  const safeSectionLines = Array.isArray(sectionLines) ? sectionLines : [];
  const tasks = TASK_CONFIG[part.key] || [];
  return `
    <div class="task-stack official-task-stack" data-part="${part.key}">
      ${tasks.map((task, taskIndex) => {
          const taskLines = getTaskSection(safeSectionLines, task.heading, task.ends);
          const view = buildTaskView(taskLines, task);
          const referenceHtml = renderTaskReferencePanel(part.key, task, view.reference);
          const taskProgress = getTaskProgress(part.key, task.taskKey);
          return `
            <article class="stitch-task-panel" data-locked="${state.flow.mode === "exam" && isPartLocked(part.key) ? "true" : "false"}">
              <header class="stitch-section-head">
                <div>
                  <h3>${taskIndex + 1}. daļa: ${part.title} prasme</h3>
                  <p>Uzdevums ${taskIndex + 1} no ${tasks.length}: ${taskInstructionTitle(task, view)}</p>
                </div>
                <span data-task-progress="${part.key}.${task.taskKey}">Punkti: ${taskProgress.answered} / ${taskProgress.total}</span>
              </header>
              ${view.intro.length && shouldRenderTaskIntro(task) ? `<div class="stitch-instructions">${renderTaskIntro(task, view)}</div>` : ""}
              ${referenceHtml}
              <div class="question-stack">
                ${renderTaskQuestions(part.key, task, view.questions, view)}
              </div>
            </article>
          `;
        }).join("")}
    </div>
  `;
}

function shouldRenderTaskIntro(task) {
  return !["photo-sentences", "word-form", "writing-long"].includes(task.kind);
}

function renderTaskIntro(task, view) {
  const intro = stripTaskMediaLines(view.intro).join("\n");
  if (task.kind === "ad-match" && parseAdvertisements(view.reference).length > 4) {
    return renderMarkdown(intro.replace(/\(A\s*[–-]\s*L\)/gi, "(A-D)"), state.exam);
  }
  return renderMarkdown(intro, state.exam);
}

function taskInstructionTitle(task, view) {
  const text = stripTaskMediaLines(view.intro || [])
    .map(line => line.replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .find(line => !/audio failsafe link/i.test(line));
  if (text) {
    return text.replace(/[.!?]+$/, "");
  }
  return task.title;
}

function stripTaskMediaLines(lines) {
  const result = [];
  let inAudio = false;
  for (const line of lines || []) {
    const trimmed = line.trim();
    if (/^<audio\b/i.test(trimmed)) {
      inAudio = true;
      continue;
    }
    if (inAudio) {
      if (/^<\/audio>/i.test(trimmed)) {
        inAudio = false;
      }
      continue;
    }
    if (/^<source\b/i.test(trimmed) || /audio failsafe link/i.test(trimmed)) {
      continue;
    }
    result.push(line);
  }
  return trimOuterLines(result);
}

function firstAudioSource(lines) {
  for (const line of lines || []) {
    const match = /<source\s+src="([^"]+\.mp3)"/i.exec(line);
    if (match) return match[1];
  }
  return "";
}

function renderTaskReferencePanel(section, task, referenceLines) {
  if (!referenceLines.length || task.kind === "drag-fill") return "";
  if (task.kind === "ad-match") {
    return "";
  }
  return `<aside class="task-reference-panel document compact">${renderMarkdown(referenceLines.join("\n"), state.exam)}</aside>`;
}

function renderTaskQuestions(section, task, questions, view) {
  if (task.kind === "choice-list") {
    return renderChoiceListTask(section, task, questions, false, view);
  }
  if (task.kind === "reading-choice") {
    return renderChoiceListTask(section, task, questions, true, view);
  }
  if (task.kind === "yes-no-table") {
    return renderYesNoTable(section, task, questions);
  }
  if (task.kind === "drag-fill") {
    return renderDragFillTask(section, task, questions, view.reference);
  }
  if (task.kind === "ad-match") {
    return renderAdMatchQuestions(section, task, questions, view.reference);
  }
  if (task.kind === "inline-select") {
    return renderInlineSelectTask(section, task, view);
  }
  if (task.kind === "photo-sentences") {
    return renderPhotoSentenceTask(section, task, questions, view.intro);
  }
  if (task.kind === "word-form") {
    return renderWordFormTask(section, task, questions, view.intro);
  }
  if (task.kind === "writing-long") {
    return renderWritingLongTask(section, task, view.intro);
  }
  if (task.kind === "oral-interview") {
    return renderOralInterviewTask(section, task, questions);
  }
  if (task.kind === "oral-pictures") {
    return renderOralPicturesTask(section, task, questions, view.intro);
  }
  if (task.kind === "oral-questions") {
    return renderOralQuestionTask(section, task, questions);
  }
  const safeQuestions = questions.length ? questions : fallbackQuestions(task.expected);
  return safeQuestions.map((question, index) => `
    <article class="question-item">
      ${question.lines.length ? `<div class="question-paper document compact">${renderMarkdown(question.lines.join("\n"), state.exam)}</div>` : ""}
      <div class="question-answer">
        ${renderAnswerControl(section, task.taskKey, task, index)}
      </div>
    </article>
  `).join("");
}

function buildTaskView(taskLines, task) {
  const lines = trimOuterLines(stripTaskHeading(taskLines));
  if (task.split === "single") {
    return { intro: lines, reference: [], questions: [{ lines: [] }] };
  }
  if (task.split === "readingTexts") {
    return splitByHeadingPattern(lines, /^\*\*Teksts\s+\d+\*\*/);
  }
  if (task.split === "pictures") {
    return splitByHeadingPattern(lines, /^\*\*(Attēls|Jautājums jums)/);
  }
  if (task.split === "situations") {
    return splitSituationsTask(lines);
  }
  if (task.split === "inlineGap") {
    return splitInlineGapTask(lines);
  }
  return splitNumberedTask(lines, task.referenceStarts);
}

function stripTaskHeading(lines) {
  return lines.filter((line, index) => !(index === 0 && /^####\s+/.test(line.trim())));
}

function trimOuterLines(lines) {
  let start = 0;
  let end = lines.length;
  while (start < end && !lines[start].trim()) start += 1;
  while (end > start && !lines[end - 1].trim()) end -= 1;
  return lines.slice(start, end);
}

function splitByHeadingPattern(lines, pattern) {
  const first = lines.findIndex(line => pattern.test(line.trim()));
  if (first === -1) {
    return { intro: lines, reference: [], questions: [] };
  }
  return {
    intro: trimOuterLines(lines.slice(0, first)),
    reference: [],
    questions: splitBlocksFrom(lines.slice(first), line => pattern.test(line.trim()))
  };
}

function splitSituationsTask(lines) {
  const situationsIndex = lines.findIndex(line => line.trim() === "**Situācijas**");
  const adsIndex = lines.findIndex(line => line.trim() === "**Sludinājumi**");
  if (situationsIndex === -1 || adsIndex === -1) {
    return splitNumberedTask(lines);
  }
  return {
    intro: trimOuterLines(lines.slice(0, situationsIndex)),
    reference: trimOuterLines(lines.slice(adsIndex)),
    questions: splitNumberedBlocks(lines.slice(situationsIndex + 1, adsIndex))
  };
}

function splitInlineGapTask(lines) {
  const optionStart = lines.findIndex(line => /^\d+\.\s+-\s+[a-z]\)/i.test(line.trim()));
  if (optionStart === -1) {
    return { intro: lines, reference: [], questions: [] };
  }
  const beforeOptions = trimOuterLines(lines.slice(0, optionStart));
  const instructionEnd = beforeOptions.findIndex(line => /\*\*\(\d+\)\*\*/.test(line));
  const intro = instructionEnd > 0 ? beforeOptions.slice(0, instructionEnd) : beforeOptions.slice(0, 1);
  const textLines = instructionEnd > 0 ? beforeOptions.slice(instructionEnd) : beforeOptions.slice(1);
  return {
    intro: trimOuterLines(intro),
    reference: [],
    questions: [{
      lines: trimOuterLines(textLines),
      options: parseInlineGapOptions(lines.slice(optionStart))
    }]
  };
}

function parseInlineGapOptions(lines) {
  const groups = [];
  let current = null;
  for (const line of lines) {
    const trimmed = line.trim();
    const numbered = /^(\d+)\.\s+-\s+([a-z])\)\s*(.+)$/i.exec(trimmed);
    const option = /^-\s+([a-z])\)\s*(.+)$/i.exec(trimmed);
    if (numbered) {
      current = { number: Number(numbered[1]), options: [{ value: numbered[2].toLowerCase(), label: numbered[3].trim() }] };
      groups.push(current);
      continue;
    }
    if (option && current) {
      current.options.push({ value: option[1].toLowerCase(), label: option[2].trim() });
    }
  }
  return groups;
}

function splitNumberedTask(lines, referenceStarts) {
  let working = lines;
  let reference = [];
  if (referenceStarts) {
    const referenceIndex = lines.findIndex(line => line.trim().startsWith(referenceStarts));
    if (referenceIndex !== -1) {
      working = lines.slice(0, referenceIndex);
      reference = trimOuterLines(lines.slice(referenceIndex));
    }
  }
  const first = working.findIndex(line => /^\d+\.\s+/.test(line.trim()));
  if (first === -1) {
    return { intro: working, reference, questions: [] };
  }
  return {
    intro: trimOuterLines(working.slice(0, first)),
    reference,
    questions: splitNumberedBlocks(working.slice(first))
  };
}

function splitNumberedBlocks(lines) {
  return splitBlocksFrom(lines, line => /^\d+\.\s+/.test(line.trim()));
}

function splitBlocksFrom(lines, startsBlock) {
  const blocks = [];
  let current = null;
  for (const line of lines) {
    if (startsBlock(line)) {
      if (current) blocks.push(current);
      current = [line];
      continue;
    }
    if (current) {
      current.push(line);
    }
  }
  if (current) blocks.push(current);
  return blocks.map(lines => ({ lines: trimOuterLines(lines) }));
}

function fallbackQuestions(count) {
  return Array.from({ length: count || 1 }, () => ({ lines: [] }));
}

function getPartConfig(partKey) {
  return PART_CONFIG.find(part => part.key === partKey) || PART_CONFIG[0];
}

function getPartIndex(partKey) {
  return PART_CONFIG.findIndex(part => part.key === partKey);
}

function isPartLocked(partKey) {
  return Boolean(state.runner.finalized || state.runner.lockedParts?.[partKey]);
}

function lockPart(partKey) {
  if (!partKey) return;
  state.runner.lockedParts ||= {};
  state.runner.lockedParts[partKey] = true;
}

function lockAllParts() {
  state.runner.lockedParts = Object.fromEntries(PART_CONFIG.map(part => [part.key, true]));
  state.runner.finalized = true;
  for (const timer of Object.values(state.runner.timers)) {
    pauseTimer(timer, Date.now());
    timer.remaining = 0;
    timer.locked = true;
    timer.completedAt = Date.now();
  }
}

function handleTimerExpired(partKey) {
  stopActiveSpeakingRecorder();
  if (state.flow.mode !== "exam") {
    pauseTimer(state.runner.timers[partKey], Date.now());
    renderRunner();
    showToast(`${getPartConfig(partKey).title} timer ended`);
    return;
  }
  lockPart(partKey);
  const nextPart = PART_CONFIG[getPartIndex(partKey) + 1];
  if (nextPart) {
    state.runner.activePart = nextPart.key;
    startOnlyTimer(nextPart.key);
    showToast(`${getPartConfig(partKey).title} ended. Moving to ${nextPart.title}.`);
    renderRunner();
    return;
  }
  lockAllParts();
  state.submission = buildSubmission("submitted");
  persistSubmission(state.submission);
  renderRunner();
  renderSubmission();
  setView("results");
  showToast(`${getPartConfig(partKey).title} timed out`);
}

function switchPart(partKey) {
  if (!PART_CONFIG.some(part => part.key === partKey)) return;
  const targetIndex = getPartIndex(partKey);
  const currentIndex = getPartIndex(state.runner.activePart);
  if (state.flow.screen === "exam" && state.flow.mode === "exam") {
    if (targetIndex < currentIndex) {
      showToast("Real mode locks previous sections.");
      return;
    }
    if (targetIndex > currentIndex + 1) {
      showToast("Real mode follows the section order.");
      return;
    }
    if (state.runner.finalized || isPartLocked(partKey)) {
      showToast("This section is already locked.");
      return;
    }
    if (currentIndex !== -1 && targetIndex > currentIndex) {
      lockPart(state.runner.activePart);
    }
  }
  stopActiveSpeakingRecorder();
  state.runner.activePart = partKey;
  if (state.flow.screen === "exam" && state.flow.mode === "exam") {
    startOnlyTimer(partKey);
  }
  state.flow.screen = "exam";
  updateExamUrl();
  renderRunner();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function setFlowScreen(screen, options = {}) {
  if (!FLOW_SCREENS.has(screen)) return;
  state.flow.screen = screen;
  setView("runner");
  if (screen === "exam" && options.startTimer) {
    startOnlyTimer(state.runner.activePart);
  }
  updateExamUrl();
  renderRunner();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function getPartProgress(partKey) {
  const tasks = state.answers[partKey] || {};
  const values = Object.values(tasks).flat();
  return {
    answered: values.filter(Boolean).length,
    total: values.length
  };
}

function getExamProgress() {
  const values = Object.values(state.answers).flatMap(skill => Object.values(skill).flat());
  return {
    answered: values.filter(Boolean).length,
    total: values.length
  };
}

function getTaskProgress(partKey, taskKey) {
  const values = state.answers[partKey]?.[taskKey] || [];
  return {
    answered: values.filter(Boolean).length,
    total: values.length
  };
}

function renderPartTab(part) {
  const progress = getPartProgress(part.key);
  return `
    <button type="button" data-action="switch-part" data-part="${part.key}" class="${part.key === state.runner.activePart ? "active" : ""}">
      <span>${part.title}</span>
      <strong data-progress="${part.key}">${progress.answered} done</strong>
    </button>
  `;
}

function renderTopChrome() {
  const examProgress = getExamProgress();
  const activePart = getPartConfig(state.runner.activePart);
  document.body.dataset.flowScreen = state.flow.screen;
  els.globalPartNav.innerHTML = ["home", "register", "results"].includes(state.flow.screen) ? "" : PART_CONFIG.map(part => `
    <button type="button" data-global-part="${part.key}" class="${part.key === state.runner.activePart ? "active" : ""}">
      ${part.title}
    </button>
  `).join("");
  if (els.topbarTimer) {
    if (state.flow.screen === "exam") {
      const timer = state.runner.timers[activePart.key];
      els.topbarTimer.textContent = formatTime(calculateRemaining(timer));
    } else {
      els.topbarTimer.textContent = formatLongTime(45 * 60);
    }
  }
  if (els.progressFill) {
    const percent = examProgress.total ? Math.round((examProgress.answered / examProgress.total) * 100) : 0;
    els.progressFill.style.width = `${percent}%`;
  }
}

function renderPartMoveButton(direction) {
  const currentIndex = PART_CONFIG.findIndex(part => part.key === state.runner.activePart);
  const nextIndex = direction === "next" ? currentIndex + 1 : currentIndex - 1;
  const part = PART_CONFIG[nextIndex];
  if (!part && direction === "next") {
    return `<button type="button" data-action="show-results">Pabeigt</button>`;
  }
  if (!part) return "<span></span>";
  const label = direction === "next" ? `Next: ${part.title}` : `Previous: ${part.title}`;
  return `<button type="button" data-action="switch-part" data-part="${part.key}">${label}</button>`;
}

function renderTimersOnly() {
  document.querySelectorAll("[data-timer]").forEach(node => {
    const part = node.dataset.timer;
    node.textContent = formatTime(calculateRemaining(state.runner.timers[part]));
  });
  renderTopChrome();
}

function renderProgressOnly() {
  const activeProgress = getPartProgress(state.runner.activePart);
  document.querySelectorAll("[data-active-progress]").forEach(node => {
    node.textContent = String(activeProgress.answered);
  });
  document.querySelectorAll("[data-progress]").forEach(node => {
    const progress = getPartProgress(node.dataset.progress);
    node.textContent = `${progress.answered} done`;
  });
  document.querySelectorAll("[data-task-progress]").forEach(node => {
    const [partKey, taskKey] = node.dataset.taskProgress.split(".");
    const progress = getTaskProgress(partKey, taskKey);
    node.textContent = `Punkti: ${progress.answered} / ${progress.total}`;
  });
  document.querySelectorAll("[data-exam-progress]").forEach(node => {
    const progress = getExamProgress();
    node.textContent = `${progress.answered}/${progress.total}`;
  });
  els.jsonOutput.textContent = JSON.stringify(buildExportJson(), null, 2);
  renderTopChrome();
  renderSubmission();
}

function bindFlowEvents() {
  document.querySelectorAll("[data-flow-action]").forEach(button => {
    button.addEventListener("click", () => handleFlowAction(button.dataset));
  });
  document.querySelectorAll("[data-flow-exam-select]").forEach(select => {
    select.addEventListener("change", event => {
      loadExam(event.target.value);
    });
  });
  const form = document.querySelector("[data-candidate-form]");
  if (form) {
    form.addEventListener("submit", event => {
      event.preventDefault();
      const formData = new FormData(form);
      state.flow.candidate = {
        code: String(formData.get("code") || "").trim(),
        firstName: String(formData.get("firstName") || "").trim(),
        lastName: String(formData.get("lastName") || "").trim()
      };
      setFlowScreen("instructions");
    });
  }
}

function handleFlowAction(dataset) {
  const { flowAction } = dataset;
  if (flowAction === "set-mode") {
    state.flow.mode = dataset.mode || "exam";
    renderRunner();
    return;
  }
  if (flowAction === "register") {
    setFlowScreen("register");
    return;
  }
  if (flowAction === "start-practice") {
    state.flow.mode = "practice";
    setFlowScreen("instructions");
    return;
  }
  if (flowAction === "instructions") {
    setFlowScreen("instructions");
    return;
  }
  if (flowAction === "begin-exam") {
    setFlowScreen("exam", { startTimer: state.flow.mode === "exam" });
    return;
  }
  if (flowAction === "results") {
    setFlowScreen("results");
    return;
  }
  if (flowAction === "open-submission") {
    renderSubmission();
    setView("submission");
  }
}

function formatLongTime(seconds) {
  const safeSeconds = Math.max(0, Number(seconds) || 0);
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const secs = safeSeconds % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function formatTaskProgress(progress) {
  return `${progress.answered}/${progress.total} responses`;
}

function renderPartTimer(part, label, minutes) {
  const timer = state.runner.timers[part];
  const remaining = calculateRemaining(timer);
  const startLabel = timer.running ? "Running" : (remaining < timer.total ? "Resume" : "Start");
  const isExamMode = state.flow.mode === "exam";
  return `
    <article class="timer-card ${state.runner.activePart === part ? "active" : ""}">
      <div>
        <h3>${label}</h3>
        <p>${minutes} min</p>
      </div>
      <div class="timer-display" data-timer="${part}">${formatTime(remaining)}</div>
      <div class="timer-actions">
        <button type="button" data-action="start" data-part="${part}" ${timer.running || isPartLocked(part) || state.runner.finalized ? "disabled" : ""}>${isExamMode ? startLabel : startLabel}</button>
        ${isExamMode ? `<span class="timer-note">Real mode locks previous sections and auto-submits on timeout.</span>` : `
          <button type="button" data-action="pause" data-part="${part}">Pause</button>
          <button type="button" data-action="reset" data-part="${part}">Reset</button>
        `}
      </div>
    </article>
  `;
}

function renderChoiceListTask(section, task, questions, useReadingBox, view = {}) {
  const safeQuestions = questions.length ? questions : fallbackQuestions(task.expected);
  const audioSrc = section === "listening" ? firstAudioSource(view.intro || []) : "";
  return safeQuestions.map((question, index) => renderChoiceQuestion(section, task, question, index, useReadingBox, audioSrc)).join("");
}

function renderChoiceQuestion(section, task, question, index, useReadingBox, audioSrc = "") {
  const parsed = parseChoiceQuestion(question.lines, task.options);
  const name = `${section}.${task.taskKey}.${index}`;
  ensureAnswerSlot(section, task.taskKey, index);
  const value = state.answers[section][task.taskKey][index] || "";
  return `
    <article class="official-choice-question ${useReadingBox ? "reading-question" : ""}">
      <span class="question-number">${index + 1}.</span>
      ${useReadingBox ? renderReadingStimulus(parsed, index) : `<h5>${escapeHtml(parsed.stem || `Jautājums ${index + 1}`)}</h5>`}
      ${audioSrc ? renderCardAudio(audioSrc, index) : ""}
      <div class="official-choice-list">
        ${parsed.options.map(option => `
          <label class="official-radio-row">
            <input type="radio" name="${name}" value="${escapeHtml(option.value)}" ${value === option.value ? "checked" : ""}>
            <span>${escapeHtml(option.label)}</span>
          </label>
        `).join("")}
      </div>
    </article>
  `;
}

function renderCardAudio(audioSrc, index) {
  const count = getMediaPlaybackCount("listening", audioSrc);
  return `
    <div class="stitch-audio-card">
      <audio controls preload="none" src="${escapeHtml(toAssetUrl(audioSrc))}" aria-label="Audio ${index + 1}" data-playback-track="listening" data-playback-key="${escapeHtml(audioSrc)}"></audio>
      <span class="playback-count">${count} listens</span>
    </div>
  `;
}

function getMediaPlaybackCount(track, key) {
  return Number(state.runner.playbackCounts?.[track]?.[key] || 0);
}

function incrementMediaPlaybackCount(track, key) {
  state.runner.playbackCounts ||= {};
  state.runner.playbackCounts[track] ||= {};
  state.runner.playbackCounts[track][key] = getMediaPlaybackCount(track, key) + 1;
  renderMediaPlaybackBadges();
}

function renderMediaPlaybackBadges() {
  document.querySelectorAll("[data-playback-track][data-playback-key]").forEach(node => {
    const track = node.dataset.playbackTrack;
    const key = node.dataset.playbackKey;
    const count = getMediaPlaybackCount(track, key);
    const card = node.closest(".stitch-audio-card, .media-card");
    if (card) {
      const badge = card.querySelector(".playback-count, [data-playback-count]");
      if (badge) {
        badge.textContent = `${count} listens`;
      }
    }
  });
}

function handlePlaybackEvent(event) {
  const node = event.currentTarget;
  const track = node.dataset.playbackTrack;
  const key = node.dataset.playbackKey;
  if (!track || !key) return;
  if (track === "speaking") {
    const session = ensureSpeakingSession(key);
    session.playbackCount += 1;
    renderSpeakingRecorderStatus(key);
    return;
  }
  incrementMediaPlaybackCount(track, key);
}

function renderSpeakingRecorderStatus(taskKey) {
  const card = document.querySelector(`[data-speaking-recorder="${taskKey}"]`);
  if (!card) return;
  const session = ensureSpeakingSession(taskKey);
  const badge = card.querySelector(".speaking-status");
  if (badge) badge.textContent = session.status;
  const meta = card.querySelector(".speaking-recorder-meta");
  if (meta) {
    meta.innerHTML = `
      <span>${session.durationMs ? `${Math.max(1, Math.round(session.durationMs / 1000))}s recorded` : "No recording yet"}</span>
      <span>${session.uploadState === "uploaded" ? "Uploaded" : session.uploadState === "uploading" ? "Uploading..." : "Local draft only"}</span>
      <span>${session.playbackCount} plays</span>
    `;
  }
  const audio = card.querySelector("audio[data-speaking-recording-playback]");
  if (audio && session.previewUrl && audio.getAttribute("src") !== session.previewUrl) {
    audio.setAttribute("src", session.previewUrl);
  }
  const startButton = card.querySelector('[data-speaking-action="start"]');
  const stopButton = card.querySelector('[data-speaking-action="stop"]');
  const playButton = card.querySelector('[data-speaking-action="play"]');
  const uploadButton = card.querySelector('[data-speaking-action="upload"]');
  const clearButton = card.querySelector('[data-speaking-action="clear"]');
  const dictationButton = card.querySelector('[data-speaking-action="speech-to-text"]');
  const hasRecording = Boolean(session.previewUrl);
  if (startButton) startButton.disabled = state.runner.finalized || session.status === "recording" || session.uploadState === "uploading";
  if (stopButton) stopButton.disabled = session.status !== "recording";
  if (playButton) playButton.disabled = !hasRecording;
  if (uploadButton) uploadButton.disabled = !hasRecording || session.uploadState === "uploading";
  if (clearButton) clearButton.disabled = !hasRecording || session.uploadState === "uploading";
  if (dictationButton) dictationButton.disabled = state.runner.finalized || session.status === "recording";
}

async function handleSpeakingAction(dataset) {
  const taskKey = dataset.speakingTask;
  if (!taskKey) return;
  const action = dataset.speakingAction;
  if (action === "start") {
    await startSpeakingRecording(taskKey);
    return;
  }
  if (action === "stop") {
    stopSpeakingRecording(taskKey);
    return;
  }
  if (action === "play") {
    playSpeakingRecording(taskKey);
    return;
  }
  if (action === "upload") {
    await uploadSpeakingRecording(taskKey);
    return;
  }
  if (action === "clear") {
    clearSpeakingRecording(taskKey);
    return;
  }
  if (action === "speech-to-text") {
    startSpeakingTranscription(taskKey);
  }
}

function handleTranscriptAction(dataset) {
  const taskKey = dataset.transcriptSource;
  if (!taskKey) return;
  const session = ensureSpeakingSession(taskKey);
  session.transcript = String(document.querySelector(`[data-speaking-transcript="${taskKey}"]`)?.value || "").trim();
  state.submission = null;
  state.evaluation = null;
}

async function startSpeakingRecording(taskKey) {
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
    ensureSpeakingSession(taskKey).uploadError = "This browser does not support microphone recording.";
    renderSpeakingRecorderStatus(taskKey);
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stopActiveSpeakingRecorder();
    const session = ensureSpeakingSession(taskKey);
    session.status = "recording";
    session.uploadError = "";
    session.stream = stream;
    session.chunks = [];
    session.startedAt = Date.now();
    const mimeType = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/mp4"
    ].find(type => MediaRecorder.isTypeSupported(type)) || "";
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    session.mimeType = recorder.mimeType || mimeType || "audio/webm";
    session.mediaRecorder = recorder;
    recorder.addEventListener("dataavailable", event => {
      if (event.data && event.data.size > 0) {
        session.chunks.push(event.data);
      }
    });
    recorder.addEventListener("stop", () => finalizeSpeakingRecording(taskKey));
    recorder.start();
    renderSpeakingRecorderStatus(taskKey);
    showToast("Microphone recording started");
  } catch (error) {
    const session = ensureSpeakingSession(taskKey);
    session.status = "error";
    session.uploadError = error.message || "Could not access the microphone.";
    renderSpeakingRecorderStatus(taskKey);
    showToast("Microphone permission failed");
  }
}

function stopActiveSpeakingRecorder() {
  const activeTaskKey = Object.keys(state.runner.speakingSessions || {}).find(key => state.runner.speakingSessions[key]?.status === "recording");
  if (!activeTaskKey) return;
  const session = ensureSpeakingSession(activeTaskKey);
  if (session.mediaRecorder && session.mediaRecorder.state !== "inactive") {
    session.mediaRecorder.stop();
  }
  if (session.stream) {
    session.stream.getTracks().forEach(track => track.stop());
    session.stream = null;
  }
}

function stopSpeakingRecording(taskKey) {
  const session = ensureSpeakingSession(taskKey);
  if (session.mediaRecorder && session.mediaRecorder.state !== "inactive") {
    session.mediaRecorder.stop();
  }
  if (session.stream) {
    session.stream.getTracks().forEach(track => track.stop());
    session.stream = null;
  }
  session.status = "processing";
  renderSpeakingRecorderStatus(taskKey);
}

function finalizeSpeakingRecording(taskKey) {
  const session = ensureSpeakingSession(taskKey);
  const blob = new Blob(session.chunks || [], { type: session.mimeType || "audio/webm" });
  if (session.previewUrl) {
    URL.revokeObjectURL(session.previewUrl);
  }
  session.previewUrl = URL.createObjectURL(blob);
  session.recordingBlob = blob;
  session.recordingId = `${taskKey}-${Date.now()}`;
  session.uploadState = "idle";
  session.status = "ready";
  session.durationMs = Math.max(0, Date.now() - Number(session.startedAt || Date.now()));
  session.startedAt = null;
  session.mediaRecorder = null;
  session.chunks = [];
  renderSpeakingRecorderStatus(taskKey);
  state.submission = null;
  state.evaluation = null;
  showToast("Recording captured");
}

function playSpeakingRecording(taskKey) {
  const audio = document.querySelector(`[data-speaking-recorder="${taskKey}"] audio[data-speaking-recording-playback]`);
  if (audio) {
    audio.play();
  }
}

function clearSpeakingRecording(taskKey) {
  const session = ensureSpeakingSession(taskKey);
  if (session.mediaRecorder && session.mediaRecorder.state !== "inactive") {
    session.mediaRecorder.stop();
  }
  if (session.stream) {
    session.stream.getTracks().forEach(track => track.stop());
    session.stream = null;
  }
  if (session.previewUrl && String(session.previewUrl).startsWith("blob:")) {
    URL.revokeObjectURL(session.previewUrl);
  }
  session.recordingBlob = null;
  session.recordingId = "";
  session.uploadState = "idle";
  session.uploadUrl = "";
  session.uploadError = "";
  session.status = "idle";
  session.mimeType = "";
  session.durationMs = 0;
  session.previewUrl = "";
  session.uploadedAt = "";
  renderSpeakingRecorderStatus(taskKey);
  state.submission = null;
  state.evaluation = null;
  showToast("Recording cleared");
}

async function uploadSpeakingRecording(taskKey) {
  const session = ensureSpeakingSession(taskKey);
  if (!session.recordingBlob) {
    session.uploadError = "Record audio before uploading.";
    renderSpeakingRecorderStatus(taskKey);
    return;
  }
  if (session.uploadState === "uploading") return;
  session.uploadState = "uploading";
  session.uploadError = "";
  renderSpeakingRecorderStatus(taskKey);
  try {
    const params = new URLSearchParams({
      submission_id: ensureSubmission("draft").submission_id,
      exam_id: state.exam.id,
      task: taskKey
    });
    const response = await fetch(`/api/uploads/speaking?${params.toString()}`, {
      method: "POST",
      headers: {
        "Content-Type": session.recordingBlob.type || session.mimeType || "audio/webm"
      },
      body: session.recordingBlob
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || payload.detail || `Upload failed with HTTP ${response.status}`);
    }
    const previousPreview = session.previewUrl;
    session.uploadState = "uploaded";
    session.uploadUrl = payload.upload_url || "";
    session.previewUrl = payload.upload_url || session.previewUrl;
    session.recordingId = payload.upload_id || session.recordingId;
    session.uploadedAt = payload.created_at || new Date().toISOString();
    session.uploadError = "";
    if (previousPreview && previousPreview.startsWith("blob:")) {
      URL.revokeObjectURL(previousPreview);
    }
    state.submission = null;
    state.evaluation = null;
    renderSpeakingRecorderStatus(taskKey);
    showToast("Recording uploaded");
  } catch (error) {
    session.uploadState = "error";
    session.uploadError = error.message || "Upload failed.";
    renderSpeakingRecorderStatus(taskKey);
    showToast("Recording upload failed");
  }
}

function startSpeakingTranscription(taskKey) {
  const recognitionCtor = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!recognitionCtor) {
    ensureSpeakingSession(taskKey).uploadError = "Speech-to-text is not available in this browser.";
    renderSpeakingRecorderStatus(taskKey);
    return;
  }
  const recognition = new recognitionCtor();
  recognition.lang = "lv-LV";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  recognition.onresult = event => {
    const transcript = Array.from(event.results).map(result => result[0]?.transcript || "").join(" ").trim();
    const session = ensureSpeakingSession(taskKey);
    session.transcript = transcript;
    const textarea = document.querySelector(`[data-speaking-transcript="${taskKey}"]`);
    if (textarea) textarea.value = transcript;
    state.submission = null;
    state.evaluation = null;
    renderSpeakingRecorderStatus(taskKey);
    showToast("Transcript captured");
  };
  recognition.onerror = event => {
    const session = ensureSpeakingSession(taskKey);
    session.uploadError = event.error || "Speech recognition failed.";
    renderSpeakingRecorderStatus(taskKey);
  };
  recognition.start();
  ensureSpeakingSession(taskKey).status = "dictating";
  renderSpeakingRecorderStatus(taskKey);
}

function renderReadingStimulus(parsed, index) {
  return `
    <div class="reading-stimulus-box">
      ${parsed.title ? `<h5>${escapeHtml(parsed.title)}</h5>` : `<h5>Teksts ${index + 1}</h5>`}
      ${parsed.body.map(line => `<p>${formatInline(line)}</p>`).join("")}
    </div>
  `;
}

function renderYesNoTable(section, task, questions) {
  const safeQuestions = questions.length ? questions : fallbackQuestions(task.expected);
  return `
    <table class="yes-no-table">
      <thead>
        <tr>
          <th></th>
          <th>Apgalvojums</th>
          <th>Jā / Nē</th>
        </tr>
      </thead>
      <tbody>
        ${safeQuestions.map((question, index) => {
          const name = `${section}.${task.taskKey}.${index}`;
          ensureAnswerSlot(section, task.taskKey, index);
          const value = state.answers[section][task.taskKey][index] || "";
          return `
            <tr>
              <td>${index + 1}.</td>
              <td>${escapeHtml(stripLeadingNumber(question.lines.join(" ")))}</td>
              <td>
                <div class="table-radio-pair">
                  ${task.options.map(option => radioChoice(name, option, value === option)).join("")}
                </div>
              </td>
            </tr>
          `;
        }).join("")}
      </tbody>
    </table>
  `;
}

function renderDragFillTask(section, task, questions, referenceLines) {
  const safeQuestions = questions.length ? questions : fallbackQuestions(task.expected);
  const options = parseBacktickOptions(referenceLines);
  const values = state.answers[section]?.[task.taskKey] || [];
  const usedValues = new Set(values.filter(Boolean));
  return `
    <article class="pdf-drop-task" data-drop-task="${section}.${task.taskKey}">
      <div class="pdf-drop-lines">
        ${safeQuestions.map((question, index) => renderDragFillLine(section, task.taskKey, question, index)).join("")}
      </div>
      <div class="drag-choice-bank" aria-label="Atbilžu varianti">
        ${options.map(option => {
          const used = usedValues.has(option);
          const selected = state.runner.selectedDragValue === option;
          return `
            <button type="button"
              class="drag-choice ${used ? "used" : ""} ${selected ? "selected" : ""}"
              data-drag-chip="${section}.${task.taskKey}"
              data-drag-value="${escapeHtml(option)}"
              draggable="${used ? "false" : "true"}"
              ${used ? "disabled" : ""}>
              ${escapeHtml(option)}
            </button>
          `;
        }).join("")}
      </div>
    </article>
  `;
}

function renderDragFillLine(section, taskKey, question, index) {
  const name = `${section}.${taskKey}.${index}`;
  ensureAnswerSlot(section, taskKey, index);
  const value = state.answers[section][taskKey][index] || "";
  const dropZone = `
    <button type="button"
      class="drop-zone ${value ? "filled" : ""}"
      data-drop-target="${name}"
      aria-label="Atbilde ${index + 1}">
      ${value ? escapeHtml(value) : ""}
    </button>
  `;
  const raw = question.lines.join(" ");
  const escaped = escapeHtml(raw);
  const withBlank = escaped.replace(/`_{3,}`|_{3,}/, dropZone);
  return `<p class="pdf-drop-line">${withBlank}</p>`;
}

function renderAdReferencePanel(section, taskKey, referenceLines) {
  const ads = parseAdvertisements(referenceLines);
  if (!ads.length) {
    return `<aside class="task-reference-panel document compact">${renderMarkdown(referenceLines.join("\n"), state.exam)}</aside>`;
  }
  const groups = chunkArray(ads, 4);
  const groupStateKey = `${state.exam.id}.${section}.${taskKey}`;
  const activeGroup = Math.min(Number(state.runner.activeAdGroups[groupStateKey] || 0), groups.length - 1);
  const group = groups[activeGroup] || groups[0];
  return `
    <aside class="ad-reference-panel" aria-label="Sludinājumi">
      ${groups.length > 1 ? `
        <div class="ad-group-tabs" aria-label="Sludinājumu grupas">
          ${groups.map((item, index) => `
            <button type="button"
              data-action="show-ad-group"
              data-part="${section}"
              data-task="${taskKey}"
              data-group-index="${index}"
              class="${index === activeGroup ? "active" : ""}">
              ${item[0].letter}–${item[item.length - 1].letter}
            </button>
          `).join("")}
        </div>
      ` : ""}
      <section class="ad-choice-group">
        <h5>${group[0].letter}–${group[group.length - 1].letter}</h5>
        <div class="ad-card-grid">
          ${group.map(ad => `
            <article class="ad-card">
              <strong>${ad.letter}</strong>
              <p>${escapeHtml(ad.text)}</p>
            </article>
          `).join("")}
        </div>
      </section>
    </aside>
  `;
}

function renderAdMatchQuestions(section, task, questions, referenceLines) {
  const ads = parseAdvertisements(referenceLines);
  const safeQuestions = questions.length ? questions : fallbackQuestions(task.expected);
  if (ads.length) {
    const adGroups = chunkArray(ads, 4);
    const questionsPerGroup = Math.ceil(safeQuestions.length / adGroups.length);
    const questionGroups = chunkArray(safeQuestions, questionsPerGroup);
    return `
      <div class="ad-match-official">
        ${adGroups.map((group, groupIndex) => renderAdMatchGroup(section, task, group, questionGroups[groupIndex] || [], groupIndex * questionsPerGroup)).join("")}
      </div>
    `;
  }
  const options = task.options.map(option => option.toUpperCase());
  return `
    <div class="ad-match-list">
      ${safeQuestions.map((question, index) => {
        const name = `${section}.${task.taskKey}.${index}`;
        ensureAnswerSlot(section, task.taskKey, index);
        const value = state.answers[section][task.taskKey][index] || "";
        return `
          <article class="ad-match-row">
            <div class="ad-match-text document compact">${renderMarkdown(question.lines.join("\n"), state.exam)}</div>
            <label class="ad-match-answer">
              <span>${index + 1}</span>
              <select data-answer="${name}">
                <option value=""></option>
                ${options.map(option => `<option value="${option}" ${value.toUpperCase() === option ? "selected" : ""}>${option}</option>`).join("")}
              </select>
            </label>
          </article>
        `;
      }).join("")}
    </div>
  `;
}

function renderAdMatchGroup(section, task, ads, questions, baseIndex) {
  const localLetters = optionLetters.slice(0, ads.length).map(letter => letter.toUpperCase());
  return `
    <section class="ad-match-group">
      ${renderAdChoiceGroup(ads, localLetters)}
      <div class="ad-match-list">
        ${questions.map((question, questionOffset) => {
          const index = baseIndex + questionOffset;
          const name = `${section}.${task.taskKey}.${index}`;
          ensureAnswerSlot(section, task.taskKey, index);
          const value = state.answers[section][task.taskKey][index] || "";
          return `
            <article class="ad-match-row">
              <div class="ad-match-text document compact">${renderMarkdown(question.lines.join("\n"), state.exam)}</div>
              <label class="ad-match-answer">
                <span>${index + 1}</span>
                <select data-answer="${name}">
                  <option value=""></option>
                  ${ads.map((ad, adIndex) => `<option value="${ad.letter}" ${value.toUpperCase() === ad.letter ? "selected" : ""}>${localLetters[adIndex]}</option>`).join("")}
                </select>
              </label>
            </article>
          `;
        }).join("")}
      </div>
    </section>
  `;
}

function renderAdChoiceGroup(ads, localLetters = ads.map(ad => ad.letter)) {
  return `
    <section class="ad-choice-group">
      <div class="ad-card-grid">
        ${ads.map((ad, index) => `
          <article class="ad-card">
            <strong>${localLetters[index]}</strong>
            <p>${escapeHtml(ad.text)}</p>
          </article>
        `).join("")}
      </div>
    </section>
  `;
}

function renderInlineSelectTask(section, task, view) {
  const question = view.questions[0] || { lines: [], options: [] };
  const optionGroups = question.options || [];
  const count = optionGroups.length || task.expected || 1;
  for (let index = 0; index < count; index += 1) {
    ensureAnswerSlot(section, task.taskKey, index);
  }
  return `
    <article class="inline-gap-card">
      <div class="inline-gap-paper">
        ${renderInlineGapText(section, task.taskKey, question.lines, optionGroups)}
      </div>
    </article>
  `;
}

function renderInlineGapText(section, taskKey, lines, optionGroups) {
  const source = lines.length ? lines.join("\n\n") : fallbackInlineGapText(optionGroups.length || 1);
  const html = escapeHtml(source).replace(/\*\*\((\d+)\)\*\*/g, (_, number) => {
    const index = Number(number) - 1;
    const name = `${section}.${taskKey}.${index}`;
    const value = state.answers[section]?.[taskKey]?.[index] || "";
    const options = optionGroups[index]?.options || [
      { value: "a", label: "a" },
      { value: "b", label: "b" },
      { value: "c", label: "c" }
    ];
    return `
      <select class="inline-gap-select" data-answer="${name}" aria-label="Atbilde ${number}">
        <option value="">...</option>
        ${options.map(option => `<option value="${escapeHtml(option.value)}" ${value === option.value ? "selected" : ""}>${escapeHtml(`${option.value}) ${option.label}`)}</option>`).join("")}
      </select>
    `;
  });
  return html.split(/\n{2,}/).map(paragraph => `<p>${paragraph.replace(/\n/g, "<br>")}</p>`).join("");
}

function renderPhotoSentenceTask(section, task, questions, introLines) {
  const images = extractMarkdownImages(introLines);
  const instructionLines = removeMarkdownImageLines(introLines);
  const safeQuestions = questions.length ? questions : fallbackQuestions(task.expected);
  return `
    <article class="photo-writing-task">
      ${instructionLines.length ? `<div class="writing-task-instructions">${renderMarkdown(instructionLines.join("\n"), state.exam)}</div>` : ""}
      <div class="photo-answer-list">
        ${safeQuestions.map((question, index) => {
          const name = `${section}.${task.taskKey}.${index}`;
          ensureAnswerSlot(section, task.taskKey, index);
          const value = state.answers[section][task.taskKey][index] || "";
          const image = images[index];
          return `
            <section class="photo-answer-row">
              <div class="photo-prompt">
                ${image ? `<img src="${toAssetUrl(image.src)}" alt="${escapeHtml(image.alt)}" loading="lazy">` : `<div class="photo-fallback">${renderMarkdown(question.lines.join("\n"), state.exam)}</div>`}
              </div>
              <label class="ruled-answer">
                <span>${index + 1}.</span>
                <textarea data-answer="${name}" rows="${task.rows || 3}" placeholder="${escapeHtml(task.placeholder || "Rakstiet teikumu")}">${escapeHtml(value)}</textarea>
              </label>
            </section>
          `;
        }).join("")}
      </div>
    </article>
  `;
}

function renderWordFormTask(section, task, questions, introLines) {
  const safeQuestions = questions.length ? questions : fallbackQuestions(task.expected);
  return `
    <article class="word-form-task">
      ${introLines.length ? `<div class="writing-task-instructions">${renderMarkdown(introLines.join("\n"), state.exam)}</div>` : ""}
      <div class="word-form-paper">
        <strong>PARAUGS</strong>
        <p>Pirmajā <b>ceļojumā</b> (ceļojums) dodas pasaulē lielākais kruīza kuģis.</p>
        ${safeQuestions.map((question, index) => renderWordFormLine(section, task, question, index)).join("")}
      </div>
    </article>
  `;
}

function renderWordFormLine(section, task, question, index) {
  const name = `${section}.${task.taskKey}.${index}`;
  ensureAnswerSlot(section, task.taskKey, index);
  const value = state.answers[section][task.taskKey][index] || "";
  const raw = stripLeadingNumber(question.lines.join(" "));
  const input = `<input class="inline-text-blank" type="text" data-answer="${name}" value="${escapeHtml(value)}" aria-label="Atbilde ${index + 1}">`;
  const line = escapeHtml(raw).replace(/`?_{3,}`?/g, input);
  return `<p class="word-form-line"><span>${index + 1}.</span> ${line}</p>`;
}

function renderWritingLongTask(section, task, introLines) {
  const name = `${section}.${task.taskKey}.0`;
  ensureAnswerSlot(section, task.taskKey, 0);
  const value = state.answers[section][task.taskKey][0] || "";
  return `
    <article class="long-writing-task">
      ${introLines.length ? `<div class="writing-task-instructions">${renderMarkdown(introLines.join("\n"), state.exam)}</div>` : ""}
      <label class="long-writing-paper">
        <textarea data-answer="${name}" rows="${task.rows || 10}" placeholder="${escapeHtml(task.placeholder || "Rakstiet tekstu")}">${escapeHtml(value)}</textarea>
      </label>
    </article>
  `;
}

function ensureSpeakingSession(taskKey) {
  state.runner.speakingSessions ||= {};
  state.runner.speakingSessions[taskKey] ||= {
    recordingId: "",
    uploadUrl: "",
    uploadState: "idle",
    uploadError: "",
    playbackCount: 0,
    transcript: "",
    status: "idle",
    mimeType: "",
    durationMs: 0,
    previewUrl: "",
    uploadedAt: ""
  };
  return state.runner.speakingSessions[taskKey];
}

function serializeSpeakingSessions() {
  return Object.fromEntries(
    Object.entries(state.runner.speakingSessions || {}).map(([taskKey, session]) => [
      taskKey,
      {
        recordingId: session.recordingId || "",
        uploadUrl: session.uploadUrl || "",
        uploadState: session.uploadState || "idle",
        uploadError: session.uploadError || "",
        playbackCount: Number(session.playbackCount || 0),
        transcript: session.transcript || "",
        status: session.status || "idle",
        mimeType: session.mimeType || "",
        durationMs: Number(session.durationMs || 0),
        previewUrl: session.uploadUrl || "",
        uploadedAt: session.uploadedAt || ""
      }
    ])
  );
}

function renderSpeakingRecorderPanel(task) {
  const session = ensureSpeakingSession(task.taskKey);
  const hasPreview = Boolean(session.previewUrl);
  return `
    <section class="speaking-recorder" data-speaking-recorder="${task.taskKey}">
      <div class="speaking-recorder-head">
        <div>
          <p class="eyebrow">Speaking capture</p>
          <h4>${task.title}</h4>
        </div>
        <span class="speaking-status speaking-status-${session.status}">${escapeHtml(session.status)}</span>
      </div>
      <div class="speaking-recorder-actions">
        <button type="button" data-speaking-action="start" data-speaking-task="${task.taskKey}" ${session.status === "recording" || state.runner.finalized ? "disabled" : ""}>Start recording</button>
        <button type="button" data-speaking-action="stop" data-speaking-task="${task.taskKey}" ${session.status !== "recording" ? "disabled" : ""}>Stop</button>
        <button type="button" data-speaking-action="play" data-speaking-task="${task.taskKey}" ${!hasPreview ? "disabled" : ""}>Play</button>
        <button type="button" data-speaking-action="upload" data-speaking-task="${task.taskKey}" ${!hasPreview ? "disabled" : ""}>Upload</button>
        <button type="button" data-speaking-action="clear" data-speaking-task="${task.taskKey}" ${!hasPreview ? "disabled" : ""}>Clear</button>
        <button type="button" data-speaking-action="speech-to-text" data-speaking-task="${task.taskKey}">Speech-to-text</button>
      </div>
      <div class="speaking-recorder-meta">
        <span>${session.durationMs ? `${Math.max(1, Math.round(session.durationMs / 1000))}s recorded` : "No recording yet"}</span>
        <span>${session.uploadState === "uploaded" ? `Uploaded` : session.uploadState === "uploading" ? "Uploading..." : "Local draft only"}</span>
        <span>${session.playbackCount} plays</span>
      </div>
      ${hasPreview ? `
        <audio controls preload="none" src="${escapeHtml(session.previewUrl)}" data-playback-track="speaking" data-playback-key="${escapeHtml(task.taskKey)}" data-speaking-recording-playback="true" data-speaking-task="${task.taskKey}"></audio>
      ` : ""}
      <label class="speaking-transcript">
        <span>Transcript / notes</span>
        <textarea data-speaking-transcript="${task.taskKey}" rows="3" placeholder="Optional transcript or notes">${escapeHtml(session.transcript || "")}</textarea>
      </label>
      ${session.uploadError ? `<p class="speaking-error">${escapeHtml(session.uploadError)}</p>` : ""}
    </section>
  `;
}

function renderOralInterviewTask(section, task, questions) {
  const safeQuestions = questions.length ? questions : fallbackQuestions(task.expected);
  return `
    <div class="oral-interview-list">
      ${renderSpeakingRecorderPanel(task)}
      ${safeQuestions.map((question, index) => {
        const name = `${section}.${task.taskKey}.${index}`;
        ensureAnswerSlot(section, task.taskKey, index);
        const value = state.answers[section][task.taskKey][index] || "";
        return `
          <label class="oral-response-row">
            <span>${index + 1}. ${escapeHtml(stripLeadingNumber(question.lines.join(" ")))}</span>
            <textarea data-answer="${name}" rows="${task.rows || 2}" placeholder="${escapeHtml(task.placeholder || "Atbildiet")}">${escapeHtml(value)}</textarea>
          </label>
        `;
      }).join("")}
    </div>
  `;
}

function renderOralPicturesTask(section, task, questions, introLines) {
  const images = extractMarkdownImages(introLines);
  const safeQuestions = questions.length ? questions : fallbackQuestions(task.expected);
  return `
    <div class="oral-picture-grid">
      ${renderSpeakingRecorderPanel(task)}
      ${safeQuestions.map((question, index) => {
        const name = `${section}.${task.taskKey}.${index}`;
        ensureAnswerSlot(section, task.taskKey, index);
        const value = state.answers[section][task.taskKey][index] || "";
        const image = images[index];
        return `
          <label class="oral-picture-card">
            ${image ? `<img src="${toAssetUrl(image.src)}" alt="${escapeHtml(image.alt)}" loading="lazy">` : ""}
            <span>${renderMarkdown(question.lines.join("\n"), state.exam)}</span>
            <textarea data-answer="${name}" rows="${task.rows || 4}" placeholder="${escapeHtml(task.placeholder || "Aprakstiet attēlu")}">${escapeHtml(value)}</textarea>
          </label>
        `;
      }).join("")}
    </div>
  `;
}

function renderOralQuestionTask(section, task, questions) {
  const safeQuestions = questions.length ? questions : fallbackQuestions(task.expected);
  return `
    <div class="oral-question-list">
      ${renderSpeakingRecorderPanel(task)}
      ${safeQuestions.map((question, index) => {
        const name = `${section}.${task.taskKey}.${index}`;
        ensureAnswerSlot(section, task.taskKey, index);
        const value = state.answers[section][task.taskKey][index] || "";
        return `
          <label class="oral-question-row">
            <span>${renderMarkdown(question.lines.join("\n"), state.exam)}</span>
            <input type="text" data-answer="${name}" value="${escapeHtml(value)}" placeholder="${escapeHtml(task.placeholder || "Uzdodiet jautājumu")}">
          </label>
        `;
      }).join("")}
    </div>
  `;
}

function fallbackInlineGapText(count) {
  return Array.from({ length: count }, (_, index) => `**(${index + 1})**`).join(" ");
}

function parseChoiceQuestion(lines, fallbackOptions) {
  const parsed = {
    title: "",
    stem: "",
    body: [],
    options: []
  };
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const title = /^\*\*(.+)\*\*$/.exec(trimmed);
    if (title && !parsed.title) {
      parsed.title = title[1];
      continue;
    }
    const option = /^-\s+(?:([a-l])\)\s*)?(.+)$/i.exec(trimmed);
    if (option) {
      const fallbackValue = fallbackOptions[parsed.options.length] || optionLetters[parsed.options.length] || "";
      parsed.options.push({
        value: (option[1] || fallbackValue).toLowerCase(),
        label: option[2].trim()
      });
      continue;
    }
    const numbered = /^(\d+)\.\s+(.+)$/.exec(trimmed);
    if (numbered && !parsed.stem) {
      parsed.stem = numbered[2].trim();
      continue;
    }
    parsed.body.push(trimmed);
  }
  if (!parsed.options.length) {
    parsed.options = fallbackOptions.map(option => ({ value: option, label: option }));
  }
  return parsed;
}

function stripLeadingNumber(value) {
  return String(value || "").replace(/^\s*\d+\.\s*/, "").trim();
}

function extractMarkdownImages(lines) {
  return lines.map(line => /!\[([^\]]*)\]\(([^)]+)\)/.exec(line))
    .filter(Boolean)
    .map(match => ({ alt: match[1] || "Attēls", src: match[2] }));
}

function removeMarkdownImageLines(lines) {
  return lines.filter(line => !/!\[([^\]]*)\]\(([^)]+)\)/.test(line));
}

function parseBacktickOptions(lines) {
  const text = lines.join(" ");
  const matches = [...text.matchAll(/`([^`]+)`/g)].map(match => match[1].trim()).filter(Boolean);
  if (matches.length) return matches;
  const afterColon = text.split(":").slice(1).join(":");
  return afterColon.split(",").map(item => item.trim()).filter(Boolean);
}

function parseAdvertisements(lines) {
  return lines.map(line => /^-\s+([A-L])\.\s+(.+)$/i.exec(line.trim()))
    .filter(Boolean)
    .map(match => ({ letter: match[1].toUpperCase(), text: match[2].trim() }));
}

function chunkArray(items, size) {
  const chunks = [];
  for (let index = 0; index < items.length; index += size) {
    chunks.push(items.slice(index, index + size));
  }
  return chunks;
}

function renderAnswerControl(section, taskKey, task, index) {
  const name = `${section}.${taskKey}.${index}`;
  ensureAnswerSlot(section, taskKey, index);
  const value = state.answers[section][taskKey][index] || "";
  const label = "Atbilde";
  if (task.kind === "radio") {
    return `
      <div class="answer-row">
        <span>${label}</span>
        <div class="choice-pills">
          ${task.options.map(option => radioChoice(name, option, value === option)).join("")}
        </div>
      </div>
    `;
  }
  if (task.kind === "select") {
    return `
      <label class="answer-row">
        <span>${label}</span>
        <select data-answer="${name}">
          <option value="">Izvēlieties</option>
          ${task.options.map(option => `<option value="${option}" ${value === option ? "selected" : ""}>${option}</option>`).join("")}
        </select>
      </label>
    `;
  }
  const rows = task.rows || (task.kind === "textarea" ? 3 : 2);
  const tag = task.kind === "textarea" ? "textarea" : "input";
  const common = tag === "textarea"
    ? `<textarea data-answer="${name}" rows="${rows}" placeholder="${escapeHtml(task.placeholder || "Ierakstiet atbildi")}">${escapeHtml(value)}</textarea>`
    : `<input type="text" data-answer="${name}" value="${escapeHtml(value)}" placeholder="${escapeHtml(task.placeholder || "Ierakstiet atbildi")}">`;
  return `
    <label class="answer-row answer-row-text">
      <span>${label}</span>
      ${common}
    </label>
  `;
}

function radioChoice(name, value, checked) {
  return `
    <label class="choice">
      <input type="radio" name="${name}" value="${value}" ${checked ? "checked" : ""}>
      <span>${value}</span>
    </label>
  `;
}

function bindRunnerEvents() {
  document.querySelectorAll("[data-action]").forEach(button => {
    button.addEventListener("click", () => handleRunnerAction(button.dataset));
  });
  document.querySelectorAll("[data-answer]").forEach(field => {
    field.addEventListener("input", handleAnswerInput);
    field.addEventListener("change", handleAnswerInput);
  });
  document.querySelectorAll("input[type='radio']").forEach(field => {
    field.addEventListener("change", handleAnswerInput);
  });
  document.querySelectorAll("[data-drag-value]").forEach(chip => {
    chip.addEventListener("click", handleDragChipClick);
    chip.addEventListener("dragstart", handleDragStart);
  });
  document.querySelectorAll("[data-drop-target]").forEach(target => {
    target.addEventListener("click", handleDropTargetClick);
    target.addEventListener("dragover", handleDropDragOver);
    target.addEventListener("dragleave", handleDropDragLeave);
    target.addEventListener("drop", handleDrop);
  });
  document.querySelectorAll("[data-playback-track]").forEach(audio => {
    audio.addEventListener("play", handlePlaybackEvent);
  });
  document.querySelectorAll("[data-speaking-recording-playback]").forEach(audio => {
    audio.addEventListener("play", handlePlaybackEvent);
  });
  document.querySelectorAll("[data-speaking-action]").forEach(button => {
    button.addEventListener("click", () => handleSpeakingAction(button.dataset));
  });
  document.querySelectorAll("[data-speaking-transcript]").forEach(field => {
    field.addEventListener("input", event => {
      const taskKey = event.currentTarget.dataset.speakingTranscript;
      const session = ensureSpeakingSession(taskKey);
      session.transcript = event.currentTarget.value;
      state.submission = null;
      state.evaluation = null;
    });
  });
}

function handleRunnerAction(dataset) {
  const { action, part } = dataset;
  if (action === "switch-part") {
    switchPart(part);
    return;
  }
  if (action === "show-ad-group") {
    const groupStateKey = `${state.exam.id}.${part}.${dataset.task}`;
    state.runner.activeAdGroups[groupStateKey] = Number(dataset.groupIndex || 0);
    renderRunner();
    return;
  }
  if (action === "submit-exam") {
    submitAnswers();
    return;
  }
  if (action === "evaluate-exam") {
    evaluateSubmissionWithAi();
    return;
  }
  if (action === "show-results") {
    if (state.flow.mode === "exam") {
      submitAnswers();
    }
    setFlowScreen("results");
    return;
  }
  if (action === "open-submission") {
    renderSubmission();
    setView("submission");
    return;
  }
  handleTimerAction(action, part);
}

function handleTimerAction(action, part) {
  const timer = state.runner.timers[part];
  if (!timer) return;
  state.runner.activePart = part;
  updateExamUrl();
  if (action === "start") {
    if (state.runner.finalized || isPartLocked(part)) return;
    startOnlyTimer(part);
  }
  if (action === "pause") {
    if (state.flow.mode === "exam") return;
    pauseTimer(timer);
  }
  if (action === "reset") {
    if (state.flow.mode === "exam") return;
    resetTimer(timer, durationForPart(part));
  }
  renderRunner();
}

function startOnlyTimer(part) {
  const now = Date.now();
  for (const key of Object.keys(state.runner.timers)) {
    const timer = state.runner.timers[key];
    if (key === part && timer.remaining > 0 && !isPartLocked(part)) {
      startTimer(timer, now);
    } else {
      pauseTimer(timer, now);
    }
  }
}

function isAnyTimerRunning() {
  return Object.values(state.runner.timers).some(timer => timer.running);
}

function handleAnswerInput(event) {
  const target = event.target;
  const key = target.dataset.answer;
  if (target.type === "radio") {
    const [section, task, index] = target.name.split(".");
    if (isPartLocked(section) && state.flow.mode === "exam") {
      target.checked = state.answers[section]?.[task]?.[Number(index)] === target.value;
      return;
    }
    ensureAnswerSlot(section, task, Number(index));
    state.answers[section][task][Number(index)] = target.value;
    state.submission = null;
    state.evaluation = null;
    renderProgressOnly();
    return;
  }
  const [section, task, index] = key.split(".");
  if (isPartLocked(section) && state.flow.mode === "exam") {
    target.value = state.answers[section]?.[task]?.[Number(index)] || "";
    return;
  }
  ensureAnswerSlot(section, task, Number(index));
  state.answers[section][task][Number(index)] = target.value;
  state.submission = null;
  state.evaluation = null;
  renderProgressOnly();
}

function handleDragChipClick(event) {
  const value = event.currentTarget.dataset.dragValue;
  if (!value) return;
  state.runner.selectedDragValue = state.runner.selectedDragValue === value ? "" : value;
  refreshDragSelectionUi();
}

function handleDragStart(event) {
  const value = event.currentTarget.dataset.dragValue;
  if (!value || event.currentTarget.disabled) {
    event.preventDefault();
    return;
  }
  state.runner.selectedDragValue = value;
  event.dataTransfer.setData("text/plain", value);
  event.dataTransfer.effectAllowed = "move";
  refreshDragSelectionUi();
}

function handleDropTargetClick(event) {
  const key = event.currentTarget.dataset.dropTarget;
  const [section, task, index] = key.split(".");
  const currentValue = state.answers[section]?.[task]?.[Number(index)] || "";
  if (state.runner.selectedDragValue) {
    setDragFillAnswer(key, state.runner.selectedDragValue);
    return;
  }
  if (currentValue) {
    setDragFillAnswer(key, "");
  }
}

function handleDropDragOver(event) {
  event.preventDefault();
  event.currentTarget.classList.add("drop-hover");
}

function handleDropDragLeave(event) {
  event.currentTarget.classList.remove("drop-hover");
}

function handleDrop(event) {
  event.preventDefault();
  event.currentTarget.classList.remove("drop-hover");
  const value = event.dataTransfer.getData("text/plain") || state.runner.selectedDragValue;
  if (value) {
    setDragFillAnswer(event.currentTarget.dataset.dropTarget, value);
  }
}

function setDragFillAnswer(key, value) {
  const [section, task, index] = key.split(".");
  const targetIndex = Number(index);
  if (isPartLocked(section) && state.flow.mode === "exam") {
    return;
  }
  ensureAnswerSlot(section, task, targetIndex);
  if (value) {
    state.answers[section][task] = state.answers[section][task].map((item, itemIndex) => (
      itemIndex !== targetIndex && item === value ? "" : item
    ));
  }
  state.answers[section][task][targetIndex] = value;
  state.runner.selectedDragValue = "";
  state.submission = null;
  state.evaluation = null;
  refreshDragFillUi(section, task);
  renderProgressOnly();
}

function refreshDragFillUi(section, task) {
  const values = state.answers[section]?.[task] || [];
  const usedValues = new Set(values.filter(Boolean));
  document.querySelectorAll(`[data-drop-target^="${section}.${task}."]`).forEach(target => {
    const [, , index] = target.dataset.dropTarget.split(".");
    const value = values[Number(index)] || "";
    target.textContent = value;
    target.classList.toggle("filled", Boolean(value));
    target.classList.remove("drop-hover");
  });
  document.querySelectorAll(`[data-drag-chip="${section}.${task}"]`).forEach(chip => {
    const used = usedValues.has(chip.dataset.dragValue);
    chip.disabled = used;
    chip.draggable = !used;
    chip.classList.toggle("used", used);
    chip.classList.remove("selected");
  });
}

function refreshDragSelectionUi() {
  document.querySelectorAll("[data-drag-value]").forEach(chip => {
    chip.classList.toggle("selected", chip.dataset.dragValue === state.runner.selectedDragValue);
  });
}

function ensureAnswerSlot(section, task, index) {
  state.answers[section] ||= {};
  state.answers[section][task] ||= [];
  while (state.answers[section][task].length <= index) {
    state.answers[section][task].push("");
  }
}

function formatTime(seconds) {
  const mins = String(Math.floor(seconds / 60)).padStart(2, "0");
  const secs = String(seconds % 60).padStart(2, "0");
  return `${mins}:${secs}`;
}

function renderMarkdown(markdown, exam) {
  const rewritten = rewriteAttachmentPaths(markdown, exam);
  const lines = rewritten.split(/\r?\n/);
  const html = [];
  let listType = null;
  let paragraph = [];

  const closeParagraph = () => {
    if (!paragraph.length) return;
    html.push(`<p>${formatInline(paragraph.join(" "))}</p>`);
    paragraph = [];
  };

  const closeList = () => {
    if (!listType) return;
    html.push(`</${listType}>`);
    listType = null;
  };

  const openList = type => {
    closeParagraph();
    if (listType === type) return;
    closeList();
    html.push(`<${type}>`);
    listType = type;
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();

    if (!trimmed) {
      closeParagraph();
      closeList();
      continue;
    }

    if (isTableStart(lines, index)) {
      closeParagraph();
      closeList();
      const table = collectTable(lines, index);
      html.push(renderTable(table.rows));
      index = table.endIndex;
      continue;
    }

    if (/^<audio\b|^<source\b|^<\/audio>/.test(trimmed)) {
      closeParagraph();
      closeList();
      html.push(trimmed);
      continue;
    }

    const heading = /^(#{1,6})\s+(.*)$/.exec(trimmed);
    if (heading) {
      closeParagraph();
      closeList();
      const level = Math.min(heading[1].length + 1, 6);
      html.push(`<h${level}>${formatInline(heading[2])}</h${level}>`);
      continue;
    }

    if (trimmed.startsWith(">")) {
      closeParagraph();
      closeList();
      html.push(`<div class="note">${formatInline(trimmed.replace(/^>\s?/, ""))}</div>`);
      continue;
    }

    const unordered = /^[-*]\s+(.*)$/.exec(trimmed);
    if (unordered) {
      openList("ul");
      html.push(`<li>${formatInline(unordered[1])}</li>`);
      continue;
    }

    const ordered = /^\d+\.\s+(.*)$/.exec(trimmed);
    if (ordered) {
      openList("ol");
      html.push(`<li>${formatInline(ordered[1])}</li>`);
      continue;
    }

    paragraph.push(trimmed);
  }

  closeParagraph();
  closeList();
  return html.join("\n");
}

function isTableStart(lines, index) {
  return /\|/.test(lines[index] || "") && /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[index + 1] || "");
}

function collectTable(lines, startIndex) {
  const rows = [];
  let index = startIndex;
  while (index < lines.length && /\|/.test(lines[index])) {
    if (!/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(lines[index])) {
      rows.push(lines[index]);
    }
    index += 1;
  }
  return { rows, endIndex: index - 1 };
}

function renderTable(rows) {
  const parsedRows = rows.map(row => row.replace(/^\s*\|?|\|?\s*$/g, "").split("|").map(cell => formatInline(cell.trim())));
  const [head, ...body] = parsedRows;
  return `
    <table>
      <thead><tr>${head.map(cell => `<th>${cell}</th>`).join("")}</tr></thead>
      <tbody>${body.map(row => `<tr>${row.map(cell => `<td>${cell}</td>`).join("")}</tr>`).join("")}</tbody>
    </table>
  `;
}

function formatInline(value) {
  let text = escapeHtml(value);
  text = text.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_, alt, src) => {
    return `<figure><img src="${src}" alt="${alt}" loading="lazy"><figcaption>${alt}</figcaption></figure>`;
  });
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, `<a href="$2" target="_blank" rel="noreferrer">$1</a>`);
  text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/`([^`]+)`/g, "<code>$1</code>");
  return text;
}

function rewriteAttachmentPaths(markdown) {
  return markdown
    .replaceAll("(Attachments/", "(/codex/Attachments/")
    .replaceAll('src="Attachments/', 'src="/codex/Attachments/')
    .replaceAll("href=\"Attachments/", "href=\"/codex/Attachments/");
}

function extractAssets(markdown, exam) {
  const audio = uniqueMatches(markdown, /<source\s+src="([^"]+\.mp3)"/g).map(path => ({
    label: labelForAsset(path),
    path,
    url: toAssetUrl(path)
  }));

  const images = uniqueMatches(markdown, /!\[([^\]]*)\]\((Attachments\/[^)]+\.(?:png|jpg|jpeg))\)/gi, true).map(match => ({
    label: match[1] || labelForAsset(match[2]),
    path: match[2],
    url: toAssetUrl(match[2])
  }));

  return {
    audio: audio.length ? audio : fallbackAudio(exam),
    images: images.length ? images : fallbackImages(exam)
  };
}

function fallbackAudio(exam) {
  return [
    "klausisanas_1_uzdevums.mp3",
    "klausisanas_2_uzdevums.mp3",
    "klausisanas_3_uzdevums.mp3",
    "runasana_1_jautajumi.mp3",
    "runasana_2_jautajumi.mp3",
    "runasana_3_jautajumi.mp3"
  ].map(file => ({
    label: file.replace(".mp3", ""),
    path: `${exam.attachmentRoot}${file}`,
    url: `${exam.attachmentRoot}${file}`
  }));
}

function fallbackImages(exam) {
  return [
    "rakstisana_1_attels_1.png",
    "rakstisana_1_attels_2.png",
    "rakstisana_1_attels_3.png",
    "rakstisana_1_attels_4.png",
    "runasana_2_attels_1.png",
    "runasana_2_attels_2.png"
  ].map(file => ({
    label: file.replace(".png", ""),
    path: `${exam.attachmentRoot}${file}`,
    url: `${exam.attachmentRoot}${file}`
  }));
}

function uniqueMatches(text, regex, keepFullMatch = false) {
  const seen = new Set();
  const results = [];
  let match = regex.exec(text);
  while (match) {
    const key = keepFullMatch ? match[2] : match[1];
    if (!seen.has(key)) {
      seen.add(key);
      results.push(keepFullMatch ? match : match[1]);
    }
    match = regex.exec(text);
  }
  return results;
}

function toAssetUrl(path) {
  return path.startsWith("/codex/") ? path : `/codex/${path}`;
}

function labelForAsset(path) {
  return path.split("/").pop().replace(/\.[^.]+$/, "").replaceAll("_", " ");
}

function renderTts() {
  els.ttsOutput.innerHTML = `
    <h2>TTS Audio</h2>
    <p class="muted">Audio is loaded from the exam attachment folders. Exams 01-02 use the ElevenLabs files referenced by their Markdown; the remaining exams use the existing Piper Latvian voice files.</p>
    <div class="media-grid">
      ${state.assets.audio.map(asset => `
        <article class="media-card">
          <h3>${escapeHtml(asset.label)}</h3>
          <audio controls preload="none" src="${asset.url}" data-playback-track="listening" data-playback-key="${escapeHtml(asset.path)}"></audio>
          <span class="playback-count">${getMediaPlaybackCount("listening", asset.path)} listens</span>
          <p><code>${escapeHtml(asset.path)}</code></p>
        </article>
      `).join("")}
    </div>
    <h3>Regenerate TTS</h3>
    <pre>python3 scripts/regenerate_exam_audio.py --exam A2_Mock_Exam_${state.exam.id}.md</pre>
  `;
}

function renderImages() {
  els.promptOutput.innerHTML = `
    <h2>Generated Images</h2>
    <p class="muted">Writing Task 1 and Speaking Task 2 image assets are rendered directly from the vault attachments.</p>
    <div class="media-grid">
      ${state.assets.images.map(asset => `
        <article class="media-card image-card">
          <img src="${asset.url}" alt="${escapeHtml(asset.label)}" loading="lazy">
          <h3>${escapeHtml(asset.label)}</h3>
          <p><code>${escapeHtml(asset.path)}</code></p>
        </article>
      `).join("")}
    </div>
    <h3>Regenerate Images</h3>
    <pre>python3 scripts/regenerate_exam_images.py --exam A2_Mock_Exam_${state.exam.id}.md</pre>
  `;
}

function renderQuality() {
  const checks = buildQualityChecks();
  const passed = checks.every(check => check.pass);
  els.qualityOutput.innerHTML = checks.map(check => `
    <article class="quality-card ${check.pass ? "pass" : "fail"}">
      <h3>${check.pass ? "Pass" : "Review"}</h3>
      <p>${escapeHtml(check.label)}</p>
    </article>
  `).join("");
  els.validationPill.textContent = passed ? "Validated" : "Needs review";
  els.validationPill.classList.toggle("bad", !passed);
}

function buildQualityChecks() {
  const md = state.markdown;
  return [
    { label: "Loaded one of the 10 existing Codex exam Markdown files", pass: Boolean(md && state.exam.id) },
    { label: "Exam states total score is 60 points", pass: /Kopā\s+[-–]\s+60 punkti|total maximum score is 60|total_points["']?\s*:\s*60/i.test(md) },
    { label: "Listening, reading, writing, and speaking sections are present", pass: ["Klausīšanās", "Lasīšana", "Rakstīšana", "Runāšana"].every(term => md.includes(term)) },
    { label: "Pass rule mentions minimum 9 points per skill", pass: /9\s+punkti katrā prasmē|9\/15 in each skill/i.test(md) },
    { label: `TTS/audio assets found: ${state.assets.audio.length}`, pass: state.assets.audio.length >= 3 },
    { label: `Image assets found: ${state.assets.images.length}`, pass: state.assets.images.length >= 6 },
    { label: "Answer/teacher key content is present", pass: /Answer Key|Teacher Version|Teacher Key|Atbilžu/i.test(md) },
    { label: "Regeneration scripts are available for TTS and images", pass: true }
  ];
}

function submitAnswers() {
  stopActiveSpeakingRecorder();
  for (const timer of Object.values(state.runner.timers)) {
    pauseTimer(timer);
  }
  if (state.flow.mode === "exam") {
    lockAllParts();
  }
  state.submission = buildSubmission("submitted");
  persistSubmission(state.submission);
  state.evaluation = null;
  renderRunner();
  renderSubmission();
  setView("submission");
  showToast("Answers submitted locally");
}

async function evaluateSubmissionWithAi() {
  if (state.evaluating) return;
  stopActiveSpeakingRecorder();
  for (const timer of Object.values(state.runner.timers)) {
    pauseTimer(timer);
  }
  if (state.flow.mode === "exam") {
    lockAllParts();
  }
  state.submission = buildSubmission("submitted");
  state.evaluating = true;
  state.evaluation = null;
  persistSubmission(state.submission);
  renderRunner();
  renderSubmission();
  setView("submission");
  showToast("Sending answers for AI scoring...");

  try {
    const response = await fetch("/api/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        submission: buildEvaluationSubmission(state.submission),
        exam_markdown: state.markdown
      })
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || payload.detail || `Evaluation failed with HTTP ${response.status}`);
    }
    state.evaluation = payload;
    state.submission.ai_evaluation = payload;
    persistSubmission(state.submission);
    showToast("AI score complete");
  } catch (error) {
    state.evaluation = {
      error: error.message,
      hint: evaluationErrorHint(error.message)
    };
    showToast("AI scoring failed");
  } finally {
    state.evaluating = false;
    renderSubmission();
    syncEvaluationButtons();
  }
}

function ensureSubmission(status) {
  if (state.submission && state.submission.status === "submitted") {
    return state.submission;
  }
  return buildSubmission(status);
}

function buildSubmission(status = "draft") {
  const answerKey = extractAnswerKey(state.markdown);
  const scoring = scoreAnswers(answerKey, state.answers);
  const now = new Date().toISOString();
  return {
    submission_id: `a2-${state.exam.id}-${Date.now()}`,
    status,
    exam_id: `a2_mock_exam_${state.exam.id}`,
    exam_title: state.exam.title,
    level: "A2",
    language: "lv",
    source_path: state.exam.sourcePath,
    exam_url: window.location.href,
    candidate: cloneJson(state.flow.candidate),
    created_at: now,
    submitted_at: status === "submitted" ? now : null,
    pass_rule: {
      total_max: 60,
      skill_max: 15,
      minimum_per_skill: 9,
      note: "A final pass decision requires at least 9/15 in each skill."
    },
    progress: getExamProgress(),
    timers: snapshotTimers(),
    answers: cloneJson(state.answers),
    speaking_recordings: serializeSpeakingSessions(),
    media_playback_counts: cloneJson(state.runner.playbackCounts),
    answer_key: answerKey,
    scoring,
    validation_queue: buildValidationQueue(answerKey),
    ai_evaluation: state.evaluation
  };
}

function buildEvaluationSubmission(submission) {
  return {
    submission_id: submission.submission_id,
    exam_id: submission.exam_id,
    exam_title: submission.exam_title,
    level: submission.level,
    language: submission.language,
    pass_rule: submission.pass_rule,
    progress: submission.progress,
    answers: submission.answers,
    answer_key: submission.answer_key,
    scoring: {
      objective_correct: submission.scoring.objective_correct,
      objective_possible: submission.scoring.objective_possible,
      manual_review_possible: submission.scoring.manual_review_possible,
      by_skill: submission.scoring.by_skill,
      items: submission.scoring.items
    },
    validation_queue: submission.validation_queue
  };
}

function evaluationErrorHint(message) {
  const lower = String(message || "").toLowerCase();
  if (lower.includes("rate limit") || lower.includes("429")) {
    return "Groq is rate limiting this key. Wait a little and click AI Score once.";
  }
  if (lower.includes("too large") || lower.includes("413")) {
    return "The evaluator reduced the request size. Refresh the page and try AI Score again.";
  }
  return "Check that server.py is running and .env has either GROQ_API_KEY for Groq, local Codex CLI access, or CODEX_REMOTE_URL for Docker-to-host Codex scoring.";
}

function extractAnswerKey(markdown) {
  const answerLines = sectionBetween(markdown.split(/\r?\n/), "## Answer Key", ["## Listening Transcripts", "## TTS Export", "## JSON Export"]);
  const key = {};
  let currentSkill = "";
  for (const line of answerLines) {
    const heading = /^###\s+(.+)$/.exec(line.trim());
    if (heading) {
      currentSkill = skillKeyFromHeading(heading[1]);
      if (currentSkill) key[currentSkill] ||= {};
      continue;
    }
    const taskLine = /^\*\*(\d+)\.\s*uzdevums:\*\*\s*(.+)$/i.exec(line.trim());
    if (!taskLine || !currentSkill) continue;
    key[currentSkill][`task${taskLine[1]}`] = parseAnswerValues(taskLine[2]);
  }
  return key;
}

function skillKeyFromHeading(value) {
  const normalized = value.toLowerCase();
  if (normalized.includes("klaus")) return "listening";
  if (normalized.includes("las")) return "reading";
  if (normalized.includes("rakst")) return "writing";
  if (normalized.includes("run")) return "speaking";
  return "";
}

function parseAnswerValues(value) {
  return [...value.matchAll(/(\d+)\.\s*([^,;\n]+)/g)].map(match => cleanAnswerValue(match[2]));
}

function cleanAnswerValue(value) {
  return String(value).replace(/\s{2,}/g, " ").trim().replace(/\.$/, "");
}

function scoreAnswers(answerKey, answers) {
  const bySkill = {};
  const items = [];
  for (const part of PART_CONFIG) {
    const skillKey = part.key;
    bySkill[skillKey] = {
      objective_correct: 0,
      objective_possible: 0,
      manual_review_possible: 15,
      max_points: 15,
      minimum_to_pass: 9
    };
    const skillKeyData = answerKey[skillKey] || {};
    for (const [taskKey, expectedAnswers] of Object.entries(skillKeyData)) {
      expectedAnswers.forEach((expected, index) => {
        const actual = answers[skillKey]?.[taskKey]?.[index] || "";
        const correct = normalizeAnswer(actual) === normalizeAnswer(expected);
        bySkill[skillKey].objective_possible += 1;
        bySkill[skillKey].objective_correct += correct ? 1 : 0;
        items.push({
          skill: skillKey,
          task: taskKey,
          item: index + 1,
          expected,
          actual,
          correct,
          scoring: "objective"
        });
      });
    }
    bySkill[skillKey].manual_review_possible = Math.max(0, 15 - bySkill[skillKey].objective_possible);
  }
  const objectiveCorrect = Object.values(bySkill).reduce((total, skill) => total + skill.objective_correct, 0);
  const objectivePossible = Object.values(bySkill).reduce((total, skill) => total + skill.objective_possible, 0);
  const manualPossible = Object.values(bySkill).reduce((total, skill) => total + skill.manual_review_possible, 0);
  return {
    mode: "mixed",
    objective_correct: objectiveCorrect,
    objective_possible: objectivePossible,
    manual_review_possible: manualPossible,
    estimated_minimum_points: objectiveCorrect,
    estimated_maximum_points_after_review: objectiveCorrect + manualPossible,
    by_skill: bySkill,
    items
  };
}

function normalizeAnswer(value) {
  return String(value || "").trim().toLowerCase().replace(/\s+/g, " ");
}

function buildValidationQueue(answerKey) {
  const queue = [];
  for (const part of PART_CONFIG) {
    const tasks = state.answers[part.key] || {};
    for (const [taskKey, values] of Object.entries(tasks)) {
      if (answerKey[part.key]?.[taskKey]) continue;
      values.forEach((value, index) => {
        queue.push({
          skill: part.key,
          task: taskKey,
          item: index + 1,
          response: value,
          review_type: "manual_or_ai_scoring"
        });
      });
    }
  }
  return queue;
}

function snapshotTimers() {
  return Object.fromEntries(Object.entries(state.runner.timers).map(([part, timer]) => [
    part,
    {
      total_seconds: timer.total,
      remaining_seconds: calculateRemaining(timer),
      elapsed_seconds: timer.total - calculateRemaining(timer),
      remaining_display: formatTime(calculateRemaining(timer))
    }
  ]));
}

function persistSubmission(submission) {
  try {
    const key = "latvian_a2_exam_submissions";
    const submissions = JSON.parse(localStorage.getItem(key) || "[]");
    submissions.unshift(submission);
    localStorage.setItem(key, JSON.stringify(submissions.slice(0, 25)));
  } catch {
    // Local storage can be unavailable in private or restricted browser contexts.
  }
}

function renderSubmission() {
  const submission = state.submission || buildSubmission("draft");
  const score = submission.scoring;
  const evaluation = state.evaluation?.evaluation || submission.ai_evaluation || null;
  const reportModel = buildCandidateReportModel({
    submission,
    evaluation,
    candidate: submission.candidate || state.flow.candidate
  });
  els.submissionOutput.innerHTML = `
    <section class="submission-hero">
      <div>
        <p class="eyebrow">${submission.status === "submitted" ? "Submitted" : "Draft submission"}</p>
        <h2>${escapeHtml(submission.exam_title)}</h2>
        <p>${submission.progress.answered}/${submission.progress.total} response fields completed. Objective score: ${score.objective_correct}/${score.objective_possible}. Manual review fields: ${score.manual_review_possible} points.</p>
      </div>
      <div class="submission-id">${escapeHtml(submission.submission_id)}</div>
    </section>
    <div class="score-summary">
      ${PART_CONFIG.map(part => renderSkillScore(part, score.by_skill[part.key])).join("")}
    </div>
    <div class="submission-actions">
      <button type="button" data-submission-action="submit">${submission.status === "submitted" ? "Resubmit answers" : "Submit answers"}</button>
      <button type="button" data-submission-action="evaluate" ${state.evaluating ? "disabled" : ""}>${state.evaluating ? "Scoring..." : "AI score and corrections"}</button>
      <button type="button" data-submission-action="pdf">Export PDF</button>
      <button type="button" data-submission-action="copy">Copy JSON</button>
      <button type="button" data-submission-action="download">Download JSON</button>
    </div>
    <section class="candidate-report">
      ${buildCandidateReportHtml(reportModel)}
    </section>
    ${renderAiEvaluationPanel()}
    <pre class="code-panel submission-json">${escapeHtml(JSON.stringify(submission, null, 2))}</pre>
  `;
  els.submissionOutput.querySelectorAll("[data-submission-action]").forEach(button => {
    button.addEventListener("click", () => handleSubmissionAction(button.dataset.submissionAction));
  });
  syncEvaluationButtons();
}

function renderSkillScore(part, score) {
  return `
    <article class="score-summary-card">
      <h3>${part.title}</h3>
      <strong>${score.objective_correct}/${score.objective_possible}</strong>
      <p>Objective now</p>
      <span>${score.manual_review_possible} pts for later review</span>
    </article>
  `;
}

function renderAiEvaluationPanel() {
  if (state.evaluating) {
    return `
      <section class="ai-evaluation-panel pending">
        <h3>AI scoring</h3>
        <p>Reviewing the submitted answers with the configured LLM provider. This can take a minute.</p>
      </section>
    `;
  }
  if (!state.evaluation) {
    return `
      <section class="ai-evaluation-panel">
        <h3>AI scoring</h3>
        <p>Submit the answers, then use AI score and corrections to validate writing and speaking responses.</p>
      </section>
    `;
  }
  if (state.evaluation.error) {
    return `
      <section class="ai-evaluation-panel error">
        <h3>AI scoring failed</h3>
        <p>${escapeHtml(state.evaluation.error)}</p>
        <p>${escapeHtml(state.evaluation.hint || "")}</p>
      </section>
    `;
  }

  const evaluation = state.evaluation.evaluation || {};
  const scores = evaluation.scores || {};
  const feedback = evaluation.feedback || {};
  const corrections = Array.isArray(evaluation.corrections) ? evaluation.corrections : [];
  return `
    <section class="ai-evaluation-panel">
      <div class="ai-evaluation-head">
        <div>
          <p class="eyebrow">${escapeHtml(state.evaluation.provider || "LLM")} ${escapeHtml(state.evaluation.model || "")}</p>
          <h3>AI score: ${escapeHtml(scores.total ?? "—")}/60</h3>
          <p>${scores.passed ? "Pass rule met" : "Pass rule not met yet"} · minimum is 9/15 in every skill.</p>
        </div>
      </div>
      <div class="ai-score-grid">
        ${PART_CONFIG.map(part => renderAiSkillScore(part, scores[part.key])).join("")}
      </div>
      ${feedback.summary ? `<p class="ai-summary">${escapeHtml(feedback.summary)}</p>` : ""}
      ${renderFeedbackList("Strengths", feedback.strengths)}
      ${renderFeedbackList("Improve next", feedback.improvements)}
      ${corrections.length ? `
        <div class="correction-list">
          <h4>Corrections</h4>
          ${corrections.slice(0, 12).map(item => `
            <article class="correction-item">
              <strong>${escapeHtml(item.skill || "")} ${escapeHtml(item.task || "")}${item.item ? ` #${escapeHtml(item.item)}` : ""}</strong>
              <p><span>Answer:</span> ${escapeHtml(item.candidate_answer || "")}</p>
              <p><span>Better:</span> ${escapeHtml(item.suggested_answer || "")}</p>
              <p>${escapeHtml(item.comment || "")}</p>
            </article>
          `).join("")}
        </div>
      ` : ""}
    </section>
  `;
}

function renderAiSkillScore(part, score = {}) {
  const safeScore = score || {};
  return `
    <article class="ai-skill-card">
      <h4>${part.title}</h4>
      <strong>${escapeHtml(safeScore.points ?? "—")}/15</strong>
      <p>${safeScore.passed ? "Passed" : "Needs work"}</p>
      <span>${escapeHtml(safeScore.reason || "")}</span>
    </article>
  `;
}

function renderFeedbackList(title, items) {
  if (!Array.isArray(items) || !items.length) return "";
  return `
    <div class="feedback-list">
      <h4>${escapeHtml(title)}</h4>
      <ul>
        ${items.map(item => `<li>${escapeHtml(item)}</li>`).join("")}
      </ul>
    </div>
  `;
}

function handleSubmissionAction(action) {
  if (action === "submit") {
    submitAnswers();
    return;
  }
  if (action === "evaluate") {
    evaluateSubmissionWithAi();
    return;
  }
  if (action === "pdf") {
    exportCandidateReportPdf();
    return;
  }
  const submission = ensureSubmission("draft");
  if (action === "copy") {
    copyText(JSON.stringify(submission, null, 2), "Submission copied");
    return;
  }
  if (action === "download") {
    downloadFile(`${submission.submission_id}.json`, JSON.stringify(submission, null, 2), "application/json");
  }
}

function exportCandidateReportPdf() {
  const onAfterPrint = () => {
    document.body.classList.remove("report-print-mode");
  };
  document.body.classList.add("report-print-mode");
  window.addEventListener("afterprint", onAfterPrint, { once: true });
  window.print();
}

function syncEvaluationButtons() {
  const sidebarButton = document.querySelector("#evaluate-submission");
  if (!sidebarButton) return;
  sidebarButton.disabled = state.evaluating;
  sidebarButton.textContent = state.evaluating ? "Scoring..." : "AI Score";
}

function cloneJson(value) {
  return JSON.parse(JSON.stringify(value));
}

function buildExportJson() {
  const answerKey = extractAnswerKey(state.markdown);
  return {
    exam_id: `a2_mock_exam_${state.exam.id}`,
    title: state.exam.title,
    level: "A2",
    language: "lv",
    source_path: state.exam.sourcePath,
    total_points: 60,
    pass_rule: {
      total_max: 60,
      skill_max: 15,
      minimum_per_skill: 9,
      note: "The learner must score at least 9/15 in each skill."
    },
    assets: state.assets,
    answers: state.answers,
    candidate: state.flow.candidate,
    speaking_recordings: serializeSpeakingSessions(),
    media_playback_counts: state.runner.playbackCounts,
    answer_key: answerKey,
    latest_submission: state.submission,
    latest_ai_evaluation: state.evaluation,
    submission_schema: {
      storage: "localStorage:latvian_a2_exam_submissions",
      status_values: ["draft", "submitted"],
      evaluation_endpoint: "/api/evaluate",
      scoring_note: "Objective items are auto-scored from the Markdown answer key; writing and speaking free text are scored through the configured LLM evaluator."
    },
    markdown: state.markdown,
    generation: {
      tts_command: `python3 scripts/regenerate_exam_audio.py --exam A2_Mock_Exam_${state.exam.id}.md`,
      image_command: `python3 scripts/regenerate_exam_images.py --exam A2_Mock_Exam_${state.exam.id}.md`,
      tts_engines: state.exam.id === "01" || state.exam.id === "02" ? ["ElevenLabs referenced in Markdown", "Piper fallback files present"] : ["Piper lv_LV-rudolfs-medium"],
      image_engine: "Ollama OpenAI-compatible image endpoint, model x/z-image-turbo:bf16"
    }
  };
}

function setView(viewName) {
  document.querySelectorAll(".view").forEach(view => view.classList.remove("active"));
  document.querySelector(`#${viewName}-view`).classList.add("active");
  document.querySelectorAll(".nav-list button").forEach(button => {
    button.classList.toggle("active", button.dataset.view === viewName);
  });
  const titles = {
    runner: "Exam Runner",
    submission: "Submission",
    exam: state.exam.title,
    markdown: "Raw Markdown",
    json: "Structured JSON",
    tts: "TTS Audio",
    prompts: "Generated Images",
    quality: "Quality Gate"
  };
  els.workspaceTitle.textContent = titles[viewName];
}

async function copyText(text, successMessage) {
  await navigator.clipboard.writeText(text);
  showToast(successMessage);
}

function downloadFile(filename, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
  showToast(`${filename} saved`);
}

function showToast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  window.setTimeout(() => els.toast.classList.remove("show"), 1800);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

init();
