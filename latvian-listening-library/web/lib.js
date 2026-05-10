/**
 * lib.js — Pure logic functions for the Latvian Listening Library.
 *
 * No ES module syntax. Works as a browser <script src="lib.js"> and
 * as a Node.js require('./lib.js') target.
 */

/**
 * Format a number of seconds into a "m:ss" string.
 * e.g. formatTime(75) → "1:15"
 *
 * @param {number} seconds - Non-negative number of seconds.
 * @returns {string} Time string in "m:ss" format.
 */
function formatTime(seconds) {
  var s = Math.floor(seconds);
  var mins = Math.floor(s / 60);
  var secs = s % 60;
  return mins + ':' + (secs < 10 ? '0' : '') + secs;
}

/**
 * Filter a catalog array by a search query.
 * Searches title, original_filename, level, status, lv_text, en_text
 * case-insensitively.
 *
 * @param {Array<Object>} catalog - Array of lesson objects.
 * @param {string} query - Search string.
 * @returns {Array<Object>} Filtered array of matching lessons.
 */
function applyFilter(catalog, query) {
  var q = (query || '').toLowerCase();
  if (!q) return catalog.slice();
  return catalog.filter(function (item) {
    var fields = [
      item.title,
      item.original_filename,
      item.level,
      item.status,
      item.lv_text,
      item.en_text
    ];
    return fields.some(function (field) {
      return field != null && String(field).toLowerCase().indexOf(q) !== -1;
    });
  });
}

/**
 * Determine whether a lesson is considered completed.
 * A lesson is completed when duration > 0 and currentTime / duration >= 0.8.
 *
 * @param {number} currentTime - Current playback position in seconds.
 * @param {number} duration - Total duration in seconds.
 * @returns {boolean}
 */
function isCompleted(currentTime, duration) {
  return duration > 0 && currentTime / duration >= 0.8;
}

/**
 * Calculate progress for a set of lessons.
 *
 * @param {string[]} lessonIds - Full array of lesson IDs for the level.
 * @param {Object} completedMap - Map of { [lessonId]: true } for completed lessons.
 * @returns {{ valuenow: number, label: string }}
 */
function calcProgress(lessonIds, completedMap) {
  var total = lessonIds.length;
  var completedCount = 0;
  for (var i = 0; i < lessonIds.length; i++) {
    if (completedMap && completedMap[lessonIds[i]] === true) {
      completedCount++;
    }
  }
  var valuenow = total === 0 ? 0 : Math.round(completedCount / total * 100);
  var label = completedCount + ' of ' + total + ' completed';
  return { valuenow: valuenow, label: label };
}

/**
 * Resolve display text for a transcript or translation panel.
 * Returns the text if it is non-empty and non-whitespace; otherwise returns
 * a language-appropriate unavailability message.
 *
 * @param {string|null|undefined} text - The raw text value.
 * @param {'lv'|'en'} lang - Language code.
 * @returns {string}
 */
function resolveText(text, lang) {
  if (text != null && String(text).trim().length > 0) {
    return text;
  }
  if (lang === 'lv') {
    return 'Latvian transcript is not available yet.';
  }
  return 'English translation is not available yet.';
}

/**
 * Toggle between light and dark themes.
 * The ariaLabel describes what clicking the button will do next
 * (i.e. it names the opposite action).
 *
 * toggleTheme('light') → { theme: 'dark',  ariaLabel: 'Switch to light mode' }
 * toggleTheme('dark')  → { theme: 'light', ariaLabel: 'Switch to dark mode'  }
 *
 * @param {'light'|'dark'} currentTheme
 * @returns {{ theme: string, ariaLabel: string }}
 */
function toggleTheme(currentTheme) {
  if (currentTheme === 'light') {
    return { theme: 'dark', ariaLabel: 'Switch to light mode' };
  }
  return { theme: 'light', ariaLabel: 'Switch to dark mode' };
}

/**
 * Return an array containing only the ID of the currently selected lesson.
 *
 * @param {Array<Object>} lessons - Array of lesson objects with an `id` property.
 * @param {number} selectedIndex - Index of the selected lesson.
 * @returns {string[]} Single-element array with the selected lesson's ID.
 */
function getActiveIds(lessons, selectedIndex) {
  return [lessons[selectedIndex].id];
}

var AudioSourceType = {
  MP3: 'mp3',
  HLS: 'hls'
};

