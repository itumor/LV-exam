const STORAGE_KEY = 'latvian_a2_exam_history';
const PASS_THRESHOLD = 9;
const TOTAL_POINTS = 15;

const MODE_DURATIONS = {
  full: 25 * 60,
  mini: 10 * 60
};

const examData = {
  announcements: [
    {
      id: 'ann-1',
      audio: '../data/A2_klausisanas/audio/lpp_32.mp3',
      transcript: 'Lūdzu, izslēdziet mobilos tālruņus. Vilciens Rīga-Jelgava atiet no 6. platformas pulksten 8:15.',
      question: 'Kurā platformā atiet vilciens?',
      options: ['5. platformā', '6. platformā', '7. platformā'],
      correct: 1
    },
    {
      id: 'ann-2',
      audio: '../data/A2_klausisanas/audio/lpp_33.mp3',
      transcript: 'Uzmanību! No rītdienas mainīsies bibliotēkas darba laiks. Tā būs atvērta no 9:00 līdz 19:00.',
      question: 'Kāds ir jaunais bibliotēkas darba laiks?',
      options: ['8:00 - 18:00', '9:00 - 19:00', '10:00 - 20:00'],
      correct: 1
    },
    {
      id: 'ann-3',
      audio: '../data/A2_klausisanas/audio/lpp_37.mp3',
      transcript: 'Nedēļas nogalē notiks lielveikala atlaidumi. Visām precēm būs 30% atlaide.',
      question: 'Cik liela atlaide būs nedēļas nogalē?',
      options: ['20%', '30%', '50%'],
      correct: 1
    },
    {
      id: 'ann-4',
      audio: '../data/A2_klausisanas/audio/lpp_45.mp3',
      transcript: 'Slimnīca aicina uz bezmaksas veselības pārbaudi. Reģistrācija pa tālruni 67000000.',
      question: 'Kā var reģistrēties uz pārbaudi?',
      options: ['Internetā', 'Pa tālruni', 'Klātienē'],
      correct: 1
    },
    {
      id: 'ann-5',
      audio: '../data/A2_klausisanas/audio/lpp_55.mp3',
      transcript: 'Autobuss nr.15 kursē ik pēc 15 minūtēm. Nākamais autobuss pienāks pulksten 10:45.',
      question: 'Cik bieži kursē autobuss nr.15?',
      options: ['Ik pēc 10 minūtēm', 'Ik pēc 15 minūtēm', 'Ik pēc 20 minūtēm'],
      correct: 1
    },
    {
      id: 'ann-6',
      audio: '../data/A2_klausisanas/audio/lpp_98.mp3',
      transcript: 'Mākslas muzejs šodien ir slēgts. Atkal būs atvērts rītdien no 10:00 līdz 18:00.',
      question: 'Kad muzejs būs atvērts?',
      options: ['Šodien', 'Rītdien', 'Pēc nedēļas'],
      correct: 1
    }
  ],
  dialogue: {
    id: 'dialog-1',
    audio: '../data/A2_klausisanas/audio/lpp_9_labdien-Labriit-Labvakar.mp3',
    transcript: 'A: Labdien! Vai šeit ir aptieka?\nB: Jā, blakus bankai.\nA: Paldies. Un kur ir parks?\nB: Parks ir aiz muzeja, pie ezera.\nA: Vai tuvumā ir restorāns?\nB: Jā, pretī baznīcai.\nA: Paldies daudz!',
    statements: [
      { text: 'Aptieka ir pie bankas', correct: true },
      { text: 'Parks ir pie slimnīcas', correct: false },
      { text: 'Restorāns ir pretī baznīcai', correct: true }
    ]
  },
  shortDialogues: [
    {
      id: 'short-1',
      audio: '../data/A2_klausisanas/audio/8_3.mp3',
      transcript: 'A: Kur tu strādā?\nB: Es strādā slimnīcā.\nA: Kāds amats?\nB: Esmu ārsts.',
      question: 'Kur strādā B?',
      options: ['Skolā', 'Slimnīcā', 'Veikalā'],
      correct: 1
    },
    {
      id: 'short-2',
      audio: '../data/A2_klausisanas/audio/8_7.mp3',
      transcript: 'A: Ko tu dari brīvajā laikā?\nB: Es lasu grāmatas un pastaigāju.\nA: Kur tu pastaigā?\nB: Parkā, pie ezera.',
      question: 'Ko B dara brīvajā laikā?',
      options: ['Sports', 'Lasīšana', 'Mūzika'],
      correct: 1
    },
    {
      id: 'short-3',
      audio: '../data/A2_klausisanas/audio/8_10.mp3',
      transcript: 'A: Kā tevi sauc?\nB: Mani sauc Anna.\nA: No kurienes tu esi?\nB: Es esmu no Latvijas, no Rīgas.',
      question: 'No kurienes ir Anna?',
      options: ['Lietuva', 'Igaunija', 'Latvija'],
      correct: 2
    },
    {
      id: 'short-4',
      audio: '../data/A2_klausisanas/audio/8_15.mp3',
      transcript: 'A: Ko tu šodien ēdīsi?\nB: Es ēdīšu zupu un maizi.\nA: Vai tev patīk zupa?\nB: Jā, ļoti patīk!',
      question: 'Ko B ēdīs šodien?',
      options: ['Salātus', 'Zupu un maizi', 'Gaļu'],
      correct: 1
    },
    {
      id: 'short-5',
      audio: '../data/A2_klausisanas/audio/8_17.mp3',
      transcript: 'A: Kāds šodien laiks?\nB: Šodien ir saulains un silts.\nA: Temperatūra?\nB: Apmēram 20 grādi.',
      question: 'Kāds ir laiks šodien?',
      options: ['Lietains', 'Saulains un silts', 'Auksts'],
      correct: 1
    }
  ]
};

