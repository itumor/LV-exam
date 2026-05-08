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

// CommonJS export for Node.js require() compatibility (e.g. unit tests).
if (typeof module !== 'undefined') {
  module.exports = {
    formatTime: formatTime,
    applyFilter: applyFilter,
    isCompleted: isCompleted,
    calcProgress: calcProgress,
    resolveText: resolveText,
    toggleTheme: toggleTheme,
    getActiveIds: getActiveIds
  };
}