function getEnvValue(name, fallback) {
  if (typeof process !== 'undefined' && process.env && process.env[name]) {
    return process.env[name];
  }
  if (typeof window !== 'undefined' && window[name]) {
    return window[name];
  }
  return fallback;
}

function AudioSource(type, baseUrl) {
  this.type = type || AudioSourceType.MP3;
  this.baseUrl = baseUrl || '';
}

AudioSource.prototype.getAudioUrl = function(audioPath) {
  if (!audioPath) return '';
  if (this.type === AudioSourceType.HLS) {
    return this.baseUrl + audioPath.replace(/\.mp3$/i, '.m3u8');
  }
  return this.baseUrl + audioPath;
};

AudioSource.prototype.getWaveformUrl = function(audioPath) {
  if (!audioPath) return '';
  return this.baseUrl + audioPath.replace(/\.mp3$/i, '.waveform.json');
};

function Analytics(remoteSinkUrl) {
  this.events = [];
  this.remoteSinkUrl = remoteSinkUrl || null;
  this.sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).slice(2, 10);
}

Analytics.EventTypes = {
  AUDIO_PLAY: 'audio_play',
  AUDIO_PAUSE: 'audio_pause',
  SENTENCE_REPLAY: 'sentence_replay',
  LESSON_COMPLETE: 'lesson_complete',
  QUIZ_SUBMIT: 'quiz_submit',
  FLASHCARD_REVIEW: 'flashcard_review',
  EXAM_SIMULATION_COMPLETE: 'exam_simulation_complete'
};

Analytics.prototype.track = function(eventType, payload) {
  var event = {
    id: 'evt_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8),
    type: eventType,
    timestamp: new Date().toISOString(),
    session_id: this.sessionId,
    payload: payload || {}
  };
  this.events.push(event);

  if (this.remoteSinkUrl && typeof fetch === 'function') {
    fetch(this.remoteSinkUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(event)
    }).catch(function() {});
  }

  return event;
};

Analytics.prototype.getEvents = function() {
  return this.events.slice();
};

Analytics.prototype.export = function() {
  return JSON.stringify(this.events, null, 2);
};

function createAnalyticsTracker(remoteSinkUrl) {
  return new Analytics(remoteSinkUrl || getEnvValue('ANALYTICS_SINK_URL', null));
}

var LessonValidation = {
  requiredFields: ['id', 'level', 'original_filename', 'audio_url', 'status'],
  validateLesson: function(lesson, isDev) {
    var errors = [];
    for (var i = 0; i < LessonValidation.requiredFields.length; i++) {
      var field = LessonValidation.requiredFields[i];
      if (lesson[field] === undefined || lesson[field] === null || lesson[field] === '') {
        errors.push('Missing required field: ' + field);
      }
    }
    if (lesson.level && ['A1', 'A2'].indexOf(lesson.level) === -1) {
      errors.push('Invalid level: ' + lesson.level);
    }
    if (lesson.status && ['completed', 'transcribed only', 'translation failed', 'failed', 'pending'].indexOf(lesson.status) === -1) {
      errors.push('Invalid status: ' + lesson.status);
    }
    if (isDev && errors.length > 0 && typeof console !== 'undefined') {
      console.warn('[LessonValidation] Invalid lesson:', lesson.id, errors);
    }
    return { valid: errors.length === 0, errors: errors };
  },
  validateCatalog: function(catalog, isDev) {
    if (!Array.isArray(catalog)) {
      return { valid: false, errors: ['Catalog must be an array'], count: 0 };
    }
    var invalidLessons = [];
    for (var i = 0; i < catalog.length; i++) {
      var result = LessonValidation.validateLesson(catalog[i], isDev);
      if (!result.valid) {
        invalidLessons.push({ index: i, id: catalog[i].id, errors: result.errors });
      }
    }
    if (isDev && invalidLessons.length > 0 && typeof console !== 'undefined') {
      console.warn('[LessonValidation] Invalid lessons in catalog:', invalidLessons);
    }
    return {
      valid: invalidLessons.length === 0,
      errors: invalidLessons.reduce(function(all, item) {
        return all.concat(item.errors);
      }, []),
      count: catalog.length,
      invalidCount: invalidLessons.length
    };
  }
};

var AIProviderType = {
  GROQ: 'groq',
  CODEX: 'codex',
  MOCK: 'mock'
};

