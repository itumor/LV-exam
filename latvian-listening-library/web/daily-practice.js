const STORAGE_KEY = 'lv_daily_practice';
const XP_COMPLETION = 10;
const XP_PERFECT_BONUS = 5;

const BADGES = {
  first_challenge: { id: 'first_challenge', name: 'First Challenge', emoji: '🌟' },
  streak_3: { id: 'streak_3', name: '3-Day Streak', emoji: '🔥' },
  streak_7: { id: 'streak_7', name: '7-Day Streak', emoji: '⚡' },
  listening_master: { id: 'listening_master', name: 'Listening Master', emoji: '🎧' },
  a2_checkpoint: { id: 'a2_checkpoint', name: 'A2 Checkpoint', emoji: '✅' },
};

const SEED_CHALLENGES = [
  {
    id: 'seed_1',
    title: 'Kā tevi sauc?',
    audio_url: 'data/A1_klausisanas/audio/1_2.mp3',
    lv_text: 'Labrīt! Mani sauc Jānis. Kā tevi sauc? Mani sauc Anna.',
    en_text: 'Good morning! My name is Jānis. What is your name? My name is Anna.',
    level: 'A1',
    questions: [
      {
        type: 'multiple_choice',
        question: 'Kurš runā pirmais?',
        options: ['Jānis', 'Anna', 'Kaspars', 'Maija'],
        correct: 'Jānis',
      },
      {
        type: 'true_false',
        statement: 'Anna runā pirmā.',
        correct: false,
      },
      {
        type: 'missing_word',
        sentence: 'Labrīt! Mani _____ Jānis.',
        missing: 'sauc',
      },
    ],
  },
  {
    id: 'seed_2',
    title: 'Iepirkšanās',
    audio_url: 'data/A1_klausisanas/audio/6_2.mp3',
    lv_text: 'Cienītājs lūdzu! Paldies, lūdzu! Dāmu, lūdzu!',
    en_text: 'Excuse me please! Thank you please! Madam please!',
    level: 'A1',
    questions: [
      {
        type: 'multiple_choice',
        question: 'Kurš teikums ir pareizs?',
        options: ['Paldies!', 'Lūdzu!', 'Abi ir pareizi', 'Neviens'],
        correct: 'Abi ir pareizi',
      },
      {
        type: 'true_false',
        statement: '"Paldies, lūdzu!" ir pareiza frāze.',
        correct: true,
      },
      {
        type: 'missing_word',
        sentence: 'Cienītājs _____!',
        missing: 'lūdzu',
      },
    ],
  },
  {
    id: 'seed_3',
    title: 'Kur ir...?',
    audio_url: 'data/A1_klausisanas/audio/2_10.mp3',
    lv_text: 'Atvainojiet, kur ir tualete? Tualete ir tur, kreisajā pusē.',
    en_text: 'Excuse me, where is the toilet? The toilet is there, on the left side.',
    level: 'A1',
    questions: [
      {
        type: 'multiple_choice',
        question: 'Kur atrodas tualete?',
        options: ['Labajā pusē', 'Kreisajā pusē', 'Augšā', 'Lejā'],
        correct: 'Kreisajā pusē',
      },
      {
        type: 'true_false',
        statement: 'Tualete ir labajā pusē.',
        correct: false,
      },
      {
        type: 'missing_word',
        sentence: 'Atvainojiet, kur _____ tualete?',
        missing: 'ir',
      },
    ],
  },
  {
    id: 'seed_4',
    title: 'Kāds ir laiks?',
    audio_url: 'data/A1_klausisanas/audio/5_10.mp3',
    lv_text: 'Kāds ir laiks šodien? Šodien ir silts un saulains.',
    en_text: 'What is the weather like today? Today it is warm and sunny.',
    level: 'A1',
    questions: [
      {
        type: 'multiple_choice',
        question: 'Kāds ir laiks šodien?',
        options: ['Auksts', 'Silts un saulains', 'Lietains', 'Mākoņains'],
        correct: 'Silts un saulains',
      },
      {
        type: 'true_false',
        statement: 'Šodien ir lietains.',
        correct: false,
      },
      {
        type: 'missing_word',
        sentence: 'Kāds ir _____ šodien?',
        missing: 'laiks',
      },
    ],
  },
  {
    id: 'seed_5',
    title: 'Kur tu strādā?',
    audio_url: 'data/A1_klausisanas/audio/10_7.mp3',
    lv_text: 'Kur tu strādā? Es strādāju bankā. Un tu? Es strādāju skolā.',
    en_text: 'Where do you work? I work at a bank. And you? I work at a school.',
    level: 'A1',
    questions: [
      {
        type: 'multiple_choice',
        question: 'Kur strādā pirmā persona?',
        options: ['Skolā', 'Bankā', ' slimnīcā', 'Kafejnīcā'],
        correct: 'Bankā',
      },
      {
        type: 'true_false',
        statement: 'Otrā persona strādā skolā.',
        correct: true,
      },
      {
        type: 'missing_word',
        sentence: 'Es _____ bankā.',
        missing: 'strādāju',
      },
    ],
  },
  {
    id: 'seed_6',
    title: 'Cena un nauda',
    audio_url: 'data/A1_klausisanas/audio/6_13.mp3',
    lv_text: 'Cik tas maksā? Tas maksā piecus eiro. Vai jūs varat samaksāt kartē?',
    en_text: 'How much does it cost? It costs five euros. Can you pay by card?',
    level: 'A1',
    questions: [
      {
        type: 'multiple_choice',
        question: 'Cik tas maksā?',
        options: ['Trīs eiro', 'Pieci eiro', 'Desmit eiro', 'Viens eiro'],
        correct: 'Pieci eiro',
      },
      {
        type: 'true_false',
        statement: 'Var samaksāt kartē.',
        correct: true,
      },
      {
        type: 'missing_word',
        sentence: 'Tas _____ piecus eiro.',
        missing: 'maksā',
      },
    ],
  },
  {
    id: 'seed_7',
    title: 'Laiks',
    audio_url: 'data/A1_klausisanas/audio/12_22.mp3',
    lv_text: 'Cik ir pulkstenis? Ir astoņi vakarā. Vai jau ir vēlu? Jā, ir vēlu.',
    en_text: 'What time is it? It is eight in the evening. Is it already late? Yes, it is late.',
    level: 'A1',
    questions: [
      {
        type: 'multiple_choice',
        question: 'Cik ir pulkstenis?',
        options: ['Astoņi no rīta', 'Astoņi vakarā', 'Astoņi dienā', 'Astoņi naktī'],
        correct: 'Astoņi vakarā',
      },
      {
        type: 'true_false',
        statement: 'Ir agri.',
        correct: false,
      },
      {
        type: 'missing_word',
        sentence: 'Cik _____ pulkstenis?',
        missing: 'ir',
      },
    ],
  },
];

