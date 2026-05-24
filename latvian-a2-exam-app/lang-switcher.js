/*
 * T-062 — Frontend language switcher
 *
 * Renders a tiny dropdown inside the unified-header mount that lets the
 * learner pick between the three locales the platform ships: Latvian
 * (lv-LV), English (en-US) and Lithuanian (lt-LT). The selection is
 * persisted to:
 *
 *   1. localStorage  (key: "lvcodex.locale") — survives reloads,
 *   2. document.cookie "locale=<code>; Path=/; Max-Age=31536000;
 *      SameSite=Lax" — picked up by the server on the next request so
 *      server-rendered surfaces (the /api/i18n/strings endpoint, future
 *      SSR pages) agree with the client.
 *
 * The script is intentionally framework-free and idempotent. It looks
 * for the unified-header mount; if absent it appends a standalone
 * floating switcher in the top-left so the option is always
 * discoverable, even on surfaces that do not host the unified header.
 *
 * The switcher fires a ``lvcodex:locale-changed`` CustomEvent on the
 * window whenever the user picks a new locale. Other scripts (e.g. the
 * exam app's i18n binding) listen for this event to re-render localized
 * strings without a full page reload.
 *
 * Public API (window.LvCodexLang):
 *   getLocale()         -> current locale code (string)
 *   setLocale(code)     -> persists + re-renders + fires the event
 *   availableLocales()  -> ordered array of supported locale objects
 */