let currentMode = null;
let currentTaskIndex = 0;
let answers = {};
let timerInterval = null;
let timeRemaining = 0;
let examAttempts = [];

function init() {
  loadHistory();
  setupEventListeners();
  updateStats();
}

function loadHistory() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      examAttempts = JSON.parse(stored);
    }
  } catch (e) {
    examAttempts = [];
  }
}

function saveHistory() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(examAttempts));
  } catch (e) {
    console.error('Failed to save history:', e);
  }
}

function updateStats() {
  document.getElementById('attempt-count').textContent = examAttempts.length;
  
  if (examAttempts.length > 0) {
    const best = Math.max(...examAttempts.map(a => a.score));
    document.getElementById('best-score').textContent = `${best}/15`;
  }
}

function setupEventListeners() {
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', () => switchView(btn.dataset.view));
  });

  document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => selectMode(btn.dataset.mode));
  });

  document.getElementById('start-exam-btn').addEventListener('click', startExam);
  document.getElementById('exit-confirm-btn').addEventListener('click', showExitModal);
  document.getElementById('next-task-btn').addEventListener('click', nextTask);
  document.getElementById('cancel-exit').addEventListener('click', hideExitModal);
  document.getElementById('confirm-exit').addEventListener('click', exitExam);
  document.getElementById('review-btn').addEventListener('click', showReview);
  document.getElementById('back-to-results').addEventListener('click', () => switchView('results'));
  document.getElementById('retry-btn').addEventListener('click', () => switchView('intro'));
}

function switchView(view) {
  document.querySelectorAll('.exam-view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  
  const viewEl = document.getElementById(`${view}-view`);
  const navEl = document.querySelector(`.nav-item[data-view="${view}"]`);
  
  if (viewEl) viewEl.classList.add('active');
  if (navEl) navEl.classList.add('active');
  
  if (view === 'history') {
    renderHistory();
  }
}

function selectMode(mode) {
  currentMode = mode;
  document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.classList.toggle('selected', btn.dataset.mode === mode);
  });
  document.getElementById('start-exam-btn').disabled = false;
}

