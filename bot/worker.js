/**
 * MOSAIC Telegram support bot — Cloudflare Worker (webhook mode).
 *
 * Telegram pushes each update here instantly; the worker replies and exits.
 * No polling, no persistent process, no server.
 *
 * Required Worker secrets (set via wrangler or the Cloudflare dashboard):
 *   TELEGRAM_BOT_TOKEN  — token from @BotFather
 *   WEBHOOK_SECRET      — arbitrary string used to verify Telegram calls
 *
 * Optional Worker secret:
 *   GITHUB_TOKEN        — raises GitHub API rate limit from 60 to 5000 req/h
 *
 * The bot must be added as a group admin with privacy mode disabled
 * (/setprivacy → Disabled in @BotFather) to read plain messages for FAQ.
 */

const REPO     = "szaghi/mosaic";
const DOCS_URL = "https://szaghi.github.io/mosaic";
const PYPI_URL = "https://pypi.org/project/mosaic-search";
const GH_URL   = `https://github.com/${REPO}`;

// ── Telegram helpers ──────────────────────────────────────────────────────────

async function tgApi(token, method, payload) {
  const resp = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return resp.json();
}

function send(token, chatId, text, replyTo) {
  const payload = {
    chat_id: chatId,
    text,
    parse_mode: "HTML",
    link_preview_options: { is_disabled: true },
  };
  if (replyTo) payload.reply_to_message_id = replyTo;
  return tgApi(token, "sendMessage", payload);
}

// ── GitHub / PyPI helpers ─────────────────────────────────────────────────────

async function ghGet(path, githubToken) {
  const headers = {
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
  };
  if (githubToken) headers.Authorization = `Bearer ${githubToken}`;
  const resp = await fetch(`https://api.github.com/repos/${REPO}/${path}`, { headers });
  return resp.json();
}

async function pypiVersion() {
  const resp = await fetch(`${PYPI_URL}/json`);
  const data = await resp.json();
  return data.info.version;
}

function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// ── Commands ──────────────────────────────────────────────────────────────────

async function cmdHelp(token, chatId, msgId) {
  await send(token, chatId, (
    "🤖 <b>MOSAIC Support Bot</b>\n\n" +
    "/help — this message\n" +
    "/install — installation instructions\n" +
    "/version — latest release on PyPI\n" +
    "/docs — documentation\n" +
    "/sources — supported search sources\n" +
    "/changelog — recent release notes\n" +
    "/bug — how to report a bug\n" +
    "/roadmap — open issues and milestones"
  ), msgId);
}

async function cmdInstall(token, chatId, msgId) {
  await send(token, chatId, (
    "📦 <b>Install MOSAIC</b>\n\n" +
    "Recommended (isolated environment):\n" +
    "<code>pipx install mosaic-search</code>\n\n" +
    "Or with pip:\n" +
    "<code>pip install mosaic-search</code>\n\n" +
    "Quick test:\n" +
    "<code>mosaic search \"transformer attention\" --max 5</code>\n\n" +
    `📘 <a href="${DOCS_URL}/guide/getting-started">Getting started</a>`
  ), msgId);
}

async function cmdVersion(token, chatId, msgId) {
  let text;
  try {
    const ver = await pypiVersion();
    text = (
      `🏷️ Latest MOSAIC: <b>${ver}</b>\n\n` +
      `📦 <a href="${PYPI_URL}/">PyPI</a>  ·  ` +
      `🔖 <a href="${GH_URL}/releases">Releases</a>\n\n` +
      "<code>pipx install --upgrade mosaic-search</code>"
    );
  } catch (e) {
    text = `⚠️ Could not fetch version: ${esc(e.message)}`;
  }
  await send(token, chatId, text, msgId);
}

async function cmdDocs(token, chatId, msgId) {
  await send(token, chatId, (
    "📘 <b>MOSAIC Documentation</b>\n\n" +
    `<a href="${DOCS_URL}">${DOCS_URL}</a>\n\n` +
    "Covers: getting started, configuration, all 21 sources, " +
    "CLI reference, Zotero/Obsidian integrations, and changelog."
  ), msgId);
}

const SOURCES_FREE = [
  "arXiv", "Semantic Scholar", "OpenAlex", "Europe PMC",
  "PubMed", "PubMed Central", "bioRxiv/medRxiv",
  "DOAJ", "Crossref", "Zenodo", "DBLP", "HAL", "PEDRO", "BASE Search",
];
const SOURCES_KEY = [
  "IEEE Xplore", "Springer", "ScienceDirect", "CORE", "NASA ADS", "Scopus",
];

