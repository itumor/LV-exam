const AudioSourceType = {
  MP3: 'mp3',
  HLS: 'hls',
  WAVEFORM: 'waveform',
};

class AudioSource {
  constructor(type = AudioSourceType.MP3, baseUrl = '') {
    this.type = type;
    this.baseUrl = baseUrl;
  }

  getAudioUrl(audioPath) {
    if (this.type === AudioSourceType.MP3) {
      return this.baseUrl + audioPath;
    }
    return this.baseUrl + audioPath.replace('.mp3', '.m3u8');
  }

  getWaveformUrl(audioPath) {
    return this.baseUrl + audioPath.replace('.mp3', '.waveform.json');
  }
}

class Analytics {
  constructor(remoteSinkUrl = null) {
    this.events = [];
    this.remoteSinkUrl = remoteSinkUrl;
    this.sessionId = this.generateSessionId();
  }

  generateSessionId() {
    return 'session_' + Date.now() + '_' + Math.random().toString(36).slice(2, 10);
  }

  static EventTypes = {
    AUDIO_PLAY: 'audio_play',
    AUDIO_PAUSE: 'audio_pause',
    SENTENCE_REPLAY: 'sentence_replay',
    LESSON_COMPLETE: 'lesson_complete',
    QUIZ_SUBMIT: 'quiz_submit',
    FLASHCARD_REVIEW: 'flashcard_review',
    EXAM_SIMULATION_COMPLETE: 'exam_simulation_complete',
  };

  track(eventType, payload = {}) {
    const event = {
      id: 'evt_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8),
      type: eventType,
      timestamp: new Date().toISOString(),
      session_id: this.sessionId,
      payload,
    };
    this.events.push(event);
    if (process.env.NODE_ENV === 'development') {
      console.log('[Analytics]', event.type, event.payload);
    }
    if (this.remoteSinkUrl) {
      this.sendRemote(event);
    }
    return event;
  }

  async sendRemote(event) {
    try {
      await fetch(this.remoteSinkUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(event),
      });
    } catch (e) {
      console.warn('[Analytics] Remote sink failed:', e.message);
    }
  }

  getEvents() {
    return [...this.events];
  }

  export() {
    return JSON.stringify(this.events, null, 2);
  }
}

const analytics = new Analytics(
  process.env.ANALYTICS_SINK_URL || null
);

function createAnalyticsTracker() {
  return analytics;
}

const LessonValidation = {
  requiredFields: ['id', 'level', 'original_filename', 'audio_url', 'status'],
  optionalFields: [
    'title', 'lv_text', 'en_text', 'lv_markdown_url', 'en_markdown_url',
    'transcription_status', 'translation_status', 'lesson_group', 'order',
    'waveform_url'
  ],

  validateLesson(lesson, isDev = process.env.NODE_ENV === 'development') {
    const errors = [];
    for (const field of this.requiredFields) {
      if (lesson[field] === undefined || lesson[field] === null || lesson[field] === '') {
        errors.push(`Missing required field: ${field}`);
      }
    }
    if (lesson.level && !['A1', 'A2'].includes(lesson.level)) {
      errors.push(`Invalid level: ${lesson.level}`);
    }
    if (lesson.status && !['completed', 'transcribed only', 'translation failed', 'failed', 'pending'].includes(lesson.status)) {
      errors.push(`Invalid status: ${lesson.status}`);
    }
    if (isDev && errors.length > 0) {
      console.warn('[LessonValidation] Invalid lesson:', lesson.id, errors);
    }
    return { valid: errors.length === 0, errors };
  },

  validateCatalog(catalog, isDev = process.env.NODE_ENV === 'development') {
    if (!Array.isArray(catalog)) {
      return { valid: false, errors: ['Catalog must be an array'], count: 0 };
    }
    const invalidLessons = [];
    catalog.forEach((lesson, index) => {
      const result = this.validateLesson(lesson, isDev);
      if (!result.valid) {
        invalidLessons.push({ index, id: lesson.id, errors: result.errors });
      }
    });
    if (isDev && invalidLessons.length > 0) {
      console.warn('[LessonValidation] Invalid lessons in catalog:', invalidLessons);
    }
    return {
      valid: invalidLessons.length === 0,
      errors: invalidLessons.flatMap(l => l.errors),
      count: catalog.length,
      invalidCount: invalidLessons.length,
    };
  },
};

