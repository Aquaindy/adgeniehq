// Google Analytics 4 (gtag.js) bootstrap.
// Externalized (not inline) so the page CSP can keep script-src strict —
// same pattern as theme-init.js. Loaded alongside the async gtag.js loader.
window.dataLayer = window.dataLayer || [];
function gtag() {
  dataLayer.push(arguments);
}
window.gtag = gtag;
gtag("js", new Date());
gtag("config", "G-N911ENZ5C6");