(function () {
  "use strict";

  var STORAGE_KEY = "lvcodex.locale";
  var COOKIE_NAME = "locale";
  var COOKIE_MAX_AGE = 60 * 60 * 24 * 365; // 1 year
  var MOUNT_ID = "unified-header-mount";
  var SWITCHER_ID = "lang-switcher";
  var EVENT_NAME = "lvcodex:locale-changed";

  // Declared SUPPORTED locales — keep in sync with
  // server_app/services/i18n.SUPPORTED_LOCALES. The frontend hard-codes
  // the same triple so the switcher renders even before any server
  // round-trip has happened.
  var SUPPORTED = [
    { code: "lv-LV", name: "Latviešu", english: "Latvian" },
    { code: "en-US", name: "English", english: "English" },
    { code: "lt-LT", name: "Lietuvių", english: "Lithuanian" }
  ];

  function readStorage() {
    try {
      return window.localStorage.getItem(STORAGE_KEY);
    } catch (e) {
      return null;
    }
  }

  function writeStorage(code) {
    try {
      window.localStorage.setItem(STORAGE_KEY, code);
    } catch (e) {
      /* private browsing / quota — fall through to cookie only */
    }
  }

  function readCookie(name) {
    var cookies = (document.cookie || "").split(";");
    for (var i = 0; i < cookies.length; i++) {
      var parts = cookies[i].trim().split("=");
      if (parts[0] === name) {
        try {
          return decodeURIComponent(parts[1] || "");
        } catch (e) {
          return parts[1] || "";
        }
      }
    }
    return null;
  }

  function writeCookie(code) {
    var encoded = encodeURIComponent(code);
    document.cookie =
      COOKIE_NAME + "=" + encoded +
      "; Path=/; Max-Age=" + COOKIE_MAX_AGE +
      "; SameSite=Lax";
  }

  function isSupported(code) {
    if (!code) return false;
    for (var i = 0; i < SUPPORTED.length; i++) {
      if (SUPPORTED[i].code === code) return true;
    }
    return false;
  }

  function detectFromNavigator() {
    var langs = (navigator.languages && navigator.languages.length)
      ? navigator.languages
      : [navigator.language || ""];
    for (var i = 0; i < langs.length; i++) {
      var raw = String(langs[i] || "").replace("_", "-");
      if (isSupported(raw)) return raw;
      // Match language family (e.g. "lt" -> "lt-LT").
      var family = raw.split("-")[0].toLowerCase();
      for (var j = 0; j < SUPPORTED.length; j++) {
        if (SUPPORTED[j].code.toLowerCase().split("-")[0] === family) {
          return SUPPORTED[j].code;
        }
      }
    }
    return null;
  }

  function getLocale() {
    var stored = readStorage();
    if (isSupported(stored)) return stored;
    var cookie = readCookie(COOKIE_NAME);
    if (isSupported(cookie)) return cookie;
    var detected = detectFromNavigator();
    if (detected) return detected;
    return SUPPORTED[0].code; // default to lv-LV
  }

  function setLocale(code) {
    if (!isSupported(code)) return false;
    writeStorage(code);
    writeCookie(code);
    document.documentElement.setAttribute("lang", code.split("-")[0]);
    renderSwitcher();
    try {
      window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: { locale: code } }));
    } catch (e) {
      /* IE fallback — skip the event */
    }
    return true;
  }

  function ensureSwitcherHost() {
    var existing = document.getElementById(SWITCHER_ID);
    if (existing) return existing;
    var host = document.createElement("span");
    host.id = SWITCHER_ID;
    host.dataset.testid = "lang-switcher";
    host.style.display = "inline-flex";
    host.style.alignItems = "center";
    host.style.marginLeft = "8px";
    var mount = document.getElementById(MOUNT_ID);
    if (mount) {
      mount.appendChild(host);
      return host;
    }
    // No unified header on this surface — fall back to a fixed corner
    // mount in the top-left so the switcher remains discoverable.
    host.style.position = "fixed";
    host.style.top = "8px";
    host.style.left = "12px";
    host.style.zIndex = "9999";
    host.style.background = "rgba(20,107,99,0.92)";
    host.style.color = "#fff";
    host.style.padding = "4px 10px";
    host.style.borderRadius = "999px";
    host.style.fontSize = "13px";
    host.style.fontFamily = "-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif";
    if (document.body) {
      document.body.appendChild(host);
    }
    return host;
  }

  function renderSwitcher() {
    var host = ensureSwitcherHost();
    if (!host) return;
    while (host.firstChild) host.removeChild(host.firstChild);

    var current = getLocale();

    var label = document.createElement("label");
    label.htmlFor = "lang-switcher-select";
    label.textContent = "🌐 ";
    label.style.opacity = "0.95";
    label.style.fontSize = "13px";

    var select = document.createElement("select");
    select.id = "lang-switcher-select";
    select.dataset.testid = "lang-switcher-select";
    select.setAttribute("aria-label", "Language");
    select.style.background = "rgba(255,255,255,0.18)";
    select.style.color = "#fff";
    select.style.border = "1px solid rgba(255,255,255,0.4)";
    select.style.borderRadius = "999px";
    select.style.padding = "2px 6px";
    select.style.font = "inherit";
    select.style.cursor = "pointer";

    for (var i = 0; i < SUPPORTED.length; i++) {
      var opt = document.createElement("option");
      opt.value = SUPPORTED[i].code;
      opt.textContent = SUPPORTED[i].name;
      opt.style.color = "#000";
      if (SUPPORTED[i].code === current) opt.selected = true;
      select.appendChild(opt);
    }

    select.addEventListener("change", function (e) {
      var target = e && e.target ? e.target : null;
      if (!target) return;
      setLocale(String(target.value));
    });

    host.appendChild(label);
    host.appendChild(select);
  }

  function init() {
    // Apply the persisted/default locale to the document tag immediately
    // so CSS :lang() rules and screen readers see the right value before
    // the first render.
    var current = getLocale();
    document.documentElement.setAttribute("lang", current.split("-")[0]);
    renderSwitcher();
  }

  window.LvCodexLang = {
    getLocale: getLocale,
    setLocale: setLocale,
    availableLocales: function () { return SUPPORTED.slice(); },
    eventName: EVENT_NAME,
    storageKey: STORAGE_KEY,
    cookieName: COOKIE_NAME
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Re-render after the unified header mounts (it appends asynchronously).
  // We poll briefly so the switcher migrates from the standalone corner
  // mount into the header strip once the header is up.
  var migrationTries = 0;
  var migrationTimer = setInterval(function () {
    migrationTries += 1;
    if (migrationTries > 20) {
      clearInterval(migrationTimer);
      return;
    }
    var header = document.getElementById(MOUNT_ID);
    var switcher = document.getElementById(SWITCHER_ID);
    if (!header || !switcher) return;
    if (switcher.parentNode === header) {
      clearInterval(migrationTimer);
      return;
    }
    // Move the switcher into the unified header strip.
    header.appendChild(switcher);
    switcher.style.position = "";
    switcher.style.top = "";
    switcher.style.left = "";
    switcher.style.background = "";
    switcher.style.padding = "";
    switcher.style.borderRadius = "";
    switcher.style.boxShadow = "";
    clearInterval(migrationTimer);
  }, 250);
})();