function createLessonValidator() {
  return LessonValidation;
}

const AIProviderType = {
  GROQ: 'groq',
  CODEX: 'codex',
  MOCK: 'mock',
};

class AIProvider {
  constructor(providerType = AIProviderType.MOCK, config = {}) {
    this.type = providerType;
    this.config = config;
    this.baseUrl = config.baseUrl || '';
    this.apiKey = config.apiKey || '';
    this.model = config.model || 'mock';
  }

  async transcriptEnrich(transcriptText, options = {}) {
    if (this.type === AIProviderType.MOCK) {
      return this.mockEnrich(transcriptText, options);
    }
    const endpoint = this.baseUrl + '/api/enrich';
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.apiKey}`,
      },
      body: JSON.stringify({
        text: transcriptText,
        model: this.model,
        ...options,
      }),
    });
    if (!response.ok) {
      throw new Error(`AI enrich failed: ${response.status}`);
    }
    return response.json();
  }

  async mockEnrich(text, options = {
    vocab: [],
    explanation: '',
    difficulty: 'A2'
  }) {
    await new Promise(resolve => setTimeout(resolve, 100));
    return {
      original: text,
      enriched: text,
      vocab: options.vocab || [],
      explanation: options.explanation || 'Mock explanation',
      difficulty: options.difficulty || 'A2',
    };
  }
}

function createAIProvider(providerType, config) {
  const envProvider = process.env.LLM_PROVIDER || AIProviderType.MOCK;
  const envBaseUrl = process.env.LLM_BASE_URL || '';
  const envApiKey = process.env.LLM_API_KEY || '';
  return new AIProvider(providerType || envProvider, {
    baseUrl: envBaseUrl,
    apiKey: envApiKey,
    ...config,
  });
}

class VocabularySearch {
  constructorIndex = null;

  constructor(vocabData = []) {
    this.index = null;
    this.buildIndex(vocabData);
  }

  buildIndex(vocabData) {
    this.index = new Map();
    for (const entry of vocabData) {
      const word = (entry.latvian || entry.word || '').toLowerCase().trim();
      if (word) {
        if (!this.index.has(word)) {
          this.index.set(word, []);
        }
        this.index.get(word).push(entry);
      }
      const en = (entry.english || entry.translation || '').toLowerCase().trim();
      if (en) {
        if (!this.index.has(en)) {
          this.index.set(en, []);
        }
        this.index.get(en).push(entry);
      }
    }
  }

  search(query) {
    if (!query || !this.index) return [];
    const q = query.toLowerCase().trim();
    if (q.length < 2) return [];
    const results = [];
    for (const [word, entries] of this.index) {
      if (word.includes(q)) {
        results.push(...entries);
      }
    }
    return results;
  }

  lookup(latvianWord) {
    return this.search(latvianWord);
  }
}

function createVocabularySearch(vocabData = []) {
  return new VocabularySearch(vocabData);
}

function createErrorBoundary(errorHandler) {
  return function errorBoundaryWrapper(componentFn) {
    return function wrapper(...args) {
      try {
        return componentFn(...args);
      } catch (error) {
        console.error('[ErrorBoundary]', error.message);
        if (errorHandler) {
          return errorHandler(error);
        }
        return { error: error.message };
      }
    };
  };
}

const DevConfig = {
  isDev: process.env.NODE_ENV === 'development',
  analyticsSinkUrl: process.env.ANALYTICS_SINK_URL || null,
  audioBaseUrl: process.env.AUDIO_BASE_URL || '',
  cacheControlMaxAge: 3600,
};

function getCacheHeaders() {
  return {
    'Cache-Control': `public, max-age=${DevConfig.cacheControlMaxAge}, s-maxage=${DevConfig.cacheControlMaxAge}`,
  };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    AudioSourceType,
    AudioSource,
    Analytics,
    LessonValidation,
    AIProviderType,
    AIProvider,
    VocabularySearch,
    createErrorBoundary,
    DevConfig,
    getCacheHeaders,
    createAnalyticsTracker,
    createLessonValidator,
    createAIProvider,
    createVocabularySearch,
  };
}