function AIProvider(providerType, config) {
  config = config || {};
  this.type = providerType || AIProviderType.MOCK;
  this.baseUrl = config.baseUrl || '';
  this.apiKey = config.apiKey || '';
  this.model = config.model || 'mock';
}

AIProvider.prototype.transcriptEnrich = function(transcriptText, options) {
  options = options || {};
  if (this.type === AIProviderType.MOCK) {
    return Promise.resolve({
      original: transcriptText,
      enriched: transcriptText,
      vocab: options.vocab || [],
      explanation: options.explanation || 'Mock explanation',
      difficulty: options.difficulty || 'A2'
    });
  }
  return fetch(this.baseUrl + '/api/enrich', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer ' + this.apiKey
    },
    body: JSON.stringify({
      text: transcriptText,
      model: this.model,
      options: options
    })
  }).then(function(response) {
    if (!response.ok) throw new Error('AI enrich failed: ' + response.status);
    return response.json();
  });
};

function createAIProvider(providerType, config) {
  return new AIProvider(providerType || getEnvValue('LLM_PROVIDER', AIProviderType.MOCK), {
    baseUrl: getEnvValue('LLM_BASE_URL', ''),
    apiKey: getEnvValue('LLM_API_KEY', ''),
    model: getEnvValue('LLM_MODEL', 'mock'),
    ...(config || {})
  });
}

function VocabularySearch(vocabData) {
  this.index = {};
  this.buildIndex(vocabData || []);
}

VocabularySearch.prototype.buildIndex = function(vocabData) {
  for (var i = 0; i < vocabData.length; i++) {
    var entry = vocabData[i];
    var keys = [
      (entry.latvian || entry.word || '').toLowerCase().trim(),
      (entry.english || entry.translation || '').toLowerCase().trim()
    ];
    for (var j = 0; j < keys.length; j++) {
      var key = keys[j];
      if (!key) continue;
      if (!this.index[key]) this.index[key] = [];
      this.index[key].push(entry);
    }
  }
};

VocabularySearch.prototype.search = function(query) {
  var q = (query || '').toLowerCase().trim();
  if (q.length < 2) return [];
  var results = [];
  Object.keys(this.index).forEach(function(word) {
    if (word.indexOf(q) !== -1) {
      results = results.concat(this.index[word]);
    }
  }, this);
  return results;
};

VocabularySearch.prototype.lookup = function(latvianWord) {
  return this.search(latvianWord);
};

function createVocabularySearch(vocabData) {
  return new VocabularySearch(vocabData || []);
}

function createErrorBoundary(errorHandler) {
  return function(componentFn) {
    return function() {
      try {
        return componentFn.apply(null, arguments);
      } catch (error) {
        if (typeof console !== 'undefined') {
          console.error('[ErrorBoundary]', error.message);
        }
        if (errorHandler) return errorHandler(error);
        return { error: error.message };
      }
    };
  };
}

var DevConfig = {
  isDev: getEnvValue('NODE_ENV', '') === 'development',
  analyticsSinkUrl: getEnvValue('ANALYTICS_SINK_URL', null),
  audioBaseUrl: getEnvValue('AUDIO_BASE_URL', ''),
  cacheControlMaxAge: 3600
};

function getCacheHeaders() {
  return {
    'Cache-Control': 'public, max-age=' + DevConfig.cacheControlMaxAge + ', s-maxage=' + DevConfig.cacheControlMaxAge
  };
}

// CommonJS export for Node.js require() compatibility (e.g. unit tests).
if (typeof module !== 'undefined') {
  module.exports = {
    formatTime: formatTime,
    applyFilter: applyFilter,
    isCompleted: isCompleted,
    calcProgress: calcProgress,
    resolveText: resolveText,
    toggleTheme: toggleTheme,
    getActiveIds: getActiveIds,
    AudioSourceType: AudioSourceType,
    AudioSource: AudioSource,
    Analytics: Analytics,
    LessonValidation: LessonValidation,
    AIProviderType: AIProviderType,
    AIProvider: AIProvider,
    VocabularySearch: VocabularySearch,
    createErrorBoundary: createErrorBoundary,
    DevConfig: DevConfig,
    getCacheHeaders: getCacheHeaders,
    createAnalyticsTracker: createAnalyticsTracker,
    createAIProvider: createAIProvider,
    createVocabularySearch: createVocabularySearch
  };
}
