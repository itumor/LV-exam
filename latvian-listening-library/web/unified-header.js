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
    mount.appendChild(signout);
    mount.dataset.state = "authenticated";
    mount.dataset.accountId = account.id || "";
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
    buildLoginHref: buildLoginHref,
    mountId: MOUNT_ID,
    lastSession: null
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { refresh(); });
  } else {
    refresh();
  }
})();
