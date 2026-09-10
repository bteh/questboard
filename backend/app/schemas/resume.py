from __future__ import annotations

from pydantic import BaseModel, Field


class ResumeStatus(BaseModel):
    profile: str
    exists: bool = False
    filename: str = ""
    file_size: int = 0
    path: str = ""


class AgentConsentStatus(BaseModel):
    """Whether the connected agent may read the local resume."""

    granted: bool = False
    granted_at: str | None = None
    expires_at: str | None = None


class AgentConsentRequest(BaseModel):
    grant: bool
    ttl_hours: int | None = None


class AgentClientStatus(BaseModel):
    """One MCP assistant (Claude Code, Codex): installed on this machine, and
    whether Questboard's local MCP server is registered with it."""

    id: str
    name: str
    installed: bool = False
    connected: bool = False
    restart_required: bool = False


class AgentClientsResponse(BaseModel):
    clients: list[AgentClientStatus] = Field(default_factory=list)


class AgentConnectRequest(BaseModel):
    client: str


class AgentRunRequest(BaseModel):
    """Ask the connected assistant to run a named task headlessly. The task id
    (not a free-form prompt) is what the client sends; the server owns the
    actual prompt and the tool allow-list."""

    client: str = "claude"
    task: str = "find_and_rank"


class AgentRunResponse(BaseModel):
    ok: bool = False
    result: str = ""
    error: str = ""
    cost_usd: float | None = None
    num_turns: int | None = None


class AgentIntentRequest(BaseModel):
    """The person is about to run a task by hand (a pasted prompt in Claude
    Desktop or Codex), so the tools treat it as asked-for, same as the in-app
    run."""

    task: str


class AgentIntentResponse(BaseModel):
    task: str
    marked: bool = True


class ResumeAnalysisSummary(BaseModel):
    """Summary of what resume analysis extracted, echoed in the upload response."""

    skills: list[str] = Field(default_factory=list)
    suggested_target_roles: list[str] = Field(default_factory=list)
    suggested_keywords: list[str] = Field(default_factory=list)
    current_title: str = ""
    seniority: str = ""
    certifications: list[str] = Field(default_factory=list)
    education: list[dict] = Field(default_factory=list)


class ResumeUploadResponse(BaseModel):
    profile: str
    filename: str
    message: str = "Resume uploaded successfully"
    parse_status: str = "ok"  # "ok" | "error"
    parse_code: str | None = None  # "SCANNED_PDF" | None
    analysis_status: str = "skipped_no_llm"  # "completed" | "skipped_no_llm" | "analysis_error" | "failed"
    analysis: ResumeAnalysisSummary | None = None


class AgentProgressStep(BaseModel):
    """One MCP tool call the running assistant has made."""

    tool: str
    at: str = ""
    # The run polls get_refresh_status on a loop; repeats collapse into a count
    # rather than filling the trail with identical rows.
    count: int = 1


class AgentProgressResponse(BaseModel):
    steps: list[AgentProgressStep] = Field(default_factory=list)
    # Plain words for the last real step, so the board never has to guess.
    phase: str = "Starting up"


class RoleProposal(BaseModel):
    """A role change the connected assistant suggested; not yet applied."""

    id: int
    workspace_id: str | None = None
    base_roles: list[str] = Field(default_factory=list)
    proposed_roles: list[str] = Field(default_factory=list)
    proposed_keywords: list[str] = Field(default_factory=list)
    rationale: str = ""
    status: str = "pending"
    created_at: str | None = None
    decided_at: str | None = None


class RoleProposalsResponse(BaseModel):
    proposals: list[RoleProposal] = Field(default_factory=list)


class RoleProposalDecisionRequest(BaseModel):
    accept: bool


class RoleProposalDecisionResponse(BaseModel):
    """The decision plus the saved lists as they stand after it: patched on
    accept, unchanged on reject."""

    id: int
    status: str
    proposed_roles: list[str] = Field(default_factory=list)
    proposed_keywords: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    decided_at: str | None = None
