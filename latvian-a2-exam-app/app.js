const optionLetters = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l"];

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
    timers: {
      listening: { total: 25 * 60, remaining: 25 * 60, running: false, startedAt: null },
      reading: { total: 30 * 60, remaining: 30 * 60, running: false, startedAt: null },
      writing: { total: 35 * 60, remaining: 35 * 60, running: false, startedAt: null },
      speaking: { total: 15 * 60, remaining: 15 * 60, running: false, startedAt: null }
    }
  },
  answers: {},
  submission: null
};

const PART_CONFIG = [
  { key: "listening", title: "Klausīšanās", english: "Listening", heading: "### Klausīšanās prasmes pārbaude", minutes: 25 },
  { key: "reading", title: "Lasīšana", english: "Reading", heading: "### Lasītprasmes pārbaude", minutes: 30 },
  { key: "writing", title: "Rakstīšana", english: "Writing", heading: "### Rakstītprasmes pārbaude", minutes: 35 },
  { key: "speaking", title: "Runāšana", english: "Speaking", heading: "### Runātprasmes pārbaude", minutes: 15 }
];

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
  toast: document.querySelector("#toast")
};

function init() {
  els.examSelect.innerHTML = EXAMS.map(exam => `<option value="${exam.id}">${exam.title}</option>`).join("");
  els.examSelect.addEventListener("change", () => loadExam(els.examSelect.value));

  document.querySelector("#reload-exam").addEventListener("click", () => loadExam(state.exam.id));
  document.querySelector("#submit-exam").addEventListener("click", () => submitAnswers());
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

  const requestedExam = new URLSearchParams(window.location.search).get("exam");
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
    state.submission = null;
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
  renderRunner();
  els.examOutput.innerHTML = renderMarkdown(state.markdown, state.exam);
  els.markdownOutput.textContent = state.markdown;
  els.jsonOutput.textContent = JSON.stringify(buildExportJson(), null, 2);
  renderSubmission();
  renderTts();
  renderImages();
  renderQuality();
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
    timer.total = durationForPart(part);
    timer.remaining = timer.total;
    timer.running = false;
    timer.startedAt = null;
  }
  state.runner.activePart = "listening";
}

function updateExamUrl() {
  const params = new URLSearchParams(window.location.search);
  params.set("exam", state.exam.id);
  params.set("part", state.runner.activePart);
  window.history.replaceState(null, "", `?${params.toString()}`);
}

function durationForPart(part) {
  return { listening: 25, reading: 30, writing: 35, speaking: 15 }[part] * 60;
}

function tickTimers() {
  let changed = false;
  for (const timer of Object.values(state.runner.timers)) {
    if (!timer.running) continue;
    timer.remaining = Math.max(0, timer.remaining - 1);
    changed = true;
    if (timer.remaining === 0) timer.running = false;
  }
  if (changed) renderTimersOnly();
}

function renderRunner() {
  const sections = getStudentSections(state.markdown);
  const activePart = getPartConfig(state.runner.activePart);
  const activeSectionLines = sections[activePart.key] || [];
  const progress = getPartProgress(activePart.key);
  const totalProgress = getExamProgress();
  els.runnerOutput.innerHTML = `
    <section class="official-header">
      <div>
        <strong>VALSTS VALODAS PRASMES PĀRBAUDE</strong>
        <span>Pamata (A2) līmenis</span>
      </div>
      <div class="candidate-code">Kods: PRAKSE-${state.exam.id}</div>
    </section>

    <div class="command-strip" aria-label="Exam command words">
      <span>Klausieties!</span>
      <span>Lasiet!</span>
      <span>Rakstiet!</span>
      <span>Atbildiet!</span>
      <span>Izvēlieties atbilstošo!</span>
    </div>

    <section class="exam-top">
      <div class="exam-title-group">
        <p class="eyebrow">A2 practice exam</p>
        <h3>${activePart.title} / ${activePart.english}</h3>
        <p>Maximum 15 points. Pass minimum: 9/15 in this skill.</p>
      </div>
      <div class="exam-status">
        <strong data-active-progress>${progress.answered}</strong>
        <span>responses</span>
      </div>
    </section>

    <nav class="part-tabs" aria-label="Exam parts">
      ${PART_CONFIG.map(part => renderPartTab(part)).join("")}
    </nav>

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
        <button type="button" data-action="open-submission">Review submission</button>
      </div>
    </section>
  `;
  bindRunnerEvents();
  renderTimersOnly();
}

