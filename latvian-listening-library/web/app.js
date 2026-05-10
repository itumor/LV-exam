(function () {
  // ---------------------------------------------------------------------------
  // ThemeManager — apply theme before any paint
  // ---------------------------------------------------------------------------
  var ThemeManager = {
    apply: function (theme) {
      document.documentElement.setAttribute('data-theme', theme);
      var btn = document.getElementById('theme-toggle');
      if (btn) {
        var result = toggleTheme(theme);
        btn.setAttribute('aria-label', result.ariaLabel);
      }
    },
    toggle: function () {
      var current = document.documentElement.getAttribute('data-theme') || 'light';
      var result = toggleTheme(current);
      ThemeManager.apply(result.theme);
      try { localStorage.setItem('theme', result.theme); } catch (e) {}
    },
    init: function () {
      var stored;
      try { stored = localStorage.getItem('theme'); } catch (e) {}
      if (stored === 'dark' || stored === 'light') {
        ThemeManager.apply(stored);
      }
    }
  };

  // Apply theme synchronously before any DOM manipulation / paint
  ThemeManager.init();

  // ---------------------------------------------------------------------------
  // State — in-memory application state
  // ---------------------------------------------------------------------------
  var State = {
    catalog: [],
    filtered: [],
    selectedIndex: -1,
    isPlaying: false,
    currentTime: 0,
    duration: 0,
    waveformData: null
  };
  var isDev = window.location.hostname === 'localhost' || window.location.hostname.indexOf('127.0.0.1') !== -1;
  var audioSource = new AudioSource(AudioSourceType.MP3, window.AUDIO_BASE_URL || '');
  var analyticsTracker = createAnalyticsTracker(isDev ? null : window.ANALYTICS_SINK_URL || null);

  // ---------------------------------------------------------------------------
  // SkeletonHelper — show/hide skeleton loading states
  // ---------------------------------------------------------------------------
  var SkeletonHelper = {
    showSidebar: function() {
      document.querySelectorAll('#menu .skeleton-item').forEach(function(el) { el.hidden = false; });
      document.querySelectorAll('#menu .audio-item').forEach(function(el) { el.hidden = true; });
    },
    hideSidebar: function() {
      document.querySelectorAll('#menu .skeleton-item').forEach(function(el) { el.hidden = true; });
    },
    showPanels: function() {
      document.querySelectorAll('.panel-body .skeleton-line').forEach(function(el) { el.hidden = false; });
      document.querySelectorAll('.reading-text').forEach(function(el) { el.hidden = true; });
    },
    hidePanels: function() {
      document.querySelectorAll('.panel-body .skeleton-line').forEach(function(el) { el.hidden = true; });
      document.querySelectorAll('.reading-text').forEach(function(el) { el.hidden = false; });
    }
  };

  // ---------------------------------------------------------------------------
  // ProgressTracker — localStorage-backed lesson completion tracking
  // ---------------------------------------------------------------------------
  var ProgressTracker = {
    _completed: {},
    load: function() {
      try {
        var raw = localStorage.getItem('lll_completed');
        if (raw) ProgressTracker._completed = JSON.parse(raw);
      } catch(e) {}
    },
    save: function(id) {
      ProgressTracker._completed[id] = true;
      try {
        localStorage.setItem('lll_completed', JSON.stringify(ProgressTracker._completed));
      } catch(e) {}
      ProgressTracker.updateUI();
    },
    isCompleted: function(id) {
      return ProgressTracker._completed[id] === true;
    },
    getCompleted: function() {
      return ProgressTracker._completed;
    },
    updateUI: function() {
      // Update completion dots on sidebar buttons
      var buttons = document.querySelectorAll('.audio-item[data-lesson-id]');
      buttons.forEach(function(btn) {
        var id = btn.getAttribute('data-lesson-id');
        var dot = btn.querySelector('.completion-dot');
        if (dot) {
          if (ProgressTracker.isCompleted(id)) {
            btn.classList.add('completed');
          } else {
            btn.classList.remove('completed');
          }
        }
      });
      // Update progress bar for current level
      var item = State.filtered[State.selectedIndex];
      if (!item) return;
      var levelItems = State.catalog.filter(function(l) { return l.level === item.level; });
      var levelIds = levelItems.map(function(l) { return l.id; });
      var progress = calcProgress(levelIds, ProgressTracker._completed);
      var bar = document.getElementById('level-progress-bar');
      var label = document.getElementById('level-progress-label');
      if (bar) {
        bar.setAttribute('aria-valuenow', progress.valuenow);
        bar.style.width = progress.valuenow + '%';
      }
      if (label) label.textContent = progress.label;
      // Show/hide exam readiness
      var examItems = levelItems.filter(function(l) { return l.exam; });
      var examEl = document.getElementById('exam-readiness');
      var examPct = document.getElementById('exam-pct');
      if (examEl && examItems.length > 0) {
        var examCompleted = examItems.filter(function(l) { return ProgressTracker.isCompleted(l.id); }).length;
        var pct = Math.round(examCompleted / examItems.length * 100);
        if (examPct) examPct.textContent = pct + '%';
        examEl.hidden = false;
      } else if (examEl) {
        examEl.hidden = true;
      }
    }
  };
  ProgressTracker.load();

  // ---------------------------------------------------------------------------
  // DOM references
  // ---------------------------------------------------------------------------
  var menu = document.querySelector('#menu');
  var search = document.querySelector('#search');
  var styleFilter = document.querySelector('#styleFilter');
  var categoryFilter = document.querySelector('#categoryFilter');
  var title = document.querySelector('#title');
  var subtitle = document.querySelector('#subtitle');
  var audio = document.querySelector('#audio');

  // Wire timeupdate to track completion via ProgressTracker
  if (audio) {
    audio.addEventListener('timeupdate', function() {
      var item = State.filtered[State.selectedIndex];
      if (item && isCompleted(audio.currentTime, audio.duration)) {
        ProgressTracker.save(item.id);
      }
    });
  }

  var lvText = document.querySelector('#lvText');
  var enText = document.querySelector('#enText');
  var lvLink = document.querySelector('#lvLink');
  var enLink = document.querySelector('#enLink');
  var statusBadge = document.querySelector('#statusBadge');
  var speakerBadge = document.querySelector('#speakerBadge');
  var previousButton = document.querySelector('#prev');
  var nextButton = document.querySelector('#next');
  var voiceRecommendation = document.querySelector('#voiceRecommendation');
  var compBarFill = document.querySelector('#compBarFill');
  var compPct = document.querySelector('#compPct');
  var compLabel = document.querySelector('#compLabel');
  var compEstimateNote = document.querySelector('#compEstimateNote');
  var compMeterCard = document.querySelector('#compMeterCard');
  var statTotal = document.querySelector('#statTotal');
  var statUnique = document.querySelector('#statUnique');
  var statUnknown = document.querySelector('#statUnknown');
  var unknownWordList = document.querySelector('#unknownWordList');
  var activeCompFilter = 'all';
  var aiService = window.AIExplanationService ? new window.AIExplanationService() : null;
  var currentExplanationSentence = null;
  var aiPanel = document.querySelector('#aiPanel');
  var aiPanelContent = document.querySelector('#aiPanelContent');
  var aiLoading = document.querySelector('#aiLoading');
  var aiError = document.querySelector('#aiError');
  var aiOverlay = document.querySelector('#aiOverlay');
  var closeAIPanelBtn = document.querySelector('#closeAIPanel');
  var aiModeToggle = document.querySelector('#aiModeToggle');
  var retryBtn = document.querySelector('#retryBtn');

  if (audio) {
    audio.addEventListener('play', function() {
      var item = State.filtered[State.selectedIndex];
      if (item) {
        analyticsTracker.track(Analytics.EventTypes.AUDIO_PLAY, {
          lesson_id: item.id,
          filename: item.original_filename
        });
      }
    });
    audio.addEventListener('pause', function() {
      var item = State.filtered[State.selectedIndex];
      if (item && !audio.ended) {
        analyticsTracker.track(Analytics.EventTypes.AUDIO_PAUSE, {
          lesson_id: item.id,
          filename: item.original_filename
        });
      }
    });
  }

  // ---------------------------------------------------------------------------
  // Constants
  // ---------------------------------------------------------------------------
  var levelLabels = {
    A1: 'A1 Klausīšanās',
    A2: 'A2 Klausīšanās',
  };

  var voiceTypeLabels = {
    cashier: 'Cashier',
    doctor: 'Doctor',
    teacher: 'Teacher',
    colleague: 'Colleague',
    driver: 'Bus Driver',
    grandmother: 'Grandmother',
    grandfather: 'Grandfather',
    government: 'Government Office',
    friend: 'Friend',
    landlord: 'Landlord'
  };

  var MODE_KEY = 'latvian_listening_library_mode';
  var SCENARIO_PROGRESS_KEY = 'latvian_listening_library_progress';
  var currentMode = localStorage.getItem(MODE_KEY) || 'library';
  var scenarioProgress = {};

  try {
    scenarioProgress = JSON.parse(localStorage.getItem(SCENARIO_PROGRESS_KEY)) || {};
  } catch (e) {
    scenarioProgress = {};
  }

  var categoryFilters = {
    family: 'Gimene',
    work: 'Darbs',
    health: 'Veseliba',
    bureaucracy: 'Birokratija',
    transport: 'Transports',
    shopping: 'Iepirksanas'
  };

  var scenarios = [
    {
      id: 'school-call',
      title: 'Zvana uz skolu',
      description: "Communicating with teachers about your child's progress, attendance, or schedule.",
      category: 'family',
      vocabulary: ['skolotajs', 'stunda', 'majasdarbs', 'atzime', 'sapulce', 'kavejums'],
      phrases: [
        { lv: 'Labdien, es gribetu runat ar savas meitas skolotaju.', en: "Hello, I'd like to speak with my daughter's teacher.", context: 'Calling a teacher' },
        { lv: 'Kad ir vecaku sapulce?', en: 'When is the parent meeting?', context: 'Asking about school events' }
      ]
    },
    {
      id: 'doctor',
      title: 'Pie arsta',
      description: 'Making appointments, describing symptoms, and understanding medical instructions.',
      category: 'health',
      vocabulary: ['arsts', 'slimiba', 'simptomi', 'recepte', 'analizes', 'aptieka'],
      phrases: [
        { lv: 'Man sap galva un ir temperatura.', en: 'I have a headache and a fever.', context: 'Describing symptoms' },
        { lv: 'Kad man jaatnak uz kontroli?', en: 'When should I come for a follow-up?', context: 'Follow-up appointment' }
      ]
    },
    {
      id: 'government',
      title: 'Valsts iestade',
      description: 'Visiting municipal offices, population registry, and social services.',
      category: 'bureaucracy',
      vocabulary: ['dokumenti', 'veidlapa', 'rinda', 'apstiprinajums', 'dzivesvieta'],
      phrases: [
        { lv: 'Kur es varu registret dzivesvietu?', en: 'Where can I register my residence?', context: 'Residence registration' },
        { lv: 'Kadi dokumenti man ir nepieciesami?', en: 'What documents do I need?', context: 'Required documents' }
      ]
    },
    {
      id: 'residency',
      title: 'Uzturesanas atlauja',
      description: 'Applying for residence permits, extensions, and understanding requirements.',
      category: 'bureaucracy',
      vocabulary: ['uzturesanas atlauja', 'pieteikums', 'termins', 'maksa', 'intervija'],
      phrases: [
        { lv: 'Es velos pieteikties uzturesanas atlaujai.', en: 'I want to apply for a residence permit.', context: 'Application' },
        { lv: 'Cik ilgi jagaida lemums?', en: 'How long does it take to get a decision?', context: 'Processing time' }
      ]
    },
    {
      id: 'work-meeting',
      title: 'Darba sanaksme',
      description: 'Participating in workplace meetings and understanding tasks.',
      category: 'work',
      vocabulary: ['sanaksme', 'projekts', 'uzdevums', 'termins', 'komanda'],
      phrases: [
        { lv: 'Kads ir projekta grafiks?', en: 'What is the project schedule?', context: 'Project planning' },
        { lv: 'Vai es varu sanemt so informaciju rakstiski?', en: 'Can I get this information in writing?', context: 'Written confirmation' }
      ]
    },
    {
      id: 'transport',
      title: 'Sabiedriskais transports',
      description: 'Buying tickets, asking about routes, schedules, and stops.',
      category: 'transport',
      vocabulary: ['autobuss', 'tramvajs', 'bilete', 'marsruts', 'pietura'],
      phrases: [
        { lv: 'Vai sis autobuss brauc uz centru?', en: 'Does this bus go to the center?', context: 'Route inquiry' },
        { lv: 'Es gribetu izkapt nakamaja pietura.', en: 'I would like to get off at the next stop.', context: 'Requesting a stop' }
      ]
    },
    {
      id: 'grocery',
      title: 'Veikals/Kase',
      description: 'Shopping, asking for products, understanding prices, and payment methods.',
      category: 'shopping',
      vocabulary: ['prece', 'cena', 'atlaide', 'svars', 'kvits'],
      phrases: [
        { lv: 'Kur es varu atrast maizi?', en: 'Where can I find bread?', context: 'Finding products' },
        { lv: 'Vai es varu maksat ar karti?', en: 'Can I pay by card?', context: 'Card payment' }
      ]
    }
  ];

  var askToRepeatPhrases = [
    { lv: 'Ludzu, atkartojiet!', en: 'Please repeat!', context: 'When you need to hear it again' },
    { lv: 'Es nesapratu.', en: "I didn't understand.", context: 'When the meaning is unclear' },
    { lv: 'Vai jus varat runat lenak?', en: 'Can you speak more slowly?', context: 'When speech is too fast' }
  ];

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------
  function badgeClass(status) {
    if (status === 'completed') return 'badge badge-completed';
    if (status === 'transcribed only' || status === 'translation failed') return 'badge badge-transcribed';
    if (status === 'failed') return 'badge badge-failed';
    return 'badge badge-muted';
  }

  function getSpeakingStyle(item) {
    if (!item) return '';
    return item.speaking_style || item.voice_style || item.style || '';
  }

  function displaySpeakerBadge(item) {
    if (!speakerBadge) return;
    if (!item || !item.has_speaker) {
      speakerBadge.style.display = 'none';
      return;
    }

    var label = item.speaker_label || voiceTypeLabels[item.voice_type] || item.voice_type;
    if (label) {
      speakerBadge.textContent = label;
      speakerBadge.style.display = 'inline-block';
    } else {
      speakerBadge.style.display = 'none';
    }
  }

  function getVoiceRecommendation(currentItem, items) {
    if (!currentItem || !currentItem.has_speaker || !currentItem.voice_type) return '';
    var otherTypes = (items || []).filter(function(item) {
      return item.has_speaker && item.voice_type && item.voice_type !== currentItem.voice_type;
    });
    if (otherTypes.length === 0) return '';

    var nextType = otherTypes[Math.floor(Math.random() * otherTypes.length)].voice_type;
    var label = voiceTypeLabels[nextType] || nextType;
    return 'Try a ' + label + ' voice next.';
  }

  function saveScenarioProgress() {
    localStorage.setItem(SCENARIO_PROGRESS_KEY, JSON.stringify(scenarioProgress));
  }

  function getScenarioProgress(id) {
    return scenarioProgress[id] || 'not_started';
  }

  function setScenarioProgress(id, status) {
    scenarioProgress[id] = status;
    saveScenarioProgress();
  }

  function renderPhraseCards(items) {
    return items.map(function(item) {
      return '<div class="phrase-card">' +
        '<div class="phrase-lv">' + escapeHtml(item.lv) + '</div>' +
        '<div class="phrase-en">' + escapeHtml(item.en) + '</div>' +
        '<div class="phrase-context">' + escapeHtml(item.context || '') + '</div>' +
        '</div>';
    }).join('');
  }

  function renderLivingMenu(filter) {
    if (!menu) return;
    menu.textContent = '';

    var backButton = document.createElement('button');
    backButton.type = 'button';
    backButton.className = 'mode-toggle';
    backButton.textContent = 'Back to library';
    backButton.addEventListener('click', function() {
      currentMode = 'library';
      localStorage.setItem(MODE_KEY, currentMode);
      window.location.reload();
    });
    menu.appendChild(backButton);

    var filterContainer = document.createElement('div');
    filterContainer.className = 'filter-container';
    var select = document.createElement('select');
    select.className = 'form-select';
    select.innerHTML = '<option value="">All real-life topics</option>' +
      Object.keys(categoryFilters).map(function(key) {
        return '<option value="' + key + '">' + categoryFilters[key] + '</option>';
      }).join('');
    select.value = filter || '';
    select.addEventListener('change', function(event) {
      renderLivingMenu(event.target.value);
    });
    filterContainer.appendChild(select);
    menu.appendChild(filterContainer);

    var list = document.createElement('div');
    list.className = 'scenario-list item-list';
    scenarios
      .filter(function(scenario) { return !filter || scenario.category === filter; })
      .forEach(function(scenario) {
        var progress = getScenarioProgress(scenario.id);
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'scenario-item audio-item ' + progress;
        button.innerHTML = '<span class="progress-dot ' + progress + '"></span>' +
          '<span>' + escapeHtml(scenario.title) + '</span>' +
          '<small>' + escapeHtml(categoryFilters[scenario.category] || scenario.category) + '</small>';
        button.addEventListener('click', function() {
          renderScenario(scenario);
        });
        list.appendChild(button);
      });
    menu.appendChild(list);
  }

  function renderLivingHome() {
    var reader = document.querySelector('.reader');
    if (!reader) return;
    var practiced = Object.keys(scenarioProgress).filter(function(key) {
      return scenarioProgress[key] !== 'not_started';
    }).length;
    var confident = Object.keys(scenarioProgress).filter(function(key) {
      return scenarioProgress[key] === 'confident';
    }).length;

    reader.innerHTML =
      '<section class="living-hero hero">' +
        '<div><p class="eyebrow">Praktiskais modulis</p><h2>Dzivo Latvija</h2>' +
        '<p>Practical listening scenarios for everyday life in Latvia.</p></div>' +
        '<span class="badge badge-muted">A2 Level</span>' +
      '</section>' +
      '<section class="living-intro">' +
        '<div class="intro-card"><h3>Scenarios</h3><p>Choose a topic from the sidebar to practice realistic phrases, vocabulary, and clarification requests.</p></div>' +
        '<div class="intro-card"><h3>Your progress</h3><div class="progress-stats">' +
          '<div class="stat"><span class="stat-num">' + practiced + '</span><span class="stat-label">Practiced</span></div>' +
          '<div class="stat"><span class="stat-num">' + confident + '</span><span class="stat-label">Confident</span></div>' +
        '</div></div>' +
      '</section>' +
      '<section class="scenario-grid">' +
        scenarios.map(function(scenario) {
          var progress = getScenarioProgress(scenario.id);
          return '<button type="button" class="scenario-card ' + progress + '" data-scenario-id="' + scenario.id + '">' +
            '<span class="category-tag">' + escapeHtml(categoryFilters[scenario.category] || scenario.category) + '</span>' +
            '<h4>' + escapeHtml(scenario.title) + '</h4>' +
            '<p>' + escapeHtml(scenario.description) + '</p>' +
            '<div class="card-footer"><span class="progress-status">' + progress.replace('_', ' ') + '</span></div>' +
          '</button>';
        }).join('') +
      '</section>';

    reader.querySelectorAll('.scenario-card').forEach(function(card) {
      card.addEventListener('click', function() {
        var scenario = scenarios.find(function(item) { return item.id === card.getAttribute('data-scenario-id'); });
        if (scenario) renderScenario(scenario);
      });
    });
  }

  function renderScenario(scenario) {
    var reader = document.querySelector('.reader');
    if (!reader) return;
    var progress = getScenarioProgress(scenario.id);
    reader.innerHTML =
      '<section class="scenario-hero">' +
        '<div class="scenario-header"><span class="category-badge">' + escapeHtml(categoryFilters[scenario.category] || scenario.category) + '</span>' +
        '<h2>' + escapeHtml(scenario.title) + '</h2><p class="scenario-subtitle">' + escapeHtml(scenario.description) + '</p></div>' +
        '<div class="progress-selector">' +
          '<button class="progress-btn ' + (progress === 'not_started' ? 'active' : '') + '" data-progress="not_started" type="button">Not started</button>' +
          '<button class="progress-btn ' + (progress === 'practiced' ? 'active' : '') + '" data-progress="practiced" type="button">Practiced</button>' +
          '<button class="progress-btn ' + (progress === 'confident' ? 'active' : '') + '" data-progress="confident" type="button">Confident</button>' +
        '</div>' +
      '</section>' +
      '<section class="scenario-section vocabulary-section"><h3>Vocabulary</h3><div class="vocabulary-list">' +
        scenario.vocabulary.map(function(word) { return '<span class="vocab-tag">' + escapeHtml(word) + '</span>'; }).join('') +
      '</div></section>' +
      '<section class="scenario-section phrases-section"><h3>Phrases</h3><div class="phrases-grid">' + renderPhraseCards(scenario.phrases) + '</div></section>' +
      '<section class="scenario-section repeat-section"><h3>Please repeat - mini practice</h3><div class="phrases-grid repeat-phrases">' + renderPhraseCards(askToRepeatPhrases) + '</div></section>' +
      '<section class="scenario-section checklist-section"><h3>Confidence checklist</h3><ul class="checklist">' +
        '<li>I can understand a greeting.</li><li>I can identify time, date, or place.</li><li>I can ask someone to repeat.</li><li>I can answer with a short sentence.</li>' +
      '</ul></section>' +
      '<button class="back-to-scenarios-btn" type="button">Back to scenarios</button>';

    reader.querySelectorAll('.progress-btn').forEach(function(button) {
      button.addEventListener('click', function() {
        setScenarioProgress(scenario.id, button.getAttribute('data-progress'));
        renderLivingMenu();
        renderScenario(scenario);
      });
    });
    var back = reader.querySelector('.back-to-scenarios-btn');
    if (back) back.addEventListener('click', renderLivingHome);
  }

  function enterLivingMode() {
    currentMode = 'living';
    localStorage.setItem(MODE_KEY, currentMode);
    renderLivingMenu();
    renderLivingHome();
  }

  function renderComprehensionMeter(text) {
    if (!compMeterCard || !window.ComprehensionMeter || !text || !text.trim()) {
      if (compMeterCard) compMeterCard.hidden = true;
      return;
    }

    compMeterCard.hidden = false;
    var stats = ComprehensionMeter.computeLessonStats(text);
    var result = ComprehensionMeter.getComprehensionLabel(stats.comprehensionPct);

    if (compBarFill) {
      compBarFill.style.width = stats.comprehensionPct + '%';
      compBarFill.className = 'comp-bar-fill comp-bar-' + result.key;
    }
    if (compPct) compPct.textContent = 'You may understand ~' + stats.comprehensionPct + '%';
    if (compLabel) {
      compLabel.textContent = result.label;
      compLabel.className = 'comp-label comp-label-' + result.key;
    }
    if (compEstimateNote) {
      compEstimateNote.textContent = stats.isEstimate
        ? 'Rough estimate - no vocabulary saved yet'
        : 'Estimate based on your saved words';
    }
    if (statTotal) statTotal.textContent = stats.totalWords;
    if (statUnique) statUnique.textContent = stats.uniqueWords;
    if (statUnknown) statUnknown.textContent = stats.unknownUniqueWords + ' unknown';

    if (!unknownWordList) return;
    unknownWordList.textContent = '';
    if (stats.topUnknownWords.length === 0) {
      var empty = document.createElement('p');
      empty.className = 'unknown-empty';
      empty.textContent = 'Great - no unknown words detected!';
      unknownWordList.appendChild(empty);
      return;
    }

    stats.topUnknownWords.forEach(function(item) {
      var tag = document.createElement('button');
      tag.type = 'button';
      tag.className = 'unknown-word-tag';
      tag.textContent = item.word + (item.count > 1 ? ' (' + item.count + ')' : '');

      var removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'unknown-word-remove';
      removeBtn.textContent = '✓';
      removeBtn.title = 'Mark as known';

      function markKnown() {
        ComprehensionMeter.saveKnownWord(item.word, 'manual');
        renderComprehensionMeter(text);
        applyCombinedFilters();
      }

      tag.addEventListener('click', markKnown);
      removeBtn.addEventListener('click', markKnown);

      var wrap = document.createElement('span');
      wrap.className = 'unknown-word-wrap';
      wrap.append(tag, removeBtn);
      unknownWordList.appendChild(wrap);
    });
  }

  function filterByComprehension(items) {
    if (activeCompFilter === 'all' || !window.ComprehensionMeter) return items;
    return ComprehensionMeter.filterCatalogByLabel(items, activeCompFilter);
  }

  function filterBySpeakingStyle(items) {
    var styleValue = styleFilter ? styleFilter.value : '';
    if (!styleValue) return items;
    return items.filter(function(item) {
      return getSpeakingStyle(item) === styleValue;
    });
  }

  function filterByCategory(items) {
    var categoryValue = categoryFilter ? categoryFilter.value : '';
    if (!categoryValue || !window.CategoryManager) return items;
    return CategoryManager.filterByCategory(items, categoryValue);
  }

  function applyCombinedFilters() {
    var query = search ? search.value.trim() : '';
    State.filtered = filterByCategory(filterBySpeakingStyle(filterByComprehension(applyFilter(State.catalog, query))));
    State.selectedIndex = State.filtered.length ? 0 : -1;
    Renderer.renderMenu(
      State.filtered,
      State.selectedIndex,
      ProgressTracker ? ProgressTracker.getCompleted() : {}
    );
    if (State.filtered.length) {
      Renderer.selectItem(0);
    } else {
      if (compMeterCard) compMeterCard.hidden = true;
      displaySpeakerBadge(null);
      if (voiceRecommendation) voiceRecommendation.textContent = '';
    }
  }

  function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
  }

  function parseTranscriptToSentences(text) {
    if (!text) return [];
    return String(text)
      .split(/(?<=[.!?])\s+/)
      .map(function(sentence) { return sentence.trim(); })
      .filter(function(sentence) { return sentence.length > 0; });
  }

  function renderTranscriptWithClickableSentences(text) {
    var sentences = parseTranscriptToSentences(text);
    if (sentences.length === 0) return escapeHtml(text || '');
    return sentences.map(function(sentence, index) {
      return '<span class="sentence-block" data-sentence="' + index + '" title="Click for AI explanation">' +
        escapeHtml(sentence) +
        '</span>';
    }).join(' ');
  }

  function openAIPanel() {
    if (!aiPanel || !aiOverlay) return;
    aiPanel.classList.add('open');
    aiPanel.setAttribute('aria-hidden', 'false');
    aiOverlay.hidden = false;
  }

  function closeAIPanel() {
    if (!aiPanel || !aiOverlay) return;
    aiPanel.classList.remove('open');
    aiPanel.setAttribute('aria-hidden', 'true');
    aiOverlay.hidden = true;
  }

  function setAILoading(isLoading) {
    if (aiLoading) aiLoading.hidden = !isLoading;
    if (aiError) aiError.hidden = true;
    if (isLoading && aiPanelContent) aiPanelContent.textContent = '';
  }

  function displayExplanation(explanation) {
    if (!aiPanelContent) return;
    setAILoading(false);

    var html = '<div class="explanation-section"><h4>Natural Translation</h4><p>' +
      escapeHtml(explanation.naturalTranslation || '') +
      '</p></div>';

    if (explanation.literalTranslation && explanation.literalTranslation !== explanation.naturalTranslation) {
      html += '<div class="explanation-section"><h4>Word-by-Word</h4><p>' +
        escapeHtml(explanation.literalTranslation) +
        '</p></div>';
    }

    if (explanation.vocabulary && explanation.vocabulary.length > 0) {
      html += '<div class="explanation-section"><h4>Key Vocabulary</h4>';
      explanation.vocabulary.forEach(function(item) {
        html += '<div class="vocab-item"><span class="vocab-word">' + escapeHtml(item.word) + '</span>' +
          '<span class="vocab-pos">' + escapeHtml(item.pos || '') + '</span>' +
          '<div class="vocab-meaning">' + escapeHtml(item.meaning || '') + '</div>' +
          (item.example ? '<div class="vocab-example">' + escapeHtml(item.example) + '</div>' : '') +
          '</div>';
      });
      html += '</div>';
    }

    if (explanation.grammarNotes && explanation.grammarNotes.length > 0) {
      html += '<div class="explanation-section"><h4>Grammar Notes</h4>';
      explanation.grammarNotes.forEach(function(note) {
        html += '<div class="grammar-note"><p>' + escapeHtml(note) + '</p></div>';
      });
      html += '</div>';
    }

    aiPanelContent.innerHTML = html;
  }

  function fetchExplanation(sentence) {
    if (!aiService) return;
    currentExplanationSentence = sentence;
    setAILoading(true);

    var item = State.filtered[State.selectedIndex];
    var lessonId = item ? item.id : 'default';
    aiService.setLessonId(lessonId);

    aiService.explainSentence(sentence, { lessonId: lessonId })
      .then(displayExplanation)
      .catch(function(error) {
        console.error('AI explanation error:', error);
        if (aiLoading) aiLoading.hidden = true;
        if (aiError) aiError.hidden = false;
      });
  }

  // ---------------------------------------------------------------------------
  // Renderer — builds and updates DOM for menu, hero, and panels
  // ---------------------------------------------------------------------------
  var Renderer = {
    renderMenu: function(filtered, selectedIndex, completed) {
      completed = completed || {};
      menu.textContent = '';
      if (currentMode === 'living') {
        renderLivingMenu();
        return;
      }
      var levels = ['A1', 'A2'];
      for (var li = 0; li < levels.length; li++) {
        var level = levels[li];
        var items = filtered.filter(function(item) { return item.level === level; });
        var section = document.createElement('section');
        section.className = 'level-section';

        var toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.className = 'level-toggle';
        toggle.setAttribute('aria-expanded', 'true');
        toggle.textContent = (levelLabels[level] || level) + ' (' + items.length + ')';
        var plus = document.createElement('span');
        plus.textContent = '−';
        toggle.appendChild(plus);

        var list = document.createElement('div');
        list.className = 'item-list';

        for (var ii = 0; ii < items.length; ii++) {
          (function(item) {
            var button = document.createElement('button');
            button.type = 'button';
            button.className = 'audio-item';
            button.setAttribute('data-lesson-id', item.id || '');

            // Apply active class to the selected item only
            if (filtered[selectedIndex] && filtered[selectedIndex].id === item.id) {
              button.classList.add('active');
            }

            // Apply completed class if lesson is in completed map
            if (completed[item.id] === true) {
              button.classList.add('completed');
            }

            button.addEventListener('click', function() {
              var newIndex = filtered.findIndex(function(candidate) { return candidate.id === item.id; });
              Renderer.selectItem(newIndex);
            });

            var playIcon = document.createElement('span');
            playIcon.className = 'play-icon';
            playIcon.setAttribute('aria-hidden', 'true');
            playIcon.textContent = '▶';

            var lessonTitle = document.createElement('span');
            lessonTitle.className = 'lesson-title';
            lessonTitle.textContent = item.title || item.original_filename || 'Audio';

            var lessonStatus = document.createElement('span');
            lessonStatus.className = 'lesson-status';
            lessonStatus.textContent = item.status || 'unknown';

            var completionDot = document.createElement('span');
            completionDot.className = 'completion-dot';
            completionDot.setAttribute('aria-hidden', 'true');

            button.append(playIcon, lessonTitle, lessonStatus, completionDot);
            list.appendChild(button);
          })(items[ii]);
        }

        // Level-toggle collapse/expand behavior
        (function(toggleBtn, plusSpan, listEl) {
          toggleBtn.addEventListener('click', function() {
            var expanded = toggleBtn.getAttribute('aria-expanded') === 'true';
            toggleBtn.setAttribute('aria-expanded', String(!expanded));
            plusSpan.textContent = expanded ? '+' : '−';
            listEl.hidden = expanded;
          });
        })(toggle, plus, list);

        section.append(toggle, list);
        menu.appendChild(section);
      }

      // Inject .search-empty paragraph when filtered is empty
      if (filtered.length === 0) {
        var emptyP = document.createElement('p');
        emptyP.className = 'search-empty';
        emptyP.textContent = 'No lessons match your search.';
        menu.appendChild(emptyP);
      }
    },

    selectItem: function(index) {
      if (index < 0 || index >= State.filtered.length) return;
      State.selectedIndex = index;
      var item = State.filtered[index];

      // Show hero-content, hide hero-empty
      var heroContent = document.getElementById('hero-content');
      var heroEmpty = document.getElementById('hero-empty');
      if (heroContent) heroContent.hidden = false;
      if (heroEmpty) heroEmpty.hidden = true;

      // Populate title, subtitle, statusBadge
      if (title) title.textContent = item.title || item.original_filename || 'Untitled audio';
      if (subtitle) subtitle.textContent = (levelLabels[item.level] || item.level) + ' · ' + (item.original_filename || '');
      if (statusBadge) {
        statusBadge.textContent = item.status || 'unknown';
        statusBadge.className = badgeClass(item.status);
      }
      displaySpeakerBadge(item);
      if (voiceRecommendation) {
        voiceRecommendation.textContent = getVoiceRecommendation(item, State.catalog);
      }

      // Show panel skeletons then immediately populate (synchronous)
      SkeletonHelper.showPanels();

      // Populate panels using resolveText() from lib.js
      if (lvText) lvText.textContent = resolveText(item.lv_text, 'lv');
      if (enText) enText.textContent = resolveText(item.en_text, 'en');

      SkeletonHelper.hidePanels();

      // Show/hide Markdown links via hidden attribute
      if (lvLink) {
        if (item.lv_markdown_url) {
          lvLink.href = item.lv_markdown_url;
          lvLink.hidden = false;
        } else {
          lvLink.hidden = true;
        }
      }
      if (enLink) {
        if (item.en_markdown_url) {
          enLink.href = item.en_markdown_url;
          enLink.hidden = false;
        } else {
          enLink.hidden = true;
        }
      }

      // Set audio src
      if (audio) {
        audio.preload = 'metadata';
        audio.src = audioSource.getAudioUrl(item.audio_url || '');
      }

      AudioController.loadWaveform(item.waveform_url || audioSource.getWaveformUrl(item.audio_url || ''));

      // Update prev/next button disabled state
      if (previousButton) previousButton.disabled = State.selectedIndex <= 0;
      if (nextButton) nextButton.disabled = State.selectedIndex >= State.filtered.length - 1;

      // Re-render menu to reflect new active state
      Renderer.renderMenu(
        State.filtered,
        State.selectedIndex,
        ProgressTracker ? ProgressTracker.getCompleted() : {}
      );
      renderComprehensionMeter(item.lv_text || '');
      if (lvText) lvText.innerHTML = renderTranscriptWithClickableSentences(item.lv_text || '');
    },

    renderEmptyState: function(type) {
      if (type === 'catalog-error') {
        // Hide .player-card and both .text-panel elements
        var playerCard = document.querySelector('.player-card');
        if (playerCard) playerCard.hidden = true;
        var textPanels = document.querySelectorAll('.text-panel');
        textPanels.forEach(function(el) { el.hidden = true; });

        // Show error message in #hero-empty
        var heroEmpty = document.getElementById('hero-empty');
        var heroContent = document.getElementById('hero-content');
        if (heroContent) heroContent.hidden = true;
        if (heroEmpty) {
          heroEmpty.hidden = false;
          // Update the heading to show the error message
          var heading = heroEmpty.querySelector('h2');
          if (heading) heading.textContent = 'Catalog not ready. Run the build script after processing audio.';
          var para = heroEmpty.querySelector('p');
          if (para) para.hidden = true;
          var ctas = heroEmpty.querySelector('.hero-ctas');
          if (ctas) ctas.hidden = true;
        }
      }
    }
  };

  // ---------------------------------------------------------------------------
  // AudioController — custom audio player, waveform, and sticky player
  // ---------------------------------------------------------------------------
  var AudioController = {
    init: function() {
      var playPauseBtn = document.getElementById('play-pause');
      var seekBar = document.getElementById('seek-bar');
      var audioErrorEl = document.getElementById('audio-error');
      var playbackStatus = document.getElementById('playback-status');

      if (playPauseBtn) {
        playPauseBtn.addEventListener('click', function() {
          if (audio.paused) {
            AudioController.play();
          } else {
            AudioController.pause();
          }
        });
      }

      if (seekBar) {
        seekBar.addEventListener('input', function() {
          AudioController.seek(seekBar.value / 100);
        });
        seekBar.addEventListener('keydown', function(e) {
          if (e.key === 'ArrowRight') {
            e.preventDefault();
            audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 1);
          } else if (e.key === 'ArrowLeft') {
            e.preventDefault();
            audio.currentTime = Math.max(0, audio.currentTime - 1);
          }
        });
      }

      if (audio) {
        audio.addEventListener('timeupdate', function() {
          AudioController.updateUI();
        });
        audio.addEventListener('ended', function() {
          State.isPlaying = false;
          var item = State.filtered[State.selectedIndex];
          if (item) {
            analyticsTracker.track(Analytics.EventTypes.LESSON_COMPLETE, {
              lesson_id: item.id,
              filename: item.original_filename
            });
          }
          AudioController.updateUI();
          if (playbackStatus) playbackStatus.textContent = 'Track ended';
        });
        audio.addEventListener('error', function() {
          if (audioErrorEl) audioErrorEl.hidden = false;
          if (playPauseBtn) playPauseBtn.disabled = true;
          if (playbackStatus) playbackStatus.textContent = 'Audio failed to load.';
        });
      }

      AudioController.initStickyPlayer();
    },

    play: function() {
      if (audio) {
        audio.play().catch(function() {});
        State.isPlaying = true;
        AudioController.updateUI();
        var playbackStatus = document.getElementById('playback-status');
        if (playbackStatus) playbackStatus.textContent = 'Playing';
      }
    },

    pause: function() {
      if (audio) {
        audio.pause();
        State.isPlaying = false;
        AudioController.updateUI();
        var playbackStatus = document.getElementById('playback-status');
        if (playbackStatus) playbackStatus.textContent = 'Paused';
      }
    },

    seek: function(ratio) {
      if (audio && audio.duration) {
        audio.currentTime = ratio * audio.duration;
      }
    },

    updateUI: function() {
      var playPauseBtn = document.getElementById('play-pause');
      var seekBar = document.getElementById('seek-bar');
      var timeDisplay = document.getElementById('time-display');
      var stickyPlayPause = document.getElementById('sticky-play-pause');
      var stickySeek = document.getElementById('sticky-seek');
      var stickyTime = document.getElementById('sticky-time');

      var currentTime = audio ? audio.currentTime : 0;
      var duration = audio ? (audio.duration || 0) : 0;
      var progress = duration > 0 ? (currentTime / duration) * 100 : 0;
      var paused = audio ? audio.paused : true;

      State.currentTime = currentTime;
      State.duration = duration;

      if (seekBar) seekBar.value = progress;
      if (timeDisplay) timeDisplay.textContent = formatTime(currentTime) + ' / ' + formatTime(duration);
      if (playPauseBtn) {
        playPauseBtn.setAttribute('aria-label', paused ? 'Play' : 'Pause');
        var icon = playPauseBtn.querySelector('.icon-play');
        if (icon) icon.textContent = paused ? '▶' : '⏸';
      }

      // Mirror to sticky player
      if (stickySeek) stickySeek.value = progress;
      if (stickyTime) stickyTime.textContent = formatTime(currentTime);
      if (stickyPlayPause) {
        stickyPlayPause.setAttribute('aria-label', paused ? 'Play' : 'Pause');
        var stickyIcon = stickyPlayPause.querySelector('.icon-play');
        if (stickyIcon) stickyIcon.textContent = paused ? '▶' : '⏸';
      }
    },

    loadWaveform: function(url) {
      if (!url) return;
      var canvas = document.getElementById('waveform-canvas');
      if (!canvas) return;
      fetch(url)
        .then(function(r) { return r.ok ? r.json() : null; })
        .then(function(data) {
          if (!Array.isArray(data) || data.length === 0) return;
          State.waveformData = data;
          var ctx = canvas.getContext('2d');
          var w = canvas.offsetWidth || canvas.width;
          var h = canvas.offsetHeight || canvas.height;
          canvas.width = w;
          canvas.height = h;
          ctx.clearRect(0, 0, w, h);
          ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--color-accent').trim() || '#d60a4f';
          var barWidth = Math.max(1, Math.floor(w / data.length));
          for (var i = 0; i < data.length; i++) {
            var barH = Math.round(data[i] * h);
            ctx.fillRect(i * barWidth, h - barH, barWidth - 1, barH);
          }
        })
        .catch(function(e) { console.warn('Waveform load failed:', e); });
    },

    initStickyPlayer: function() {
      var stickyPlayer = document.getElementById('sticky-player');
      var playerCard = document.querySelector('.player-card');
      var stickyPlayPause = document.getElementById('sticky-play-pause');
      var stickySeek = document.getElementById('sticky-seek');

      if (!stickyPlayer || !playerCard) return;

      // Wire sticky controls
      if (stickyPlayPause) {
        stickyPlayPause.addEventListener('click', function() {
          if (audio && audio.paused) {
            AudioController.play();
          } else {
            AudioController.pause();
          }
        });
      }
      if (stickySeek) {
        stickySeek.addEventListener('input', function() {
          AudioController.seek(stickySeek.value / 100);
        });
      }

      // IntersectionObserver: show sticky player when player-card is out of view on mobile
      if ('IntersectionObserver' in window) {
        var observer = new IntersectionObserver(function(entries) {
          var isMobile = window.innerWidth <= 768;
          entries.forEach(function(entry) {
            if (isMobile && !entry.isIntersecting) {
              stickyPlayer.hidden = false;
            } else {
              stickyPlayer.hidden = true;
            }
          });
        }, { threshold: 0 });
        observer.observe(playerCard);
      }
    }
  };

  // ---------------------------------------------------------------------------
  // SearchHandler — debounced search input handling
  // ---------------------------------------------------------------------------
  var SearchHandler = {
    _timer: null,
    init: function() {
      var searchInput = document.getElementById('search');
      if (!searchInput) return;
      searchInput.addEventListener('input', function() {
        clearTimeout(SearchHandler._timer);
        SearchHandler._timer = setTimeout(function() {
          applyCombinedFilters();
        }, 300);
      });
    }
  };

  // ---------------------------------------------------------------------------
  // Event wiring
  // ---------------------------------------------------------------------------
  previousButton.addEventListener('click', function () { Renderer.selectItem(State.selectedIndex - 1); });
  nextButton.addEventListener('click', function () { Renderer.selectItem(State.selectedIndex + 1); });
  SearchHandler.init();
  if (styleFilter) {
    styleFilter.addEventListener('change', applyCombinedFilters);
  }
  if (categoryFilter) {
    categoryFilter.addEventListener('change', function() {
      updateURLWithCategory(categoryFilter.value);
      applyCombinedFilters();
    });
  }

  var brandSection = document.querySelector('.brand');
  if (brandSection) {
    var modeButton = document.createElement('button');
    modeButton.type = 'button';
    modeButton.className = 'mode-switch-btn';
    modeButton.textContent = currentMode === 'living' ? 'Library' : 'Dzivo Latvija';
    modeButton.addEventListener('click', function() {
      if (currentMode === 'living') {
        currentMode = 'library';
        localStorage.setItem(MODE_KEY, currentMode);
        window.location.reload();
      } else {
        modeButton.textContent = 'Library';
        enterLivingMode();
      }
    });
    brandSection.appendChild(modeButton);
  }

  // Wire theme toggle
  var themeToggleBtn = document.getElementById('theme-toggle');
  if (themeToggleBtn) {
    themeToggleBtn.addEventListener('click', function () {
      ThemeManager.toggle();
    });
  }

  document.querySelectorAll('.comp-filter-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      document.querySelectorAll('.comp-filter-btn').forEach(function(other) {
        other.classList.remove('active');
      });
      btn.classList.add('active');
      activeCompFilter = btn.getAttribute('data-filter') || 'all';
      applyCombinedFilters();
    });
  });

  if (closeAIPanelBtn) closeAIPanelBtn.addEventListener('click', closeAIPanel);
  if (aiOverlay) aiOverlay.addEventListener('click', closeAIPanel);
  if (aiModeToggle && aiService) {
    aiModeToggle.addEventListener('change', function(event) {
      aiService.setExplanationMode(event.target.checked ? 'detailed' : 'simple');
      if (currentExplanationSentence) fetchExplanation(currentExplanationSentence);
    });
  }
  if (retryBtn) {
    retryBtn.addEventListener('click', function() {
      if (currentExplanationSentence) fetchExplanation(currentExplanationSentence);
    });
  }
  if (lvText) {
    lvText.addEventListener('click', function(event) {
      var target = event.target;
      if (!target || !target.classList || !target.classList.contains('sentence-block')) return;
      openAIPanel();
      fetchExplanation(target.textContent || '');
    });
  }

  AudioController.init();

  // ---------------------------------------------------------------------------
  // Category population
  // ---------------------------------------------------------------------------
  function populateCategoryFilter() {
    if (!categoryFilter || !window.CategoryManager) return;
    var categories = CategoryManager.getCategoriesWithCounts(State.catalog);
    var currentValue = categoryFilter.value;
    categoryFilter.innerHTML = '<option value="">All categories</option>';
    categories.forEach(function(cat) {
      if (cat.id === 'uncategorized' && cat.count === 0) return;
      var option = document.createElement('option');
      option.value = cat.id;
      option.textContent = cat.icon + ' ' + cat.title + ' (' + cat.count + ')';
      categoryFilter.appendChild(option);
    });
    var urlParams = new URLSearchParams(window.location.search);
    var urlCategory = urlParams.get('category');
    if (urlCategory) {
      categoryFilter.value = urlCategory;
    } else if (currentValue) {
      categoryFilter.value = currentValue;
    }
  }

  function updateURLWithCategory(categoryId) {
    var url = new URL(window.location.href);
    if (categoryId) {
      url.searchParams.set('category', categoryId);
    } else {
      url.searchParams.delete('category');
    }
    window.history.replaceState({}, '', url);
  }

  function updateCategoryLanding() {
    var heroEmpty = document.getElementById('hero-empty');
    var categoryLanding = document.getElementById('category-landing');
    var categoryCards = document.getElementById('category-cards');
    var heroCtas = document.getElementById('hero-ctas');
    if (!heroEmpty || !categoryLanding || !categoryCards) return;
    if (State.selectedIndex === -1 && window.CategoryManager && State.catalog.length > 0) {
      var categories = CategoryManager.getCategoriesWithCounts(State.catalog).filter(function(c) { return c.id !== 'uncategorized' && c.count > 0; });
      categoryCards.innerHTML = categories.map(function(cat) {
        return '<div class="category-card" data-category="' + cat.id + '">' +
          '<span class="category-icon">' + cat.icon + '</span>' +
          '<span class="category-title">' + cat.title + '</span>' +
          '<span class="category-count">' + cat.count + ' lessons</span>' +
          '<span class="category-desc">' + cat.description + '</span>' +
          '</div>';
      }).join('');
      categoryCards.querySelectorAll('.category-card').forEach(function(card) {
        card.addEventListener('click', function() {
          if (categoryFilter) {
            categoryFilter.value = card.getAttribute('data-category');
            applyCombinedFilters();
          }
        });
      });
      categoryLanding.hidden = false;
      if (heroCtas) heroCtas.hidden = true;
    } else {
      categoryLanding.hidden = true;
      if (heroCtas) heroCtas.hidden = false;
    }
  }

  var btnBrowseCategory = document.getElementById('btn-browse-category');
  if (btnBrowseCategory) {
    btnBrowseCategory.addEventListener('click', function() {
      updateCategoryLanding();
    });
  }

  // ---------------------------------------------------------------------------
  // Catalog fetch
  // ---------------------------------------------------------------------------
  SkeletonHelper.showSidebar();
  fetch('catalog.json', { cache: 'no-store' })
    .then(function (response) {
      if (!response.ok) throw new Error('Catalog request failed: ' + response.status);
      return response.json();
    })
    .then(function (items) {
      var validation = LessonValidation.validateCatalog(items, isDev);
      if (!validation.valid) {
        console.warn('[Catalog] Lesson data validation failed:', validation.errors);
      }
      State.catalog = Array.isArray(items) ? items : [];
      State.filtered = filterByComprehension(State.catalog.slice());
      SkeletonHelper.hideSidebar();
      populateCategoryFilter();
      updateCategoryLanding();
      if (currentMode === 'living') {
        enterLivingMode();
        return;
      }
      Renderer.renderMenu(
        State.filtered,
        State.selectedIndex,
        ProgressTracker ? ProgressTracker.getCompleted() : {}
      );
      if (State.filtered.length) {
        Renderer.selectItem(0);
      }
    })
    .catch(function (error) {
      console.error(error);
      State.filtered = [];
      Renderer.renderEmptyState('catalog-error');
    });

  // ---------------------------------------------------------------------------
  // Expose test hooks
  // ---------------------------------------------------------------------------
  window.__lll = {
    selectItem: function(index) { Renderer.selectItem(index); },
    State: State,
    ProgressTracker: ProgressTracker,
    ThemeManager: ThemeManager,
    Analytics: analyticsTracker
  };
  window.analytics = analyticsTracker;
})();
