/* AdVanta AI — A/B traffic split snippet.
 * Usage on the customer's landing page:
 *
 *   <script
 *     src="https://api.advantaai.com/static/advanta-ab.js"
 *     data-test="<test_id>"
 *     data-mode="redirect"
 *   ></script>
 *
 * Modes:
 *   redirect  — fetch the assigned variant and window.location.replace() to its url
 *               (use this when each variant lives at its own URL)
 *   inplace   — show only the matching <[data-advanta-variant="<name>"]> elements
 *               (use this for hero-copy / button-text swaps on a single URL)
 *
 * Convert call (fire on form submit, button click, etc.):
 *   window.advantaConvert(testId, { value_cents: 4900 });
 */
(function () {
  var script = document.currentScript;
  if (!script) return;
  var testId = script.getAttribute("data-test");
  var mode = script.getAttribute("data-mode") || "inplace";
  if (!testId) {
    console.warn("[advanta] missing data-test attribute on script tag");
    return;
  }
  var apiBase = (script.getAttribute("data-api") || script.src.replace(/\/static\/advanta-ab\.js.*$/, "")).replace(/\/$/, "");
  var STORAGE_KEY = "advanta_visitor_id";

  function getVisitorId() {
    try {
      var existing = localStorage.getItem(STORAGE_KEY);
      if (existing) return existing;
      var fresh = (crypto && crypto.randomUUID) ? crypto.randomUUID() : ("v-" + Date.now() + "-" + Math.random().toString(36).slice(2));
      localStorage.setItem(STORAGE_KEY, fresh);
      return fresh;
    } catch (e) {
      // localStorage may be blocked (Safari private mode, third-party cookies off, etc.).
      // Fall back to a session-scoped id so the visitor still gets a sticky variant
      // for this page view.
      window.__advantaTransientVisitor = window.__advantaTransientVisitor || (
        "v-" + Date.now() + "-" + Math.random().toString(36).slice(2)
      );
      return window.__advantaTransientVisitor;
    }
  }

  function postJSON(path, body) {
    return fetch(apiBase + "/api/v1/public/ab-tests/" + encodeURIComponent(testId) + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      keepalive: true,
    });
  }

  function applyInplace(name) {
    document.querySelectorAll("[data-advanta-variant]").forEach(function (el) {
      el.style.display = el.getAttribute("data-advanta-variant") === name ? "" : "none";
    });
  }

  var visitorId = getVisitorId();
  postJSON("/assign", { visitor_id: visitorId })
    .then(function (resp) {
      if (!resp.ok) {
        console.warn("[advanta] assign returned", resp.status);
        return;
      }
      return resp.json();
    })
    .then(function (data) {
      if (!data) return;
      window.__advantaAssignment = data;
      if (mode === "redirect") {
        var url = data.payload && data.payload.url;
        if (!url) return;
        try {
          var here = new URL(window.location.href);
          var there = new URL(url, window.location.href);
          // Already on the assigned variant — don't redirect-loop.
          if (here.href === there.href) return;
          window.location.replace(there.href);
        } catch (_) {
          /* malformed url — silently no-op */
        }
      } else {
        applyInplace(data.variant_name);
      }
    })
    .catch(function (err) {
      console.warn("[advanta] assign failed", err);
    });

  // Conversion helper — exposed globally so the customer's site can call it
  // on form submit, purchase, etc.
  window.advantaConvert = function (otherTestId, opts) {
    opts = opts || {};
    var t = otherTestId || testId;
    return fetch(apiBase + "/api/v1/public/ab-tests/" + encodeURIComponent(t) + "/convert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        visitor_id: visitorId,
        value_cents: opts.value_cents != null ? opts.value_cents : null,
        metadata: opts.metadata || null,
      }),
      keepalive: true,
    }).catch(function () { /* swallow — analytics shouldn't break the page */ });
  };
})();
