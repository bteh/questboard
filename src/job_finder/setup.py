"""Interactive setup wizard for new users.

Usage:
    python -m job_finder.setup
    # or via the CLI entry point:
    launchboard-setup
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

# Template profiles for common personas
PERSONAS = {
    "swe": {
        "label": "Software Engineer",
        "roles": [
            "software engineer",
            "backend engineer",
            "full stack developer",
            "frontend engineer",
        ],
        "keywords": ["python", "javascript", "react", "node", "aws"],
        "level": "mid",
        "weights": {
            "technical_skills": 0.30,
            "leadership_signal": 0.10,
            "comp_potential": 0.10,
            "platform_building": 0.10,
            "company_trajectory": 0.10,
            "culture_fit": 0.20,
            "career_progression": 0.10,
        },
    },
    "data": {
        "label": "Data Engineer / Analyst",
        "roles": [
            "data engineer",
            "analytics engineer",
            "data analyst",
            "data scientist",
        ],
        "keywords": ["sql", "python", "dbt", "spark", "airflow", "snowflake"],
        "level": "mid",
        "weights": {
            "technical_skills": 0.25,
            "leadership_signal": 0.10,
            "comp_potential": 0.12,
            "platform_building": 0.13,
            "company_trajectory": 0.10,
            "culture_fit": 0.15,
            "career_progression": 0.15,
        },
    },
    "leader": {
        "label": "Engineering Manager / Director",
        "roles": [
            "engineering manager",
            "director of engineering",
            "VP engineering",
            "head of engineering",
        ],
        "keywords": ["team lead", "people management", "roadmap", "strategy"],
        "level": "manager",
        "weights": {
            "technical_skills": 0.15,
            "leadership_signal": 0.25,
            "comp_potential": 0.12,
            "platform_building": 0.10,
            "company_trajectory": 0.10,
            "culture_fit": 0.10,
            "career_progression": 0.18,
        },
    },
    "custom": {
        "label": "Custom (I'll configure manually)",
        "roles": [],
        "keywords": [],
        "level": "mid",
        "weights": {
            "technical_skills": 0.30,
            "leadership_signal": 0.10,
            "comp_potential": 0.10,
            "platform_building": 0.10,
            "company_trajectory": 0.10,
            "culture_fit": 0.20,
            "career_progression": 0.10,
        },
    },
}


def _input(prompt: str, default: str = "") -> str:
    """Read input with a default value shown in brackets."""
    suffix = f" [{default}]" if default else ""
    val = input(f"  {prompt}{suffix}: ").strip()
    return val or default


def _choice(prompt: str, options: list[str], default: int = 0) -> int:
    """Show a numbered list and return the chosen index."""
    print(f"\n  {prompt}\n")
    for i, opt in enumerate(options):
        marker = ">" if i == default else " "
        print(f"  {marker} {i + 1}) {opt}")
    while True:
        raw = input(f"\n  Choice [default: {default + 1}]: ").strip()
        if not raw:
            return default
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return idx
        except ValueError:
            pass
        print("  Invalid choice, try again.")


def _build_yaml(
    name: str,
    persona_key: str,
    roles: list[str],
    keywords: list[str],
    locations: list[str],
    level: str,
    tc: int,
    min_tc: int,
    weights: dict,
) -> str:
    """Build a profile YAML string."""
    persona = PERSONAS[persona_key]
    roles_yaml = "\n".join(f'  - "{r}"' for r in roles)
    kw_yaml = "\n".join(f'  - "{k}"' for k in keywords)
    loc_yaml = "\n".join(f'  - "{loc}"' for loc in locations)

    return f"""# Auto-generated profile for {name}
profile:
  name: "{name}"
  description: "{persona['label']} job search"
  resume_path: ""

target_roles:
{roles_yaml}

keyword_searches:
{kw_yaml}

locations:
{loc_yaml}

keywords:
  technical:
{kw_yaml}
  leadership:
    - "lead"
    - "manager"
    - "mentor"
  platform_building:
    - "greenfield"
    - "from scratch"
    - "0 to 1"
  high_comp_signals: []

scoring:
  technical_skills: {weights['technical_skills']}
  leadership_signal: {weights['leadership_signal']}
  comp_potential: {weights['comp_potential']}
  platform_building: {weights['platform_building']}
  company_trajectory: {weights['company_trajectory']}
  culture_fit: {weights['culture_fit']}
  career_progression: {weights['career_progression']}
  thresholds:
    strong_apply: 70
    apply: 55
    maybe: 40

career_baseline:
  current_title: "{persona['label']}"
  current_level: "{level}"
  current_tc: {tc}
  min_acceptable_tc: {min_tc}
  preferred_direction: "any"

compensation:
  min_base: {min_tc}
  target_total_comp: {tc}
  include_equity: true

search_settings:
  results_per_board: 25
  max_days_old: 14
  exclude_staffing_agencies: true
  country: "USA"
  ai_score_top_n: 60

job_boards:
  - "indeed"
  - "glassdoor"
  - "zip_recruiter"
  - "google"

additional_sources:
  - name: "workatastartup"
    enabled: true
  - name: "remotive"
    enabled: true
  - name: "himalayas"
    enabled: true
  - name: "weworkremotely"
    enabled: true
  - name: "hackernews"
    enabled: true
  - name: "greenhouse"
    enabled: true
  - name: "lever"
    enabled: true
  - name: "remoteok"
    enabled: true


