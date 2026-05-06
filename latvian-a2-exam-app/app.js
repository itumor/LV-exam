const optionLetters = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l"];

let EXAMS = Array.from({ length: 10 }, (_, index) => {
  const number = String(index + 1).padStart(2, "0");
  return {
    id: number,
    title: `A2 Mock Exam ${number}`,
    contentVersion: 1,
    markdownPath: `/api/exams/${number}/content`,
    sourcePath: `codex/A2_Mock_Exam_${number}.md`,
    attachmentRoot: `/codex/Attachments/A2_Mock_Exam_${number}/`
  };
});

const flowCore = window.ExamFlowCore;
if (!flowCore) {
  throw new Error("ExamFlowCore helper script did not load before app.js");
}

const state = {
  exam: EXAMS[0],
  markdown: "",
  answerKey: null,
  assets: {
    audio: [],
    images: []
  },
   auth: {
     status: "loading",
     account: null,
     profile: null,
     dashboard: null,
     error: ""
   },
   helpLang: (navigator.language || navigator.userLanguage || '').startsWith('lv') ? 'lv' : 'en',
  admin: {
    overview: null,
    accounts: [],
    exams: [],
    attempts: [],
    settings: {},
    selectedExamId: "",
    error: "",
    loaded: false
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
  flow: {
    screen: "home",
    mode: "exam",
    debugMode: false,
    candidate: {
      code: "",
      firstName: "",
      lastName: ""
    }
  },
  billing: {
    config: null,
    state: null,
    loading: false,
    error: "",
    learnerId: "",
    email: "",
    lastCheckout: null
  },
  attempt: {
    id: "",
    status: "",
    saveState: "idle",
    lastSavedAt: "",
    error: "",
    pendingTimers: {}
  },
  answers: {},
  submission: null,
  evaluation: null,
  evaluating: false,
  speaking: {
    recorder: null,
    recognition: null,
    chunks: {},
    audioUrls: {},
    uploadIds: {},
    recordingKey: null,
    transcripts: {},
    transcriptInterims: {},
    transcriptErrors: {}
  },
  listenPlayCount: {}
};

const PART_CONFIG = [
  { key: "listening", title: "Listening", english: "Listening", heading: "### Listening Skills Test", minutes: 25 },
  { key: "reading", title: "Reading", english: "Reading", heading: "### Reading Skills Test", minutes: 30 },
  { key: "writing", title: "Writing", english: "Writing", heading: "### Writing Skills Test", minutes: 35 },
  { key: "speaking", title: "Speaking", english: "Speaking", heading: "### Speaking Skills Test", minutes: 15 }
];

const FLOW_SCREENS = new Set(["home", "register", "instructions", "exam", "results"]);
const DEBUG_VIEWS = new Set(["markdown", "json", "tts", "prompts", "quality"]);
const PROTECTED_VIEWS = new Set(["dashboard", "admin"]);

function normalizeIncomingFlowScreen(screen) {
  if (!screen) return "";
  const aliases = { welcome: "home", candidate: "register" };
  const mapped = aliases[screen] || screen;
  return FLOW_SCREENS.has(mapped) ? mapped : "";
}

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
  billingOutput: document.querySelector("#billing-output"),
  helpOutput: document.querySelector("#help-output"),
  ttsOutput: document.querySelector("#tts-output"),
  promptOutput: document.querySelector("#prompt-output"),
  qualityOutput: document.querySelector("#quality-output"),
  authOutput: document.querySelector("#auth-output"),
  dashboardOutput: document.querySelector("#dashboard-output"),
  adminOutput: document.querySelector("#admin-output"),
  workspaceTitle: document.querySelector("#workspace-title"),
  validationPill: document.querySelector("#validation-pill"),
  globalPartNav: document.querySelector("#global-part-nav"),
  megaTrigger: document.querySelector("#mega-menu-trigger"),
  megaPanel: document.querySelector("#mega-dropdown-panel"),
  topbarTimer: document.querySelector("#topbar-timer"),
  progressFill: document.querySelector("#exam-progress-fill"),
  toast: document.querySelector("#toast")
};

async function init() {
  const params = new URLSearchParams(window.location.search);
  const requestedDebugMode = params.get("debug") === "1" || params.get("debug") === "true";
  renderExamSelectOptions();
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

  document.querySelectorAll(".sidebar-item").forEach(button => {
    button.addEventListener("click", () => {
      const view = button.dataset.view;
      const sub = button.dataset.sub;
      if (button.dataset.action === "toggle-auth") {
        if (state.auth.status === "authenticated") {
          logout();
        } else {
          setView("auth");
        }
        return;
      }
      if (view) {
        if (view === "help" && button.dataset.lang) {
          state.helpLang = button.dataset.lang;
        }
        setView(view);
        if (sub) handleSubView(view, sub);
      } else if (button.dataset.action === "start-exam") {
        startExamFromMenu();
      }
    });
  });

  document.getElementById("quick-start-exam")?.addEventListener("click", () => {
    state.flow.screen = "home";
    setView("runner");
    renderRunner();
  });
  document.getElementById("quick-resume")?.addEventListener("click", () => resumeExam().catch(error => showToast(error.message || "Resume failed")));
  document.getElementById("quick-status")?.addEventListener("click", () => { setView("billing"); handleSubView("billing", "status"); });
  document.getElementById("quick-buy")?.addEventListener("click", () => { setView("billing"); handleSubView("billing", "purchase"); });
  document.getElementById("quick-help")?.addEventListener("click", () => setView("help"));
  document.getElementById("quick-manual")?.addEventListener("click", () => showManual());
  initializeMegaDropdown();
  document.getElementById("sidebar-toggle")?.addEventListener("click", () => {
    document.querySelector(".sidebar")?.classList.toggle("open");
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      persistLocalDraft();
    }
  });

  document.querySelectorAll(".breadcrumb-item a").forEach(link => {
    link.addEventListener("click", event => {
      event.preventDefault();
      const targetView = link.dataset.bcView;
      if (targetView) setView(targetView);
    });
  });

  els.globalPartNav.addEventListener("click", event => {
    const button = event.target.closest("[data-global-part]");
    if (!button) return;
    switchPart(button.dataset.globalPart);
  });

  const urlParams = new URLSearchParams(window.location.search);
  const requestedScreenRaw = urlParams.get("screen");
  const requestedScreen = normalizeIncomingFlowScreen(requestedScreenRaw);
  const requestedView = urlParams.get("view");
  const requestedPart = urlParams.get("part");
  const requestedAttempt = urlParams.get("attempt");
  state.flow.screen = requestedScreen || (PART_CONFIG.some(part => part.key === requestedPart) ? "exam" : "home");
  if (requestedView === "billing") {
    setView("billing");
  }
  const requestedExam = urlParams.get("exam");
  await bootstrapAuth();
  ensureLearnerIdentity();
  state.flow.debugMode = requestedDebugMode && isAdminAccount();
  await loadExamCatalog();
  updateExamListInSidebar();
  if (state.auth.status === "authenticated") {
    await loadDashboard();
    if (isAdminAccount()) {
      await loadAdminData().catch(error => {
        state.admin.error = error.message;
      });
    }
    await loadExam(String(requestedExam || "01").padStart(2, "0"), { silent: true });
    if (requestedAttempt) {
      await loadServerAttempt(requestedAttempt).catch(() => false);
    }
    state.flow.screen = requestedScreen || (PART_CONFIG.some(part => part.key === requestedPart) ? "exam" : "home");
    const requestedOuterView = requestedView === "admin" && isAdminAccount()
      ? "admin"
      : requestedScreenRaw === "dashboard" ? "dashboard" : (requestedScreenRaw ? "runner" : "dashboard");
    setView(requestedOuterView);
  } else {
    await loadExam(String(requestedExam || "01").padStart(2, "0"), { silent: true });
    state.flow.screen = requestedScreen || (PART_CONFIG.some(part => part.key === requestedPart) ? "exam" : "home");
    setView("runner");
  }
  await loadBillingContext();
  renderTopChrome();
  renderAuth();
  renderDashboard();
  renderAdmin();
  updateSidebarMenu("runner");
  updateQuickActions();
  setInterval(tickTimers, 1000);
}

function renderExamSelectOptions() {
  els.examSelect.innerHTML = EXAMS.map(exam => `<option value="${exam.id}">${exam.title}</option>`).join("");
}

async function loadExamCatalog() {
  try {
    const response = await fetch("/api/exams/catalog", { credentials: "same-origin", cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !Array.isArray(payload.exams)) return;
    EXAMS = payload.exams.map(exam => ({
      id: String(exam.id),
      title: exam.title || `Exam ${exam.id}`,
      description: exam.description || "",
      status: exam.status || "published",
      contentVersion: exam.content_version || exam.contentVersion || 1,
      markdownPath: exam.markdownPath || `/api/exams/${encodeURIComponent(String(exam.id))}/content`,
      sourcePath: exam.sourcePath || `codex/A2_Mock_Exam_${String(exam.id).padStart(2, "0")}.md`,
      attachmentRoot: exam.attachmentRoot || `/codex/Attachments/A2_Mock_Exam_${String(exam.id).padStart(2, "0")}/`
    }));
    if (!EXAMS.length) {
      EXAMS = [];
      els.examSelect.innerHTML = "";
      return;
    }
    renderExamSelectOptions();
    if (!EXAMS.some(exam => exam.id === state.exam.id)) {
      state.exam = EXAMS[0];
    }
  } catch {
    // Static fallback keeps the local exam runner usable if the API is unavailable.
  }
}

async function fetchAnswerKey(examId) {
  try {
    const response = await fetch(`/api/exams/${examId}/answer-key`);
    if (response.ok) {
      const data = await response.json();
      state.answerKey = data.answer_key || {};
    }
  } catch {
    state.answerKey = null;
  }
}

async function loadExam(examId, options = {}) {
  const exam = EXAMS.find(item => item.id === examId) || EXAMS[0];
  if (!exam) {
    renderLoadError(new Error("No published exams are available."));
    return;
  }
  state.exam = exam;
  els.examSelect.value = exam.id;
  els.workspaceTitle.textContent = exam.title;
  els.examOutput.innerHTML = `<div class="loading">Loading ${escapeHtml(exam.sourcePath)}...</div>`;
  if (state.flow.mode === "practice") {
    fetchAnswerKey(exam.id);
  }

  try {
    const response = await fetch(`${exam.markdownPath}?v=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`);
    }
    state.markdown = await response.text();
    state.assets = extractAssets(state.markdown, exam);
    resetAnswers();
    resetTimers();
    resetAttemptState();
    state.submission = null;
    state.evaluation = null;
    state.evaluating = false;
    const requestedPart = new URLSearchParams(window.location.search).get("part");
    if (PART_CONFIG.some(part => part.key === requestedPart)) {
      state.runner.activePart = requestedPart;
    }
    restoreLocalDraft();
    updateExamUrl();
    renderAll();
    if (!options.silent) {
      showToast(`${exam.title} loaded`);
    }
  } catch (error) {
    renderLoadError(error);
  }
}

async function bootstrapAuth() {
  try {
    const response = await fetch("/api/session", { credentials: "same-origin" });
    const payload = await response.json();
    state.auth.status = payload.authenticated ? "authenticated" : "anonymous";
    state.auth.account = payload.account || null;
    state.auth.profile = payload.profile || null;
    state.auth.dashboard = null;
    state.auth.error = "";
  } catch (error) {
    state.auth.status = "anonymous";
    state.auth.account = null;
    state.auth.profile = null;
    state.auth.dashboard = null;
    state.auth.error = error.message;
  }
}

async function loadDashboard() {
   if (state.auth.status !== "authenticated") return null;
   // Fetch basic dashboard data
   const response = await fetch("/api/dashboard", { credentials: "same-origin" });
   const payload = await response.json();
   if (!response.ok) {
     throw new Error(payload.error || `Dashboard request failed with HTTP ${response.status}`);
   }
   
   // Fetch analytics data
   try {
     const analyticsResponse = await fetch("/api/attempts/analytics", { credentials: "same-origin" });
     const analyticsPayload = await analyticsResponse.json();
     if (analyticsResponse.ok) {
       payload.analytics = analyticsPayload;
     }
   } catch (error) {
     // If analytics fails, continue with basic dashboard data
     console.warn("Failed to load analytics:", error);
     payload.analytics = {};
   }
   
   state.auth.account = payload.account || state.auth.account;
   state.auth.profile = payload.profile || state.auth.profile;
   state.auth.dashboard = payload;
   return payload;
 }

function isAdminAccount() {
  return ["admin", "superadmin"].includes(state.auth.account?.role);
}

function apiErrorMessage(payload, fallback) {
  if (typeof payload?.error === "string") return payload.error;
  if (payload?.error?.message) return payload.error.message;
  return fallback;
}

async function adminFetch(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    body: options.body && typeof options.body !== "string" ? JSON.stringify(options.body) : options.body
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(apiErrorMessage(payload, `Admin request failed with HTTP ${response.status}`));
  }
  return payload;
}

async function loadAdminData() {
  if (!isAdminAccount()) return;
  const [overview, exams, accounts, attempts, settings] = await Promise.all([
    adminFetch("/api/admin/overview"),
    adminFetch("/api/admin/exams"),
    adminFetch("/api/admin/accounts"),
    adminFetch("/api/admin/attempts"),
    adminFetch("/api/admin/settings")
  ]);
  state.admin.overview = overview.summary || {};
  state.admin.exams = exams.exams || [];
  state.admin.accounts = accounts.accounts || [];
  state.admin.attempts = attempts.attempts || [];
  state.admin.settings = settings.settings || {};
  state.admin.loaded = true;
  if (!state.admin.selectedExamId && state.admin.exams[0]) {
    state.admin.selectedExamId = state.admin.exams[0].id;
  }
}