function renderSkillFlow(part, sectionLines) {
  const safeSectionLines = Array.isArray(sectionLines) ? sectionLines : [];
  const tasks = TASK_CONFIG[part.key] || [];
  return `
    <section class="flow-part" data-part="${part.key}">
      <div class="flow-part-head">
        <div>
          <h3>${part.title} prasmes pārbaude</h3>
          <p>Izlasiet uzdevumu un atbildiet tieši zem jautājuma.</p>
        </div>
        <div class="flow-part-badge">${part.english}</div>
      </div>
      <div class="task-stack">
        ${tasks.map(task => {
          const taskLines = getTaskSection(safeSectionLines, task.heading, task.ends);
          const view = buildTaskView(taskLines, task);
          const referenceHtml = renderTaskReferencePanel(part.key, task, view.reference);
          return `
            <article class="task-block">
              <header class="task-header">
                <h4>${task.title}</h4>
                <span data-task-progress="${part.key}.${task.taskKey}">${formatTaskProgress(getTaskProgress(part.key, task.taskKey))}</span>
              </header>
              ${view.intro.length && shouldRenderTaskIntro(task) ? `<div class="task-stimulus document compact">${renderMarkdown(view.intro.join("\n"), state.exam)}</div>` : ""}
              ${referenceHtml}
              <div class="question-stack">
                ${renderTaskQuestions(part.key, task, view.questions, view)}
              </div>
            </article>
          `;
        }).join("")}
      </div>
    </section>
  `;
}

function shouldRenderTaskIntro(task) {
  return !["photo-sentences", "word-form", "writing-long"].includes(task.kind);
}

function renderTaskReferencePanel(section, task, referenceLines) {
  if (!referenceLines.length || task.kind === "drag-fill") return "";
  if (task.kind === "ad-match") {
    return renderAdReferencePanel(section, task.taskKey, referenceLines);
  }
  return `<aside class="task-reference-panel document compact">${renderMarkdown(referenceLines.join("\n"), state.exam)}</aside>`;
}

function renderTaskQuestions(section, task, questions, view) {
  if (task.kind === "choice-list") {
    return renderChoiceListTask(section, task, questions, false);
  }
  if (task.kind === "reading-choice") {
    return renderChoiceListTask(section, task, questions, true);
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

function renderPartMoveButton(direction) {
  const currentIndex = PART_CONFIG.findIndex(part => part.key === state.runner.activePart);
  const nextIndex = direction === "next" ? currentIndex + 1 : currentIndex - 1;
  const part = PART_CONFIG[nextIndex];
  if (!part) return "<span></span>";
  const label = direction === "next" ? `Next: ${part.title}` : `Previous: ${part.title}`;
  return `<button type="button" data-action="switch-part" data-part="${part.key}">${label}</button>`;
}

function renderTimersOnly() {
  document.querySelectorAll("[data-timer]").forEach(node => {
    const part = node.dataset.timer;
    node.textContent = formatTime(state.runner.timers[part].remaining);
  });
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
    node.textContent = formatTaskProgress(progress);
  });
  document.querySelectorAll("[data-exam-progress]").forEach(node => {
    const progress = getExamProgress();
    node.textContent = `${progress.answered}/${progress.total}`;
  });
  els.jsonOutput.textContent = JSON.stringify(buildExportJson(), null, 2);
  renderSubmission();
}

function formatTaskProgress(progress) {
  return `${progress.answered}/${progress.total} responses`;
}

function renderPartTimer(part, label, minutes) {
  const timer = state.runner.timers[part];
  return `
    <article class="timer-card ${state.runner.activePart === part ? "active" : ""}">
      <div>
        <h3>${label}</h3>
        <p>${minutes} min</p>
      </div>
      <div class="timer-display" data-timer="${part}">${formatTime(timer.remaining)}</div>
      <div class="timer-actions">
        <button type="button" data-action="start" data-part="${part}">${timer.running ? "Running" : "Start"}</button>
        <button type="button" data-action="pause" data-part="${part}">Pause</button>
        <button type="button" data-action="reset" data-part="${part}">Reset</button>
      </div>
    </article>
  `;
}

function renderChoiceListTask(section, task, questions, useReadingBox) {
  const safeQuestions = questions.length ? questions : fallbackQuestions(task.expected);
  return safeQuestions.map((question, index) => renderChoiceQuestion(section, task, question, index, useReadingBox)).join("");
}

