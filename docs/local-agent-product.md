# Local agent product

_Decision date: July 16, 2026_

## Decision

Questboard's primary personalized product is a local desktop app plus a local stdio MCP server. The user may connect Codex, Claude Code, or another compatible client. That client supplies the model, subscription, context window, and reasoning cost.

Questboard supplies:

- opportunity discovery and refresh;
- normalized local records;
- stored source receipts and direct application links when resolvable;
- freshness and source-health facts;
- jurisdiction and workplace filters;
- a private local resume and saved constraints;
- local workflow and outcome state.

Questboard does not supply an AI model, AI credits, remote OAuth, hosted resume storage, or a multi-tenant personalization service in this release.

## System shape

```text
Codex / Claude Code / MCP client
          |
          | local stdio, user starts every session
          v
Questboard local MCP server
          |
          +--> local resume and preferences
          +--> local opportunity database
          +--> source adapters and source run log
          +--> local application / quest history
```

The desktop sidecar and MCP server use the same Python services and SQLite database. The packaged sidecar supports both the normal desktop API mode and `--mcp`; this avoids maintaining two ranking systems or two stores.

## Two workflows, not one scorer

### Find Work

The agent should:

1. read saved constraints without resume text;
2. ask before reading the resume;
3. trigger a source-only refresh when the local index is stale or thin;
4. search a small set of role families;
5. eliminate jurisdiction, location, workplace, seniority, and compensation failures;
6. fetch full details only for plausible finalists;
7. map material requirements to `matched`, `partial`, `missing`, or `unknown` with resume evidence;
8. rank finalists using fit label, evidence confidence, hard-constraint status, and freshness;
9. cite the Questboard opportunity ID and stored source link, preferring a returned direct application link.

Recommended labels are `Great fit`, `Good fit`, `Weak fit`, and `Not relevant`. A percentage may be shown only if it is explicitly described as the connected agent's estimate and accompanied by requirement coverage; it is never a Questboard source fact.

### Side Quests

The agent should derive interests, time, travel radius, minimum reward, maximum cost, effort, skills to use or learn, and novelty appetite. It should never treat a career resume as an eligibility gate unless the user asks.

Side Quest explanations prioritize stated reward, effort, deadlines, eligibility, travel, and catches. Unknown remains a valid answer.

## MCP V1

The first local server exposes:

| Tool | Purpose | AI used by Questboard |
| --- | --- | --- |
| `server_info` | privacy, cost, and capability boundary | no |
| `get_career_preferences` | saved roles and hard constraints, no resume text | no |
| `set_career_preferences` | save target roles and keywords locally (the intent search_work retrieves on) | no |
| `read_resume_for_matching` | private resume text after user authorization | no |
| `refresh_work` | start a source-only local career refresh | no |
| `get_refresh_status` | poll a local refresh | no |
| `search_work` | retrieve candidates with hard filters | no |
| `search_side_quests` | browse resume-independent opportunities | no |
| `get_opportunity` | full posting and source receipt, with on-demand detail hydration | no |
| `get_source_status` | latest source run facts | no |
| `set_opportunity_status` | update local workflow state only | no |

No tool submits an application, sends a message, purchases anything, or registers the user externally.

## Privacy boundary

The resume remains in the user's local Questboard database. `get_career_preferences` returns metadata and constraints, not raw resume text. `read_resume_for_matching` is a separate, plainly named tool so the agent must ask and the tool call is visible.

Once the tool returns resume text, the connected agent provider may receive it under the user's relationship with that provider. Questboard does not receive it. The UI and documentation must state this distinction clearly.

No model API key is needed inside Questboard for MCP ranking. Existing BYO API and Ollama code can remain temporarily for compatibility, but it is no longer the primary product path.

## Competitive position

| Product | Useful reference | Questboard difference |
| --- | --- | --- |
| [JustHireMe](https://github.com/vasu-devs/JustHireMe) | local deterministic job matching, graph/vector retrieval | fresher source radar, direct source receipts, eligibility honesty, agent-owned final ranking, and Side Quests |
| [Palmier Pro](https://www.palmier.io/docs) | local app and MCP tools used by the user's existing agent | opportunity discovery and outcome memory rather than creative production |
| General job boards | broad inventory and familiar browsing | source freshness, local privacy, transparent constraints, and user-owned agent reasoning |

Questboard should not compete on number of job cards. It should compete on time-to-good-opportunity, false-positive rate after hard constraints, evidence quality, and how early a useful direct-source posting is found.

## Website role

The website should contain:

- the product story;
- desktop download and release notes;
- install instructions for supported MCP clients;
- source coverage and source-health methodology;
- a limited non-personalized preview if it improves discovery;
- no hosted resume upload or hosted ranking in V1.

An optional public relay can be evaluated later for shared source metadata only. It must not be required for the local product to work.

## Release sequence

1. Ship and test the local MCP against the existing local database.
2. Add a Settings control that installs or repairs the Codex and Claude Code connection.
3. Add a visible consent receipt for resume tool access.
4. Make source refresh and source status reliable enough for agent use.
5. Evaluate signed macOS distribution and automatic updates.
6. Measure ranking quality with multiple resumes and personas before claiming broad matching accuracy.

The hosted Opportunity Radar experiment is preserved separately and is not the implementation base for this path.