async function handleAuthSubmit(event, mode) {
  event.preventDefault();
  const form = event.currentTarget;
  const formData = new FormData(form);
  const payload = {
    email: String(formData.get("email") || "").trim(),
    password: String(formData.get("password") || "")
  };
  if (mode === "register") {
    payload.full_name = String(formData.get("full_name") || "").trim();
    payload.native_language = String(formData.get("native_language") || "").trim();
    payload.exam_target_date = String(formData.get("exam_target_date") || "").trim();
  }
  try {
    const response = await fetch(`/api/auth/${mode}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(payload)
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(result.error || `Authentication failed with HTTP ${response.status}`);
    }
    state.auth.status = "authenticated";
    state.auth.account = result.account || null;
    state.auth.profile = result.profile || null;
    state.auth.dashboard = result.dashboard || null;
    state.auth.error = "";
    await loadExam(state.exam.id || "01");
    await loadDashboard().catch(() => {});
    if (isAdminAccount()) {
      await loadAdminData().catch(error => {
        state.admin.error = error.message;
      });
    }
    setView(isAdminAccount() ? "admin" : "dashboard");
    renderAuth();
    renderDashboard();
    renderAdmin();
    updateSidebarMenu(isAdminAccount() ? "admin" : "dashboard");
    updateQuickActions();
    showToast(mode === "register" ? "Account created" : "Signed in");
  } catch (error) {
    state.auth.error = error.message;
    renderAuth();
    showToast(error.message);
  }
}

async function handleProfileSubmit(event) {
  event.preventDefault();
  if (state.auth.status !== "authenticated") {
    setView("auth");
    return;
  }
  const formData = new FormData(event.currentTarget);
  const payload = {
    full_name: String(formData.get("full_name") || "").trim(),
    native_language: String(formData.get("native_language") || "").trim(),
    exam_target_date: String(formData.get("exam_target_date") || "").trim(),
    exam_pack_status: String(formData.get("exam_pack_status") || "").trim()
  };
  const response = await fetch("/api/profile", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify(payload)
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    showToast(result.error || `Profile update failed with HTTP ${response.status}`);
    return;
  }
  state.auth.profile = result.profile || state.auth.profile;
  await loadDashboard().catch(() => {});
  renderAuth();
  renderDashboard();
  showToast("Profile updated");
}

async function logout() {
  await fetch("/api/auth/logout", {
    method: "POST",
    credentials: "same-origin"
  });
  state.auth = {
    status: "anonymous",
    account: null,
    profile: null,
    dashboard: null,
    error: ""
  };
  state.admin = {
    overview: null,
    accounts: [],
    exams: [],
    attempts: [],
    settings: {},
    selectedExamId: "",
    error: "",
    loaded: false
  };
  state.flow.screen = "home";
  state.runner.activePart = "listening";
  state.submission = null;
  state.evaluation = null;
  setView("auth");
  renderAuth();
  renderDashboard();
  updateSidebarMenu("auth");
  updateQuickActions();
  showToast("Signed out");
}

async function deleteAccount() {
  if (!window.confirm("Delete this account and its stored attempts?")) return;
  const response = await fetch("/api/account/delete", {
    method: "POST",
    credentials: "same-origin"
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    showToast(payload.error || `Account deletion failed with HTTP ${response.status}`);
    return;
  }
  await logout();
  showToast("Account deleted");
}

async function exportAccount() {
  const response = await fetch("/api/account/export", { credentials: "same-origin" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    showToast(payload.error || `Export failed with HTTP ${response.status}`);
    return;
  }
  downloadFile(`a2-account-${state.auth.account?.id || "export"}.json`, JSON.stringify(payload, null, 2), "application/json");
}

function ensureLearnerIdentity() {
  const storageKey = "latvian_a2_learner_identity";
  if (state.auth.status === "authenticated" && state.auth.account?.id) {
    state.billing.learnerId = state.auth.account.id;
    state.billing.email = state.auth.account.email || state.billing.email || "";
    return { learnerId: state.billing.learnerId, email: state.billing.email };
  }
  let identity = {};
  try {
    identity = JSON.parse(localStorage.getItem(storageKey) || "{}");
  } catch {
    identity = {};
  }
  if (!identity.learnerId) {
    identity.learnerId = crypto.randomUUID();
    localStorage.setItem(storageKey, JSON.stringify(identity));
  }
  state.billing.learnerId = identity.learnerId;
  state.billing.email = identity.email || "";
  return identity;
}

function saveLearnerIdentity(partial) {
  const storageKey = "latvian_a2_learner_identity";
  const current = ensureLearnerIdentity();
  const merged = { ...current, ...partial, learnerId: current.learnerId };
  localStorage.setItem(storageKey, JSON.stringify(merged));
  state.billing.learnerId = merged.learnerId;
  state.billing.email = merged.email || "";
  return merged;
}

async function loadBillingContext() {
  ensureLearnerIdentity();
  state.billing.loading = true;
  state.billing.error = "";
  try {
    const [configResponse, stateResponse] = await Promise.all([
      fetch("/api/billing/config", { cache: "no-store" }),
      fetch(`/api/billing/state?learner_id=${encodeURIComponent(state.billing.learnerId)}`, { cache: "no-store" })
    ]);
    const config = await configResponse.json().catch(() => null);
    const billingState = await stateResponse.json().catch(() => null);
    if (!configResponse.ok) {
      throw new Error(config?.error || `Failed to load billing config (${configResponse.status}).`);
    }
    if (!stateResponse.ok) {
      throw new Error(billingState?.error || `Failed to load billing state (${stateResponse.status}).`);
    }
    state.billing.config = config;
    state.billing.state = billingState.state;
  } catch (error) {
    state.billing.error = error.message;
  } finally {
    state.billing.loading = false;
    renderBilling();
    renderTopChrome();
  }
}

function renderAll() {
  renderTopChrome();
  renderAuth();
  renderDashboard();
  renderRunner();
  els.examOutput.innerHTML = renderMarkdown(state.markdown, state.exam);
  if (flowCore.shouldShowDebugPanels(state.flow.debugMode)) {
    els.markdownOutput.textContent = state.markdown;
    els.jsonOutput.textContent = JSON.stringify(buildExportJson(), null, 2);
  } else {
    els.markdownOutput.textContent = "";
    els.jsonOutput.textContent = "";
  }
  renderSubmission();
  renderBilling();
  if (flowCore.shouldShowDebugPanels(state.flow.debugMode)) {
    renderTts();
    renderImages();
    renderQuality();
  } else {
    els.ttsOutput.innerHTML = "";
    els.promptOutput.innerHTML = "";
    els.qualityOutput.innerHTML = "";
  }
  syncEvaluationButtons();
}

function renderAuth() {
  if (!els.authOutput) return;
  const sessionLabel = state.auth.status === "authenticated"
    ? `${escapeHtml(state.auth.account?.email || "")}`
    : "Guest";
  els.authOutput.innerHTML = `
    <section class="auth-shell">
      <article class="auth-card hero">
        <p class="eyebrow">Accounts</p>
        <h2>Latvian A2 learner access</h2>
        <p>Sign in to save attempts across sessions, protect exam routes, and track progress from the dashboard.</p>
        <div class="auth-session-chip">${sessionLabel}</div>
        ${state.auth.error ? `<p class="auth-error">${escapeHtml(state.auth.error)}</p>` : ""}
      </article>
      <article class="auth-card">
        <h3>Sign in</h3>
        <form id="login-form" class="auth-form">
          <label>Email<input class="form-control" name="email" type="email" autocomplete="email" required></label>
          <label>Password<input class="form-control" name="password" type="password" autocomplete="current-password" required></label>
          <button class="btn btn-primary" type="submit">Sign in</button>
        </form>
      </article>
      <article class="auth-card">
        <h3>Create account</h3>
        <form id="register-form" class="auth-form">
          <label>Full name<input class="form-control" name="full_name" type="text" autocomplete="name" required></label>
          <label>Email<input class="form-control" name="email" type="email" autocomplete="email" required></label>
          <label>Password<input class="form-control" name="password" type="password" autocomplete="new-password" minlength="8" required></label>
          <label>Native language<input class="form-control" name="native_language" type="text" autocomplete="off" placeholder="Optional"></label>
          <label>Exam target date<input class="form-control" name="exam_target_date" type="date"></label>
          <button class="btn btn-primary" type="submit">Create account</button>
        </form>
      </article>
    </section>
  `;
  els.authOutput.querySelector("#login-form")?.addEventListener("submit", event => handleAuthSubmit(event, "login"));
  els.authOutput.querySelector("#register-form")?.addEventListener("submit", event => handleAuthSubmit(event, "register"));

  const authToggle = document.getElementById("auth-toggle");
  if (authToggle) {
    authToggle.textContent = state.auth.status === "authenticated" ? "Sign Out" : "Sign In";
  }
}

function renderDashboard() {
   if (!els.dashboardOutput) return;
   if (state.auth.status !== "authenticated") {
     els.dashboardOutput.innerHTML = `
       <section class="dashboard-shell empty">
         <h2>Protected dashboard</h2>
         <p>Sign in to see attempts, latest score, and account controls.</p>
       </section>
     `;
     return;
   }
   const dashboard = state.auth.dashboard || {};
   const analytics = dashboard.analytics || {};
   const summary = dashboard.summary || {};
   const attempts = Array.isArray(dashboard.attempts) ? dashboard.attempts : [];
   const profile = state.auth.profile || dashboard.profile || {};
   const latestScore = summary.latest_score ?? "—";
   const skillCards = Object.entries(summary.skill_progress || {}).map(([skill, values]) => `
     <article class="dashboard-stat">
       <span>${escapeHtml(skill)}</span>
       <strong>${escapeHtml(values.objective_correct || 0)} / ${escapeHtml(values.objective_possible || 0)}</strong>
     </article>
   `).join("");
   
   // Analytics section
   const analyticsSection = analytics.trends && analytics.trends.length > 0 ? `
     <article class="dashboard-card analytics">
       <h3>Progress Over Time</h3>
       <div class="analytics-chart-container">
         <canvas id="progressChart" height="80"></canvas>
         <div class="chart-labels">
           <div>Total Score Trend</div>
           <div>Last updated: ${new Date().toLocaleDateString()}</div>
         </div>
       </div>
       <div class="analytics-insights">
         <h4>Category Performance</h4>
         <div class="category-grid">
           ${Object.entries(analytics.category_stats || {}).map(([category, stats]) => `
             <div class="category-card ${stats.status}">
               <h5>${escapeHtml(category.charAt(0).toUpperCase() + category.slice(1))}</h5>
               <div class="score-value">${stats.average_score}/15</div>
               <div class="status-label">${stats.label}</div>
               <div class="attempt-count">${stats.attempt_count} attempts</div>
             </div>
           `).join("")}
         </div>
       </div>
     </article>
   ` : `
     <article class="dashboard-card analytics empty">
       <h3>Progress Over Time</h3>
       <p>Complete more exams to see your progress trends and category insights.</p>
     </article>
   `;
   
   els.dashboardOutput.innerHTML = `
     <section class="dashboard-shell">
       <article class="dashboard-card hero">
         <p class="eyebrow">Dashboard</p>
         <h2>${escapeHtml(profile.full_name || state.auth.account?.email || "Learner")}</h2>
         <p>${escapeHtml(state.auth.account?.email || "")}</p>
         <div class="dashboard-actions">
           <button id="logout-button" class="btn btn-outline-light" type="button">Sign out</button>
           <button id="export-account-button" class="btn btn-outline-light" type="button">Export account</button>
           <button id="delete-account-button" type="button" class="btn btn-danger danger">Delete account</button>
         </div>
       </article>
       <article class="dashboard-card">
         <h3>Profile</h3>
         <form id="profile-form" class="auth-form compact">
           <label>Full name<input class="form-control" name="full_name" type="text" value="${escapeHtml(profile.full_name || "")}" required></label>
           <label>Native language<input class="form-control" name="native_language" type="text" value="${escapeHtml(profile.native_language || "")}"></label>
           <label>Exam target date<input class="form-control" name="exam_target_date" type="date" value="${escapeHtml(profile.exam_target_date || "")}"></label>
           <label>Exam pack status
             <select class="form-select" name="exam_pack_status">
               ${["free", "paid", "trial"].map(value => `<option value="${value}" ${String(profile.exam_pack_status || "free") === value ? "selected" : ""}>${value}</option>`).join("")}
             </select>
           </label>
           <button class="btn btn-primary" type="submit">Save profile</button>
         </form>
       </article>
       <article class="dashboard-card metrics">
         <div class="dashboard-metric"><span>Attempts taken</span><strong>${escapeHtml(summary.attempts_taken ?? 0)}</strong></div>
         <div class="dashboard-metric"><span>Latest score</span><strong>${escapeHtml(latestScore)}</strong></div>
         <div class="dashboard-metric"><span>Subscription</span><strong>${escapeHtml(summary.subscription_status || "free")}</strong></div>
         <div class="dashboard-metric"><span>Protected access</span><strong>${state.auth.status === "authenticated" ? "On" : "Off"}</strong></div>
       </article>
       <article class="dashboard-card">
         <h3>Skill progress</h3>
         <div class="dashboard-stats-grid">${skillCards || "<p>No attempts saved yet.</p>"}</div>
       </article>
       ${analyticsSection}
       <article class="dashboard-card attempts">
         <h3>Recent attempts</h3>
         ${attempts.length ? attempts.map(attempt => `
           <div class="attempt-row">
             <div>
               <strong>${escapeHtml(attempt.exam_title)}</strong>
               <p>${escapeHtml(attempt.submitted_at)}</p>
             </div>
             <span>${escapeHtml(attempt.score_total ?? "—")} points</span>
           </div>
         `).join("") : "<p>No server-backed attempts yet.</p>"}
       </article>
     </section>
   `;
   
   // Add event listeners
   els.dashboardOutput.querySelector("#logout-button")?.addEventListener("click", () => logout());
   els.dashboardOutput.querySelector("#delete-account-button")?.addEventListener("click", () => deleteAccount());
   els.dashboardOutput.querySelector("#export-account-button")?.addEventListener("click", () => exportAccount());
   els.dashboardOutput.querySelector("#profile-form")?.addEventListener("submit", handleProfileSubmit);
   
   // Initialize chart if we have data
   if (analytics.trends && analytics.trends.length > 0) {
     initProgressChart(analytics.trends);
   }
 }

function renderAdmin() {
  if (!els.adminOutput) return;
  if (state.auth.status !== "authenticated") {
    els.adminOutput.innerHTML = `
      <section class="dashboard-shell empty">
        <h2>Protected admin console</h2>
        <p>Sign in with an admin account to manage exams, users, submissions, and settings.</p>
      </section>
    `;
    return;
  }
  if (!isAdminAccount()) {
    els.adminOutput.innerHTML = `
      <section class="dashboard-shell empty">
        <h2>Admin access required</h2>
        <p>Your account can take exams and view allowed results, but it cannot manage platform data.</p>
      </section>
    `;
    return;
  }
  const overview = state.admin.overview || {};
  const selectedExam = state.admin.exams.find(exam => exam.id === state.admin.selectedExamId) || state.admin.exams[0] || null;
  els.adminOutput.innerHTML = `
    <section class="admin-shell">
      <article class="admin-hero">
        <div>
          <p class="eyebrow">Admin Console</p>
          <h2>Latvian A2 exam operations</h2>
          <p>Manage exam availability, learner accounts, submissions, scores, and platform settings from one protected workspace.</p>
          ${state.admin.error ? `<p class="auth-error">${escapeHtml(state.admin.error)}</p>` : ""}
        </div>
        <button id="refresh-admin" class="btn btn-light" type="button">Refresh</button>
      </article>
      <div class="admin-metrics">
        ${[
          ["Accounts", overview.accounts ?? 0],
          ["Admins", overview.admins ?? 0],
          ["Exams", overview.exams ?? 0],
          ["Published", overview.published ?? 0],
          ["Submissions", overview.submissions ?? 0]
        ].map(([label, value]) => `<div class="dashboard-metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("")}
      </div>
      <article class="admin-panel">
        <div class="admin-panel-header">
          <h3>Exams</h3>
          <button id="admin-new-exam" class="btn btn-primary" type="button">New exam</button>
        </div>
        <div class="admin-grid">
          <div class="admin-list">
            ${state.admin.exams.map(exam => `
              <button type="button" data-admin-exam="${escapeHtml(exam.id)}" class="${selectedExam?.id === exam.id ? "active" : ""}">
                <strong>${escapeHtml(exam.title)}</strong>
                <span>${escapeHtml(exam.id)} · ${escapeHtml(exam.status)}</span>
              </button>
            `).join("") || "<p>No exams in the catalog.</p>"}
          </div>
          <form id="admin-exam-form" class="auth-form">
            <label>Exam ID<input class="form-control" name="id" value="${escapeHtml(selectedExam?.id || "")}" ${selectedExam ? "readonly" : ""} required></label>
            <label>Title<input class="form-control" name="title" value="${escapeHtml(selectedExam?.title || "")}" required></label>
            <label>Status
              <select class="form-select" name="status">
                ${["draft", "published", "archived"].map(status => `<option value="${status}" ${selectedExam?.status === status ? "selected" : ""}>${status}</option>`).join("")}
              </select>
            </label>
            <label>Description<input class="form-control" name="description" value="${escapeHtml(selectedExam?.description || "")}"></label>
            <label>Markdown path<input class="form-control" name="markdownPath" value="${escapeHtml(selectedExam?.markdownPath || "")}" required></label>
            <label>Source path<input class="form-control" name="sourcePath" value="${escapeHtml(selectedExam?.sourcePath || "")}" required></label>
            <label>Attachment root<input class="form-control" name="attachmentRoot" value="${escapeHtml(selectedExam?.attachmentRoot || "")}"></label>
            <label class="full-span">Answer key JSON<textarea class="form-control" name="answerKeyJson" rows="6" placeholder='{"listening":{"task1":["a"]}}'>${escapeHtml(JSON.stringify(selectedExam?.answer_key || {}, null, 2))}</textarea></label>
            <button class="btn btn-primary" type="submit">${selectedExam ? "Save exam" : "Create exam"}</button>
            ${selectedExam ? `
              <div class="dashboard-actions">
                <button class="btn btn-primary" type="button" data-exam-status="published">Publish</button>
                <button class="btn btn-outline-primary" type="button" data-exam-status="archived">Archive</button>
                <button class="btn btn-outline-primary" type="button" data-exam-status="draft">Unpublish</button>
                <button type="button" id="delete-admin-exam" class="btn btn-danger danger">Delete</button>
              </div>
            ` : ""}
          </form>
        </div>
      </article>
      <article class="admin-panel">
        <h3>Users and roles</h3>
        <div class="admin-table-wrap">
          <table class="admin-table">
            <thead><tr><th>User</th><th>Role</th><th>Status</th><th></th></tr></thead>
            <tbody>
              ${state.admin.accounts.map(item => {
                const account = item.account || {};
                const profile = item.profile || {};
                const canPromote = state.auth.account?.role === "superadmin";
                return `
                  <tr>
                    <td><strong>${escapeHtml(profile.full_name || account.email)}</strong><br><span>${escapeHtml(account.email)}</span></td>
                    <td>
                      <select class="form-select form-select-sm" data-account-role="${escapeHtml(account.id)}">
                        ${["user", "admin", "superadmin"].map(role => `<option value="${role}" ${account.role === role ? "selected" : ""} ${!canPromote && role !== "user" ? "disabled" : ""}>${role}</option>`).join("")}
                      </select>
                    </td>
                    <td>
                      <select class="form-select form-select-sm" data-account-status="${escapeHtml(account.id)}">
                        ${["active", "disabled"].map(status => `<option value="${status}" ${account.status === status ? "selected" : ""}>${status}</option>`).join("")}
                      </select>
                    </td>
                    <td><button type="button" class="btn btn-primary btn-sm" data-save-account="${escapeHtml(account.id)}">Save</button></td>
                  </tr>
                `;
              }).join("")}
            </tbody>
          </table>
        </div>
      </article>
      <article class="admin-panel">
        <h3>Submissions and scores</h3>
        <div class="admin-table-wrap">
          <table class="admin-table">
            <thead><tr><th>Learner</th><th>Exam</th><th>Status</th><th>Score</th><th>Submitted</th></tr></thead>
            <tbody>
              ${state.admin.attempts.map(attempt => `
                <tr>
                  <td>${escapeHtml(attempt.account_email || attempt.account_id)}</td>
                  <td>${escapeHtml(attempt.exam_title)}</td>
                  <td>${escapeHtml(attempt.status)}</td>
                  <td>${escapeHtml(attempt.score_total ?? "—")}</td>
                  <td>${escapeHtml(attempt.submitted_at || attempt.started_at || "")}</td>
                </tr>
              `).join("") || `<tr><td colspan="5">No submissions yet.</td></tr>`}
            </tbody>
          </table>
        </div>
      </article>
      <article class="admin-panel">
        <h3>Settings</h3>
        <form id="admin-settings-form" class="auth-form compact">
          <label>Results visibility<input class="form-control" name="results_visibility" value="${escapeHtml(state.admin.settings.results_visibility || "show_allowed_results_only")}"></label>
          <label>Default exam mode<input class="form-control" name="default_exam_mode" value="${escapeHtml(state.admin.settings.default_exam_mode || "exam")}"></label>
          <button class="btn btn-primary" type="submit">Save settings</button>
        </form>
      </article>
    </section>
  `;
  bindAdminEvents();
}

function bindAdminEvents() {
  els.adminOutput.querySelector("#refresh-admin")?.addEventListener("click", () => refreshAdminView());
  els.adminOutput.querySelector("#admin-new-exam")?.addEventListener("click", () => {
    state.admin.selectedExamId = "";
    renderAdmin();
  });
  els.adminOutput.querySelectorAll("[data-admin-exam]").forEach(button => {
    button.addEventListener("click", () => {
      state.admin.selectedExamId = button.dataset.adminExam;
      renderAdmin();
    });
  });
  els.adminOutput.querySelector("#admin-exam-form")?.addEventListener("submit", saveAdminExam);
  els.adminOutput.querySelectorAll("[data-exam-status]").forEach(button => {
    button.addEventListener("click", () => updateAdminExamStatus(button.dataset.examStatus));
  });
  els.adminOutput.querySelector("#delete-admin-exam")?.addEventListener("click", deleteAdminExam);
  els.adminOutput.querySelectorAll("[data-save-account]").forEach(button => {
    button.addEventListener("click", () => saveAdminAccount(button.dataset.saveAccount));
  });
  els.adminOutput.querySelector("#admin-settings-form")?.addEventListener("submit", saveAdminSettings);
}

async function refreshAdminView() {
  try {
    await loadAdminData();
    await loadExamCatalog();
    renderAdmin();
    renderDashboard();
    showToast("Admin data refreshed");
  } catch (error) {
    state.admin.error = error.message;
    renderAdmin();
    showToast(error.message);
  }
}

async function saveAdminExam(event) {
  event.preventDefault();
  const formData = new FormData(event.currentTarget);
  const examId = String(formData.get("id") || "").trim();
  const selected = state.admin.exams.find(exam => exam.id === state.admin.selectedExamId);
  const path = selected ? `/api/admin/exams/${encodeURIComponent(selected.id)}` : "/api/admin/exams";
  try {
    let answerKey = {};
    const rawAnswerKey = String(formData.get("answerKeyJson") || "").trim();
    if (rawAnswerKey) {
      answerKey = JSON.parse(rawAnswerKey);
    }
    const payload = await adminFetch(path, {
      method: "POST",
      body: {
        id: examId,
        title: String(formData.get("title") || "").trim(),
        status: String(formData.get("status") || "draft"),
        description: String(formData.get("description") || "").trim(),
        markdownPath: String(formData.get("markdownPath") || "").trim(),
        sourcePath: String(formData.get("sourcePath") || "").trim(),
        attachmentRoot: String(formData.get("attachmentRoot") || "").trim(),
        answer_key: answerKey
      }
    });
    state.admin.selectedExamId = payload.exam?.id || examId;
    await refreshAdminView();
    showToast("Exam saved");
  } catch (error) {
    showToast(error.message);
  }
}

async function updateAdminExamStatus(status) {
  if (!state.admin.selectedExamId) return;
  try {
    await adminFetch(`/api/admin/exams/${encodeURIComponent(state.admin.selectedExamId)}/status`, {
      method: "POST",
      body: { status }
    });
    await refreshAdminView();
    showToast(`Exam ${status}`);
  } catch (error) {
    showToast(error.message);
  }
}

async function deleteAdminExam() {
  if (!state.admin.selectedExamId || !window.confirm("Delete this exam from the server catalog?")) return;
  try {
    await adminFetch(`/api/admin/exams/${encodeURIComponent(state.admin.selectedExamId)}/delete`, {
      method: "POST",
      body: {}
    });
    state.admin.selectedExamId = "";
    await refreshAdminView();
    showToast("Exam deleted");
  } catch (error) {
    showToast(error.message);
  }
}

async function saveAdminAccount(accountId) {
  try {
    await adminFetch(`/api/admin/accounts/${encodeURIComponent(accountId)}`, {
      method: "POST",
      body: {
        role: els.adminOutput.querySelector(`[data-account-role="${CSS.escape(accountId)}"]`)?.value || "user",
        status: els.adminOutput.querySelector(`[data-account-status="${CSS.escape(accountId)}"]`)?.value || "active"
      }
    });
    await refreshAdminView();
    showToast("Account updated");
  } catch (error) {
    showToast(error.message);
  }
}

async function saveAdminSettings(event) {
  event.preventDefault();
  const formData = new FormData(event.currentTarget);
  try {
    const payload = await adminFetch("/api/admin/settings", {
      method: "POST",
      body: {
        settings: Object.fromEntries(formData.entries())
      }
    });
    state.admin.settings = payload.settings || state.admin.settings;
    renderAdmin();
    showToast("Settings saved");
  } catch (error) {
    showToast(error.message);
  }
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

function resetAttemptState() {
  for (const timerId of Object.values(state.attempt.pendingTimers || {})) {
    clearTimeout(timerId);
  }
  state.attempt = {
    id: "",
    status: "",
    saveState: "idle",
    lastSavedAt: "",
    error: "",
    pendingTimers: {}
  };
}

function localDraftKey() {
  const learner = state.billing.learnerId || "guest";
  return `latvian_a2_exam_draft_${learner}_${state.exam.id}`;
}

function persistLocalDraft() {
  try {
    const draft = {
      examId: state.exam.id,
      attemptId: state.attempt.id,
      attemptStatus: state.attempt.status,
      flow: {
        screen: state.flow.screen,
        mode: state.flow.mode,
        candidate: state.flow.candidate
      },
      activePart: state.runner.activePart,
      timers: snapshotTimers(),
      answers: cloneJson(state.answers),
      updatedAt: new Date().toISOString()
    };
    localStorage.setItem(localDraftKey(), JSON.stringify(draft));
  } catch {
    // Private browsing or storage quotas should not block exam entry.
  }
}

function restoreLocalDraft() {
  try {
    const raw = localStorage.getItem(localDraftKey());
    if (!raw) return false;
    const draft = JSON.parse(raw);
    if (!draft || draft.examId !== state.exam.id || draft.attemptStatus === "submitted" || draft.attemptStatus === "scored") {
      return false;
    }
    if (draft.answers && typeof draft.answers === "object") {
      state.answers = draft.answers;
    }
    if (draft.flow && typeof draft.flow === "object") {
      state.flow.mode = draft.flow.mode === "practice" ? "practice" : "exam";
      state.flow.candidate = draft.flow.candidate || state.flow.candidate;
    }
    if (draft.activePart && PART_CONFIG.some(part => part.key === draft.activePart)) {
      state.runner.activePart = draft.activePart;
    }
    if (draft.timers && typeof draft.timers === "object") {
      for (const [part, timer] of Object.entries(draft.timers)) {
        if (!state.runner.timers[part]) continue;
        const savedTotal = Number(timer.total_seconds) || state.runner.timers[part].total;
        const savedRemaining = Number(timer.remaining_seconds) || savedTotal;
        if (timer.started_at && savedRemaining > 0) {
          const elapsedWhileAway = Math.floor((Date.now() - timer.started_at) / 1000);
          state.runner.timers[part].remaining = Math.max(0, savedRemaining - elapsedWhileAway);
          state.runner.timers[part].running = state.runner.timers[part].remaining > 0;
          state.runner.timers[part].startedAt = state.runner.timers[part].running ? timer.started_at : null;
        } else {
          state.runner.timers[part].remaining = savedRemaining;
          state.runner.timers[part].running = false;
          state.runner.timers[part].startedAt = null;
        }
        state.runner.timers[part].total = savedTotal;
      }
    }
    if (draft.attemptId) {
      state.attempt.id = draft.attemptId;
      state.attempt.status = draft.attemptStatus || "in_progress";
    }
    return true;
  } catch {
    return false;
  }
}

function clearLocalDraft() {
  try {
    localStorage.removeItem(localDraftKey());
  } catch {
    // Ignore restricted storage.
  }
}

function applyServerAttempt(attempt) {
  if (!attempt || typeof attempt !== "object") return;
  state.attempt.id = attempt.id || state.attempt.id;
  state.attempt.status = attempt.status || state.attempt.status;
  if (attempt.answers && typeof attempt.answers === "object") {
    state.answers = mergeAnswers(state.answers, attempt.answers);
  }
  if (attempt.exam_id && String(attempt.exam_id).endsWith(state.exam.id)) {
    state.exam.title = attempt.exam_title || state.exam.title;
  }
  if (attempt.status === "scored" || attempt.status === "submitted") {
    state.submission = buildSubmission("submitted");
    const scoring = attempt.score_payload?.scoring || attempt.score_payload?.evaluation?.scoring;
    if (scoring) {
      state.submission.scoring = scoring;
    }
  }
}

function mergeAnswers(base, incoming) {
  const merged = cloneJson(base);
  for (const [skill, tasks] of Object.entries(incoming || {})) {
    if (!tasks || typeof tasks !== "object") continue;
    merged[skill] ||= {};
    for (const [task, values] of Object.entries(tasks)) {
      if (Array.isArray(values)) {
        merged[skill][task] = values.slice();
      }
    }
  }
  return merged;
}

async function ensureServerAttempt() {
  if (state.auth.status !== "authenticated") {
    if (state.attempt.id) return true;
    state.attempt.id = `local_${state.exam.id}_${crypto.randomUUID()}`;
    const response = await fetch("/api/billing/consume-exam", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        learner_id: state.billing.learnerId,
        exam_id: state.exam.id,
        source_reference: state.attempt.id,
        source_event_id: state.attempt.id
      })
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.allowed) {
      state.attempt.id = "";
      state.billing.state = payload.state || state.billing.state;
      state.billing.error = payload.reason === "account_frozen"
        ? "This account is frozen. Open Billing to resolve the entitlement."
        : "No exam attempts are available. Open Billing to buy more access.";
      renderBilling();
      setView("billing");
      showToast("Upgrade required");
      return false;
    }
    state.billing.state = payload.state || state.billing.state;
    state.attempt.status = "started";
    persistLocalDraft();
    return true;
  }
  if (state.attempt.id) return true;
  const attemptId = `attempt_${state.exam.id}_${crypto.randomUUID()}`;
  try {
    const response = await fetch("/api/attempts/start", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        attempt_id: attemptId,
        exam_id: state.exam.id,
        exam_title: state.exam.title,
        content_version: state.exam.contentVersion || 1
      })
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      state.billing.state = payload.state || state.billing.state;
      state.billing.error = payload.reason === "account_frozen"
        ? "This account is frozen. Open Billing to resolve the entitlement."
        : "No exam attempts are available. Open Billing to buy more access.";
      renderBilling();
      setView("billing");
      showToast("Upgrade required");
      return false;
    }
    applyServerAttempt(payload.attempt);
    persistLocalDraft();
    return true;
  } catch (error) {
    state.attempt.error = error.message;
    showToast("Could not start a saved attempt. Check your connection.");
    return false;
  }
}

async function loadServerAttempt(attemptId) {
  if (!attemptId || state.auth.status !== "authenticated") return false;
  const response = await fetch(`/api/attempts/${encodeURIComponent(attemptId)}`, { credentials: "same-origin", cache: "no-store" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || !payload.attempt) return false;
  applyServerAttempt(payload.attempt);
  persistLocalDraft();
  return true;
}

function queueAttemptAnswerSave(section, task, index, answer, delay = 450) {
  persistLocalDraft();
  if (state.auth.status !== "authenticated" || !state.attempt.id) return;
  const key = `${section}.${task}.${index}`;
  clearTimeout(state.attempt.pendingTimers[key]);
  state.attempt.pendingTimers[key] = window.setTimeout(() => {
    saveAttemptAnswer(section, task, index, answer).catch(() => {});
  }, delay);
}

async function saveAttemptAnswer(section, task, index, answer) {
  if (state.auth.status !== "authenticated" || !state.attempt.id) return;
  state.attempt.saveState = "saving";
  try {
    const response = await fetch(`/api/attempts/${encodeURIComponent(state.attempt.id)}/answers`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        skill: section,
        task_key: task,
        item_index: Number(index) + 1,
        answer
      })
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error?.message || payload.error || `Save failed with HTTP ${response.status}`);
    }
    state.attempt.status = payload.attempt?.status || "in_progress";
    state.attempt.saveState = "saved";
    state.attempt.lastSavedAt = new Date().toISOString();
    state.attempt.error = "";
  } catch (error) {
    state.attempt.saveState = "error";
    state.attempt.error = error.message;
    showToast("Answer saved locally; server retry needed.");
  } finally {
    persistLocalDraft();
  }
}