function startExam() {
  if (!currentMode) return;
  
  currentTaskIndex = 0;
  answers = {};
  timeRemaining = MODE_DURATIONS[currentMode];
  
  startTimer();
  switchView('simulation');
  showCurrentTask();
}

function startTimer() {
  updateTimerDisplay();
  timerInterval = setInterval(() => {
    timeRemaining--;
    updateTimerDisplay();
    
    if (timeRemaining <= 0) {
      finishExam();
    }
  }, 1000);
}

function updateTimerDisplay() {
  const minutes = Math.floor(timeRemaining / 60);
  const seconds = timeRemaining % 60;
  const timerEl = document.getElementById('exam-timer');
  timerEl.textContent = `${minutes}:${seconds.toString().padStart(2, '0')}`;
  
  if (timeRemaining < 300) {
    timerEl.classList.add('warning');
  }
}

function stopTimer() {
  if (timerInterval) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
}

function showCurrentTask() {
  const mini = currentMode === 'mini';
  const tasks = getTasks(mini);
  const task = tasks[currentTaskIndex];
  
  const taskTypes = ['announcement', 'dialogue', 'shortdialogue'];
  const currentType = taskTypes[currentTaskIndex];
  
  document.querySelectorAll('.task-type').forEach(el => el.hidden = true);
  document.getElementById('question-progress').textContent = `Question ${currentTaskIndex + 1} of ${tasks.length}`;
  document.getElementById('task-progress').textContent = `Task ${currentTaskIndex + 1} of 3`;
  
  if (currentType === 'announcement') {
    showAnnouncementTask(task);
  } else if (currentType === 'dialogue') {
    showDialogueTask(task);
  } else if (currentType === 'shortdialogue') {
    showShortDialogueTask(task);
  }
  
  document.getElementById('next-task-btn').disabled = true;
}

function getTasks(mini) {
  const tasks = [];
  
  const annCount = mini ? 2 : examData.announcements.length;
  for (let i = 0; i < annCount; i++) {
    tasks.push({ type: 'announcement', index: i, data: examData.announcements[i] });
  }
  
  tasks.push({ type: 'dialogue', index: 0, data: examData.dialogue });
  
  const shortCount = mini ? 2 : examData.shortDialogues.length;
  for (let i = 0; i < shortCount; i++) {
    tasks.push({ type: 'shortdialogue', index: i, data: examData.shortDialogues[i] });
  }
  
  return tasks;
}

function showAnnouncementTask(task) {
  const container = document.getElementById('announcement-task');
  container.hidden = false;
  
  document.getElementById('ann-num').textContent = task.index + 1;
  const audio = document.getElementById('ann-audio');
  audio.src = task.data.audio;
  
  const optionsContainer = document.getElementById('ann-options');
  optionsContainer.innerHTML = '';
  
  task.data.options.forEach((opt, i) => {
    const btn = document.createElement('button');
    btn.className = 'option-btn';
    btn.innerHTML = `<span class="option-letter">${String.fromCharCode(65 + i)}</span> ${opt}`;
    btn.addEventListener('click', () => selectAnnouncementAnswer(task.data.id, i, btn));
    optionsContainer.appendChild(btn);
  });
}