function getDateString(date = new Date()) {
  return date.toISOString().split('T')[0];
}

function getDaysBetween(date1, date2) {
  const d1 = new Date(date1);
  const d2 = new Date(date2);
  d1.setHours(0, 0, 0, 0);
  d2.setHours(0, 0, 0, 0);
  return Math.round((d2 - d1) / (1000 * 60 * 60 * 24));
}

function selectChallengeByDate(date, catalog) {
  const dateStr = getDateString(date);
  let hash = 0;
  for (let i = 0; i < dateStr.length; i++) {
    hash = ((hash << 5) - hash + dateStr.charCodeAt(i)) | 0;
  }
  const seedCount = SEED_CHALLENGES.length;
  const catalogCount = catalog.filter(c => c.status === 'completed').length;
  const total = seedCount + catalogCount;
  const index = Math.abs(hash) % total;
  if (index < seedCount) {
    return SEED_CHALLENGES[index];
  }
  const catalogItems = catalog.filter(c => c.status === 'completed');
  return catalogItems[index - seedCount] || SEED_CHALLENGES[0];
}

function loadProgress() {
  try {
    const data = localStorage.getItem(STORAGE_KEY);
    return data ? JSON.parse(data) : createDefaultProgress();
  } catch {
    return createDefaultProgress();
  }
}

function saveProgress(progress) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(progress));
  } catch (e) {
    console.warn('Could not save progress:', e);
  }
}

function createDefaultProgress() {
  return {
    streak: 0,
    longestStreak: 0,
    totalXp: 0,
    lastCompletedDate: null,
    badges: [],
    history: [],
    completedChallenges: 0,
  };
}

function calculateStreak(progress, today) {
  const todayStr = getDateString(today);
  const lastCompleted = progress.lastCompletedDate;
  if (!lastCompleted) return 0;
  const daysDiff = getDaysBetween(lastCompleted, todayStr);
  if (daysDiff === 0) return progress.streak;
  if (daysDiff === 1) return progress.streak + 1;
  return 1;
}

function checkStreakReset(progress, today) {
  const todayStr = getDateString(today);
  const lastCompleted = progress.lastCompletedDate;
  if (!lastCompleted) return false;
  const daysDiff = getDaysBetween(lastCompleted, todayStr);
  return daysDiff > 1;
}

