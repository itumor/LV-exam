/*
 * T-023 — Unified account header
 *
 * Shared between latvian-a2-exam-app/ and latvian-listening-library/.
 * The two apps live behind the same origin and share the
 * a2_session HttpOnly cookie (Path=/). This script renders a
 * tiny fixed-position header that:
 *
 *   - calls /api/session to discover the unified account
 *   - shows "Hi, <name> · Sign out" when authenticated
 *   - shows "Sign in to sync progress" linking to the exam-app login,
 *     carrying ?return=<encoded-origin-path> so the exam app can
 *     redirect back here after login (single login flow).
 *
 * The script is intentionally framework-free, side-effect-only on a
 * <div id="unified-header-mount"> that it creates if absent. It is
 * safe to include before any other app code: every public method is
 * idempotent and re-runs cheaply on each navigation event.
 */
(function () {
  "use strict";

  var MOUNT_ID = "unified-header-mount";
  var LOGIN_PATH = "/latvian-a2-exam-app/#auth";
  var LOGOUT_API = "/api/auth/logout";
  var SESSION_API = "/api/session";
  // T-034 — XP + streak summary endpoint
  var XP_API = "/api/xp/summary";
  // Surfaces are derived from the URL prefix so this script can be
  // dropped into either app without configuration.
  var ON_LISTENING = window.location.pathname.indexOf("/latvian-listening-library/") === 0;
  var ON_EXAM = window.location.pathname.indexOf("/latvian-a2-exam-app/") === 0 || window.location.pathname === "/";

  function buildLoginHref() {
    var here = window.location.pathname + window.location.search + window.location.hash;
    try {
      return LOGIN_PATH + "?return=" + encodeURIComponent(here);
    } catch (e) {
      return LOGIN_PATH;
    }
  }

  function ensureMount() {
    var mount = document.getElementById(MOUNT_ID);
    if (mount) return mount;
    mount = document.createElement("div");
    mount.id = MOUNT_ID;
    mount.setAttribute("role", "region");
    mount.setAttribute("aria-label", "Account");
    mount.style.position = "fixed";
    mount.style.top = "8px";
    mount.style.right = "12px";
    mount.style.zIndex = "9999";
    mount.style.fontSize = "13px";
    mount.style.fontFamily = "-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif";
    mount.style.background = "rgba(20,107,99,0.92)";
    mount.style.color = "#fff";
    mount.style.padding = "6px 10px";
    mount.style.borderRadius = "999px";
    mount.style.boxShadow = "0 2px 8px rgba(0,0,0,0.18)";
    mount.style.display = "inline-flex";
    mount.style.alignItems = "center";
    mount.style.gap = "8px";
    mount.dataset.surface = ON_LISTENING ? "listening" : (ON_EXAM ? "exam" : "other");
    if (document.body) document.body.appendChild(mount);
    return mount;
  }

  function render(session) {
    var mount = ensureMount();
    if (!mount) return;
    while (mount.firstChild) mount.removeChild(mount.firstChild);

    if (!session || !session.authenticated) {
      var anonLabel = document.createElement("span");
      anonLabel.textContent = ON_LISTENING ? "Pierakstīties · Sign in to sync" : "Sign in to sync progress";
      anonLabel.style.opacity = "0.95";
      var loginLink = document.createElement("a");
      loginLink.href = buildLoginHref();
      loginLink.textContent = "Sign in →";
      loginLink.style.color = "#fff";
      loginLink.style.textDecoration = "underline";
      loginLink.style.fontWeight = "600";
      loginLink.dataset.testid = "unified-header-login";
      mount.appendChild(anonLabel);
      mount.appendChild(loginLink);
      mount.dataset.state = "anonymous";
      return;
    }

    var profile = session.profile || {};
    var account = session.account || {};
    var name = profile.full_name || account.email || "Learner";
    var greeting = document.createElement("span");
    greeting.textContent = "Hi, " + name;
    greeting.dataset.testid = "unified-header-name";
    var dot = document.createElement("span");
    dot.textContent = "·";
    dot.style.opacity = "0.55";

    // T-034 — XP badge + streak flame. Rendered as empty containers
    // first so the header layout is stable; populated asynchronously by
    // fetchXpSummary(). The two badges are always present in the DOM
    // when authenticated so tests can assert on them by testid.
    var xpBadge = document.createElement("span");
    xpBadge.dataset.testid = "unified-header-xp";
    xpBadge.setAttribute("aria-label", "Experience points");
    xpBadge.title = "Experience points";
    xpBadge.style.display = "inline-flex";
    xpBadge.style.alignItems = "center";
    xpBadge.style.gap = "3px";
    xpBadge.style.fontWeight = "600";
    xpBadge.textContent = "✦ 0 XP";

    var streakBadge = document.createElement("span");
    streakBadge.dataset.testid = "unified-header-streak";
    streakBadge.setAttribute("aria-label", "Daily streak");
    streakBadge.title = "Daily streak";
    streakBadge.style.display = "inline-flex";
    streakBadge.style.alignItems = "center";
    streakBadge.style.gap = "3px";
    streakBadge.style.fontWeight = "600";
    streakBadge.textContent = "🔥 0";

    var dotXp = document.createElement("span");
    dotXp.textContent = "·";
    dotXp.style.opacity = "0.55";

    var signout = document.createElement("button");
    signout.type = "button";
    signout.textContent = "Sign out";
    signout.dataset.testid = "unified-header-signout";
    signout.style.background = "transparent";
    signout.style.color = "#fff";
    signout.style.border = "1px solid rgba(255,255,255,0.6)";
    signout.style.borderRadius = "999px";
    signout.style.padding = "2px 10px";
    signout.style.cursor = "pointer";
    signout.style.font = "inherit";
    signout.addEventListener("click", function () {
      handleSignOut(signout);
    });
    mount.appendChild(greeting);
    mount.appendChild(dot);
    mount.appendChild(xpBadge);
    mount.appendChild(streakBadge);
    mount.appendChild(dotXp);
    mount.appendChild(signout);
    mount.dataset.state = "authenticated";
    mount.dataset.accountId = account.id || "";

    // Best-effort XP/streak fetch — silent on failure so the header
    // never breaks because the XP endpoint is unreachable.
    fetchXpSummary().then(function (summary) {
      if (!summary) return;
      renderXp(summary);
    });
  }

  function fetchXpSummary() {
    return fetch(XP_API, { credentials: "same-origin" })
      .then(function (response) {
        if (!response || !response.ok) return null;
        return response.json().catch(function () { return null; });
      })
      .catch(function () { return null; });
  }

  function renderXp(summary) {
    if (!summary || typeof summary !== "object") return;
    var totalXp = Number(summary.total_xp || 0) || 0;
    var currentStreak = Number(summary.current_streak || 0) || 0;
    var longestStreak = Number(summary.longest_streak || 0) || 0;
    var xpBadge = document.querySelector('[data-testid="unified-header-xp"]');
    var streakBadge = document.querySelector('[data-testid="unified-header-streak"]');
    if (xpBadge) {
      xpBadge.textContent = "✦ " + totalXp + " XP";
      xpBadge.dataset.totalXp = String(totalXp);
    }
    if (streakBadge) {
      streakBadge.textContent = "🔥 " + currentStreak;
      streakBadge.dataset.currentStreak = String(currentStreak);
      streakBadge.dataset.longestStreak = String(longestStreak);
      streakBadge.title =
        "Streak: " + currentStreak + " day(s) — longest " + longestStreak;
    }
    if (window.UnifiedHeader) {
      window.UnifiedHeader.lastXp = summary;
    }
  }

  function handleSignOut(button) {
    if (button) {
      button.disabled = true;
      button.textContent = "Signing out…";
    }
    fetch(LOGOUT_API, {
      method: "POST",
      credentials: "same-origin"
    }).catch(function () {
      // best-effort — even on network error we re-render anonymous below
    }).then(function () {
      window.UnifiedHeader.refresh();
    });
  }

  function fetchSession() {
    return fetch(SESSION_API, { credentials: "same-origin" })
      .then(function (response) {
        if (!response || !response.ok) return { authenticated: false };
        return response.json().catch(function () { return { authenticated: false }; });
      })
      .catch(function () { return { authenticated: false }; });
  }

  function refresh() {
    return fetchSession().then(function (session) {
      render(session);
      window.UnifiedHeader.lastSession = session;
      return session;
    });
  }

  window.UnifiedHeader = {
    refresh: refresh,
    render: render,
    renderXp: renderXp,
    fetchXpSummary: fetchXpSummary,
    buildLoginHref: buildLoginHref,
    mountId: MOUNT_ID,
    lastSession: null,
    lastXp: null
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { refresh(); });
  } else {
    refresh();
  }
})();
