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
  var previousButton = document.querySelector('#prev');
  var nextButton = document.querySelector('#next');
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

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------
  function badgeClass(status) {
    if (status === 'completed') return 'badge badge-completed';
    if (status === 'transcribed only' || status === 'translation failed') return 'badge badge-transcribed';
    if (status === 'failed') return 'badge badge-failed';
    return 'badge badge-muted';
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

  function applyCombinedFilters() {
    var query = search ? search.value.trim() : '';
    State.filtered = filterByComprehension(applyFilter(State.catalog, query));
    State.selectedIndex = State.filtered.length ? 0 : -1;
    Renderer.renderMenu(
      State.filtered,
      State.selectedIndex,
      ProgressTracker ? ProgressTracker.getCompleted() : {}
    );
    if (State.filtered.length) {
      Renderer.selectItem(0);
    } else if (compMeterCard) {
      compMeterCard.hidden = true;
    }
  }

  // ---------------------------------------------------------------------------
  // Renderer — builds and updates DOM for menu, hero, and panels
  // ---------------------------------------------------------------------------
  var Renderer = {
    renderMenu: function(filtered, selectedIndex, completed) {
      completed = completed || {};
      menu.textContent = '';
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

  AudioController.init();

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