function selectAnnouncementAnswer(questionId, answerIndex, btn) {
  answers[questionId] = answerIndex;
  
  document.querySelectorAll('#ann-options .option-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  
  document.getElementById('next-task-btn').disabled = false;
}

function showDialogueTask(task) {
  const container = document.getElementById('dialogue-task');
  container.hidden = true;
  document.getElementById('announcement-task').hidden = true;
  container.hidden = false;
  
  const audio = document.getElementById('dialogue-audio');
  audio.src = task.data.audio;
  
  const containerEl = document.getElementById('tf-statements');
  containerEl.innerHTML = '';
  
  task.data.statements.forEach((stmt, i) => {
    const item = document.createElement('div');
    item.className = 'tf-item';
    item.innerHTML = `
      <div class="tf-statement">${i + 1}. ${stmt.text}</div>
      <div class="tf-buttons">
        <button class="tf-btn yes" data-idx="${i}" data-value="yes">Jā</button>
        <button class="tf-btn no" data-idx="${i}" data-value="no">Nē</button>
      </div>
    `;
    containerEl.appendChild(item);
    
    item.querySelectorAll('.tf-btn').forEach(btn => {
      btn.addEventListener('click', () => selectDialogueAnswer(task.data.id, i, btn.value === 'yes', btn));
    });
  });
}

function selectDialogueAnswer(questionId, statementIndex, answerValue, btn) {
  const key = `${questionId}-${statementIndex}`;
  answers[key] = answerValue;
  
  const parent = btn.closest('.tf-item');
  parent.querySelectorAll('.tf-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  
  checkAllDialogueAnswered();
}

function checkAllDialogueAnswered() {
  const task = examData.dialogue;
  const totalStatements = task.statements.length;
  let answered = 0;
  
  for (let i = 0; i < totalStatements; i++) {
    if (answers[`${task.id}-${i}`] !== undefined) {
      answered++;
    }
  }
  
  document.getElementById('next-task-btn').disabled = answered < totalStatements;
}

function showShortDialogueTask(task) {
  document.querySelectorAll('.task-type').forEach(el => el.hidden = true);
  const container = document.getElementById('shortdialogue-task');
  container.hidden = false;
  
  document.getElementById('short-num').textContent = task.index + 1;
  const audio = document.getElementById('short-audio');
  audio.src = task.data.audio;
  
  const containerEl = document.getElementById('word-options');
  containerEl.innerHTML = '';
  
  task.data.options.forEach((opt, i) => {
    const btn = document.createElement('button');
    btn.className = 'word-btn';
    btn.textContent = opt;
    btn.addEventListener('click', () => selectWordAnswer(task.data.id, i, btn));
    containerEl.appendChild(btn);
  });
}

function selectWordAnswer(questionId, answerIndex, btn) {
  answers[questionId] = answerIndex;
  
  document.querySelectorAll('#word-options .word-btn').forEach(b => b.classList.remove('selected'));
  btn.classList.add('selected');
  
  document.getElementById('next-task-btn').disabled = false;
}

function nextTask() {
  const mini = currentMode === 'mini';
  const tasks = getTasks(mini);
  
  currentTaskIndex++;
  
  if (currentTaskIndex >= tasks.length) {
    finishExam();
  } else {
    showCurrentTask();
  }
}

function finishExam() {
  stopTimer();
  calculateAndShowResults();
}

function calculateAndShowResults() {
  const mini = currentMode === 'mini';
  const tasks = getTasks(mini);
  
  let totalScore = 0;
  let breakdown = { announcements: 0, dialogue: 0, shortDialogue: 0 };
  const skillScores = {
    'announcements': { correct: 0, total: 0 },
    'dialogues': { correct: 0, total: 0 },
    'numbers': { correct: 0, total: 0 },
    'places': { correct: 0, total: 0 },
    'everyday': { correct: 0, total: 0 }
  };
  
  tasks.forEach(task => {
    if (task.type === 'announcement') {
      const correct = task.data.correct;
      const userAnswer = answers[task.data.id];
      if (userAnswer === correct) {
        totalScore++;
        breakdown.announcements++;
        skillScores.announcements.correct++;
      }
      skillScores.announcements.total++;
    }
    else if (task.type === 'dialogue') {
      const statements = task.data.statements;
      statements.forEach((stmt, i) => {
        const key = `${task.data.id}-${i}`;
        const userAnswer = answers[key];
        if (userAnswer === stmt.correct) {
          totalScore++;
          breakdown.dialogue++;
          skillScores.numbers.correct++;
        }
        skillScores.numbers.total++;
      });
    }
    else if (task.type === 'shortdialogue') {
      const correct = task.data.correct;
      const userAnswer = answers[task.data.id];
      if (userAnswer === correct) {
        totalScore++;
        breakdown.shortDialogue++;
        skillScores.everyday.correct++;
      }
      skillScores.everyday.total++;
    }
  });
  
  const pass = totalScore >= PASS_THRESHOLD;
  const percent = Math.round((totalScore / TOTAL_POINTS) * 100);
  
  const attempt = {
    date: new Date().toISOString(),
    mode: currentMode,
    score: totalScore,
    pass: pass,
    breakdown: breakdown,
    answers: { ...answers },
    timeSpent: MODE_DURATIONS[currentMode] - timeRemaining,
    tasks: tasks.map(t => ({ type: t.type, data: t.data }))
  };
  
  examAttempts.push(attempt);
  saveHistory();
  updateStats();
  
  displayResults(attempt, skillScores);
}

function displayResults(attempt, skillScores) {
  const date = new Date(attempt.date);
  document.getElementById('result-date').textContent = date.toLocaleDateString('lv-LV');
  
  document.getElementById('score-value').textContent = attempt.score;
  
  const badge = document.getElementById('pass-fail-badge');
  if (attempt.pass) {
    badge.textContent = 'Iestājies!';
    badge.className = 'pass-fail pass';
  } else {
    badge.textContent = 'Neiestājies';
    badge.className = 'pass-fail fail';
  }
  
  const percent = Math.round((attempt.score / TOTAL_POINTS) * 100);
  document.getElementById('readiness-text').textContent = 
    `Tu esi pašreiz ${percent}% gatavs A2 klausīšanās eksāmenam.`;
  
  const breakdownGrid = document.getElementById('breakdown-grid');
  const maxAnn = currentMode === 'mini' ? 2 : 6;
  const maxShort = currentMode === 'mini' ? 2 : 5;
  
  breakdownGrid.innerHTML = `
    <div class="breakdown-item">
      <div class="breakdown-label">Paziņojumi</div>
      <div class="breakdown-score">${attempt.breakdown.announcements}/${maxAnn}</div>
    </div>
    <div class="breakdown-item">
      <div class="breakdown-label">Dialogs</div>
      <div class="breakdown-score">${attempt.breakdown.dialogue}/3</div>
    </div>
    <div class="breakdown-item">
      <div class="breakdown-label">Īsi Dialogi</div>
      <div class="breakdown-score">${attempt.breakdown.shortDialogue}/${maxShort}</div>
    </div>
  `;
  
  const skillBars = document.getElementById('skill-bars');
  const skillLabels = {
    'announcements': 'Paziņojumi',
    'dialogues': 'Dialogi',
    'numbers': 'Skaitļi/Dati',
    'places': 'Vietas',
    'everyday': 'Ikdienas pakalpojumi'
  };
  
  skillBars.innerHTML = '';
  Object.keys(skillScores).forEach(skill => {
    const data = skillScores[skill];
    const percent = data.total > 0 ? Math.round((data.correct / data.total) * 100) : 0;
    const levelClass = percent >= 70 ? '' : percent >= 40 ? 'medium' : 'low';
    
    skillBars.innerHTML += `
      <div class="skill-item">
        <span class="skill-label">${skillLabels[skill] || skill}</span>
        <div class="skill-bar">
          <div class="skill-fill ${levelClass}" style="width: ${percent}%"></div>
        </div>
        <span>${percent}%</span>
      </div>
    `;
  });
  
  switchView('results');
}

function showReview() {
  switchView('review');
  
  const mini = currentMode === 'mini';
  const tasks = getTasks(mini);
  const container = document.getElementById('review-container');
  container.innerHTML = '';
  
  tasks.forEach((task, idx) => {
    const item = document.createElement('div');
    item.className = 'review-item';
    
    let question = '';
    let userAnswer = '';
    let correctAnswer = '';
    let isCorrect = false;
    
    if (task.type === 'announcement') {
      question = task.data.question;
      const userIdx = answers[task.data.id];
      const correctIdx = task.data.correct;
      
      userAnswer = userIdx !== undefined ? task.data.options[userIdx] : 'Nav atbildēts';
      correctAnswer = task.data.options[correctIdx];
      isCorrect = userIdx === correctIdx;
      
      item.innerHTML = `
        <div class="review-question">${idx + 1}. ${question}</div>
        <div class="review-answer ${isCorrect ? 'correct' : 'incorrect'}">Tava atbilde: ${userAnswer}</div>
        ${!isCorrect ? `<div class="review-correct">Pareiza atbilde: ${correctAnswer}</div>` : ''}
        <div class="review-audio"><audio controls src="${task.data.audio}"></audio></div>
        <div class="review-correct">Transkripcija: ${task.data.transcript}</div>
      `;
    }
    else if (task.type === 'dialogue') {
      question = 'Jā/Nē jautājumi';
      const statements = task.data.statements;
      
      let answersHtml = '';
      statements.forEach((stmt, i) => {
        const key = `${task.data.id}-${i}`;
        const userAns = answers[key];
        const correct = stmt.correct;
        const isCorrect = userAns === correct;
        
        answersHtml += `<div class="review-answer ${isCorrect ? 'correct' : 'incorrect'}">
          ${i + 1}. ${stmt.text} - Tavs: ${userAns ? 'Jā' : 'Nē'}, Pareizi: ${correct ? 'Jā' : 'Nē'}
        </div>`;
      });
      
      item.innerHTML = `
        <div class="review-question">${idx + 1}. ${question}</div>
        ${answersHtml}
        <div class="review-audio"><audio controls src="${task.data.audio}"></audio></div>
        <div class="review-correct">Transkripcija: ${task.data.transcript}</div>
      `;
    }
    else if (task.type === 'shortdialogue') {
      question = task.data.question;
      const userIdx = answers[task.data.id];
      const correctIdx = task.data.correct;
      
      userAnswer = userIdx !== undefined ? task.data.options[userIdx] : 'Nav atbildēts';
      correctAnswer = task.data.options[correctIdx];
      isCorrect = userIdx === correctIdx;
      
      item.innerHTML = `
        <div class="review-question">${idx + 1}. ${question}</div>
        <div class="review-answer ${isCorrect ? 'correct' : 'incorrect'}">Tava atbilde: ${userAnswer}</div>
        ${!isCorrect ? `<div class="review-correct">Pareiza atbilde: ${correctAnswer}</div>` : ''}
        <div class="review-audio"><audio controls src="${task.data.audio}"></audio></div>
        <div class="review-correct">Transkripcija: ${task.data.transcript}</div>
      `;
    }
    
    container.appendChild(item);
  });
}

function renderHistory() {
  const container = document.getElementById('history-list');
  
  if (examAttempts.length === 0) {
    container.innerHTML = '<p class="empty-state">Nav veiktu mēģinājumu</p>';
    return;
  }
  
  container.innerHTML = '';
  
  examAttempts.slice().reverse().forEach((attempt, idx) => {
    const date = new Date(attempt.date);
    const item = document.createElement('div');
    item.className = 'history-item';
    item.innerHTML = `
      <div>
        <div class="history-date">${date.toLocaleDateString('lv-LV')} ${date.toLocaleTimeString('lv-LV', { hour: '2-digit', minute: '2-digit' })}</div>
        <div>${attempt.mode === 'full' ? 'Pilna simulācija' : 'Mini simulācija'}</div>
      </div>
      <div class="history-score ${attempt.pass ? 'pass' : 'fail'}">${attempt.score}/15</div>
    `;
    container.appendChild(item);
  });
}

function showExitModal() {
  document.getElementById('exit-modal').hidden = false;
}

function hideExitModal() {
  document.getElementById('exit-modal').hidden = true;
}

function exitExam() {
  hideExitModal();
  stopTimer();
  switchView('intro');
}

document.addEventListener('DOMContentLoaded', init);