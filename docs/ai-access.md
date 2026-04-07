# AI Access Policy

_Last updated: April 6, 2026_

Launchboard is now a **desktop-first, open-source** product. That changes which AI access patterns are practical and which ones we should avoid.

## Supported today

These are the supported AI connection paths for Launchboard desktop:

- **Gemini API key**
- **OpenAI API key**
- **Anthropic API key**
- **Ollama / local model**
- **Your own local OpenAI-compatible endpoint**

This is the product-safe baseline because it is easy to explain, easy to support, and keeps the app honest about how it connects to models.

## Not supported today

These are **not** supported as first-class Launchboard features right now:

- **Use my ChatGPT account**
- **Use my Claude account**

The reason is not just implementation effort. It is policy clarity.

## Why ChatGPT account login is not a supported path

OpenAI officially separates **ChatGPT billing** from **API billing**:

- [Billing settings in ChatGPT vs Platform](https://help.openai.com/en/articles/9039756-billing-settings-in-chatgpt-vs-platform)
- [How can I move my ChatGPT subscription to the API?](https://help.openai.com/en/articles/8156019)

OpenAI also officially supports **Codex** local tooling with ChatGPT plans:

- [Using Codex with your ChatGPT plan](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan)
- [Codex CLI](https://developers.openai.com/codex/cli)

That means local account-backed use is becoming more realistic, but it is still different from Launchboard directly signing into a ChatGPT subscription as if it were normal app API access.

## Why Claude account login is not a supported path

Anthropic also separates **Claude subscriptions** from **API usage**:

- [Why do I have to pay separately for the Claude API and Console?](https://support.anthropic.com/en/articles/9876003-i-subscribe-to-a-paid-claude-ai-plan-why-do-i-have-to-pay-separately-for-api-usage-on-console)

Anthropic does officially support **Claude Code** with Pro/Max:

- [Using Claude Code with your Pro or Max plan](https://support.anthropic.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan)

But that still does **not** mean Launchboard should present Claude account login as a normal supported product feature.

## What open-source tools are doing

There are active desktop/local tools exploring account-backed access:

- [OpenCode](https://opencode.ai/) documents ChatGPT and Claude-related provider paths in a local tool context.
- [ChatMock](https://github.com/RayBytes/ChatMock) exposes a local OpenAI-compatible server backed by OpenAI/Codex login.

Those examples are useful product references, but they are **not** the same as a cleanly supported Launchboard feature.

## Product decision

Launchboard should use this rule set:

- **Supported now:** API keys, Ollama, custom local endpoints
- **Possible later:** desktop-only experimental ChatGPT-account integration if it can be built on an official local OpenAI path
- **Not for now:** public Claude-account integration as a normal product option

This keeps the desktop app useful today without making policy promises we cannot defend.