function updateExamUrl() {
  const params = new URLSearchParams(window.location.search);
  params.set("exam", state.exam.id);
  params.set("part", state.runner.activePart);
  params.set("screen", state.flow.screen);
  if (state.attempt.id) {
    params.set("attempt", state.attempt.id);
  }
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
  if (!changed) return;
  persistLocalDraft();
  if (state.flow.screen === "exam" && state.flow.mode === "exam" && !isAnyTimerRunning()) {
    const outcome = flowCore.advanceExamOnTimer(state.flow, state.runner, PART_CONFIG.map(part => part.key));
    state.flow = outcome.flow;
    state.runner = outcome.runner;
    if (outcome.action === "submit") {
      submitAnswers({ autoSubmitted: true });
      return;
    }
    updateExamUrl();
    renderRunner();
    return;
  }
  renderTimersOnly();
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
        <button type="button" class="btn btn-primary" data-action="submit-exam">Submit answers</button>
        <button type="button" class="btn btn-outline-primary" data-action="evaluate-exam">AI score</button>
        <button type="button" class="btn btn-outline-primary" data-action="open-submission">Review submission</button>
        <button type="button" class="btn btn-outline-primary" data-action="end-exam">End exam</button>
        <button type="button" class="btn btn-outline-primary" data-action="start-new-exam">Start new exam</button>
      </div>
    </section>
    ${renderUpgradePrompt("runner")}
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
      <h1>State Language Exam - Level A2</h1>
      <p>Official state language exam simulator prepared according to education and content standards.</p>
      ${renderAccessSummaryCard()}
      ${renderModeBadge()}
      ${renderFlowStepper("welcome")}
      ${renderFlowExamPicker()}
      <div class="mode-switch" role="group" aria-label="Režīms">
        <button type="button" data-flow-action="set-mode" data-mode="exam" class="btn ${state.flow.mode === "exam" ? "active btn-primary" : "btn-outline-primary"}">Exam Mode</button>
        <button type="button" data-flow-action="set-mode" data-mode="practice" class="btn ${state.flow.mode === "practice" ? "active btn-primary" : "btn-outline-primary"}">Practice Mode</button>
      </div>
      <div class="flow-primary-stack">
        <button type="button" class="btn btn-primary btn-lg flow-primary-button" data-flow-action="register">Start Full Exam</button>
        <button type="button" class="btn btn-outline-primary btn-lg flow-secondary-button" data-flow-action="start-practice">Practice by Section</button>
      </div>
      <div class="flow-home-links">
        <button type="button" class="btn btn-outline-primary" data-flow-action="open-auth">Account / Sign In</button>
        <button type="button" class="btn btn-outline-primary" data-flow-action="results">View Results</button>
        <button type="button" class="btn btn-outline-primary" data-flow-action="instructions">Instructions</button>
      </div>
      <p class="flow-version">System Version 1.2.0 • Official Simulator</p>
    </section>
  `;
}

function renderRegistrationScreen() {
  const candidate = state.flow.candidate;
  return `
    <section class="flow-card flow-register">
      <div class="flow-emblem" aria-hidden="true"></div>
      <h1>Candidate Registration</h1>
      <p>A2 State Language Exam Simulator</p>
      ${renderModeBadge()}
      ${renderFlowStepper("candidate")}
      ${renderFlowExamPicker("Selected Exam")}
      <form class="candidate-form" data-candidate-form>
        <label>
          Candidate Code
          <input class="form-control form-control-lg" name="code" value="${escapeHtml(candidate.code)}" autocomplete="off" required>
        </label>
        <label>
          First Name
          <input class="form-control form-control-lg" name="firstName" value="${escapeHtml(candidate.firstName)}" autocomplete="given-name" required>
        </label>
        <label>
          Last Name
          <input class="form-control form-control-lg" name="lastName" value="${escapeHtml(candidate.lastName)}" autocomplete="family-name" required>
        </label>
        <button type="submit" class="btn btn-success btn-lg flow-success-button">Start Exam</button>
      </form>
      <p class="form-note">Please enter data exactly as shown on your exam sheet.</p>
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
      ${renderModeBadge()}
      ${renderFlowStepper("instructions")}
      ${renderFlowExamPicker("Eksāmens")}
      <div class="instruction-panel">
        ${commands.map(([icon, label]) => `
          <div class="instruction-row">
            <span class="instruction-icon instruction-icon-${icon}" aria-hidden="true"></span>
            <strong>${label}</strong>
          </div>
        `).join("")}
      </div>
      <button type="button" class="btn btn-primary btn-lg flow-primary-button compact" data-flow-action="begin-exam">Saprasts / Atpakaļ</button>
    </section>
  `;
}

function renderFlowExamPicker(label = "Izvēlieties eksāmenu") {
  return `
    <label class="flow-exam-picker">
      <span>${label}</span>
      <select class="form-select form-select-lg" data-flow-exam-select aria-label="${label}">
        ${EXAMS.map(exam => `<option value="${exam.id}" ${exam.id === state.exam.id ? "selected" : ""}>${exam.title}</option>`).join("")}
      </select>
    </label>
  `;
}

function renderFlowStepper(activeKey) {
  return `
    <ol class="flow-stepper" aria-label="Exam flow">
      ${flowCore.FLOW_STEPS.map(step => `
        <li class="${step.key === activeKey ? "active" : ""}">
          <span>${step.label}</span>
        </li>
      `).join("")}
    </ol>
  `;
}

function renderModeBadge() {
  return `
    <div class="mode-badge ${state.flow.mode === "practice" ? "practice" : "exam"}" aria-label="Current mode">
      ${state.flow.mode === "practice" ? "Practice mode" : "Real simulation mode"}
    </div>
  `;
}

function renderResultsScreen() {
  const submission = ensureSubmission("draft");
  const summary = flowCore.buildResultsSummary({
    submission,
    evaluation: state.evaluation,
    partConfig: PART_CONFIG,
    skillLabels: {
      listening: "Klausīšanās",
      reading: "Lasīšana",
      writing: "Rakstīšana",
      speaking: "Runāšana"
    }
  });
  return `
    <section class="results-flow">
      <h1>Exam Results</h1>
      <p>Your performance summary by exam section.</p>
      ${renderModeBadge()}
      ${renderFlowStepper("results")}
      <div class="results-total">
        <strong>${summary.total} / ${summary.totalMax}</strong>
        <span>${summary.passed ? "Passed" : "Keep practicing"}</span>
      </div>
      <div class="results-table" role="table" aria-label="Eksāmena rezultāti">
        <div class="results-row results-head" role="row">
          <span>Sadaļa</span><span>Punkti</span><span>Procenti</span><span>Statuss</span>
        </div>
        ${summary.scores.map(score => {
          const part = PART_CONFIG.find(item => item.key === score.key) || { title: score.label };
          const percent = Math.round((score.points / 15) * 100);
          return `
          <div class="results-row" role="row">
            <span>${part.title}</span>
            <span>${score.points} / 15</span>
            <span><b>${percent}%</b><i style="--value:${percent}%"></i></span>
            <span class="${score.passed ? "status-pass" : "status-fail"}">${score.passed ? "Nokārtots" : "Jātrenējas"}</span>
          </div>
        `; }).join("")}
      </div>
      <div class="final-status ${summary.passed ? "passed" : "failed"}">
        <p>Noslēguma statuss</p>
        <h2>Kopējais rezultāts: ${summary.passed ? "nokārtots" : "nav nokārtots"}</h2>
        <span>Minimums ir 9 punkti katrā prasmē. Šis pārskats izmanto lokālo objektīvo vērtējumu un saglabā rakstīšanas/runāšanas darbus pārbaudei.</span>
      </div>
      <div class="results-insights">
        <article>
          <h3>Weak areas</h3>
          <p>${summary.weakAreas.length ? summary.weakAreas.join(", ") : "None"}</p>
        </article>
        <article>
          <h3>Suggested next practice</h3>
          <p>${summary.nextPractice.length ? summary.nextPractice.join(", ") : "Review the weakest skills."}</p>
        </article>
      </div>
      ${renderUpgradePrompt("results")}
      <div class="results-actions">
        <button type="button" class="btn btn-primary flow-primary-button results-action" data-flow-action="open-submission">Skatīt detalizētu pārskatu</button>
        <button type="button" class="btn btn-outline-primary flow-secondary-button" data-flow-action="view-candidate-report">Kandidāta pārskats</button>
        <button type="button" class="btn btn-outline-primary flow-secondary-button" data-flow-action="download-pdf-report">Lejupielādēt PDF</button>
      </div>
      ${renderCandidateReport()}
    </section>
  `;
}

function renderCandidateReport() {
  if (!state.evaluation) return "";
  const submission = ensureSubmission("draft");
  const report = flowCore.buildCandidateReportModel({
    submission,
    evaluation: state.evaluation.evaluation || state.evaluation,
    candidate: state.flow.candidate
  });
  const html = flowCore.buildCandidateReportHtml(report);
  return `<div class="candidate-report-wrapper" id="candidate-report-section">${html}</div>`;
}

function getBillingSnapshot() {
  return state.billing.state || {
    free_exam_available: true,
    free_exam_taken: 0,
    paid_attempts_remaining: 0,
    ai_credits_remaining: 0,
    subscription_active: false,
    frozen: false,
    current_plan: "free",
    recent_events: [],
    recent_activity: []
  };
}

function canRunAiScoring() {
  if (!state.billing.config?.stripe_enabled) return true;
  if (state.auth.status !== "authenticated") return true;
  const billing = getBillingSnapshot();
  return !billing.frozen && (billing.subscription_active || (billing.ai_credits_remaining || 0) > 0);
}

function renderAccessSummaryCard() {
  const billing = getBillingSnapshot();
  const status = billing.frozen
    ? "Account frozen"
    : billing.subscription_active
      ? "Subscription active"
      : billing.paid_attempts_remaining > 0
        ? "Paid attempts available"
        : billing.free_exam_available
          ? "Free exam available"
          : "Upgrade required";
  const plan = billing.current_plan || "free";
  return `
    <section class="billing-summary-card">
      <div>
        <p class="eyebrow">Access</p>
        <h3>${escapeHtml(status)}</h3>
        <p>Plan: <strong>${escapeHtml(plan)}</strong> · Free exam remaining: <strong>${billing.free_exam_available ? "1" : "0"}</strong> · Paid attempts: <strong>${escapeHtml(billing.paid_attempts_remaining ?? 0)}</strong> · AI credits: <strong>${escapeHtml(billing.ai_credits_remaining ?? 0)}</strong></p>
      </div>
      <div class="billing-summary-actions">
        <button type="button" class="btn btn-outline-primary" data-billing-action="open-billing">Open billing</button>
        <button type="button" class="btn btn-outline-primary" data-billing-action="refresh-billing">Refresh access</button>
      </div>
    </section>
  `;
}

function renderUpgradePrompt(context = "home") {
  const billing = getBillingSnapshot();
  const shouldPrompt = billing.frozen || (!billing.free_exam_available && billing.paid_attempts_remaining <= 0);
  if (!shouldPrompt) return "";
  const title = billing.frozen ? "Access paused" : "Free exam finished";
  const body = billing.frozen
    ? "This account is frozen because a refund, dispute, or manual freeze removed the active entitlement."
    : "The configured free exam has been used. Upgrade to unlock more attempts or the monthly subscription.";
  return `
    <section class="upgrade-prompt ${context}">
      <div>
        <p class="eyebrow">Upgrade</p>
        <h3>${escapeHtml(title)}</h3>
        <p>${escapeHtml(body)}</p>
      </div>
      <div class="upgrade-actions">
        <button type="button" class="btn btn-primary" data-billing-action="checkout" data-product="single_exam">Buy one exam</button>
        <button type="button" class="btn btn-outline-primary" data-billing-action="checkout" data-product="exam_pack">Buy pack</button>
        <button type="button" class="btn btn-outline-primary" data-billing-action="checkout" data-product="monthly_subscription">Subscribe monthly</button>
      </div>
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
            <article class="stitch-task-panel">
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
              ${renderTaskHint(part.key, task)}
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

function renderTaskHint(section, task) {
  if (state.flow.mode !== "practice" || !state.answerKey) return "";
  const taskAnswers = (state.answerKey[section] || {})[task.taskKey];
  if (!taskAnswers) return "";
  return `
    <div class="task-hint">
      <button type="button" class="btn btn-outline-secondary btn-sm" data-action="toggle-hint" data-section="${section}" data-task="${task.taskKey}">
        Show Correct Answer
      </button>
      <div class="hint-answer" id="hint-${section}-${task.taskKey}" style="display:none;">
        <strong>Correct Answer:</strong> ${Array.isArray(taskAnswers) ? taskAnswers.join(", ") : taskAnswers}
      </div>
    </div>
  `;
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

function switchPart(partKey) {
  if (!PART_CONFIG.some(part => part.key === partKey)) return;
  if (!flowCore.canSwitchPart(state.flow.mode, state.runner.activePart, partKey, PART_CONFIG.map(part => part.key))) {
    showToast("In exam mode, follow the fixed section order.");
    return;
  }
  const keepTimerRunning = state.flow.screen === "exam" && state.flow.mode === "exam" && isAnyTimerRunning();
  state.runner.activePart = partKey;
  if (keepTimerRunning) {
    startOnlyTimer(partKey);
  }
  state.flow.screen = "exam";
  updateExamUrl();
  persistLocalDraft();
  renderRunner();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function setFlowScreen(screen, options = {}) {
  if (!FLOW_SCREENS.has(screen)) return;
  state.flow.screen = screen;
  if (screen === "exam") {
    setView("runner");
    if (options.startTimer) {
      startOnlyTimer(state.runner.activePart);
    }
  }
  updateExamUrl();
  persistLocalDraft();
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
    <button type="button" data-action="switch-part" data-part="${part.key}" class="btn ${part.key === state.runner.activePart ? "active btn-primary" : "btn-outline-primary"}">
      <span>${part.title}</span>
      <strong data-progress="${part.key}">${progress.answered} done</strong>
    </button>
  `;
}

function renderTopChrome() {
  const examProgress = getExamProgress();
  const activePart = getPartConfig(state.runner.activePart);
  document.body.dataset.flowScreen = state.flow.screen;
  document.body.dataset.authenticated = String(state.auth.status === "authenticated");
  document.body.dataset.debugMode = String(flowCore.shouldShowDebugPanels(state.flow.debugMode));
  const allowPartNav = state.flow.screen === "exam" && state.flow.mode === "practice";
  els.globalPartNav.innerHTML = allowPartNav ? PART_CONFIG.map(part => `
    <button type="button" data-global-part="${part.key}" class="nav-link ${part.key === state.runner.activePart ? "active" : ""}">
      ${part.title}
    </button>
  `).join("") : "";
  if (els.topbarTimer) {
    if (state.flow.screen === "exam") {
      els.topbarTimer.textContent = formatTime(state.runner.timers[activePart.key].remaining);
    } else if (state.auth.status === "authenticated") {
      els.topbarTimer.textContent = formatLongTime(45 * 60);
    } else {
      els.topbarTimer.textContent = "Guest mode";
    }
  }
  if (els.progressFill) {
    const percent = examProgress.total
      ? Math.round((examProgress.answered / examProgress.total) * 100)
      : 0;
    els.progressFill.style.width = `${percent}%`;
  }
}

function renderPartMoveButton(direction) {
  const currentIndex = PART_CONFIG.findIndex(part => part.key === state.runner.activePart);
  const nextIndex = direction === "next" ? currentIndex + 1 : currentIndex - 1;
  const part = PART_CONFIG[nextIndex];
  if (!part && direction === "next") {
    return `<button type="button" class="btn btn-primary" data-action="${state.flow.mode === "exam" ? "submit-exam" : "show-results"}">Pabeigt</button>`;
  }
  if (!part) return "<span></span>";
  if (direction === "previous" && state.flow.mode === "exam") {
    return `<button type="button" class="btn btn-outline-secondary" disabled title="Navigation is forward-only in exam mode">← ${part.title}</button>`;
  }
  const label = direction === "next" ? `Next: ${part.title}` : `Previous: ${part.title}`;
  return `<button type="button" class="btn btn-primary" data-action="switch-part" data-part="${part.key}">${label}</button>`;
}

function renderTimersOnly() {
  document.querySelectorAll("[data-timer]").forEach(node => {
    const part = node.dataset.timer;
    node.textContent = formatTime(state.runner.timers[part].remaining);
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
    button.addEventListener("click", () => {
      handleFlowAction(button.dataset).catch(error => {
        console.error(error);
        showToast(error.message || "Action failed");
      });
    });
  });
  document.querySelectorAll("[data-billing-action]").forEach(button => {
    button.addEventListener("click", () => handleBillingAction(button.dataset.billingAction, button.dataset.product));
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

async function handleFlowAction(dataset) {
  const { flowAction } = dataset;
  if (flowAction === "set-mode") {
    const newMode = dataset.mode || "exam";
    state.flow = flowCore.switchFlowMode(state.flow, newMode);
    if (newMode === "practice") {
      fetchAnswerKey(state.exam.id);
    } else {
      state.answerKey = null;
    }
    renderRunner();
    return;
  }
  if (flowAction === "register") {
    setFlowScreen("register");
    return;
  }
  if (flowAction === "start-practice") {
    state.flow = flowCore.switchFlowMode(state.flow, "practice");
    setFlowScreen("instructions");
    return;
  }
  if (flowAction === "instructions") {
    setFlowScreen("instructions");
    return;
  }
  if (flowAction === "begin-exam") {
    const ready = await ensureServerAttempt();
    if (!ready) return;
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
    return;
  }
  if (flowAction === "open-auth") {
    renderAuth();
    setView("auth");
    return;
  }
  if (flowAction === "open-admin") {
    renderAdmin();
    setView("admin");
    return;
  }
  if (flowAction === "open-billing") {
    setView("billing");
  }
  if (flowAction === "view-candidate-report") {
    const reportSection = document.querySelector("#candidate-report-section");
    if (reportSection) reportSection.scrollIntoView({ behavior: "smooth" });
    return;
  }
  if (flowAction === "download-pdf-report") {
    downloadCandidateReportPdf();
    return;
  }
}

function downloadCandidateReportPdf() {
  const reportSection = document.querySelector("#candidate-report-section");
  const submission = ensureSubmission("draft");
  const report = state.evaluation
    ? flowCore.buildCandidateReportModel({
        submission,
        evaluation: state.evaluation.evaluation || state.evaluation,
        candidate: state.flow.candidate
      })
    : null;
  const html = report ? flowCore.buildCandidateReportHtml(report) : "<p>No AI evaluation available. Run AI scoring first.</p>";
  const full = `<!DOCTYPE html>
<html lang="lv"><head><meta charset="UTF-8"><title>Kandidāta pārskats</title>
<style>
  body { font-family: sans-serif; max-width: 800px; margin: 2rem auto; padding: 1rem; }
  table { border-collapse: collapse; width: 100%; }
  th, td { border: 1px solid #ccc; padding: .4rem .6rem; text-align: left; }
  .pass { color: green; } .fail { color: red; }
  footer { margin-top: 2rem; font-size: 0.8rem; color: #666; border-top: 1px solid #ccc; padding-top: 1rem; }
</style>
</head><body>${html}</body></html>`;
  const blob = new Blob([full], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `kandidata-parskats-${submission.submission_id || "draft"}.html`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
  showToast("Report downloaded as HTML — open in browser and use Print > Save as PDF.");
}

function formatLongTime(seconds) {
   const safeSeconds = Math.max(0, Number(seconds) || 0);
   const hours = Math.floor(safeSeconds / 3600);
   const minutes = Math.floor((safeSeconds % 3600) / 60);
   const secs = safeSeconds % 60;
   return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
 }

function initProgressChart(trendsData) {
   // Check if Chart.js is available (it should be loaded via CDN in the HTML)
   if (typeof Chart === 'undefined') {
     console.warn('Chart.js not available, skipping chart initialization');
     return;
   }
   
   const ctx = document.getElementById('progressChart');
   if (!ctx) return;
   
   // Prepare data for chart
   const labels = trendsData.map(trend => {
     const date = new Date(trend.submitted_at);
     return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
   });
   
   const totalScores = trendsData.map(trend => trend.total_score);
   
   // Category scores
   const categoryScores = {
     listening: [],
     reading: [],
     writing: [],
     speaking: []
   };
   
   trendsData.forEach(trend => {
     Object.keys(categoryScores).forEach(category => {
       categoryScores[category].push(trend.categories[category]?.score || 0);
     });
   });
   
   // Destroy existing chart if present
   if (ctx.chart) {
     ctx.chart.destroy();
   }
   
   // Create new chart
   ctx.chart = new Chart(ctx, {
     type: 'line',
     data: {
       labels: labels,
       datasets: [
         {
           label: 'Total Score',
           data: totalScores,
           borderColor: '#146b63',
           backgroundColor: 'rgba(20, 107, 99, 0.1)',
           tension: 0.1,
           fill: true,
           yAxisID: 'y-total'
         },
         {
           label: 'Listening',
           data: categoryScores.listening,
           borderColor: '#ff6b6b',
           backgroundColor: 'rgba(255, 107, 107, 0.1)',
           tension: 0.1,
           hidden: true
         },
         {
           label: 'Reading',
           data: categoryScores.reading,
           borderColor: '#4ecdc4',
           backgroundColor: 'rgba(78, 205, 196, 0.1)',
           tension: 0.1,
           hidden: true
         },
         {
           label: 'Writing',
           data: categoryScores.writing,
           borderColor: '#45b7d1',
           backgroundColor: 'rgba(69, 183, 209, 0.1)',
           tension: 0.1,
           hidden: true
         },
         {
           label: 'Speaking',
           data: categoryScores.speaking,
           borderColor: '#96ceb4',
           backgroundColor: 'rgba(150, 206, 180, 0.1)',
           tension: 0.1,
           hidden: true
         }
       ]
     },
     options: {
       responsive: true,
       maintainAspectRatio: false,
       interaction: {
         mode: 'index',
         intersect: false,
       },
       scales: {
         y: {
           type: 'linear',
           display: true,
           position: 'left',
           id: 'y-total',
           min: 0,
           max: 60,
           ticks: {
             stepSize: 10,
             callback: function(value) {
               return value + ' pts';
             }
           }
         },
         y1: {
           type: 'linear',
           display: false,
           position: 'right',
           id: 'y-category',
           min: 0,
           max: 15,
           ticks: {
             stepSize: 3,
             callback: function(value) {
               return value + ' pts';
             }
           }
         },
         x: {
           display: true,
           ticks: {
             maxRotation: 45,
             minRotation: 45
           }
         }
       },
       plugins: {
         title: {
           display: false
         },
         legend: {
           position: 'top',
         },
         tooltip: {
           mode: 'index',
           intersect: false,
         }
       }
     }
   });
 }

function formatTaskProgress(progress) {
  return `${progress.answered}/${progress.total} responses`;
}

function renderPartTimer(part, label, minutes) {
  const timer = state.runner.timers[part];
  const isExamMode = state.flow.mode === "exam";
  const startLabel = timer.running ? "Running" : (timer.remaining < timer.total ? "Resume" : "Start");
  return `
    <article class="timer-card ${state.runner.activePart === part ? "active" : ""}">
      <div>
        <h3>${label}</h3>
        <p>${minutes} min</p>
      </div>
      <div class="timer-display" data-timer="${part}">${formatTime(timer.remaining)}</div>
      <div class="timer-actions">
        <button type="button" class="btn btn-primary btn-sm" data-action="start" data-part="${part}" ${timer.running ? "disabled" : ""}>${startLabel}</button>
        ${isExamMode ? "" : `<button type="button" class="btn btn-outline-primary btn-sm" data-action="pause" data-part="${part}">Pause</button>`}
        ${isExamMode ? "" : `<button type="button" class="btn btn-outline-primary btn-sm" data-action="reset" data-part="${part}">Reset</button>`}
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
          <label class="official-radio-row form-check">
            <input class="form-check-input" type="radio" name="${name}" value="${escapeHtml(option.value)}" ${value === option.value ? "checked" : ""}>
            <span class="form-check-label">${escapeHtml(option.label)}</span>
          </label>
        `).join("")}
      </div>
    </article>
  `;
}

function renderCardAudio(audioSrc, index) {
  const trackKey = `listening.${index}`;
  const playCount = state.listenPlayCount[trackKey] || 0;
  return `
    <div class="stitch-audio-card">
      <audio controls preload="none" src="${escapeHtml(toAssetUrl(audioSrc))}" aria-label="Audio ${index + 1}" data-listen-track="${escapeHtml(trackKey)}"></audio>
      <span class="play-count" data-play-count="${escapeHtml(trackKey)}">${playCount > 0 ? playCount + "× played" : "Not yet played"}</span>
    </div>
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
  return `
    <aside class="ad-reference-panel" aria-label="Sludinājumi">
      <section class="ad-choice-group">
        <h5>A–L</h5>
        <div class="ad-card-grid">
          ${ads.map(ad => `
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
        ${adGroups.map((group, groupIndex) => renderAdMatchGroup(
          section,
          task,
          group,
          questionGroups[groupIndex] || [],
          groupIndex * questionsPerGroup
        )).join("")}
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
              <select class="form-select" data-answer="${name}">
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
  return `
    <section class="ad-match-group">
      ${renderAdChoiceGroup(ads)}
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
                <select class="form-select" data-answer="${name}">
                  <option value=""></option>
                  ${ads.map(ad => `<option value="${ad.letter}" ${value.toUpperCase() === ad.letter ? "selected" : ""}>${ad.letter}</option>`).join("")}
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
      <select class="form-select inline-gap-select" data-answer="${name}" aria-label="Atbilde ${number}">
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
                <textarea class="form-control" data-answer="${name}" rows="${task.rows || 3}" placeholder="${escapeHtml(task.placeholder || "Rakstiet teikumu")}">${escapeHtml(value)}</textarea>
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
  const input = `<input class="form-control inline-text-blank" type="text" data-answer="${name}" value="${escapeHtml(value)}" aria-label="Atbilde ${index + 1}">`;
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
        <textarea class="form-control" data-answer="${name}" rows="${task.rows || 10}" placeholder="${escapeHtml(task.placeholder || "Rakstiet tekstu")}">${escapeHtml(value)}</textarea>
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
            <textarea class="form-control" data-answer="${name}" rows="${task.rows || 2}" placeholder="${escapeHtml(task.placeholder || "Atbildiet")}">${escapeHtml(value)}</textarea>
          </label>
          ${renderRecordingControls(name)}
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
            <textarea class="form-control" data-answer="${name}" rows="${task.rows || 4}" placeholder="${escapeHtml(task.placeholder || "Aprakstiet attēlu")}">${escapeHtml(value)}</textarea>
          </label>
          ${renderRecordingControls(name)}
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
            <input class="form-control" type="text" data-answer="${name}" value="${escapeHtml(value)}" placeholder="${escapeHtml(task.placeholder || "Uzdodiet jautājumu")}">
          </label>
          ${renderRecordingControls(name)}
        `;
      }).join("")}
    </div>
  `;
}

function renderRecordingControls(key) {
  const isRecording = state.speaking.recordingKey === key;
  const audioUrl = state.speaking.audioUrls[key];
  const uploadId = state.speaking.uploadIds[key];
  const statusText = isRecording
    ? "Recording..."
    : uploadId
      ? "Uploaded ✓"
      : audioUrl
        ? "Recorded (not uploaded)"
        : "";
  return `
    <div class="speaking-recorder" data-recorder-key="${escapeHtml(key)}">
      <div class="recorder-controls">
        ${isRecording
          ? `<button type="button" class="btn btn-danger btn-sm recorder-stop" data-action="stop-recording" data-key="${escapeHtml(key)}" aria-label="Stop recording">Stop</button>`
          : `<button type="button" class="btn btn-primary btn-sm recorder-start" data-action="start-recording" data-key="${escapeHtml(key)}" aria-label="Start recording">Record</button>`
        }
        ${audioUrl ? `
          <audio controls class="recorder-playback" src="${escapeHtml(audioUrl)}" aria-label="Playback recording for ${escapeHtml(key)}"></audio>
          <button type="button" class="btn btn-outline-primary btn-sm recorder-upload" data-action="upload-recording" data-key="${escapeHtml(key)}" ${uploadId ? "disabled" : ""} aria-label="Upload recording">
            ${uploadId ? "Uploaded" : "Upload"}
          </button>
        ` : ""}
      </div>
      ${statusText ? `<span class="recorder-status">${escapeHtml(statusText)}</span>` : ""}
      ${renderSpeechTranscript(key)}
      <span class="recorder-mic-error" data-mic-error="${escapeHtml(key)}" hidden></span>
    </div>
  `;
}

function renderSpeechTranscript(key) {
  const finalText = state.speaking.transcripts[key] || "";
  const interimText = state.speaking.transcriptInterims[key] || "";
  const errorText = state.speaking.transcriptErrors[key] || "";
  const unsupported = !getSpeechRecognitionConstructor();
  const bodyText = finalText || interimText || (unsupported
    ? "Live speech text is not available in this browser."
    : "Start recording to see your Latvian speech as text.");
  return `
    <div class="recorder-transcript ${finalText || interimText ? "" : "empty"}" data-transcript-key="${escapeHtml(key)}" aria-live="polite">
      <span class="recorder-transcript-label">Recognized Latvian text</span>
      <p data-transcript-text="${escapeHtml(key)}">${escapeHtml(bodyText)}</p>
      <span class="recorder-transcript-interim" data-transcript-interim="${escapeHtml(key)}">${finalText && interimText ? escapeHtml(interimText) : ""}</span>
      <span class="recorder-transcript-error" data-transcript-error="${escapeHtml(key)}" ${errorText ? "" : "hidden"}>${escapeHtml(errorText)}</span>
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
        <select class="form-select" data-answer="${name}">
          <option value="">Izvēlieties</option>
          ${task.options.map(option => `<option value="${option}" ${value === option ? "selected" : ""}>${option}</option>`).join("")}
        </select>
      </label>
    `;
  }
  const rows = task.rows || (task.kind === "textarea" ? 3 : 2);
  const tag = task.kind === "textarea" ? "textarea" : "input";
  const common = tag === "textarea"
    ? `<textarea class="form-control" data-answer="${name}" rows="${rows}" placeholder="${escapeHtml(task.placeholder || "Ierakstiet atbildi")}">${escapeHtml(value)}</textarea>`
    : `<input class="form-control" type="text" data-answer="${name}" value="${escapeHtml(value)}" placeholder="${escapeHtml(task.placeholder || "Ierakstiet atbildi")}">`;
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
      <input class="form-check-input" type="radio" name="${name}" value="${value}" ${checked ? "checked" : ""}>
      <span>${value}</span>
    </label>
  `;
}

function bindRunnerEvents() {
  document.querySelectorAll("[data-action]").forEach(button => {
    button.addEventListener("click", () => {
      Promise.resolve(handleRunnerAction(button.dataset)).catch(error => {
        console.error(error);
        showToast(error.message || "Action failed");
      });
    });
  });
  document.querySelectorAll("[data-billing-action]").forEach(button => {
    button.addEventListener("click", () => handleBillingAction(button.dataset.billingAction, button.dataset.product));
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
  // Track listening playback counts
  document.querySelectorAll("audio[data-listen-track]").forEach(audio => {
    audio.addEventListener("play", () => {
      const key = audio.dataset.listenTrack;
      state.listenPlayCount[key] = (state.listenPlayCount[key] || 0) + 1;
      const counter = document.querySelector(`[data-play-count="${CSS.escape(key)}"]`);
      if (counter) counter.textContent = state.listenPlayCount[key] + "× played";
    });
  });
}

function handleRunnerAction(dataset) {
  const { action, part, section, task } = dataset;
  if (action === "toggle-hint") {
    const hintDiv = document.getElementById(`hint-${section}-${task}`);
    if (hintDiv) {
      hintDiv.style.display = hintDiv.style.display === "none" ? "block" : "none";
      const button = document.querySelector(`[data-action="toggle-hint"][data-section="${section}"][data-task="${task}"]`);
      if (button) {
        button.textContent = hintDiv.style.display === "none" ? "Show Correct Answer" : "Hide Correct Answer";
      }
    }
    return;
  }
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
    submitAnswers().catch(error => {
      console.error(error);
      state.billing.error = error.message;
      renderBilling();
    });
    return;
  }
  if (action === "evaluate-exam") {
    evaluateSubmissionWithAi().catch(error => {
      console.error(error);
      state.billing.error = error.message;
      renderBilling();
    });
    return;
  }
  if (action === "show-results") {
    setFlowScreen("results");
    return;
  }
  if (action === "open-submission") {
    renderSubmission();
    setView("submission");
    return;
  }
  if (action === "end-exam") {
    return endCurrentExam();
  }
  if (action === "start-new-exam") {
    return startNewExam();
  }
  if (action === "start-recording") {
    startMicRecording(dataset.key);
    return;
  }
  if (action === "stop-recording") {
    stopMicRecording(dataset.key);
    return;
  }
  if (action === "upload-recording") {
    uploadSpeakingAudio(dataset.key).catch(error => showToast("Upload failed: " + error.message));
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
    startOnlyTimer(part);
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

async function expireCurrentAttempt() {
  if (state.auth.status !== "authenticated" || !state.attempt.id || state.attempt.id.startsWith("local_")) {
    return;
  }
  const response = await fetch(`/api/attempts/${encodeURIComponent(state.attempt.id)}/expire`, {
    method: "POST",
    credentials: "same-origin"
  });
  if (!response.ok && response.status !== 409) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.error?.message || payload.error || `End exam failed with HTTP ${response.status}`);
  }
}

function resetExamSession() {
  resetAnswers();
  resetTimers();
  resetAttemptState();
  clearLocalDraft();
  state.submission = null;
  state.evaluation = null;
  state.evaluating = false;
  state.runner.activePart = PART_CONFIG[0].key;
}

async function endCurrentExam() {
  if (!window.confirm("End this exam attempt? Your current answers will be cleared and this attempt will not be scored.")) return;
  try {
    await expireCurrentAttempt();
  } catch (error) {
    showToast(error.message || "Could not end the saved attempt");
    return;
  }
  resetExamSession();
  state.flow.screen = "home";
  setView("runner");
  updateExamUrl();
  renderRunner();
  showToast("Exam ended");
}

async function startNewExam() {
  if (state.attempt.id || getExamProgress().answered > 0) {
    if (!window.confirm("Start a new exam? Your current answers will be cleared and this attempt will not be scored.")) return;
    try {
      await expireCurrentAttempt();
    } catch (error) {
      showToast(error.message || "Could not end the saved attempt");
      return;
    }
  }
  resetExamSession();
  state.flow = flowCore.switchFlowMode(state.flow, "exam");
  state.flow.screen = "register";
  setView("runner");
  updateExamUrl();
  renderRunner();
  showToast("New exam ready");
}

function startOnlyTimer(part) {
  const now = Date.now();
  for (const key of Object.keys(state.runner.timers)) {
    if (key === part && state.runner.timers[key].remaining > 0) {
      state.runner.timers[key].running = true;
      state.runner.timers[key].startedAt = state.runner.timers[key].startedAt || now;
    } else {
      state.runner.timers[key].running = false;
    }
  }
}

function isAnyTimerRunning() {
  return Object.values(state.runner.timers).some(timer => timer.running);
}

function getSpeechRecognitionConstructor() {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function normalizeTranscriptText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function appendTranscriptText(current, next) {
  const cleanNext = normalizeTranscriptText(next);
  if (!cleanNext) return normalizeTranscriptText(current);
  return normalizeTranscriptText(`${current || ""} ${cleanNext}`);
}

function speechRecognitionErrorMessage(error) {
  if (error === "not-allowed" || error === "service-not-allowed") {
    return "Speech text permission was denied. Audio recording can still continue.";
  }
  if (error === "no-speech") {
    return "No speech was detected yet. Try speaking a little louder or closer to the microphone.";
  }
  if (error === "language-not-supported") {
    return "Latvian speech recognition is not supported by this browser.";
  }
  return "Speech text is temporarily unavailable. Audio recording can still continue.";
}

function setSpeakingTranscriptError(key, message) {
  state.speaking.transcriptErrors[key] = message;
  const errEl = document.querySelector(`[data-transcript-error="${CSS.escape(key)}"]`);
  if (errEl) {
    errEl.textContent = message;
    errEl.hidden = !message;
  }
}

function updateSpeakingTranscriptUi(key) {
  const finalText = state.speaking.transcripts[key] || "";
  const interimText = state.speaking.transcriptInterims[key] || "";
  const displayText = normalizeTranscriptText(`${finalText} ${interimText}`) || "Listening for Latvian speech...";
  const textEl = document.querySelector(`[data-transcript-text="${CSS.escape(key)}"]`);
  if (textEl) textEl.textContent = displayText;
  const interimEl = document.querySelector(`[data-transcript-interim="${CSS.escape(key)}"]`);
  if (interimEl) interimEl.textContent = finalText && interimText ? interimText : "";
  const box = document.querySelector(`[data-transcript-key="${CSS.escape(key)}"]`);
  if (box) box.classList.toggle("empty", !finalText && !interimText);
}

function syncSpeakingTranscriptAnswer(key) {
  const [section, task, indexValue] = key.split(".");
  const index = Number(indexValue);
  if (!section || !task || !Number.isInteger(index)) return;
  const text = normalizeTranscriptText(`${state.speaking.transcripts[key] || ""} ${state.speaking.transcriptInterims[key] || ""}`);
  ensureAnswerSlot(section, task, index);
  state.answers[section][task][index] = text;
  state.submission = null;
  state.evaluation = null;
  const field = document.querySelector(`[data-answer="${CSS.escape(key)}"]`);
  if (field && field.value !== text) field.value = text;
  renderProgressOnly();
  queueAttemptAnswerSave(section, task, index, text);
}

function startSpeechRecognition(key) {
  const Recognition = getSpeechRecognitionConstructor();
  if (!Recognition) {
    setSpeakingTranscriptError(key, "Live speech text is not available in this browser.");
    return null;
  }
  const recognition = new Recognition();
  recognition.lang = "lv-LV";
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.maxAlternatives = 1;
  recognition.onresult = event => {
    let finalText = state.speaking.transcripts[key] || "";
    let interimText = "";
    for (let index = event.resultIndex || 0; index < event.results.length; index += 1) {
      const result = event.results[index];
      const text = result[0]?.transcript || "";
      if (result.isFinal) {
        finalText = appendTranscriptText(finalText, text);
      } else {
        interimText = appendTranscriptText(interimText, text);
      }
    }
    state.speaking.transcripts[key] = finalText;
    state.speaking.transcriptInterims[key] = interimText;
    state.speaking.transcriptErrors[key] = "";
    updateSpeakingTranscriptUi(key);
    syncSpeakingTranscriptAnswer(key);
  };
  recognition.onerror = event => {
    setSpeakingTranscriptError(key, speechRecognitionErrorMessage(event.error));
  };
  recognition.onend = () => {
    if (state.speaking.recognition === recognition) {
      state.speaking.recognition = null;
    }
    state.speaking.transcriptInterims[key] = "";
    updateSpeakingTranscriptUi(key);
    syncSpeakingTranscriptAnswer(key);
  };
  try {
    recognition.start();
    state.speaking.recognition = recognition;
    return recognition;
  } catch (error) {
    setSpeakingTranscriptError(key, "Could not start live speech text: " + error.message);
    return null;
  }
}

function stopSpeechRecognition() {
  if (!state.speaking.recognition) return;
  const recognition = state.speaking.recognition;
  state.speaking.recognition = null;
  try {
    recognition.stop();
  } catch (error) {
    console.warn("Could not stop speech recognition", error);
  }
}

async function startMicRecording(key) {
  const errEl = document.querySelector(`[data-mic-error="${CSS.escape(key)}"]`);
  if (errEl) { errEl.textContent = ""; errEl.hidden = true; }
  try {
    if (state.speaking.recordingKey && state.speaking.recordingKey !== key) {
      stopMicRecording(state.speaking.recordingKey);
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm";
    const recorder = new MediaRecorder(stream, { mimeType });
    state.speaking.chunks[key] = [];
    state.speaking.transcripts[key] = "";
    state.speaking.transcriptInterims[key] = "";
    state.speaking.transcriptErrors[key] = "";
    recorder.addEventListener("dataavailable", event => {
      if (event.data.size > 0) state.speaking.chunks[key].push(event.data);
    });
    recorder.addEventListener("stop", () => {
      stream.getTracks().forEach(track => track.stop());
      const blob = new Blob(state.speaking.chunks[key], { type: mimeType });
      const url = URL.createObjectURL(blob);
      if (state.speaking.audioUrls[key]) URL.revokeObjectURL(state.speaking.audioUrls[key]);
      state.speaking.audioUrls[key] = url;
      state.speaking.recordingKey = null;
      state.speaking.uploadIds[key] = null;
      stopSpeechRecognition();
      renderRunner();
    });
    state.speaking.recorder = recorder;
    state.speaking.recordingKey = key;
    recorder.start(200);
    renderRunner();
    startSpeechRecognition(key);
  } catch (error) {
    const msg = error.name === "NotAllowedError"
      ? "Microphone access denied. Please allow microphone in browser settings."
      : "Could not start recording: " + error.message;
    if (errEl) { errEl.textContent = msg; errEl.hidden = false; }
    showToast(msg);
  }
}

function stopMicRecording(key) {
  if (state.speaking.recorder && state.speaking.recordingKey === key) {
    stopSpeechRecognition();
    state.speaking.recorder.stop();
    state.speaking.recorder = null;
  }
}

async function uploadSpeakingAudio(key) {
  const blob = new Blob(state.speaking.chunks[key] || [], { type: "audio/webm" });
  if (!blob.size) { showToast("No audio to upload."); return; }
  const submission = state.submission || {};
  const [section, task] = key.split(".");
  const params = new URLSearchParams({
    submission_id: submission.submission_id || "draft",
    task: task || key,
    exam_id: state.exam.id
  });
  const response = await fetch(`/api/uploads/speaking?${params.toString()}`, {
    method: "POST",
    headers: { "Content-Type": "audio/webm" },
    body: blob
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ error: "Upload failed" }));
    throw new Error(err.error || "Upload failed");
  }
  const result = await response.json();
  state.speaking.uploadIds[key] = result.upload_id;
  showToast("Audio uploaded successfully.");
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
    state.evaluation = null;
    renderProgressOnly();
    queueAttemptAnswerSave(section, task, Number(index), target.value, 0);
    return;
  }
  const [section, task, index] = key.split(".");
  ensureAnswerSlot(section, task, Number(index));
  state.answers[section][task][Number(index)] = target.value;
  state.submission = null;
  state.evaluation = null;
  renderProgressOnly();
  queueAttemptAnswerSave(section, task, Number(index), target.value);
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
  state.evaluation = null;
  refreshDragFillUi(section, task);
  renderProgressOnly();
  queueAttemptAnswerSave(section, task, targetIndex, value, 0);
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

async function submitAnswers(options = {}) {
  for (const timer of Object.values(state.runner.timers)) {
    timer.running = false;
  }
  if (state.auth.status !== "authenticated") {
    state.submission = buildSubmission("submitted");
    persistSubmission(state.submission);
    state.evaluation = null;
    renderRunner();
    renderSubmission();
    renderBilling();
    setFlowScreen("results");
    if (!options.autoSubmitted) {
      setView("submission");
    }
    showToast("Answers submitted locally");
    return;
  }
  const ready = await ensureServerAttempt();
  if (!ready) return;
  await Promise.all(Object.entries(state.attempt.pendingTimers || {}).map(async ([key, timerId]) => {
    clearTimeout(timerId);
    const [section, task, index] = key.split(".");
    const value = state.answers[section]?.[task]?.[Number(index)] || "";
    await saveAttemptAnswer(section, task, Number(index), value);
  }));
  state.attempt.pendingTimers = {};
  const response = await fetch(`/api/attempts/${encodeURIComponent(state.attempt.id)}/submit`, {
    method: "POST",
    credentials: "same-origin"
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error?.message || payload.error || `Submit failed with HTTP ${response.status}`);
  }
  applyServerAttempt(payload.attempt);
  state.submission = buildSubmission("submitted");
  if (payload.score) {
    state.submission.scoring = payload.score;
  }
  persistSubmission(state.submission);
  clearLocalDraft();
  state.evaluation = null;
  renderRunner();
  renderSubmission();
  renderBilling();
  setFlowScreen("results");
  if (!options.autoSubmitted) {
    setView("submission");
  }
  showToast("Answers submitted locally");
}

async function evaluateSubmissionWithAi() {
  if (state.evaluating) return;
  for (const timer of Object.values(state.runner.timers)) {
    timer.running = false;
  }
  if (!state.submission || state.submission.status !== "submitted") {
    await submitAnswers();
    if (!state.submission || state.submission.status !== "submitted") {
      return;
    }
  }
  state.submission = buildSubmission("submitted");
  state.evaluating = true;
  state.evaluation = null;
  persistSubmission(state.submission);
  renderRunner();
  renderSubmission();
  setView("submission");
  showToast("Sending answers for AI scoring...");

  const evaluatePayload = {
    submission: buildEvaluationSubmission(state.submission),
    exam_markdown: state.markdown,
    learner_id: state.billing.learnerId,
    email: state.billing.email
  };

  try {
    const response = await fetch("/api/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(evaluatePayload)
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(payload.error || payload.detail || `Evaluation failed with HTTP ${response.status}`);
      error.retry_state = payload.retry_state;
      error.provider_status = payload.provider_status;
      error.telemetry = payload.telemetry;
      throw error;
    }
    if (!payload || typeof payload !== "object" || !payload.evaluation || typeof payload.evaluation !== "object" || !payload.evaluation.scores) {
      throw new Error("AI scoring response was invalid.");
    }
    state.evaluation = payload;
    state.submission.ai_evaluation = payload;
    persistSubmission(state.submission);
    showToast("AI score complete");
  } catch (error) {
    state.evaluation = {
      error: error.message,
      hint: evaluationErrorHint(error.message),
      retry_state: error.retry_state,
      provider_status: error.provider_status,
      telemetry: error.telemetry
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
    learner_id: state.billing.learnerId,
    learner_email: state.billing.email || "",
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
    scoring,
    ai_evaluation: state.evaluation
  };
}

function buildEvaluationSubmission(submission) {
  return {
    submission_id: submission.submission_id,
    learner_id: submission.learner_id,
    learner_email: submission.learner_email,
    exam_id: submission.exam_id,
    exam_title: submission.exam_title,
    level: submission.level,
    language: submission.language,
    pass_rule: submission.pass_rule,
    progress: submission.progress,
    answers: submission.answers,
    scoring: {
      objective_correct: submission.scoring.objective_correct,
      objective_possible: submission.scoring.objective_possible,
      manual_review_possible: submission.scoring.manual_review_possible,
      by_skill: submission.scoring.by_skill,
      items: submission.scoring.items
    }
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
    const taskLine = /^(\d+)\.?\s*uzdevums:?\s*(.+)$/i.exec(line.trim().replaceAll("**", ""));
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
      remaining_display: formatTime(timer.remaining),
      started_at: timer.startedAt
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
  const visibleSubmission = flowCore.shouldShowDebugPanels(state.flow.debugMode)
    ? submission
    : flowCore.sanitizeSubmissionForLearner(submission);
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
      <button type="button" class="btn btn-primary" data-submission-action="submit">${submission.status === "submitted" ? "Resubmit answers" : "Submit answers"}</button>
      <button type="button" class="btn btn-outline-primary" data-submission-action="evaluate" ${state.evaluating || !canRunAiScoring() ? "disabled" : ""}>${state.evaluating ? "Scoring..." : canRunAiScoring() ? "AI score and corrections" : "Buy AI credits"}</button>
      <button type="button" class="btn btn-outline-primary" data-submission-action="copy">Copy JSON</button>
      <button type="button" class="btn btn-outline-primary" data-submission-action="download">Download JSON</button>
    </div>
    ${renderAiEvaluationPanel()}
    <pre class="code-panel submission-json">${escapeHtml(JSON.stringify(visibleSubmission, null, 2))}</pre>
  `;
  els.submissionOutput.querySelectorAll("[data-submission-action]").forEach(button => {
    button.addEventListener("click", () => handleSubmissionAction(button.dataset.submissionAction));
  });
  syncEvaluationButtons();
}

function renderBilling() {
  if (!els.billingOutput) return;
  const billing = getBillingSnapshot();
  const config = state.billing.config || { products: [] };
  const products = Array.isArray(config.products) ? config.products : [];
  els.billingOutput.innerHTML = `
    <section class="billing-hero">
      <div>
        <p class="eyebrow">Billing</p>
        <h2>Access, checkout, and entitlements</h2>
        <p>Stable learner ID: <code>${escapeHtml(state.billing.learnerId || "generating…")}</code></p>
      </div>
      <div class="billing-state-chip ${billing.frozen ? "bad" : ""}">${escapeHtml(billing.current_plan || "free")}</div>
    </section>
    <section class="billing-grid">
      <article class="billing-card">
        <h3>Current access</h3>
        <ul>
          <li>Free exam available: <strong>${billing.free_exam_available ? "yes" : "no"}</strong></li>
          <li>Paid attempts remaining: <strong>${escapeHtml(billing.paid_attempts_remaining ?? 0)}</strong></li>
          <li>AI credits remaining: <strong>${escapeHtml(billing.ai_credits_remaining ?? 0)}</strong></li>
          <li>Subscription active: <strong>${billing.subscription_active ? "yes" : "no"}</strong></li>
          <li>Frozen: <strong>${billing.frozen ? "yes" : "no"}</strong></li>
        </ul>
        <label class="billing-input">
          Email for checkout
          <input class="form-control" name="billing-email" value="${escapeHtml(state.billing.email || "")}" placeholder="learner@example.com" autocomplete="email">
        </label>
        <div class="billing-actions">
          <button type="button" class="btn btn-primary" data-billing-action="refresh-billing">Refresh from server</button>
          <button type="button" class="btn btn-outline-primary" data-billing-action="open-audit">View audit log</button>
        </div>
      </article>
      <article class="billing-card billing-products">
        <h3>Purchase options</h3>
        <div class="billing-product-list">
          ${products.map(product => `
            <section class="billing-product">
              <div>
                <strong>${escapeHtml(product.name)}</strong>
                <p>${product.mode === "subscription" ? "Monthly subscription" : "One-time purchase"}</p>
                <small>${escapeHtml(product.grants_attempts || 0)} exam attempts · ${escapeHtml(product.grants_ai_credits || 0)} AI credits</small>
              </div>
              <button type="button" class="btn btn-primary" data-billing-action="checkout" data-product="${escapeHtml(product.key)}">${product.price_id ? "Checkout" : "Configure Stripe"}</button>
            </section>
          `).join("")}
        </div>
      </article>
      <article class="billing-card billing-card-audit">
        <h3>Recent billing events</h3>
        ${billing.recent_events?.length ? `
          <ul class="billing-events">
            ${billing.recent_events.slice(0, 5).map(event => `
              <li>
                <strong>${escapeHtml(event.event_type)}</strong>
                <span>${escapeHtml(event.created_at)}</span>
              </li>
            `).join("")}
          </ul>
        ` : "<p>No billing events recorded yet.</p>"}
      </article>
    </section>
    ${state.billing.error ? `<p class="billing-error">${escapeHtml(state.billing.error)}</p>` : ""}
  `;
  els.billingOutput.querySelectorAll("[data-billing-action]").forEach(button => {
    button.addEventListener("click", () => handleBillingAction(button.dataset.billingAction, button.dataset.product));
  });
  const emailField = els.billingOutput.querySelector('input[name="billing-email"]');
  if (emailField) {
    emailField.addEventListener("change", () => {
      saveLearnerIdentity({ email: emailField.value.trim() });
      renderBilling();
    });
   }
}

function renderHelp() {
   if (!els.helpOutput) return;
   
   // Create a container for the manual
   const helpContainer = document.createElement('div');
   helpContainer.style.padding = '20px';
   helpContainer.style.maxHeight = '80vh';
   helpContainer.style.overflowY = 'auto';
   
   // Determine language: check URL param first, then stored language, then browser
   const urlParams = new URLSearchParams(window.location.search);
   const langParam = urlParams.get('lang');
   const browserLang = navigator.language || navigator.userLanguage || "";
   const preferredLang = langParam || state.helpLang || (browserLang.startsWith('lv') ? 'lv' : 'en');
   
   // Fetch and display the manual
   const manualFile = preferredLang === 'lv' ? 'USER_MANUAL.md' : 'USER_MANUAL_EN.md';
   fetch(manualFile)
      .then(response => {
         if (!response.ok) {
            throw new Error(`Failed to load manual: ${manualFile}`);
         }
         return response.text();
      })
      .then(markdownContent => {
         // Simple markdown to HTML conversion for basic formatting
         let htmlContent = markdownContent
            .replace(/^# (.+)$/gm, '<h1>$1</h1>')
            .replace(/^## (.+)$/gm, '<h2>$1</h2>')
            .replace(/^### (.+)$/gm, '<h3>$1</h3>')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/^\* (.+)$/gm, '<li>$1</li>')
            .replace(/^(.+)$/gm, '<p>$1</p>');
            
         // Fix list formatting
         htmlContent = htmlContent.replace(/(<li>.*<\/li>)/g, '<ul>$1</ul>');
         
         helpContainer.innerHTML = htmlContent;
      })
      .catch(error => {
         console.error('Failed to load manual:', error);
         helpContainer.innerHTML = `
            <div class="alert alert-danger">
               <h4>Error loading manual</h4>
               <p>Unable to load the user manual. Please try again later.</p>
            </div>
         `;
      });
      
   els.helpOutput.innerHTML = '';
   els.helpOutput.appendChild(helpContainer);
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
  if (!canRunAiScoring()) {
    return `
      <section class="ai-evaluation-panel warning">
        <h3>AI scoring needs credits</h3>
        <p>Buy AI scoring credits or start a monthly subscription to unlock automatic corrections.</p>
        ${renderUpgradePrompt("submission")}
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
        ${state.evaluation.provider_status ? `<p>Provider status: ${escapeHtml(state.evaluation.provider_status)}</p>` : ""}
        ${state.evaluation.retry_state ? `<p>Retry state: ${escapeHtml(state.evaluation.retry_state)}</p>` : ""}
        ${state.evaluation.telemetry?.prompt_version ? `<p>Prompt version: ${escapeHtml(state.evaluation.telemetry.prompt_version)}</p>` : ""}
        ${state.evaluation.telemetry?.rubric_version ? `<p>Rubric version: ${escapeHtml(state.evaluation.telemetry.rubric_version)}</p>` : ""}
        ${state.evaluation.telemetry?.input_hash ? `<p>Input hash: ${escapeHtml(state.evaluation.telemetry.input_hash.slice(0, 8))}</p>` : ""}
        ${state.evaluation.telemetry?.estimated_cost_cents != null ? `<p>Estimated cost: ${escapeHtml(state.evaluation.telemetry.estimated_cost_cents)} cents</p>` : ""}
        <p>${escapeHtml(state.evaluation.hint || "")}</p>
      </section>
    `;
  }

  const evaluation = state.evaluation.evaluation || {};
  const telemetry = state.evaluation.telemetry || evaluation.telemetry || {};
  const scores = evaluation.scores || {};
  const feedback = evaluation.feedback || {};
  const corrections = Array.isArray(evaluation.corrections) ? evaluation.corrections : [];
  const metaBits = [
    state.evaluation.provider_status || "ok",
    state.evaluation.prompt_version ? `Prompt ${state.evaluation.prompt_version}` : null,
    state.evaluation.rubric_version ? `Rubric ${state.evaluation.rubric_version}` : null,
    state.evaluation.input_hash ? `Hash ${state.evaluation.input_hash.slice(0, 8)}` : null,
    telemetry.retry_limit != null ? `Retries ${Array.isArray(telemetry.attempts) ? telemetry.attempts.length : 0}/${telemetry.retry_limit}` : null,
    telemetry.estimated_cost_cents != null ? `Est. cost ${telemetry.estimated_cost_cents} cents` : null
  ].filter(Boolean).join(" · ");
  return `
    <section class="ai-evaluation-panel">
      <div class="ai-evaluation-head">
        <div>
          <p class="eyebrow">${escapeHtml(state.evaluation.provider || "LLM")} ${escapeHtml(state.evaluation.model || "")}</p>
          <h3>AI score: ${escapeHtml(scores.total ?? "—")}/60</h3>
          <p>${scores.passed ? "Pass rule met" : "Pass rule not met yet"} · minimum is 9/15 in every skill.</p>
          ${metaBits ? `<p class="ai-meta">${escapeHtml(metaBits)}</p>` : ""}
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
    submitAnswers().catch(error => {
      console.error(error);
      state.billing.error = error.message;
      renderBilling();
    });
    return;
  }
  if (action === "evaluate") {
    evaluateSubmissionWithAi().catch(error => {
      console.error(error);
      state.billing.error = error.message;
      renderBilling();
    });
    return;
  }
  const submission = ensureSubmission("draft");
  if (action === "copy") {
    const visibleSubmission = flowCore.shouldShowDebugPanels(state.flow.debugMode)
      ? submission
      : flowCore.sanitizeSubmissionForLearner(submission);
    copyText(JSON.stringify(visibleSubmission, null, 2), "Submission copied");
    return;
  }
  if (action === "download") {
    const visibleSubmission = flowCore.shouldShowDebugPanels(state.flow.debugMode)
      ? submission
      : flowCore.sanitizeSubmissionForLearner(submission);
    downloadFile(`${submission.submission_id}.json`, JSON.stringify(visibleSubmission, null, 2), "application/json");
  }
}

async function handleBillingAction(action, productKey) {
  if (action === "refresh-billing") {
    await loadBillingContext();
    return;
  }
  if (action === "open-billing" || action === "open-audit") {
    setView("billing");
    await loadBillingContext();
    return;
  }
  if (action === "checkout" && productKey) {
    await startCheckout(productKey);
  }
}

async function startCheckout(productKey) {
  const config = state.billing.config || { products: [] };
  const product = (config.products || []).find(item => item.key === productKey);
  if (!product) {
    showToast("Billing config is not loaded yet.");
    return;
  }
  if (!product.price_id) {
    showToast("Stripe price ID missing for this product.");
    return;
  }
  const email = state.billing.email || "";
  const payload = {
    learner_id: state.billing.learnerId,
    email,
    product_key: productKey,
    success_url: `${window.location.origin}${window.location.pathname}?view=billing&checkout=success`,
    cancel_url: `${window.location.origin}${window.location.pathname}?view=billing&checkout=cancel`
  };
  try {
    const response = await fetch("/api/billing/checkout-session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(result.error || `Checkout failed with HTTP ${response.status}`);
    }
    state.billing.lastCheckout = result;
    renderBilling();
    if (result.checkout_url) {
      window.location.assign(result.checkout_url);
      return;
    }
    showToast("Checkout session created.");
  } catch (error) {
    state.billing.error = error.message;
    renderBilling();
    showToast("Could not start checkout");
  }
}

function syncEvaluationButtons() {
  const sidebarButton = document.querySelector("#evaluate-submission");
  if (!sidebarButton) return;
  sidebarButton.disabled = state.evaluating || !canRunAiScoring();
  sidebarButton.textContent = state.evaluating ? "Scoring..." : canRunAiScoring() ? "AI Score" : "AI credits needed";
}

function cloneJson(value) {
  return JSON.parse(JSON.stringify(value));
}

function buildExportJson() {
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
    latest_submission: state.submission,
    latest_ai_evaluation: state.evaluation,
    billing: {
      learner_id: state.billing.learnerId,
      email: state.billing.email,
      config: state.billing.config,
      state: state.billing.state
    },
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

function initializeMegaDropdown() {
  if (!els.megaTrigger || !els.megaPanel) return;

  els.megaTrigger.addEventListener("click", () => {
    if (els.megaPanel.hidden) {
      openMegaDropdown();
    } else {
      closeMegaDropdown({ restoreFocus: true });
    }
  });

  els.megaTrigger.addEventListener("keydown", event => {
    if (event.key !== "ArrowDown") return;
    event.preventDefault();
    openMegaDropdown({ focusFirst: true });
  });

  els.megaPanel.querySelectorAll("[data-mega-panel]").forEach(button => {
    button.addEventListener("mouseenter", () => activateMegaPanel(button.dataset.megaPanel));
    button.addEventListener("focus", () => activateMegaPanel(button.dataset.megaPanel));
    button.addEventListener("click", () => activateMegaPanel(button.dataset.megaPanel));
  });

  els.megaPanel.addEventListener("click", event => {
    const button = event.target.closest("[data-mega-destination]");
    if (!button) return;
    closeMegaDropdown();
    navigateFromMegaDropdown(button.dataset.megaDestination);
  });

  els.megaPanel.addEventListener("keydown", event => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeMegaDropdown({ restoreFocus: true });
      return;
    }
    if (!["ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight"].includes(event.key)) return;
    const focusable = getMegaFocusableItems();
    const currentIndex = focusable.indexOf(document.activeElement);
    if (currentIndex === -1) return;
    event.preventDefault();
    const delta = ["ArrowDown", "ArrowRight"].includes(event.key) ? 1 : -1;
    focusable[(currentIndex + delta + focusable.length) % focusable.length].focus();
  });

  document.addEventListener("click", event => {
    if (els.megaPanel.hidden || event.target.closest(".mega-nav")) return;
    closeMegaDropdown();
  });

  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && !els.megaPanel.hidden) {
      closeMegaDropdown({ restoreFocus: true });
    }
  });
}

function getMegaFocusableItems() {
  if (!els.megaPanel) return [];
  return Array.from(els.megaPanel.querySelectorAll("button:not([hidden]):not([disabled])"))
    .filter(item => item.offsetParent !== null);
}

function openMegaDropdown(options = {}) {
  if (!els.megaTrigger || !els.megaPanel) return;
  els.megaPanel.hidden = false;
  els.megaTrigger.setAttribute("aria-expanded", "true");
  updateMegaDropdownVisibility();
  if (options.focusFirst) {
    requestAnimationFrame(() => getMegaFocusableItems()[0]?.focus());
  }
}

function closeMegaDropdown(options = {}) {
  if (!els.megaTrigger || !els.megaPanel) return;
  els.megaPanel.hidden = true;
  els.megaTrigger.setAttribute("aria-expanded", "false");
  if (options.restoreFocus) {
    els.megaTrigger.focus();
  }
}

function activateMegaPanel(panelName) {
  if (!els.megaPanel || !panelName) return;
  els.megaPanel.querySelectorAll("[data-mega-panel]").forEach(button => {
    const active = button.dataset.megaPanel === panelName;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  });
  els.megaPanel.querySelectorAll(".mega-panel").forEach(panel => {
    const active = panel.id === `mega-panel-${panelName}`;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
  });
}

function navigateFromMegaDropdown(destination) {
  if (!destination) return;
  if (destination === "start-exam") {
    startExamFromMenu();
    return;
  }
  if (destination === "toggle-auth") {
    if (state.auth.status === "authenticated") {
      logout();
    } else {
      setView("auth");
    }
    return;
  }
  if (destination === "contact") {
    showToast("Sazinieties ar atbalstu: support@codex.lv");
    return;
  }
  if (destination.startsWith("part:")) {
    const part = destination.split(":", 2)[1];
    state.flow.screen = "exam";
    setView("runner");
    switchPart(part);
    return;
  }
  if (destination.startsWith("billing:")) {
    const sub = destination.split(":", 2)[1];
    setView("billing");
    handleSubView("billing", sub);
    return;
  }
  if (destination.startsWith("admin:")) {
    const sub = destination.split(":", 2)[1];
    setView("admin");
    handleSubView("admin", sub);
    return;
  }
  setView(destination);
}

function updateMegaDropdownVisibility() {
  if (!els.megaPanel) return;
  const adminAllowed = isAdminAccount();
  els.megaPanel.querySelectorAll("[data-requires-admin]").forEach(element => {
    element.hidden = !adminAllowed;
  });
  els.megaPanel.querySelectorAll("#mega-panel-admin [data-mega-destination]").forEach(element => {
    element.hidden = !adminAllowed;
  });
  const authToggle = document.getElementById("mega-auth-toggle");
  if (authToggle) {
    authToggle.textContent = state.auth.status === "authenticated" ? "Sign Out" : "Sign In";
  }
  const activeTab = els.megaPanel.querySelector("[data-mega-panel].active");
  if (activeTab?.hidden) {
    activateMegaPanel("exams");
  }
}

function setView(viewName) {
  if (DEBUG_VIEWS.has(viewName) && !flowCore.shouldShowDebugPanels(state.flow.debugMode)) {
    viewName = "runner";
  }
  if (PROTECTED_VIEWS.has(viewName) && state.auth.status !== "authenticated") {
    viewName = "runner";
  }
  if (viewName === "admin" && !isAdminAccount()) {
    viewName = state.auth.status === "authenticated" ? "dashboard" : "runner";
  }
  document.querySelectorAll(".view").forEach(view => view.classList.remove("active"));
  document.querySelector(`#${viewName}-view`).classList.add("active");
  document.querySelectorAll(".nav-list button").forEach(button => {
    const showButton = !DEBUG_VIEWS.has(button.dataset.view) || flowCore.shouldShowDebugPanels(state.flow.debugMode);
    const showAdmin = button.dataset.view !== "admin" || isAdminAccount();
    button.hidden = !showButton || !showAdmin;
    button.classList.toggle("active", button.dataset.view === viewName);
  });
   const titles = {
     auth: "Account access",
     dashboard: "Dashboard",
     admin: "Admin Console",
     runner: "Exam Runner",
     submission: "Submission",
     billing: "Billing",
     help: "User Manual",
     exam: state.exam.title,
     markdown: "Raw Markdown",
     json: "Structured JSON",
     tts: "TTS Audio",
     prompts: "Generated Images",
     quality: "Quality Gate"
   };
  els.workspaceTitle.textContent = titles[viewName];
  updateSidebarMenu(viewName);
  updateBreadcrumbs(viewName);
  updateQuickActions();
  updateMegaDropdownVisibility();
   if (viewName === "billing") renderBilling();
   if (viewName === "help") renderHelp();
}

function handleSubView(view, sub) {
  const billingSection = document.querySelector("#billing-output");
  if (!billingSection) return;

  if (sub === "status") {
    renderBilling();
  } else if (sub === "purchase") {
    renderBilling();
  } else if (sub === "history") {
    renderBilling();
  }
}

function startExamFromMenu() {
  const dashboard = state.auth.dashboard;
  const billingAttempts = (state.billing.state?.paid_attempts_remaining ?? 0) + (state.billing.state?.free_exam_available ? 1 : 0);
  const attemptsRemaining = dashboard?.summary?.attempts_remaining ?? (state.billing.state?.attempts_remaining ?? billingAttempts);
  if (attemptsRemaining <= 0) {
    setView("billing");
    handleSubView("billing", "purchase");
    showToast("Nav atlikušu mēģinājumu. Iegādājieties jaunu eksāmenu.");
    return;
  }
  if (state.auth.status !== "authenticated") {
    showToast("Piezīme: atbildes tiks saglabātas lokāli. Nepārlādējiet lapu pirms iesniegšanas.");
  }
  state.flow.screen = "register";
  setView("runner");
  renderRunner();
}

async function resumeExam() {
  const dashboard = state.auth.dashboard;
  const lastAttempt = dashboard?.attempts?.[0];
  if (lastAttempt && lastAttempt.status === "in_progress") {
    if (lastAttempt.id) {
      await loadServerAttempt(lastAttempt.id).catch(() => false);
    }
    state.flow.screen = "exam";
    setView("runner");
    renderRunner();
    return;
  }
  const localKey = `latvian_a2_exam_draft_${state.billing.learnerId || "guest"}_${state.exam.id}`;
  const localDraft = (() => {
    try {
      return JSON.parse(localStorage.getItem(localKey) || "null");
    } catch { return null; }
  })();
  if (localDraft && localDraft.attemptStatus !== "submitted" && localDraft.attemptStatus !== "scored") {
    if (restoreLocalDraft()) {
      state.flow.screen = "exam";
      setView("runner");
      renderRunner();
      showToast("Eksāmens atjaunots no vietējās saglabāšanas");
      return;
    }
  }
  showToast("Nav atjaunojamu eksāmenu");
}

function updateSidebarMenu(activeView) {
  document.querySelectorAll(".sidebar-item").forEach(item => {
    const view = item.dataset.view;
    const isActive = view === activeView || (view === "exam-list" && activeView === "runner");
    item.classList.toggle("active", isActive);
  });

  const adminSection = document.getElementById("admin-section");
  const debugSection = document.getElementById("debug-section");
  if (adminSection) {
    adminSection.classList.toggle("d-none", !isAdminAccount());
  }
  if (debugSection) {
    debugSection.style.display = flowCore.shouldShowDebugPanels(state.flow.debugMode) ? "block" : "none";
  }

  updateStatusBadge();
}

function updateStatusBadge() {
  const badge = document.getElementById("status-badge");
  if (!badge) return;

  const dashboard = state.auth.dashboard;
  const billingState = state.billing.state;
  const billingAttempts = (billingState?.paid_attempts_remaining ?? 0) + (billingState?.free_exam_available ? 1 : 0);
  const attempts = dashboard?.summary?.attempts_remaining ?? billingState?.attempts_remaining ?? billingAttempts;
  const credits = dashboard?.summary?.ai_credits_remaining ?? billingState?.ai_credits_remaining ?? 0;

  if (attempts > 0) {
    badge.className = "status-badge attempts";
    badge.textContent = `${attempts} left`;
  } else if (credits > 0) {
    badge.className = "status-badge credits";
    badge.textContent = `${credits} credits`;
  } else {
    badge.className = "status-badge none";
    badge.textContent = "No access";
  }
}

function updateBreadcrumbs(viewName) {
  const breadcrumbNav = document.getElementById("breadcrumb-nav");
  const breadcrumbList = document.getElementById("breadcrumb-list");
  if (!breadcrumbNav || !breadcrumbList) return;

  const crumbs = getBreadcrumbs(viewName);
  if (crumbs.length <= 1) {
    breadcrumbNav.classList.add("d-none");
    return;
  }

  breadcrumbNav.classList.remove("d-none");
  breadcrumbList.innerHTML = crumbs.map((c, i) => `
    <li class="breadcrumb-item ${i === crumbs.length - 1 ? 'active' : ''}">
      ${i === crumbs.length - 1 ? c.label : `<a href="#" data-bc-view="${c.view}">${c.label}</a>`}
    </li>
  `).join("");

  document.querySelectorAll(".breadcrumb-item a").forEach(link => {
    link.addEventListener("click", event => {
      event.preventDefault();
      const targetView = link.dataset.bcView;
      if (targetView) setView(targetView);
    });
  });
}

function getBreadcrumbs(viewName) {
  const crumbs = [{ view: "home", label: "Home" }];
  const sectionMap = {
    auth: "My Account",
    dashboard: "My Account",
    runner: "Exams",
    "exam-list": "Exams",
    results: "Results",
    billing: "Payments",
    admin: "Administrator"
  };
  if (sectionMap[viewName]) {
    crumbs.push({ view: viewName, label: sectionMap[viewName] });
  }
  const viewTitles = {
    auth: "Profile",
    dashboard: "My Progress",
    runner: "Start Exam",
    "exam-list": "Available Exams",
    results: "Results",
    billing: "My Status"
  };
  if (viewTitles[viewName]) {
    crumbs.push({ view: viewName, label: viewTitles[viewName] });
  }
  return crumbs;
}

function updateQuickActions() {
  const quickStart = document.getElementById("quick-start-exam");
  const quickResume = document.getElementById("quick-resume");
  const quickStatus = document.getElementById("quick-status");
  const quickBuy = document.getElementById("quick-buy");

  const dashboard = state.auth.dashboard;
  const billingState = state.billing.state;
  const billingAttempts = (billingState?.paid_attempts_remaining ?? 0) + (billingState?.free_exam_available ? 1 : 0);
  const attempts = dashboard?.summary?.attempts_remaining ?? billingState?.attempts_remaining ?? billingAttempts;
  const hasServerInProgress = dashboard?.attempts?.some(a => a.status === "in_progress");
  const hasLocalDraft = (() => {
    try {
      const key = `latvian_a2_exam_draft_${state.billing.learnerId || "guest"}_${state.exam.id}`;
      const draft = JSON.parse(localStorage.getItem(key) || "null");
      return draft && draft.attemptStatus !== "submitted" && draft.attemptStatus !== "scored";
    } catch { return false; }
  })();
  const hasInProgress = hasServerInProgress || hasLocalDraft;

  if (quickStart) {
    quickStart.disabled = false;
    quickStart.title = attempts <= 0 ? "Open exam start and access options" : "Start a new exam";
  }
  if (quickResume) {
    quickResume.classList.toggle("d-none", !hasInProgress);
    quickResume.title = hasLocalDraft ? "Resume interrupted exam from this browser" : "Resume exam from server";
  }
  if (quickBuy) {
    quickBuy.classList.toggle("d-none", attempts > 0 && (billingState?.ai_credits_remaining ?? 0) > 0);
  }
  if (quickStatus) {
    const attemptsText = attempts > 0 ? `${attempts} mēģ.` : "0 mēģ.";
    const creditsText = billingState?.ai_credits_remaining ?? 0;
    quickStatus.title = `Mēģinājumi: ${attemptsText} | AI kredīti: ${creditsText}`;
  }
}

function updateExamListInSidebar() {
  const container = document.getElementById("exam-list-container");
  if (!container) return;

  container.innerHTML = EXAMS.map(exam => `
    <button class="sidebar-item" data-action="load-exam" data-exam-id="${exam.id}">
      ${exam.title}
    </button>
  `).join("");

  container.querySelectorAll("[data-action='load-exam']").forEach(btn => {
    btn.addEventListener("click", () => {
      loadExam(btn.dataset.examId);
      setView("runner");
      updateBreadcrumbs("runner");
    });
  });
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

function showManual() {
   // Create a modal overlay
   const overlay = document.createElement('div');
   overlay.style.position = 'fixed';
   overlay.style.top = '0';
   overlay.style.left = '0';
   overlay.style.width = '100%';
   overlay.style.height = '100%';
   overlay.style.backgroundColor = 'rgba(0,0,0,0.8)';
   overlay.style.display = 'flex';
   overlay.style.alignItems = 'center';
   overlay.style.justifyContent = 'center';
   overlay.style.zIndex = '1000';
   
   // Create modal content
   const modal = document.createElement('div');
   modal.style.backgroundColor = 'white';
   modal.style.borderRadius = '8px';
   modal.style.maxWidth = '90%';
   modal.style.maxHeight = '90vh';
   modal.style.overflowY = 'auto';
   modal.style.padding = '20px';
   modal.style.boxShadow = '0 4px 6px rgba(0,0,0,0.1)';
   
   // Load the manual content
   fetch('USER_MANUAL.md')
      .then(response => response.text())
      .then(markdownContent => {
         // Simple markdown to HTML conversion for basic formatting
         let htmlContent = markdownContent
            .replace(/^# (.+)$/gm, '<h1>$1</h1>')
            .replace(/^## (.+)$/gm, '<h2>$1</h2>')
            .replace(/^### (.+)$/gm, '<h3>$1</h3>')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/^\* (.+)$/gm, '<li>$1</li>')
            .replace(/^(.+)$/gm, '<p>$1</p>');
            
         // Fix list formatting
         htmlContent = htmlContent.replace(/(<li>.*<\/li>)/g, '<ul>$1</ul>');
         
         modal.innerHTML = htmlContent;
         
         // Add close button
         const closeButton = document.createElement('button');
         closeButton.textContent = 'Aizvērt';
         closeButton.style.position = 'fixed';
         closeButton.style.top = '20px';
         closeButton.style.right = '20px';
         closeButton.style.padding = '8px 16px';
         closeButton.style.backgroundColor = '#dc3545';
         closeButton.style.color = 'white';
         closeButton.style.border = 'none';
         closeButton.style.borderRadius = '4px';
         closeButton.style.cursor = 'pointer';
         closeButton.style.zIndex = '1001';
         
         closeButton.addEventListener('click', () => {
            document.body.removeChild(overlay);
            document.body.removeChild(closeButton);
         });
         
         document.body.appendChild(overlay);
         document.body.appendChild(closeButton);
      })
      .catch(error => {
         console.error('Failed to load manual:', error);
         modal.textContent = 'Nevar ielādēt rokasgrāmatu. Lūdzu, mēģiniet vēlāk reiz.';
         
         // Add close button even on error
         const closeButton = document.createElement('button');
         closeButton.textContent = 'Aizvērt';
         closeButton.style.marginTop = '10px';
         closeButton.style.padding = '8px 16px';
         closeButton.style.backgroundColor = '#dc3545';
         closeButton.style.color = 'white';
         closeButton.style.border = 'none';
         closeButton.style.borderRadius = '4px';
         closeButton.style.cursor = 'pointer';
         
         modal.appendChild(closeButton);
         
         closeButton.addEventListener('click', () => {
            document.body.removeChild(overlay);
            document.body.removeChild(closeButton);
         });
         
         document.body.appendChild(overlay);
         document.body.appendChild(modal);
      });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setupTestHooks() {
  if (!window.__A2_TEST_HOOKS__) return;
  window.__a2TestHooks = {
    loadExam,
    renderAll,
    submitAnswers,
    evaluateSubmissionWithAi,
    setFlowScreen: (screen) => setFlowScreen(screen),
    setFlowMode: (mode) => {
      state.flow.mode = mode;
      renderRunner();
    },
    setActivePart: (partKey) => {
      state.runner.activePart = partKey;
      renderRunner();
    },
    setTimerRemaining: (partKey, remainingSeconds) => {
      const timer = state.runner.timers[partKey];
      if (!timer) return;
      timer.remaining = Math.max(0, Number(remainingSeconds) || 0);
      timer.running = timer.remaining > 0 && timer.running;
      renderTimersOnly();
    },
    startTimer: (partKey) => {
      startOnlyTimer(partKey);
      renderTimersOnly();
    },
    stopTimers: () => {
      for (const timer of Object.values(state.runner.timers)) {
        timer.running = false;
      }
      renderTimersOnly();
    },
    setAnswer: (partKey, taskKey, index, value) => {
      ensureAnswerSlot(partKey, taskKey, index);
      state.answers[partKey][taskKey][index] = value;
      queueAttemptAnswerSave(partKey, taskKey, index, value, 0);
      renderProgressOnly();
    },
    getState: () => cloneJson({
      exam: state.exam,
      flow: state.flow,
      runner: state.runner,
      answers: state.answers,
      submission: state.submission,
      evaluation: state.evaluation
    }),
    getSubmission: () => buildSubmission(state.submission?.status || "draft")
  };
}

setupTestHooks();
init();
