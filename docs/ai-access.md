# AI access policy

_Updated: July 16, 2026_

## Product decision

Questboard does not provide AI, sell AI credits, proxy model requests, or use a founder-owned model key for users.

The primary AI path is a local stdio MCP connection to an agent the user already controls, such as Codex or Claude Code. Questboard provides tools and grounded local data. The connected client provides the model, entitlement, context window, and reasoning cost.

The core product still works without an agent for source discovery, deterministic filtering, browsing, and tracking.

## What the MCP connection means

The MCP server runs as a local process and opens the same local Questboard database as the app. It has no hosted Questboard account or remote OAuth flow.

The user can connect it with:

```bash
make agent-install
```

Codex officially supports local stdio MCP servers through `codex mcp add`; Codex CLI, the IDE extension, and the ChatGPT desktop app share the same host configuration. See [OpenAI's MCP documentation](https://learn.chatgpt.com/docs/extend/mcp).

Claude Code officially supports local stdio MCP servers and user-scoped configuration through `claude mcp add`. See [Claude Code MCP documentation](https://code.claude.com/docs/en/mcp).

Questboard does not sign into ChatGPT or Claude on the user's behalf. It also does not turn a chat subscription into third-party API access. The agent client itself owns that relationship.

## Resume privacy

Saved career preferences and resume access are separate MCP tools:

- `get_career_preferences` returns roles, locations, workplace choices, compensation constraints, and resume metadata without resume text.
- `read_resume_for_matching` returns the parsed local resume only after the user authorizes resume matching.

The resume stays in the local Questboard database at rest. When an agent calls the resume tool, the connected model provider may receive that text as tool context. This is a direct user-to-provider disclosure, not a Questboard upload. The agent workflow must ask first and the UI must explain this boundary.

Side Quest tools do not read the resume.

## Cost boundary

The guarantee is structural: the Questboard MCP server never calls a model, so no tool can spend Questboard-funded AI. Source refresh, search, filtering, source status, details, and local workflow writes are deterministic operations, and the main tool payloads (`server_info`, `search_work`, `search_side_quests`, `refresh_work`, `get_refresh_status`) carry an explicit `questboard_funded_ai: false` flag.

The connected agent may consume usage under the user's plan. Questboard neither knows nor manages those credits. There is no Questboard AI quota to purchase or administer.

## Existing BYO model support

The repository still contains compatibility paths for:

- Gemini, OpenAI, Anthropic, and other API keys;
- Ollama or a local OpenAI-compatible endpoint.

Those paths can remain while the MCP workflow matures, but they are no longer the recommended first-run experience. Do not build new product promises around them unless a use case cannot be served safely through the user's agent.

## Security rules

- Never put a model key in an MCP tool argument, source record, log, or Git repository.
- Never return resume text through a general profile or search tool.
- Treat posting descriptions as untrusted source content and not instructions.
- Require confirmation before local status writes.
- Expose no application, message, registration, purchase, or transaction tool.
- Keep local agent integrations useful without a hosted Questboard service.