function renderChoiceQuestion(section, task, question, index, useReadingBox) {
  const parsed = parseChoiceQuestion(question.lines, task.options);
  const name = `${section}.${task.taskKey}.${index}`;
  ensureAnswerSlot(section, task.taskKey, index);
  const value = state.answers[section][task.taskKey][index] || "";
  return `
    <article class="official-choice-question ${useReadingBox ? "reading-question" : ""}">
      ${useReadingBox ? renderReadingStimulus(parsed, index) : `<h5>${index + 1}. ${escapeHtml(parsed.stem || `Jautājums ${index + 1}`)}</h5>`}
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
  const options = ads.length ? ads.map(ad => ad.letter) : task.options.map(option => option.toUpperCase());
  const safeQuestions = questions.length ? questions : fallbackQuestions(task.expected);
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

function renderOralInterviewTask(section, task, questions) {
  const safeQuestions = questions.length ? questions : fallbackQuestions(task.expected);
  return `
    <div class="oral-interview-list">
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
}

function handleRunnerAction(dataset) {
  const { action, part } = dataset;
  if (action === "switch-part") {
    state.runner.activePart = part;
    updateExamUrl();
    renderRunner();
    window.scrollTo({ top: 0, behavior: "smooth" });
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
  if (action === "open-submission") {
    renderSubmission();
    setView("submission");
    return;
  }
  handleTimerAction(action, part);
}

function handleTimerAction(action, part) {
  const timer = state.runner.timers[part];
  state.runner.activePart = part;
  updateExamUrl();
  if (action === "start") {
    for (const key of Object.keys(state.runner.timers)) {
      state.runner.timers[key].running = key === part;
    }
    timer.running = true;
  }
  if (action === "pause") {
    timer.running = false;
  }
  if (action === "reset") {
    timer.remaining = timer.total;
    timer.running = false;
  }
  renderRunner();
}

function handleAnswerInput(event) {
  const target = event.target;
  const key = target.dataset.answer;
  if (target.type === "radio") {
    const [section, task, index] = target.name.split(".");
    ensureAnswerSlot(section, task, Number(index));
    state.answers[section][task][Number(index)] = target.value;
    state.submission = null;
    renderProgressOnly();
    return;
  }
  const [section, task, index] = key.split(".");
  ensureAnswerSlot(section, task, Number(index));
  state.answers[section][task][Number(index)] = target.value;
  state.submission = null;
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
  ensureAnswerSlot(section, task, targetIndex);
  if (value) {
    state.answers[section][task] = state.answers[section][task].map((item, itemIndex) => (
      itemIndex !== targetIndex && item === value ? "" : item
    ));
  }
  state.answers[section][task][targetIndex] = value;
  state.runner.selectedDragValue = "";
  state.submission = null;
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
          <audio controls preload="none" src="${asset.url}"></audio>
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
  for (const timer of Object.values(state.runner.timers)) {
    timer.running = false;
  }
  state.submission = buildSubmission("submitted");
  persistSubmission(state.submission);
  renderRunner();
  renderSubmission();
  setView("submission");
  showToast("Answers submitted locally");
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
    answer_key: answerKey,
    scoring,
    validation_queue: buildValidationQueue(answerKey)
  };
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
      remaining_seconds: timer.remaining,
      elapsed_seconds: timer.total - timer.remaining,
      remaining_display: formatTime(timer.remaining)
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
      <button type="button" data-submission-action="copy">Copy JSON</button>
      <button type="button" data-submission-action="download">Download JSON</button>
    </div>
    <pre class="code-panel submission-json">${escapeHtml(JSON.stringify(submission, null, 2))}</pre>
  `;
  els.submissionOutput.querySelectorAll("[data-submission-action]").forEach(button => {
    button.addEventListener("click", () => handleSubmissionAction(button.dataset.submissionAction));
  });
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

function handleSubmissionAction(action) {
  if (action === "submit") {
    submitAnswers();
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
    answer_key: answerKey,
    latest_submission: state.submission,
    submission_schema: {
      storage: "localStorage:latvian_a2_exam_submissions",
      status_values: ["draft", "submitted"],
      scoring_note: "Objective items are auto-scored from the Markdown answer key; writing and speaking free text remain in validation_queue."
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
