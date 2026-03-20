---
title: Telegram Community
---

# Telegram Community

MOSAIC has a Telegram presence with two connected spaces:

| | Purpose |
|---|---|
| **Channel** [`@mosaic_search`](https://t.me/mosaic_search) | Read-only announcements: releases, CI events, weekly digest |
| **Support Group** [`@mosaic_search_support`](https://t.me/mosaic_search_support) | Interactive support, questions, discussion |

The channel and group are linked — every channel post gets a comments thread in the group.

---

## For users

### Joining

- **Announcements only** → join the channel: [t.me/mosaic_search](https://t.me/mosaic_search)
- **Ask questions / get help** → join the group: [t.me/mosaic_search_support](https://t.me/mosaic_search_support)

### Support bot

The group has an automated support bot. It responds instantly to commands and common questions.

#### Commands

| Command | What it returns |
|---|---|
| `/help` | List of all commands |
| `/install` | Installation instructions (`pipx`, `pip`) |
| `/version` | Latest release version from PyPI |
| `/docs` | Link to the documentation |
| `/sources` | All 21 supported sources, grouped by auth requirement |
| `/changelog` | Last 3 release notes from GitHub |
| `/bug` | How to file a bug report (links to GitHub issue template) |
| `/roadmap` | Open milestones and planned enhancements from GitHub |

Commands work in the group and in private chat with the bot.

#### FAQ auto-reply

The bot also recognises common questions in plain text and replies automatically. Topics covered:

- Installation (`pipx`, `pip install`)
- API keys — which sources need them and how to get free ones
- Proxy / firewall / timeout issues
- Zotero integration
- Obsidian integration
- PDF download (`--pdf`, open-access)
- Configuration (`mosaic config --show`)
- Finding similar papers (`mosaic similar`)
- Batch download from `.bib` / `.csv` files

#### Welcome message

New members receive an automatic welcome with install instructions and links.

---

## For maintainers

This section documents the Telegram infrastructure so it can be understood, updated, and reproduced without exposing any credentials.

### Overview

```
┌─────────────────────────┐     ┌──────────────────────────┐
│   GitHub Actions (CI)   │     │  Cloudflare Worker       │
│                         │     │  mosaic-bot              │
│  telegram-release.yml   │────▶│                          │
│  telegram-push.yml      │     │  Receives webhook from   │
│  telegram-pr.yml        │     │  Telegram instantly,     │
│  telegram-issues.yml    │     │  handles commands, FAQ,  │
│  telegram-weekly.yml    │     │  and welcome events      │
└─────────────────────────┘     └──────────────────────────┘
          │                                  ▲
          │ sendMessage                      │ POST (webhook)
          ▼                                  │
   ┌─────────────┐                   ┌───────────────┐
   │  @mosaic    │◀── linked ───────▶│ @mosaic       │
   │  _channel   │                   │ _support      │
   └─────────────┘                   └───────────────┘
```

### Channel notifications (CI-driven)

Five GitHub Actions workflows send messages to the **channel** automatically:

| Workflow | Trigger | What it sends |
|---|---|---|
| `telegram-release.yml` | GitHub Release published | Release announcement with version, changelog excerpt, PyPI and docs links |
| `telegram-push.yml` | Push to `main` | Commit list with authors and diff link |
| `telegram-pr.yml` | PR opened / closed / merged | PR title, status, and link |
| `telegram-issues.yml` | Issue opened / closed / reopened | Issue title, excerpt, and link |
| `telegram-weekly.yml` | Every Monday 08:00 UTC | Weekly digest: commits, merged PRs, issue stats |

All five use only Python stdlib (`urllib`, `json`) — no external dependencies. The bot token and channel ID are read from GitHub secrets at runtime.

### Support bot (webhook-driven)

The support bot lives in `bot/worker.js` and runs on Cloudflare Workers.

#### Architecture

```
User sends message in @mosaic_search_support
        │
        ▼
Telegram servers POST the update to the Worker URL
        │
        ▼
Worker verifies X-Telegram-Bot-Api-Secret-Token header
        │  (rejects with 401 if token doesn't match)
        ▼
Worker returns 200 OK immediately
        │
        ▼  (ctx.waitUntil — background)
Worker processes the update:
  • Command? → call the appropriate handler
  • Plain text in a group? → check FAQ keyword list
  • new_chat_members event? → send welcome message
        │
        ▼
Worker calls Telegram sendMessage API → reply appears instantly
```

#### Files

| File | Purpose |
|---|---|
| `bot/worker.js` | Cloudflare Worker — all bot logic (commands, FAQ, welcome) |
| `bot/bot.py` | Equivalent Python script — reference implementation and polling fallback |
| `wrangler.toml` | Cloudflare Worker configuration (entry point, name, compatibility date) |
| `.github/workflows/deploy-worker.yml` | CI workflow — deploys the worker and re-registers the Telegram webhook |

#### Deploy workflow

The deploy workflow (`deploy-worker.yml`) fires on:
- Push to `main` when `bot/worker.js`, `wrangler.toml`, or the workflow file itself changes
- Manual `workflow_dispatch`

Steps:
1. Checkout the repo
2. `npm install -g wrangler`
3. `wrangler deploy` — uploads `bot/worker.js` to Cloudflare
4. `wrangler secret put` — pushes `TELEGRAM_BOT_TOKEN` and `WEBHOOK_SECRET` into the Worker environment
5. Python script calls `setWebhook` to register the Worker URL with Telegram

#### Required secrets and variables

Stored in **GitHub → Settings → Secrets and variables → Actions**. No credentials are stored in the repository.

**Secrets:**

| Name | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather — shared by channel workflows and the Worker |
| `TELEGRAM_CHANNEL_ID` | Numeric channel ID used by the five channel notification workflows |
| `CF_API_TOKEN` | Cloudflare API token with *Workers Scripts: Edit* permission |
| `CF_ACCOUNT_ID` | Cloudflare account ID — prevents wrangler from calling `/memberships` |
| `WEBHOOK_SECRET` | Arbitrary random string; set on `setWebhook` and verified by the Worker |

**Variables:**

| Name | Description |
|---|---|
| `CF_WORKER_URL` | Deployed Worker URL (e.g. `https://mosaic-bot.<account>.workers.dev`) — set after first deploy |

#### Updating the bot

To add a command, change an FAQ reply, or modify the welcome message:

1. Edit `bot/worker.js`
2. Commit and push to `main`
3. The deploy workflow fires automatically — the new version is live in under a minute

#### Re-registering the webhook

The webhook is re-registered automatically on every deploy. To force re-registration without changing bot logic, run the deploy workflow manually via **Actions → Deploy Telegram Bot Worker → Run workflow**.

#### Security notes

- The Worker rejects all requests that do not carry the correct `X-Telegram-Bot-Api-Secret-Token` header — only Telegram servers can trigger it
- `WEBHOOK_SECRET` and `TELEGRAM_BOT_TOKEN` are stored as Cloudflare Worker secrets (encrypted at rest, never exposed in logs)
- No credentials appear in `wrangler.toml` or any tracked file
- The `CF_API_TOKEN` has the minimum required scope (*Workers Scripts: Edit*); it cannot read DNS, billing, or other account data

#### Fallback: polling mode

`bot/bot.py` is a pure-Python (stdlib only) equivalent of the worker. It uses `getUpdates` polling instead of webhooks. To switch back to polling mode:

1. Call `deleteWebhook` to deregister the current webhook
2. Run `bot/bot.py` on any machine with `TELEGRAM_BOT_TOKEN` set
3. Or restore the `telegram-bot.yml` workflow (see git history) for scheduled polling via GitHub Actions
