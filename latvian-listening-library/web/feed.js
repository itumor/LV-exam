/* T-035 — TikTok-style vertical listening feed.
 *
 * Layout: one scroll-snap card per clip. Tapping the card (or the play
 * button) starts the audio; when the audio ends the micro-quiz unlocks.
 * Swiping up scrolls to the next card. The next page of clips is
 * prefetched as soon as the learner advances within two cards of the
 * end of the current page.
 *
 * Backend contract:
 *   GET  /api/listening-feed?cursor=...&limit=...
 *     -> { clips: [{id, audio_url, transcript, micro_quiz, ...}], next_cursor }
 *   POST /api/listening-feed/{id}/answer  { quiz_answer_index }
 *     -> { correct, xp_delta, correct_index }
 *
 * The frontend tracks XP locally for instant feedback; the server is the
 * authoritative source of truth and the T-034 XP engine will reconcile
 * the value on the readiness dashboard.
 */
(function () {
  "use strict";

  var FEED_ROOT = document.getElementById("feed");
  var LOADER = document.getElementById("feed-loader");
  var STATUS_EL = document.getElementById("feed-status");
  var XP_EL = document.getElementById("feed-xp");

  if (!FEED_ROOT) {
    return;
  }

  var state = {
    clips: [],
    nextCursor: null,
    fetching: false,
    exhausted: false,
    activeId: null,
    answered: Object.create(null),
    xp: 0,
  };

  var API = {
    feed: function (cursor) {
      var qs = cursor ? "?cursor=" + encodeURIComponent(cursor) : "";
      return fetch("/api/listening-feed" + qs, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      }).then(parseJson);
    },
    answer: function (clipId, idx) {
      return fetch(
        "/api/listening-feed/" + encodeURIComponent(clipId) + "/answer",
        {
          method: "POST",
          credentials: "same-origin",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          body: JSON.stringify({ quiz_answer_index: idx }),
        }
      ).then(parseJson);
    },
  };

  function parseJson(response) {
    if (!response.ok) {
      return response.text().then(function (text) {
        var error;
        try {
          var data = JSON.parse(text);
          error = (data && data.error && data.error.message) || text;
        } catch (e) {
          error = text || response.statusText;
        }
        throw new Error(error || "Request failed");
      });
    }
    return response.json();
  }

  function showStatus(text, ms) {
    STATUS_EL.textContent = text;
    STATUS_EL.dataset.visible = "true";
    if (ms) {
      window.setTimeout(function () {
        if (STATUS_EL.textContent === text) {
          STATUS_EL.dataset.visible = "false";
        }
      }, ms);
    }
  }

  function clearNode(node) {
    while (node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  function showError(message) {
    clearNode(FEED_ROOT);
    var wrap = document.createElement("div");
    wrap.className = "feed-error";
    var heading = document.createElement("h2");
    heading.textContent = "Feed unavailable";
    var detail = document.createElement("p");
    detail.textContent = message || "Could not load the listening feed.";
    var retry = document.createElement("button");
    retry.type = "button";
    retry.textContent = "Try again";
    retry.addEventListener("click", boot);
    wrap.appendChild(heading);
    wrap.appendChild(detail);
    wrap.appendChild(retry);
    FEED_ROOT.appendChild(wrap);
  }

  function showEmpty() {
    clearNode(FEED_ROOT);
    var wrap = document.createElement("div");
    wrap.className = "feed-empty";
    var heading = document.createElement("h2");
    heading.textContent = "No clips yet";
    var detail = document.createElement("p");
    detail.textContent =
      "Check back soon — new Latvian listening clips are published every week.";
    wrap.appendChild(heading);
    wrap.appendChild(detail);
    FEED_ROOT.appendChild(wrap);
  }

  function addXp(delta) {
    state.xp += Number(delta) || 0;
    if (XP_EL) {
      XP_EL.textContent = "XP: " + state.xp;
    }
  }

  // -------------------------------------------------------------------
  // Card rendering
  // -------------------------------------------------------------------

  function buildCard(clip) {
    var card = document.createElement("section");
    card.className = "feed-card";
    card.dataset.clipId = clip.id;
    card.setAttribute("aria-label", clip.title || "Latvian listening clip");

    var progress = document.createElement("div");
    progress.className = "feed-card__progress";
    var progressBar = document.createElement("div");
    progressBar.className = "feed-card__progress-bar";
    progress.appendChild(progressBar);
    card.appendChild(progress);

    var audio = document.createElement("audio");
    audio.preload = "none";
    audio.src = audioSrc(clip.audio_url);
    audio.playsInline = true;
    card.appendChild(audio);

    var inner = document.createElement("div");
    inner.className = "feed-card__inner";

    var meta = document.createElement("div");
    meta.className = "feed-card__meta";
    if (clip.difficulty) {
      meta.appendChild(chip(clip.difficulty));
    }
    if (clip.category) {
      meta.appendChild(chip(clip.category));
    }
    if (typeof clip.duration_seconds === "number") {
      meta.appendChild(chip(clip.duration_seconds + "s"));
    }
    inner.appendChild(meta);

    if (clip.title) {
      var title = document.createElement("h2");
      title.className = "feed-card__title";
      title.textContent = clip.title;
      inner.appendChild(title);
    }

    if (clip.transcript) {
      var transcript = document.createElement("div");
      transcript.className = "feed-card__transcript";
      var lv = document.createElement("p");
      lv.style.margin = "0";
      lv.textContent = clip.transcript;
      transcript.appendChild(lv);
      if (clip.translation) {
        var en = document.createElement("p");
        en.className = "feed-card__translation";
        en.textContent = clip.translation;
        transcript.appendChild(en);
      }
      inner.appendChild(transcript);
    }

    var controls = document.createElement("div");
    controls.className = "feed-card__controls";
    var playBtn = document.createElement("button");
    playBtn.className = "feed-card__play";
    playBtn.type = "button";
    playBtn.setAttribute("aria-label", "Play clip");
    playBtn.dataset.state = "idle";
    playBtn.textContent = "▶";
    controls.appendChild(playBtn);
    var hint = document.createElement("span");
    hint.className = "feed-card__hint";
    hint.textContent = "Tap to listen. Swipe up for the next clip.";
    controls.appendChild(hint);
    inner.appendChild(controls);

    var quiz = buildQuiz(clip);
    inner.appendChild(quiz.root);

    card.appendChild(inner);

    // Wire interactions
    playBtn.addEventListener("click", function (event) {
      event.stopPropagation();
      toggleAudio(audio, playBtn);
    });
    card.addEventListener("click", function () {
      if (audio.paused) {
        toggleAudio(audio, playBtn);
      }
    });
    audio.addEventListener("timeupdate", function () {
      if (audio.duration && isFinite(audio.duration)) {
        var pct = (audio.currentTime / audio.duration) * 100;
        progressBar.style.width = Math.max(0, Math.min(100, pct)) + "%";
      }
    });
    audio.addEventListener("ended", function () {
      playBtn.dataset.state = "idle";
      playBtn.textContent = "↻";
      quiz.unlock();
    });
    audio.addEventListener("pause", function () {
      if (audio.ended) {
        return;
      }
      playBtn.dataset.state = "idle";
      playBtn.textContent = "▶";
    });
    audio.addEventListener("play", function () {
      playBtn.dataset.state = "playing";
      playBtn.textContent = "⏸";
      pauseSiblings(audio);
    });

    card._listeningFeed = {
      audio: audio,
      playBtn: playBtn,
      quiz: quiz,
    };
    return card;
  }

  function audioSrc(url) {
    if (!url) {
      return "";
    }
    if (
      url.indexOf("http://") === 0 ||
      url.indexOf("https://") === 0 ||
      url.indexOf("//") === 0
    ) {
      return url;
    }
    if (url.charAt(0) === "/") {
      return url;
    }
    // Curated clips ship inside latvian-listening-library/web/ — relative
    // URLs are resolved against the document base by the browser.
    return url;
  }

  function chip(label) {
    var el = document.createElement("span");
    el.className = "feed-card__chip";
    el.textContent = String(label);
    return el;
  }

  function buildQuiz(clip) {
    var quiz = document.createElement("aside");
    quiz.className = "feed-quiz";
    quiz.hidden = true;
    quiz.setAttribute("aria-label", "Micro-quiz");

    var prompt = document.createElement("p");
    prompt.className = "feed-quiz__prompt";
    prompt.textContent =
      (clip.micro_quiz && clip.micro_quiz.prompt) || "Did you understand?";
    quiz.appendChild(prompt);

    if (clip.micro_quiz && clip.micro_quiz.prompt_lv) {
      var promptLv = document.createElement("p");
      promptLv.className = "feed-quiz__prompt-lv";
      promptLv.textContent = clip.micro_quiz.prompt_lv;
      quiz.appendChild(promptLv);
    }

    var options = (clip.micro_quiz && clip.micro_quiz.options) || [];
    var list = document.createElement("ul");
    list.className = "feed-quiz__options";

    var buttons = [];
    options.forEach(function (label, idx) {
      var item = document.createElement("li");
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "feed-quiz__btn";
      btn.textContent = label;
      btn.dataset.index = String(idx);
      btn.addEventListener("click", function () {
        if (state.answered[clip.id]) {
          return;
        }
        submitAnswer(clip.id, idx, buttons, resultEl);
      });
      buttons.push(btn);
      item.appendChild(btn);
      list.appendChild(item);
    });
    quiz.appendChild(list);

    var resultEl = document.createElement("div");
    resultEl.className = "feed-quiz__result";
    resultEl.setAttribute("aria-live", "polite");
    quiz.appendChild(resultEl);

    return {
      root: quiz,
      unlock: function () {
        quiz.hidden = false;
      },
      buttons: buttons,
      result: resultEl,
    };
  }

  function submitAnswer(clipId, idx, buttons, resultEl) {
    state.answered[clipId] = true;
    buttons.forEach(function (b) {
      b.disabled = true;
    });
    resultEl.textContent = "Checking...";
    resultEl.dataset.state = "pending";
    API.answer(clipId, idx)
      .then(function (data) {
        var correct = Boolean(data && data.correct);
        var correctIndex =
          data && typeof data.correct_index === "number"
            ? data.correct_index
            : null;
        buttons.forEach(function (b, i) {
          if (i === idx) {
            b.dataset.result = correct ? "correct" : "wrong";
          } else if (!correct && correctIndex !== null && i === correctIndex) {
            b.dataset.result = "reveal";
          }
        });
        if (correct) {
          resultEl.textContent = "+" + (data.xp_delta || 0) + " XP — labi!";
          resultEl.dataset.state = "correct";
        } else {
          resultEl.textContent =
            "+" + (data.xp_delta || 0) + " XP — keep practising.";
          resultEl.dataset.state = "wrong";
        }
        addXp(data.xp_delta || 0);
      })
      .catch(function (error) {
        state.answered[clipId] = false;
        buttons.forEach(function (b) {
          b.disabled = false;
        });
        resultEl.textContent = "Could not save: " + error.message;
        resultEl.dataset.state = "wrong";
      });
  }

  function toggleAudio(audio, btn) {
    if (audio.paused) {
      var playPromise = audio.play();
      if (playPromise && typeof playPromise.then === "function") {
        playPromise.catch(function () {
          btn.dataset.state = "idle";
          btn.textContent = "▶";
        });
      }
    } else {
      audio.pause();
    }
  }

  function pauseSiblings(currentAudio) {
    var audios = FEED_ROOT.querySelectorAll("audio");
    audios.forEach(function (audio) {
      if (audio !== currentAudio && !audio.paused) {
        audio.pause();
      }
    });
  }

  // -------------------------------------------------------------------
  // Pagination
  // -------------------------------------------------------------------

  function fetchPage() {
    if (state.fetching || state.exhausted) {
      return Promise.resolve(null);
    }
    state.fetching = true;
    return API.feed(state.nextCursor)
      .then(function (data) {
        state.fetching = false;
        var clips = (data && data.clips) || [];
        state.nextCursor = (data && data.next_cursor) || null;
        if (!state.nextCursor) {
          state.exhausted = true;
        }
        clips.forEach(function (clip) {
          state.clips.push(clip);
          FEED_ROOT.appendChild(buildCard(clip));
        });
        return clips.length;
      })
      .catch(function (error) {
        state.fetching = false;
        throw error;
      });
  }

  function ensureLookahead() {
    if (state.fetching || state.exhausted) {
      return;
    }
    var cards = FEED_ROOT.querySelectorAll(".feed-card");
    if (!cards.length) {
      return;
    }
    var activeIdx = -1;
    for (var i = 0; i < cards.length; i++) {
      if (cards[i].dataset.clipId === state.activeId) {
        activeIdx = i;
        break;
      }
    }
    if (activeIdx === -1) {
      return;
    }
    if (cards.length - activeIdx <= 2) {
      fetchPage().catch(function (error) {
        showStatus("Could not load more clips: " + error.message, 3500);
      });
    }
  }

  // -------------------------------------------------------------------
  // Active-card observer (autoplays the visible clip)
  // -------------------------------------------------------------------

  var observer = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        var card = entry.target;
        var data = card._listeningFeed;
        if (!data) {
          return;
        }
        if (entry.intersectionRatio >= 0.6) {
          state.activeId = card.dataset.clipId;
          ensureLookahead();
          // Try to autoplay the active clip — browsers may block this
          // without a prior user gesture, so we silently fall back to
          // the tap-to-play UX.
          if (data.audio.paused) {
            var playPromise = data.audio.play();
            if (playPromise && typeof playPromise.catch === "function") {
              playPromise.catch(function () {
                /* autoplay blocked — user must tap */
              });
            }
          }
        } else if (entry.intersectionRatio < 0.2) {
          if (!data.audio.paused) {
            data.audio.pause();
          }
        }
      });
    },
    { root: FEED_ROOT, threshold: [0.2, 0.6] }
  );

  function observeNewCards() {
    var cards = FEED_ROOT.querySelectorAll(".feed-card");
    cards.forEach(function (card) {
      if (card._observed) {
        return;
      }
      card._observed = true;
      observer.observe(card);
    });
  }

  // -------------------------------------------------------------------
  // Bootstrap
  // -------------------------------------------------------------------

  function boot() {
    state.clips = [];
    state.nextCursor = null;
    state.fetching = false;
    state.exhausted = false;
    state.activeId = null;
    state.answered = Object.create(null);
    clearNode(FEED_ROOT);
    var loader = document.createElement("div");
    loader.className = "feed-loader";
    loader.textContent = "Loading feed";
    FEED_ROOT.appendChild(loader);

    fetchPage()
      .then(function () {
        if (loader.parentNode) {
          loader.parentNode.removeChild(loader);
        }
        if (!state.clips.length) {
          showEmpty();
          return;
        }
        observeNewCards();
        // Make the first card the "active" one so the lookahead heuristic
        // kicks in immediately.
        state.activeId = state.clips[0].id;
      })
      .catch(function (error) {
        showError(error.message);
      });

    // After each page fetch, ensure the new cards are observed.
    var mo = new MutationObserver(observeNewCards);
    mo.observe(FEED_ROOT, { childList: true });
  }

  // Pause audio when the tab is hidden — saves bandwidth + battery.
  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      FEED_ROOT.querySelectorAll("audio").forEach(function (audio) {
        if (!audio.paused) {
          audio.pause();
        }
      });
    }
  });

  // Expose a tiny test surface so Playwright (T-002 @smoke tag) can
  // assert state from the browser without monkey-patching internals.
  window.__listeningFeed = {
    getState: function () {
      return {
        clipIds: state.clips.map(function (c) {
          return c.id;
        }),
        activeId: state.activeId,
        xp: state.xp,
        answered: Object.keys(state.answered),
      };
    },
    refresh: boot,
  };

  boot();
})();
