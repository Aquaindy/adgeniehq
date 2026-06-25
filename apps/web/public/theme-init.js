// Apply the saved/system theme before first paint to avoid a flash.
// Externalized (not inline) so the page CSP can keep script-src strict ('self')
// without needing 'unsafe-inline' or a per-build hash.
(function () {
  try {
    var stored = localStorage.getItem("advanta-theme");
    var dark = stored
      ? stored === "dark"
      : window.matchMedia("(prefers-color-scheme: dark)").matches;
    var root = document.documentElement;
    root.classList.toggle("dark", dark);
    root.style.colorScheme = dark ? "dark" : "light";
  } catch (e) {
    /* localStorage blocked — fall back to light */
  }
})();