async function cmdSources(token, chatId, msgId) {
  await send(token, chatId, (
    `🔍 <b>MOSAIC sources (${SOURCES_FREE.length + SOURCES_KEY.length} total)</b>\n\n` +
    "<b>No auth required:</b>\n" + SOURCES_FREE.join(", ") + "\n\n" +
    "<b>Free API key / browser session:</b>\n" + SOURCES_KEY.join(", ") + "\n\n" +
    `📘 <a href="${DOCS_URL}/guide/sources">Source docs</a>`
  ), msgId);
}

async function cmdChangelog(token, chatId, msgId, githubToken) {
  let text;
  try {
    const releases = await ghGet("releases?per_page=3", githubToken);
    const lines = ["📋 <b>Recent MOSAIC releases</b>\n"];
    for (const r of releases.slice(0, 3)) {
      const body  = (r.body || "").trim();
      const notes = esc(body.slice(0, 200) + (body.length > 200 ? "…" : ""));
      lines.push(`<b><a href="${r.html_url}">${r.tag_name}</a></b>\n${notes}\n`);
    }
    text = lines.join("\n");
  } catch (e) {
    text = `⚠️ Could not fetch releases: ${esc(e.message)}`;
  }
  await send(token, chatId, text, msgId);
}

async function cmdBug(token, chatId, msgId) {
  await send(token, chatId, (
    "🐛 <b>Report a Bug</b>\n\n" +
    "Please open a GitHub issue and include:\n" +
    "• MOSAIC version — <code>mosaic --version</code>\n" +
    "• The exact command you ran\n" +
    "• Error message or unexpected output\n" +
    "• OS and Python version\n\n" +
    `🔗 <a href="${GH_URL}/issues/new?labels=bug&template=bug_report.md">Open a bug report →</a>`
  ), msgId);
}

async function cmdRoadmap(token, chatId, msgId, githubToken) {
  let text;
  try {
    const [milestones, issues] = await Promise.all([
      ghGet("milestones?state=open&per_page=5", githubToken),
      ghGet("issues?state=open&labels=enhancement&per_page=8&sort=created&direction=desc", githubToken),
    ]);
    const lines = ["🗺️ <b>MOSAIC Roadmap</b>\n"];
    if (milestones.length) {
      lines.push("<b>Milestones:</b>");
      for (const m of milestones.slice(0, 3)) {
        lines.push(`  · <a href="${m.html_url}">${esc(m.title)}</a> (${m.open_issues} open)`);
      }
      lines.push("");
    }
    if (issues.length) {
      lines.push("<b>Planned enhancements:</b>");
      for (const i of issues.slice(0, 6)) {
        lines.push(`  · <a href="${i.html_url}">#${i.number}</a> ${esc(i.title)}`);
      }
    }
    if (!milestones.length && !issues.length) lines.push("No open milestones or enhancements found.");
    text = lines.join("\n");
  } catch (e) {
    text = `⚠️ Could not fetch roadmap: ${esc(e.message)}`;
  }
  await send(token, chatId, text, msgId);
}

const COMMANDS = {
  "/help":      cmdHelp,
  "/install":   cmdInstall,
  "/version":   cmdVersion,
  "/docs":      cmdDocs,
  "/sources":   cmdSources,
  "/changelog": cmdChangelog,
  "/bug":       cmdBug,
  "/roadmap":   cmdRoadmap,
};

// ── FAQ auto-reply ────────────────────────────────────────────────────────────

