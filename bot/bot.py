"""MOSAIC Telegram support bot.

Stateless polling script — no external dependencies (stdlib only).
Designed to be run every 5 minutes via GitHub Actions.

State (last processed update_id) is persisted in OFFSET_FILE, which
the CI workflow caches between runs using actions/cache.

Required environment variables:
  TELEGRAM_BOT_TOKEN   — bot token from @BotFather
  GITHUB_REPOSITORY    — e.g. "szaghi/mosaic" (set automatically by GH Actions)

Optional:
  GITHUB_TOKEN         — for higher-rate GitHub API calls (set automatically)
  OFFSET_FILE          — path to offset file (default: offset.txt)
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
REPO = os.environ.get("GITHUB_REPOSITORY", "szaghi/mosaic")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
OFFSET_FILE = os.environ.get("OFFSET_FILE", "offset.txt")

DOCS_URL = "https://szaghi.github.io/mosaic"
GITHUB_URL = f"https://github.com/{REPO}"
PYPI_URL = "https://pypi.org/project/mosaic-search"


# ── Telegram helpers ──────────────────────────────────────────────────────────

def tg(method, payload=None):
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    data = json.dumps(payload).encode() if payload else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def send(chat_id, text, reply_to=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    return tg("sendMessage", payload)


# ── GitHub / PyPI helpers ─────────────────────────────────────────────────────

def gh_get(path):
    url = f"https://api.github.com/repos/{REPO}/{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def pypi_version():
    with urllib.request.urlopen(f"{PYPI_URL}/json", timeout=10) as resp:
        return json.loads(resp.read())["info"]["version"]


def html_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── Bot commands ──────────────────────────────────────────────────────────────

def cmd_help(chat_id, msg_id):
    send(chat_id, (
        "🤖 <b>MOSAIC Support Bot</b>\n\n"
        "/help — this message\n"
        "/install — installation instructions\n"
        "/version — latest release on PyPI\n"
        "/docs — documentation\n"
        "/sources — supported search sources\n"
        "/changelog — recent release notes\n"
        "/bug — how to report a bug\n"
        "/roadmap — open issues and milestones"
    ), reply_to=msg_id)


def cmd_install(chat_id, msg_id):
    send(chat_id, (
        "📦 <b>Install MOSAIC</b>\n\n"
        "Recommended (isolated environment):\n"
        "<code>pipx install mosaic-search</code>\n\n"
        "Or with pip:\n"
        "<code>pip install mosaic-search</code>\n\n"
        "Quick test:\n"
        "<code>mosaic search \"transformer attention\" --max 5</code>\n\n"
        f'📘 <a href="{DOCS_URL}/guide/getting-started">Getting started</a>'
    ), reply_to=msg_id)


def cmd_version(chat_id, msg_id):
    try:
        ver = pypi_version()
        text = (
            f"🏷️ Latest MOSAIC: <b>{ver}</b>\n\n"
            f'📦 <a href="{PYPI_URL}/">PyPI</a>  ·  '
            f'🔖 <a href="{GITHUB_URL}/releases">Releases</a>\n\n'
            f"<code>pipx install --upgrade mosaic-search</code>"
        )
    except Exception as exc:
        text = f"⚠️ Could not fetch version: {html_escape(str(exc))}"
    send(chat_id, text, reply_to=msg_id)


def cmd_docs(chat_id, msg_id):
    send(chat_id, (
        f"📘 <b>MOSAIC Documentation</b>\n\n"
        f'<a href="{DOCS_URL}">{DOCS_URL}</a>\n\n'
        "Covers: getting started, configuration, all 21 sources, "
        "CLI reference, Zotero/Obsidian integrations, and changelog."
    ), reply_to=msg_id)


_SOURCES_FREE = [
    "arXiv", "Semantic Scholar", "OpenAlex", "Europe PMC",
    "PubMed", "PubMed Central", "bioRxiv/medRxiv",
    "DOAJ", "Crossref", "Zenodo", "DBLP", "HAL", "PEDRO",
    "BASE Search",
]
_SOURCES_KEY = [
    "IEEE Xplore", "Springer", "ScienceDirect", "CORE",
    "NASA ADS", "Scopus",
]


def cmd_sources(chat_id, msg_id):
    send(chat_id, (
        f"🔍 <b>MOSAIC sources ({len(_SOURCES_FREE) + len(_SOURCES_KEY)} total)</b>\n\n"
        "<b>No auth required:</b>\n"
        + ", ".join(_SOURCES_FREE) + "\n\n"
        "<b>Free API key / browser session:</b>\n"
        + ", ".join(_SOURCES_KEY) + "\n\n"
        f'📘 <a href="{DOCS_URL}/guide/sources">Source docs</a>'
    ), reply_to=msg_id)


def cmd_changelog(chat_id, msg_id):
    try:
        releases = gh_get("releases?per_page=3")
        lines = ["📋 <b>Recent MOSAIC releases</b>\n"]
        for r in releases[:3]:
            tag = r["tag_name"]
            url = r["html_url"]
            body = r.get("body", "").strip()
            notes = html_escape(body[:200] + ("…" if len(body) > 200 else ""))
            lines.append(f'<b><a href="{url}">{tag}</a></b>\n{notes}\n')
        text = "\n".join(lines)
    except Exception as exc:
        text = f"⚠️ Could not fetch releases: {html_escape(str(exc))}"
    send(chat_id, text, reply_to=msg_id)


def cmd_bug(chat_id, msg_id):
    send(chat_id, (
        "🐛 <b>Report a Bug</b>\n\n"
        "Please open a GitHub issue and include:\n"
        "• MOSAIC version — <code>mosaic --version</code>\n"
        "• The exact command you ran\n"
        "• Error message or unexpected output\n"
        "• OS and Python version\n\n"
        f'🔗 <a href="{GITHUB_URL}/issues/new?labels=bug&template=bug_report.md">'
        "Open a bug report →</a>"
    ), reply_to=msg_id)


def cmd_roadmap(chat_id, msg_id):
    try:
        milestones = gh_get("milestones?state=open&per_page=5")
        issues = gh_get(
            "issues?state=open&labels=enhancement"
            "&per_page=8&sort=created&direction=desc"
        )
        lines = [f"🗺️ <b>MOSAIC Roadmap</b>\n"]
        if milestones:
            lines.append("<b>Milestones:</b>")
            for m in milestones[:3]:
                open_n = m["open_issues"]
                lines.append(
                    f'  · <a href="{m["html_url"]}">{html_escape(m["title"])}</a>'
                    f" ({open_n} open)"
                )
            lines.append("")
        if issues:
            lines.append("<b>Planned enhancements:</b>")
            for i in issues[:6]:
                lines.append(
                    f'  · <a href="{i["html_url"]}">#{i["number"]}</a>'
                    f" {html_escape(i['title'])}"
                )
        if not milestones and not issues:
            lines.append("No open milestones or enhancements found.")
        text = "\n".join(lines)
    except Exception as exc:
        text = f"⚠️ Could not fetch roadmap: {html_escape(str(exc))}"
    send(chat_id, text, reply_to=msg_id)


COMMANDS = {
    "/help": cmd_help,
    "/install": cmd_install,
    "/version": cmd_version,
    "/docs": cmd_docs,
    "/sources": cmd_sources,
    "/changelog": cmd_changelog,
    "/bug": cmd_bug,
    "/roadmap": cmd_roadmap,
}

# ── FAQ auto-reply ────────────────────────────────────────────────────────────
# Each entry: (list-of-trigger-keywords, reply-text)
# First matching rule wins.

FAQ = [
    (
        ["how to install", "how do i install", "pipx", "pip install"],
        (
            "💡 Install MOSAIC with:\n"
            "<code>pipx install mosaic-search</code>\n"
            "Use /install for full instructions."
        ),
    ),
    (
        ["api key", "apikey", "api_key", "need a key", "requires key"],
        (
            "🔑 Most MOSAIC sources work without any API key.\n"
            "IEEE, Springer, ScienceDirect, CORE, and NASA ADS "
            "offer free keys for higher rate limits.\n"
            f'See <a href="{DOCS_URL}/guide/configuration">configuration docs</a>.'
        ),
    ),
    (
        ["proxy", "vpn", "firewall", "blocked", "timeout"],
        (
            "🌐 If a source is unreachable, MOSAIC skips it and continues.\n"
            "To target a specific source:\n"
            "<code>mosaic search ... --source arxiv</code>"
        ),
    ),
    (
        ["zotero"],
        (
            "📚 MOSAIC integrates with Zotero!\n"
            "Configure the <code>[zotero]</code> section in your config, then:\n"
            "<code>mosaic search ... --zotero</code>\n"
            f'<a href="{DOCS_URL}/guide/zotero">Zotero integration docs</a>'
        ),
    ),
    (
        ["obsidian"],
        (
            "🗒️ MOSAIC can push papers to Obsidian!\n"
            "<code>mosaic search ... --obsidian</code>\n"
            f'<a href="{DOCS_URL}/guide/obsidian">Obsidian integration docs</a>'
        ),
    ),
    (
        ["download pdf", "get pdf", "--pdf", "open access", "oa"],
        (
            "📄 MOSAIC downloads open-access PDFs with:\n"
            "<code>mosaic search ... --pdf</code>\n"
            "Only OA papers are downloaded automatically."
        ),
    ),
    (
        ["config", "configuration", "settings", "config.toml"],
        (
            "⚙️ View your current config:\n"
            "<code>mosaic config --show</code>\n"
            f'<a href="{DOCS_URL}/guide/configuration">Configuration docs</a>'
        ),
    ),
    (
        ["similar", "related", "find similar"],
        (
            "🔗 Find papers similar to a known one:\n"
            "<code>mosaic similar 10.1234/doi</code>\n"
            "Uses OpenAlex related works and Semantic Scholar recommendations."
        ),
    ),
    (
        ["bib", "bibtex", "bibliography", "from file", "--from"],
        (
            "📑 Batch-fetch papers from a .bib or .csv file:\n"
            "<code>mosaic get --from refs.bib</code>"
        ),
    ),
]


def faq_reply(chat_id, msg_id, text_lower):
    for keywords, reply in FAQ:
        if any(kw in text_lower for kw in keywords):
            send(chat_id, reply, reply_to=msg_id)
            return True
    return False


# ── New-member welcome ────────────────────────────────────────────────────────

def welcome(chat_id, members):
    names = ", ".join(m.get("first_name", "there") for m in members)
    send(chat_id, (
        f"👋 Welcome, <b>{html_escape(names)}</b>!\n\n"
        "This is the official MOSAIC support group.\n\n"
        "🔍 <b>MOSAIC</b> — Multi-source Scientific Article Indexer and Collector\n"
        "<i>A vivid mosaic of open scientific literature, assembled in seconds</i>\n\n"
        f"📦 <code>pipx install mosaic-search</code>\n"
        f'📘 <a href="{DOCS_URL}">Docs</a>  ·  '
        f'🐙 <a href="{GITHUB_URL}">GitHub</a>  ·  '
        "/help for bot commands"
    ))


# ── Update processing ─────────────────────────────────────────────────────────

def process(update):
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return

    chat_id = msg["chat"]["id"]
    msg_id = msg["message_id"]

    # Welcome new human members
    new_members = msg.get("new_chat_members")
    if new_members:
        humans = [m for m in new_members if not m.get("is_bot")]
        if humans:
            welcome(chat_id, humans)
        return

    text = msg.get("text", "")
    if not text:
        return

    # Commands — strip bot-name suffix (e.g. /help@mosaic_bot → /help)
    first_word = text.split()[0]
    cmd = first_word.split("@")[0].lower()
    if cmd in COMMANDS:
        COMMANDS[cmd](chat_id, msg_id)
        return

    # FAQ auto-reply (groups only, to avoid replying in private DMs)
    chat_type = msg.get("chat", {}).get("type", "")
    if chat_type in ("group", "supergroup"):
        faq_reply(chat_id, msg_id, text.lower())


# ── Offset persistence ────────────────────────────────────────────────────────

def load_offset():
    if os.path.exists(OFFSET_FILE):
        try:
            return int(open(OFFSET_FILE).read().strip())
        except ValueError:
            pass
    return None


def save_offset(offset):
    with open(OFFSET_FILE, "w") as fh:
        fh.write(str(offset))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    offset = load_offset()

    # First run: jump to the tip of the update queue without processing old messages.
    if offset is None:
        result = tg("getUpdates", {"limit": 1, "offset": -1})
        updates = result.get("result", [])
        new_offset = (updates[-1]["update_id"] + 1) if updates else 0
        save_offset(new_offset)
        print(f"First run: offset initialised to {new_offset}, no messages processed.")
        return

    result = tg("getUpdates", {"offset": offset, "limit": 100, "timeout": 0})
    updates = result.get("result", [])

    for update in updates:
        uid = update["update_id"]
        try:
            process(update)
        except Exception as exc:
            print(f"Error on update {uid}: {exc}")
        offset = uid + 1
        save_offset(offset)

    print(f"Processed {len(updates)} update(s); offset now {offset}.")


if __name__ == "__main__":
    main()
