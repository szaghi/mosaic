---
title: Telegram
---

# Telegram

| Space | For |
|---|---|
| Channel [`@mosaic_search`](https://t.me/mosaic_search) | Announcements: releases, pushes, pull requests, issues, a weekly digest. Read-only. |
| Group [`@mosaic_search_support`](https://t.me/mosaic_search_support) | Questions, help, discussion. |

The two are linked: each channel post has a comment thread in the group.

## The support bot

A bot answers in the group and in a private chat with it.

| Command | Reply |
|---|---|
| `/help` | the list of commands |
| `/install` | installation with pipx and pip |
| `/version` | the latest release on PyPI |
| `/docs` | a link to this documentation |
| `/sources` | the sources, grouped by the authentication they need |
| `/changelog` | the last three release notes from GitHub |
| `/bug` | how to file a bug report |
| `/roadmap` | open milestones and planned enhancements |

In the group, the bot also answers plain-text questions it recognises: installation, API keys, proxies and
timeouts, Zotero, Obsidian, PDF downloads, configuration, similar papers, bulk downloads from `.bib` and `.csv`. It
greets new members with installation instructions and links.

## For maintainers

The channel posts come from GitHub Actions; the bot is a Cloudflare Worker that Telegram calls on every message.

```
GitHub Actions (telegram-*.yml) ──sendMessage──▶ channel ◀── linked ──▶ group
                                                                          │ webhook POST
                                                     Cloudflare Worker ◀──┘ (bot/worker.js)
```

### Channel workflows

| Workflow | Trigger | Post |
|---|---|---|
| `telegram-release.yml` | a GitHub release is published | version, changelog excerpt, PyPI and docs links |
| `telegram-push.yml` | push to `main` | the commits, their authors, the diff link |
| `telegram-pr.yml` | pull request opened, closed, merged | title, status, link |
| `telegram-issues.yml` | issue opened, closed, reopened | title, excerpt, link (pull requests are filtered out) |
| `telegram-weekly.yml` | Mondays 08:00 UTC | commits, merged pull requests, issue counts of the week |

They use the Python standard library only, and read the bot token and channel ID from GitHub secrets.

### The bot

| File | Role |
|---|---|
| `bot/worker.js` | the Worker: commands, FAQ answers, welcome messages |
| `bot/bot.py` | the same bot in standard-library Python, polling `getUpdates`: the fallback |
| `wrangler.toml` | Worker configuration |
| `.github/workflows/deploy-worker.yml` | deploys the Worker and registers the webhook |

The Worker checks the `X-Telegram-Bot-Api-Secret-Token` header (401 when it does not match), answers 200 at once,
and handles the update in the background (`ctx.waitUntil`).

`deploy-worker.yml` runs on a push to `main` that changes `bot/worker.js`, `wrangler.toml` or the workflow, and on
demand (Actions, Deploy Telegram Bot Worker, Run workflow). It runs `wrangler deploy`, stores `TELEGRAM_BOT_TOKEN`
and `WEBHOOK_SECRET` as Worker secrets, and calls `setWebhook` with the Worker URL. To change the bot, edit
`bot/worker.js` and push.

Repository secrets (Settings, Secrets and variables, Actions):

| Secret | Use |
|---|---|
| `TELEGRAM_BOT_TOKEN` | the bot token from @BotFather, for the workflows and the Worker |
| `TELEGRAM_CHANNEL_ID` | the channel the workflows post to |
| `CF_API_TOKEN` | Cloudflare token with Workers Scripts: Edit, nothing more |
| `CF_ACCOUNT_ID` | the Cloudflare account, so wrangler does not look it up |
| `WEBHOOK_SECRET` | a random string, given to `setWebhook` and checked by the Worker |

and one variable, `CF_WORKER_URL`, the Worker's URL, set after the first deploy. No credential is in a tracked
file.

To fall back to polling: call `deleteWebhook`, then run `bot/bot.py` with `TELEGRAM_BOT_TOKEN` set.