const FAQ = [
  {
    keys: ["how to install", "how do i install", "pipx", "pip install"],
    reply: "💡 Install MOSAIC with:\n<code>pipx install mosaic-search</code>\nUse /install for full instructions.",
  },
  {
    keys: ["api key", "apikey", "api_key", "need a key", "requires key"],
    reply:
      "🔑 Most MOSAIC sources work without any API key.\n" +
      "IEEE, Springer, ScienceDirect, CORE, and NASA ADS offer free keys.\n" +
      `<a href="${DOCS_URL}/guide/configuration">Configuration docs</a>`,
  },
  {
    keys: ["proxy", "vpn", "firewall", "blocked", "timeout"],
    reply:
      "🌐 If a source is unreachable, MOSAIC skips it and continues.\n" +
      "Target a specific source:\n<code>mosaic search ... --source arxiv</code>",
  },
  {
    keys: ["zotero"],
    reply:
      "📚 MOSAIC integrates with Zotero!\n" +
      "Configure the <code>[zotero]</code> section, then:\n" +
      "<code>mosaic search ... --zotero</code>\n" +
      `<a href="${DOCS_URL}/guide/zotero">Zotero integration docs</a>`,
  },
  {
    keys: ["obsidian"],
    reply:
      "🗒️ MOSAIC can push papers to Obsidian!\n" +
      "<code>mosaic search ... --obsidian</code>\n" +
      `<a href="${DOCS_URL}/guide/obsidian">Obsidian integration docs</a>`,
  },
  {
    keys: ["download pdf", "get pdf", "--pdf", "open access"],
    reply:
      "📄 MOSAIC downloads open-access PDFs with:\n" +
      "<code>mosaic search ... --pdf</code>",
  },
  {
    keys: ["config", "configuration", "settings", "config.toml"],
    reply:
      "⚙️ View your current config:\n" +
      "<code>mosaic config --show</code>\n" +
      `<a href="${DOCS_URL}/guide/configuration">Configuration docs</a>`,
  },
  {
    keys: ["similar", "related", "find similar"],
    reply:
      "🔗 Find papers similar to a known one:\n" +
      "<code>mosaic similar 10.1234/doi</code>",
  },
  {
    keys: ["bib", "bibtex", "--from"],
    reply:
      "📑 Batch-fetch papers from a .bib or .csv file:\n" +
      "<code>mosaic get --from refs.bib</code>",
  },
];

async function faqReply(token, chatId, msgId, textLower) {
  for (const { keys, reply } of FAQ) {
    if (keys.some((k) => textLower.includes(k))) {
      await send(token, chatId, reply, msgId);
      return true;
    }
  }
  return false;
}

// ── Welcome ───────────────────────────────────────────────────────────────────

async function welcome(token, chatId, members) {
  const names = members.map((m) => esc(m.first_name || "there")).join(", ");
  await send(token, chatId, (
    `👋 Welcome, <b>${names}</b>!\n\n` +
    "This is the official MOSAIC support group.\n\n" +
    "🔍 <b>MOSAIC</b> — Multi-source Scientific Article Indexer and Collector\n" +
    "<i>A vivid mosaic of open scientific literature, assembled in seconds</i>\n\n" +
    "<code>pipx install mosaic-search</code>\n" +
    `📘 <a href="${DOCS_URL}">Docs</a>  ·  ` +
    `🐙 <a href="${GH_URL}">GitHub</a>  ·  /help for bot commands`
  ));
}

// ── Update processing ─────────────────────────────────────────────────────────

async function processUpdate(update, token, githubToken) {
  const msg = update.message || update.edited_message;
  if (!msg) return;

  const chatId = msg.chat.id;
  const msgId  = msg.message_id;

  // Welcome new human members
  const newMembers = msg.new_chat_members;
  if (newMembers) {
    const humans = newMembers.filter((m) => !m.is_bot);
    if (humans.length) await welcome(token, chatId, humans);
    return;
  }

  const text = msg.text || "";
  if (!text) return;

  // Commands — strip bot-name suffix (e.g. /help@mosaic_bot → /help)
  const firstWord = text.split(/\s/)[0];
  const cmd = firstWord.split("@")[0].toLowerCase();

  if (cmd in COMMANDS) {
    // changelog and roadmap need githubToken; others ignore extra args
    await COMMANDS[cmd](token, chatId, msgId, githubToken);
    return;
  }

  // FAQ auto-reply (groups only)
  const chatType = msg.chat.type;
  if (chatType === "group" || chatType === "supergroup") {
    await faqReply(token, chatId, msgId, text.toLowerCase());
  }
}

// ── Entry point ───────────────────────────────────────────────────────────────

export default {
  async fetch(request, env, ctx) {
    // Only accept POST (Telegram webhook calls)
    if (request.method !== "POST") {
      return new Response("OK", { status: 200 });
    }

    // Verify the shared secret Telegram sends in the header
    const incoming = request.headers.get("X-Telegram-Bot-Api-Secret-Token");
    if (incoming !== env.WEBHOOK_SECRET) {
      return new Response("Unauthorized", { status: 401 });
    }

    const update = await request.json();

    // Respond to Telegram immediately; process in background.
    // This prevents Telegram from timing out and re-delivering the update.
    ctx.waitUntil(processUpdate(update, env.TELEGRAM_BOT_TOKEN, env.GITHUB_TOKEN || ""));

    return new Response("OK", { status: 200 });
  },
};
