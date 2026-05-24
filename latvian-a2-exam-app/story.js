/*
 * T-050 — Story-mode mission map UI.
 *
 * Vanilla JS, no framework. Talks to the two endpoints shipped by
 * ``server_app/routes/story.py``:
 *
 *   GET  /api/story/state
 *   POST /api/story/<mission_id>/scene/<scene_id>/complete
 *
 * Flow:
 *   1. On load, GET /api/story/state and render:
 *      - summary header (missions completed, XP, streak)
 *      - city markers placed on a stylised Latvia map
 *      - cards listing each mission with status (locked / available /
 *        in_progress / completed)
 *   2. Clicking a mission card opens the scenes panel with one row per
 *      scene; each scene has a "Mark complete" button.
 *   3. Clicking that button POSTs the scene completion. On success we
 *      refresh the state and surface a toast (e.g. "Mission complete!
 *      +50 XP").
 *
 * Defensive: all dynamic content uses textContent (no innerHTML), all
 * mission ids and scene ids are URL-encoded before being pasted into
 * the POST path.
 */

(function () {
  "use strict";

  var state = {
    catalogue: null,
    summary: null,
    activeMissionId: null,
    inflight: false,
  };

  var elements = {
    summary: document.getElementById("story-summary"),
    error: document.getElementById("story-error"),
    map: document.getElementById("story-map"),
    missions: document.getElementById("story-missions"),
    scenePanel: document.getElementById("story-scene-panel"),
    sceneMeta: document.getElementById("story-scene-mission-meta"),
    sceneList: document.getElementById("story-scene-list"),
    toast: document.getElementById("story-toast"),
  };

  // ---- Helpers ----

  function setError(msg) {
    if (!msg) {
      elements.error.hidden = true;
      elements.error.textContent = "";
      return;
    }
    elements.error.hidden = false;
    elements.error.textContent = msg;
  }

  function clearChildren(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }

  function showToast(message, durationMs) {
    if (!elements.toast) return;
    elements.toast.textContent = message;
    elements.toast.classList.add("show");
    setTimeout(function () {
      elements.toast.classList.remove("show");
    }, durationMs || 3200);
  }

  // ---- API ----

  function fetchState() {
    return fetch("/api/story/state", {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    }).then(function (resp) {
      if (resp.status === 401) {
        window.location.href = "./index.html";
        throw new Error("auth_required");
      }
      if (!resp.ok) {
        return resp.json().catch(function () { return {}; }).then(function (body) {
          throw new Error(body.error || "story_state_failed");
        });
      }
      return resp.json();
    });
  }

  function completeScene(missionId, sceneId) {
    var url =
      "/api/story/" +
      encodeURIComponent(missionId) +
      "/scene/" +
      encodeURIComponent(sceneId) +
      "/complete";
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: "{}",
    }).then(function (resp) {
      if (resp.status === 401) {
        window.location.href = "./index.html";
        throw new Error("auth_required");
      }
      if (!resp.ok) {
        return resp.json().catch(function () { return {}; }).then(function (body) {
          var err = new Error(body.error || "story_complete_failed");
          err.status = resp.status;
          err.detail = body.detail || body.message || "";
          throw err;
        });
      }
      return resp.json();
    });
  }

  // ---- Rendering ----

  function renderSummary(summary) {
    clearChildren(elements.summary);
    function pill(label, value) {
      var span = document.createElement("span");
      span.className = "pill";
      span.textContent = label + ": " + value;
      return span;
    }
    elements.summary.appendChild(pill("Missions", summary.missions_completed + " / " + summary.missions_total));
    elements.summary.appendChild(pill("Scenes", summary.scenes_completed + " / " + summary.scenes_total));
    elements.summary.appendChild(pill("Total XP", summary.total_xp));
    elements.summary.appendChild(pill("Streak", summary.current_streak_days + "d"));
  }

  function statusClass(status) {
    switch (status) {
      case "completed": return "is-completed";
      case "available": return "is-available";
      case "in_progress": return "is-in-progress";
      default: return "is-locked";
    }
  }

  function statusLabel(status) {
    switch (status) {
      case "completed": return "Completed";
      case "available": return "Available";
      case "in_progress": return "In progress";
      default: return "Locked";
    }
  }

  // Convert a Latvia-bbox lat/lng into the 0..100% rectangle of the map.
  // Bounding box (approximate): lat 55.6..58.1, lng 20.9..28.3.
  function projectMapPosition(pos) {
    if (!pos || typeof pos.lat !== "number" || typeof pos.lng !== "number") {
      return null;
    }
    var minLat = 55.6, maxLat = 58.1;
    var minLng = 20.9, maxLng = 28.3;
    var x = (pos.lng - minLng) / (maxLng - minLng);
    var y = 1 - (pos.lat - minLat) / (maxLat - minLat);
    // Clamp.
    x = Math.max(0.05, Math.min(0.95, x));
    y = Math.max(0.10, Math.min(0.95, y));
    return { left: (x * 100).toFixed(1) + "%", top: (y * 100).toFixed(1) + "%" };
  }

  function renderMap(missions) {
    // Drop any previously-rendered markers (preserve the SVG outline).
    var markers = elements.map.querySelectorAll(".story-marker");
    for (var i = 0; i < markers.length; i += 1) {
      markers[i].parentNode.removeChild(markers[i]);
    }
    missions.forEach(function (mission, idx) {
      var pos = projectMapPosition(mission.map_position);
      if (!pos) return;
      var marker = document.createElement("button");
      marker.type = "button";
      marker.className = "story-marker " + statusClass(mission.status);
      marker.style.left = pos.left;
      marker.style.top = pos.top;
      marker.title = mission.title;
      marker.setAttribute("aria-label", mission.title + " (" + statusLabel(mission.status) + ")");
      marker.addEventListener("click", function () {
        focusMission(mission.id);
      });
      var pin = document.createElement("span");
      pin.className = "pin";
      var num = document.createElement("span");
      num.textContent = String(idx + 1);
      pin.appendChild(num);
      var label = document.createElement("span");
      label.className = "label";
      label.textContent = mission.city || mission.title;
      marker.appendChild(pin);
      marker.appendChild(label);
      elements.map.appendChild(marker);
    });
  }

  function renderMissionList(missions) {
    clearChildren(elements.missions);
    missions.forEach(function (mission) {
      var card = document.createElement("li");
      card.className =
        "story-mission-card " +
        statusClass(mission.status) +
        (state.activeMissionId === mission.id ? " is-active" : "");
      card.setAttribute("role", "button");
      card.setAttribute("tabindex", "0");
      card.setAttribute("aria-pressed", state.activeMissionId === mission.id ? "true" : "false");

      var title = document.createElement("div");
      title.className = "title";
      title.textContent = mission.title;

      var meta = document.createElement("div");
      meta.className = "meta";
      var citySpan = document.createElement("span");
      citySpan.textContent = (mission.city_lv || mission.city || "") + " · " + mission.estimated_duration_minutes + " min";
      var tag = document.createElement("span");
      tag.className = "status-tag";
      tag.textContent = statusLabel(mission.status);
      meta.appendChild(citySpan);
      meta.appendChild(tag);

      var summary = document.createElement("div");
      summary.className = "summary";
      summary.textContent = mission.summary;

      var ratio = mission.scenes_total ? mission.scenes_completed / mission.scenes_total : 0;
      var progressWrap = document.createElement("div");
      progressWrap.className = "progress";
      progressWrap.setAttribute("role", "progressbar");
      progressWrap.setAttribute("aria-valuemin", "0");
      progressWrap.setAttribute("aria-valuemax", String(mission.scenes_total || 1));
      progressWrap.setAttribute("aria-valuenow", String(mission.scenes_completed || 0));
      var bar = document.createElement("div");
      bar.className = "progress-bar";
      bar.style.width = (ratio * 100).toFixed(0) + "%";
      progressWrap.appendChild(bar);

      card.appendChild(title);
      card.appendChild(meta);
      card.appendChild(summary);
      card.appendChild(progressWrap);

      if (mission.status === "locked") {
        var hint = document.createElement("div");
        hint.className = "lock-hint";
        var reasons = [];
        if (mission.unlock && mission.unlock.missing_missions && mission.unlock.missing_missions.length) {
          reasons.push("Complete: " + mission.unlock.missing_missions.join(", "));
        }
        if (mission.unlock && mission.unlock.has_total_xp < mission.unlock.needs_total_xp) {
          reasons.push("XP " + mission.unlock.has_total_xp + "/" + mission.unlock.needs_total_xp);
        }
        if (mission.unlock && mission.unlock.has_streak_days < mission.unlock.needs_streak_days) {
          reasons.push("Streak " + mission.unlock.has_streak_days + "/" + mission.unlock.needs_streak_days + " days");
        }
        hint.textContent = reasons.join(" · ") || "Locked";
        card.appendChild(hint);
      }

      card.addEventListener("click", function () {
        focusMission(mission.id);
      });
      card.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          focusMission(mission.id);
        }
      });

      elements.missions.appendChild(card);
    });
  }

  function renderScenePanel(mission) {
    if (!mission) {
      elements.scenePanel.classList.remove("is-open");
      return;
    }
    elements.scenePanel.classList.add("is-open");
    elements.sceneMeta.textContent =
      mission.title +
      " · " +
      (mission.city_lv || mission.city || "") +
      " · " +
      mission.scenes_completed +
      "/" +
      mission.scenes_total +
      " scenes completed";
    clearChildren(elements.sceneList);
    mission.scenes.forEach(function (scene) {
      var item = document.createElement("li");
      item.className = "story-scene" + (scene.completed ? " is-done" : "");

      var titleRow = document.createElement("div");
      titleRow.className = "row";
      var title = document.createElement("strong");
      title.textContent = "Scene " + scene.order + " — " + scene.title;
      titleRow.appendChild(title);
      if (scene.npc_id) {
        var npc = document.createElement("span");
        npc.className = "npc-pill";
        npc.textContent = "NPC: " + scene.npc_id;
        titleRow.appendChild(npc);
      }
      var xpPill = document.createElement("span");
      xpPill.className = "npc-pill";
      xpPill.textContent = "+" + scene.xp + " XP";
      titleRow.appendChild(xpPill);
      item.appendChild(titleRow);

      var titleLv = document.createElement("div");
      titleLv.style.fontSize = "0.85rem";
      titleLv.style.color = "#57606a";
      titleLv.textContent = scene.title_lv || "";
      item.appendChild(titleLv);

      var actionRow = document.createElement("div");
      actionRow.className = "row";
      var btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = scene.completed ? "Replay scene" : "Mark scene complete";
      if (scene.completed) btn.className = "secondary";
      btn.disabled = mission.status === "locked";
      btn.addEventListener("click", function () {
        attemptCompleteScene(mission.id, scene.id, btn);
      });
      actionRow.appendChild(btn);

      if (scene.npc_id) {
        var npcLink = document.createElement("a");
        npcLink.href = "./npc-chat.html?npc=" + encodeURIComponent(scene.npc_id);
        npcLink.textContent = "Open NPC chat →";
        npcLink.style.fontSize = "0.85rem";
        actionRow.appendChild(npcLink);
      }
      item.appendChild(actionRow);

      elements.sceneList.appendChild(item);
    });
  }

  function focusMission(missionId) {
    state.activeMissionId = missionId;
    var mission = state.catalogue
      ? state.catalogue.find(function (m) { return m.id === missionId; })
      : null;
    if (!mission) return;
    renderMissionList(state.catalogue);
    renderScenePanel(mission);
    // Scroll the scene panel into view on smaller screens.
    elements.scenePanel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function attemptCompleteScene(missionId, sceneId, button) {
    if (state.inflight) return;
    state.inflight = true;
    if (button) button.disabled = true;
    setError("");
    completeScene(missionId, sceneId)
      .then(function (result) {
        var msg = "Scene completed";
        if (result.scene_xp_awarded) msg += " · +" + result.scene_xp_awarded + " XP";
        if (result.mission_just_completed && result.mission_bonus_xp_awarded) {
          msg = "Mission complete! · +" + result.mission_bonus_xp_awarded + " XP bonus";
        } else if (!result.newly_completed) {
          msg = "Already completed earlier — no XP awarded";
        }
        showToast(msg);
        return fetchState();
      })
      .then(function (payload) {
        applyState(payload);
        if (state.activeMissionId) {
          var mission = state.catalogue.find(function (m) { return m.id === state.activeMissionId; });
          renderScenePanel(mission);
        }
      })
      .catch(function (err) {
        if (err && err.message === "auth_required") return;
        var detail = err && err.detail ? " — " + err.detail : "";
        setError((err && err.message ? err.message : "Could not complete scene") + detail);
      })
      .then(function () {
        state.inflight = false;
        if (button) button.disabled = false;
      });
  }

  function applyState(payload) {
    if (!payload || !Array.isArray(payload.missions)) {
      throw new Error("invalid_state_payload");
    }
    state.catalogue = payload.missions;
    state.summary = payload.summary || {};
    renderSummary(state.summary);
    renderMap(state.catalogue);
    renderMissionList(state.catalogue);
  }

  function init() {
    fetchState()
      .then(applyState)
      .catch(function (err) {
        if (err && err.message === "auth_required") return;
        setError("Could not load story progress: " + (err && err.message ? err.message : "unknown error"));
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