applicant_info:
  first_name: ""
  last_name: ""
  email: ""
  phone: ""
  linkedin_url: ""

auto_apply:
  enabled: false
  dry_run: true
  methods:
    greenhouse: true
    lever: true
    linkedin_easy_apply: false
  max_applications_per_run: 5
"""


def run_setup():
    """Interactive setup wizard."""
    print()
    print("=" * 60)
    print("  Launchboard  -  Setup Wizard")
    print("=" * 60)
    print()
    print("  This will create a search profile and check your setup.")
    print("  You can always edit the generated YAML file later.")
    print()

    # 1. Profile name
    name = _input("Your name (for the profile)", os.environ.get("USER", "default"))
    profile_slug = name.lower().replace(" ", "_")

    # 2. Check if profile already exists
    config_dir = Path(__file__).resolve().parent / "config" / "profiles"
    config_dir.mkdir(parents=True, exist_ok=True)
    profile_path = config_dir / f"{profile_slug}.yaml"
    if profile_path.exists():
        overwrite = _input(f"Profile '{profile_slug}' already exists. Overwrite? (y/N)", "N")
        if overwrite.lower() != "y":
            print(f"\n  Keeping existing profile: {profile_path}")
            profile_path = None

    # 3. Persona selection
    persona_idx = _choice(
        "What kind of roles are you looking for?",
        [p["label"] for p in PERSONAS.values()],
    )
    persona_key = list(PERSONAS.keys())[persona_idx]
    persona = PERSONAS[persona_key]

    # 4. Roles
    if persona["roles"]:
        print(f"\n  Starting roles: {', '.join(persona['roles'])}")
        extra = _input("Add more roles? (comma-separated, or press Enter to skip)")
        roles = persona["roles"] + [r.strip() for r in extra.split(",") if r.strip()]
    else:
        roles_raw = _input("Enter target roles (comma-separated)")
        roles = [r.strip() for r in roles_raw.split(",") if r.strip()] or ["software engineer"]

    # 5. Keywords
    if persona["keywords"]:
        print(f"  Starting keywords: {', '.join(persona['keywords'])}")
        extra = _input("Add more keywords? (comma-separated, or press Enter)")
        keywords = persona["keywords"] + [k.strip() for k in extra.split(",") if k.strip()]
    else:
        kw_raw = _input("Enter skill keywords (comma-separated)")
        keywords = [k.strip() for k in kw_raw.split(",") if k.strip()] or ["python"]

    # 6. Locations
    print()
    location_raw = _input("Locations to search (comma-separated)", "Remote")
    locations = [loc.strip() for loc in location_raw.split(",") if loc.strip()]

    # 7. Compensation
    print()
    tc_raw = _input("Target total compensation ($)", "150000")
    tc = int(tc_raw.replace(",", "").replace("$", "").strip() or "150000")
    min_tc = int(tc * 0.7)

    # 8. Generate profile
    yaml_content = _build_yaml(
        name=name,
        persona_key=persona_key,
        roles=roles,
        keywords=keywords,
        locations=locations,
        level=persona["level"],
        tc=tc,
        min_tc=min_tc,
        weights=persona["weights"],
    )

    if profile_path:
        profile_path.write_text(yaml_content, encoding="utf-8")
        print(f"\n  Profile saved: {profile_path}")

    # 9. Check resume
    print()
    knowledge_dir = Path.cwd() / "knowledge"
    knowledge_dir.mkdir(exist_ok=True)
    resume_path = knowledge_dir / f"{profile_slug}_resume.pdf"
    if resume_path.exists():
        print(f"  Resume found: {resume_path}")
    else:
        print(f"  No resume found at: {resume_path}")
        print(f"  To enable scoring, copy your resume there:")
        print(f"    cp ~/your_resume.pdf {resume_path}")

    # 10. Check .env
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        example = Path.cwd() / ".env.example"
        if example.exists():
            shutil.copy(example, env_path)
            print(f"\n  Created .env from .env.example")
        else:
            print(f"\n  No .env file found. Create one to configure LLM.")

    # 11. Check LLM
    print()
    llm_provider = os.environ.get("LLM_PROVIDER", "")
    if llm_provider:
        print(f"  LLM provider: {llm_provider}")
    else:
        # Check if Ollama is available
        if shutil.which("ollama"):
            print("  LLM: Ollama is installed — run 'ollama pull llama3.2:3b' to enable AI")
        else:
            print("  LLM: not configured (search + basic scoring still work)")
            print("  Easiest options to enable AI:")
            print("    • Run: bash scripts/setup-ai.sh   (installs Ollama, free, private)")
            print("    • Or set LLM_PROVIDER=gemini + get a free key at https://aistudio.google.com/apikey")

    # Summary
    print()
    print("=" * 60)
    print("  Setup complete!")
    print("=" * 60)
    print()
    print("  Quick start:")
    print()
    print(f"    make dev                          # Start the web UI")
    print(f"    launchboard --profile {profile_slug}   # Run from CLI")
    print()
    print(f"  Or search without AI:")
    print(f"    make search PROFILE={profile_slug}")
    print()


if __name__ == "__main__":
    run_setup()
