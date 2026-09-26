/*
 * Safe Markdown rendering for LLM answers (requires marked.min.js).
 *
 * marked does not sanitise its output, and RAG answers are shaped by paper
 * abstracts fetched from third-party APIs, so raw HTML, script-capable links
 * and remote images are neutralised before anything reaches innerHTML.
 */
(function (root) {
  "use strict";

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // http(s), mailto, in-page anchors and same-origin relative paths only
  var SAFE_URL = /^(https?:|mailto:|#|\/(?!\/))/i;

  root.marked.use({
    renderer: {
      html: function (token) {
        return escapeHtml(token.text || token.raw || "");
      },
      link: function (token) {
        var text = this.parser.parseInline(token.tokens);
        var href = String(token.href || "").trim();
        if (!SAFE_URL.test(href)) return text;
        var title = token.title ? ' title="' + escapeHtml(token.title) + '"' : "";
        return '<a href="' + escapeHtml(href) + '"' + title +
          ' target="_blank" rel="noopener noreferrer">' + text + "</a>";
      },
      image: function (token) {
        // Never let an answer load remote resources
        return escapeHtml(token.text || "");
      },
    },
  });

  root.mosaicRenderMarkdown = function (el) {
    el.innerHTML = root.marked.parse(el.textContent);
    el.dataset.rendered = "1";
  };
})(typeof window !== "undefined" ? window : globalThis);