function getPracticeHistory(progress) {
  const history = [];
  const today = new Date();
  for (let i = 6; i >= 0; i--) {
    const date = new Date(today);
    date.setDate(date.getDate() - i);
    const dateStr = getDateString(date);
    const entry = progress.history.find(h => h.date === dateStr);
    history.push({
      date: dateStr,
      completed: entry ? entry.completed : false,
      score: entry ? entry.score : null,
    });
  }
  return history;
}

function awardBadges(progress, completedChallenges, isPerfect, streak) {
  const newBadges = [];
  if (completedChallenges === 1) {
    if (!progress.badges.includes('first_challenge')) {
      newBadges.push('first_challenge');
    }
  }
  if (streak >= 3 && !progress.badges.includes('streak_3')) {
    newBadges.push('streak_3');
  }
  if (streak >= 7 && !progress.badges.includes('streak_7')) {
    newBadges.push('streak_7');
  }
  if (completedChallenges >= 10 && !progress.badges.includes('listening_master')) {
    newBadges.push('listening_master');
  }
  if (isPerfect && completedChallenges >= 5 && !progress.badges.includes('a2_checkpoint')) {
    newBadges.push('a2_checkpoint');
  }
  return newBadges;
}

function calculateScore(answers, questions) {
  if (!questions || questions.length === 0) return { correct: 0, total: 0, percentage: 0 };
  let correct = 0;
  for (let i = 0; i < questions.length; i++) {
    const q = questions[i];
    const answer = answers[i];
    if (q.type === 'multiple_choice' && answer === q.correct) correct++;
    if (q.type === 'true_false' && answer === q.correct) correct++;
    if (q.type === 'missing_word') {
      const normalizedAnswer = (answer || '').toLowerCase().trim().replace(/[.,!?;]/g, '');
      const normalizedCorrect = q.missing.toLowerCase().trim();
      if (normalizedAnswer === normalizedCorrect) correct++;
    }
  }
  const total = questions.length;
  return {
    correct,
    total,
    percentage: Math.round((correct / total) * 100),
  };
}

function submitChallenge(answers, questions) {
  const progress = loadProgress();
  const today = new Date();
  const todayStr = getDateString(today);
  const alreadyCompleted = progress.history.some(h => h.date === todayStr && h.completed);
  if (alreadyCompleted) {
    return { error: 'already_completed', message: 'Jūs jau esat pabeidzis šodienas izaicinājumu.' };
  }
  const score = calculateScore(answers, questions);
  const isPerfect = score.correct === score.total;
  const xpEarned = XP_COMPLETION + (isPerfect ? XP_PERFECT_BONUS : 0);
  const newStreak = calculateStreak(progress, today);
  const progressCopy = { ...progress };
  if (checkStreakReset(progress, today)) {
    progressCopy.streak = 1;
  } else {
    progressCopy.streak = newStreak;
  }
  if (progressCopy.streak > progressCopy.longestStreak) {
    progressCopy.longestStreak = progressCopy.streak;
  }
  progressCopy.totalXp += xpEarned;
  progressCopy.lastCompletedDate = todayStr;
  progressCopy.completedChallenges += 1;
  progressCopy.history = progressCopy.history.filter(h => {
    const daysDiff = getDaysBetween(h.date, todayStr);
    return daysDiff < 7;
  });
  progressCopy.history.push({ date: todayStr, completed: true, score: score.percentage });
  const newBadges = awardBadges(progressCopy, progressCopy.completedChallenges, isPerfect, progressCopy.streak);
  progressCopy.badges = [...progressCopy.badges, ...newBadges];
  saveProgress(progressCopy);
  return {
    score,
    xpEarned,
    newStreak: progressCopy.streak,
    longestStreak: progressCopy.longestStreak,
    totalXp: progressCopy.totalXp,
    newBadges: newBadges.map(id => BADGES[id]),
    progress: progressCopy,
  };
}

function getTodayChallenge(catalog) {
  const today = new Date();
  const todayStr = getDateString(today);
  const progress = loadProgress();
  const todayEntry = progress.history.find(h => h.date === todayStr);
  const challenge = selectChallengeByDate(today, catalog);
  return {
    challenge,
    alreadyCompleted: todayEntry ? todayEntry.completed : false,
    previousScore: todayEntry ? todayEntry.score : null,
    progress,
    practiceHistory: getPracticeHistory(progress),
  };
}

function getProgress() {
  return loadProgress();
}

function getAllBadges() {
  return BADGES;
}

function resetProgress() {
  localStorage.removeItem(STORAGE_KEY);
}
