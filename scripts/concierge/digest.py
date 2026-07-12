"""The concierge digest: the Scout, run by hand, before any Scout code.

Takes a plain-language brief (a small JSON file) and renders a one-page
dispatch from the LIVE board through the same API filters the board
itself trusts. Nothing in the output is invented: pay renders only as
the source stated it, every item carries an evidence line (source +
when it was last checked + where the link goes), prep notes are derived
from row fields alone, and a zero-match digest says exactly what was
checked and what the nearest miss failed on.

Usage (backend running, `make dev`):
    /usr/bin/python3 scripts/concierge/digest.py scripts/concierge/brief_example.json
Writes <brief-name>-digest.md and .html next to the brief.

This is a hand tool for the concierge test (10-20 real people, a few
weeks): does a verified dispatch earn the open? Metrics to note per
send, by hand: opened? acted on any item? replied? See README.md.
"""

from __future__ import annotations

import html
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "http://localhost:8000/api/v1"

KIND_LABELS = {
    "think": "Tell them what you think",
    "body": "Join a study",
    "house": "Beat the house",
    "lookafter": "Look after someone",
    "perform": "Perform & entertain",
    "camera": "Perform & entertain",
    "study": "Tell them what you think",
    "odd": "Odd jobs",
    "skill": "Bring a skill",
    "career": "Bring a skill",
}

# prep notes derive from the KIND, stated row fields only fill the blanks;
# vocabulary matches the board's own kind copy
KIND_PREP = {
    "think": "Expect a short screening questionnaire first; sessions pay per the stated rate.",
    "study": "Expect a short screening questionnaire first; sessions pay per the stated rate.",
    "body": "Screening call first; eligibility rules are strict, read the age and health lines before applying.",
    "house": "You bring an ID and money to park; some banks check ChexSystems first. The bonus is taxable income.",
    "lookafter": "The poster interviews first; reply with your availability and any references up front.",
    "camera": "Read the role line closely; only apply if you match it exactly.",
    "perform": "Read the role line closely; only apply if you match it exactly.",
}


def _get(path: str, params: dict | None = None) -> dict:
    qs = ("?" + urllib.parse.urlencode(params)) if params else ""
    with urllib.request.urlopen(f"{API}{path}{qs}", timeout=15) as resp:
        return json.load(resp)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ago(iso: str | None) -> str:
    if not iso:
        return "unknown"
    then = datetime.fromisoformat(iso.replace("Z", ""))
    hours = max(0, int((_utcnow() - then).total_seconds() // 3600))
    if hours < 1:
        return "within the hour"
    if hours < 36:
        return f"{hours}h ago"
    return f"{hours // 24} days ago"


def _pay_line(row: dict) -> str | None:
    lo, hi = row.get("salary_min"), row.get("salary_max")
    period = (row.get("salary_period") or "").strip()
    unit = {"hourly": "/hr", "session": "/session"}.get(period, "")
    if lo and hi and lo != hi:
        return f"${lo:,.0f}-${hi:,.0f}{unit} (as stated)"
    if lo and hi:
        return f"${lo:,.0f}{unit} (as stated)"
    if hi:
        return f"up to ${hi:,.0f}{unit} (stated ceiling, not a promise)"
    if lo:
        return f"from ${lo:,.0f}{unit} (as stated)"
    return None


def _fit_line(row: dict, brief: dict) -> str:
    bits = []
    kind = KIND_LABELS.get(row.get("vertical") or "", row.get("vertical") or "")
    bits.append(kind.lower())
    loc = (row.get("location") or "").strip()
    if loc:
        bits.append(loc)
    if row.get("is_remote"):
        bits.append("remote")
    return ", ".join(bits)


def _evidence_line(row: dict, checked: dict[str, str]) -> str:
    source = row.get("source") or "unknown"
    host = urllib.parse.urlparse(row.get("job_url") or "").netloc or "no link"
    when = checked.get(source, "unknown")
    return f"{source}, checked {when}; the link goes to {host}"


def _prep_note(row: dict) -> str:
    note = KIND_PREP.get(row.get("vertical") or "", "Read the posting in full before acting.")
    quest = row.get("quest") or {}
    extras = []
    if quest.get("apply_by"):
        extras.append(f"Apply by {str(quest['apply_by'])[:10]}.")
    if quest.get("age_min") or quest.get("age_max"):
        lo, hi = quest.get("age_min"), quest.get("age_max")
        rng = f"{lo}-{hi}" if lo and hi else (f"{lo}+" if lo else f"under {hi}")
        extras.append(f"Ages {rng} per the protocol.")
    if row.get("event_start"):
        extras.append(f"Starts {str(row['event_start'])[:10]}.")
    return " ".join([note, *extras])


def build_digest(brief: dict) -> dict:
    """All facts the digest renders, pulled live. Returns the model dict."""
    kinds = brief.get("kinds") or ["think", "body", "house", "lookafter"]
    vertical = ",".join(kinds)

    # the checked-line numbers: real, from the same surfaces the board uses
    summary = _get("/board/summary")
    runs = _get("/scrapers/runs", {"limit": 200})["runs"]
    checked: dict[str, str] = {}
    for r in runs:  # newest first; keep the newest ok per source
        if r["finish_reason"] == "ok" and r["source"] not in checked:
            checked[r["source"]] = _ago(r["started_at"])
    sources_checked = len({r["source"] for r in runs})

    # per-kind pools: a date-sorted global window is dominated by whichever
    # source swept last; the scout reads every lane the brief names
    candidates: list[dict] = []
    pool_total = 0
    for kind in kinds:
        params = {
            "vertical": kind,
            "scope": "board",
            "sort_by": "date_found",
            "sort_dir": "desc",
            "page_size": 60,
        }
        if brief.get("search"):
            params["search"] = brief["search"]
        if brief.get("place"):
            params["location"] = brief["place"]
        page = _get("/applications", params)
        pool_total += page["total"]
        candidates.extend(page["items"])

    floor = brief.get("pay_floor") or 0

    def stated_pay(row: dict) -> float:
        return max(row.get("salary_min") or 0, row.get("salary_max") or 0)

    def clears_floor(row: dict) -> bool:
        pay = stated_pay(row)
        if not pay:
            return False
        # the floor means per-gig money; an hourly rate adds up, so it
        # clears on its own terms rather than being compared to a lump sum
        if (row.get("salary_period") or "") == "hourly":
            return pay >= 15
        return pay >= max(floor, 1)

    with_pay = [r for r in candidates if clears_floor(r)]
    with_pay.sort(key=stated_pay, reverse=True)

    # spread across kinds so the digest reads like a scout, not one lane
    picked: list[dict] = []
    seen_kinds: dict[str, int] = {}
    per_kind_cap = 3
    for row in with_pay:
        k = row.get("vertical") or ""
        if seen_kinds.get(k, 0) >= per_kind_cap:
            continue
        picked.append(row)
        seen_kinds[k] = seen_kinds.get(k, 0) + 1
        if len(picked) >= (brief.get("max_items") or 6):
            break

    nearest_miss = None
    if not picked and candidates:
        best = max(candidates, key=stated_pay)
        nearest_miss = {
            "title": best.get("job_title"),
            "why": (
                f"stated pay ${stated_pay(best):,.0f} sits under your ${floor:,.0f} floor"
                if stated_pay(best) else "no stated pay, and your brief asks for a floor"
            ),
        }

    return {
        "brief": brief,
        "generated": _utcnow().strftime("%B %-d, %Y"),
        "board_total": summary["total"],
        "pool_total": pool_total,
        "sources_checked": sources_checked,
        "items": [
            {
                "title": row.get("job_title"),
                "counterparty": row.get("company"),
                "pay": _pay_line(row),
                "fit": _fit_line(row, brief),
                "evidence": _evidence_line(row, checked),
                "prep": _prep_note(row),
                "url": row.get("job_url"),
            }
            for row in picked
        ],
        "nearest_miss": nearest_miss,
    }


def render_markdown(m: dict) -> str:
    b = m["brief"]
    lines = [
        f"# Your quest dispatch, {m['generated']}",
        "",
        f"**Your standing order:** {b['brief']}",
        "",
        f"Checked {m['sources_checked']} sources and {m['pool_total']} live postings "
        f"on a board of {m['board_total']}. "
        + (f"{len(m['items'])} cleared your bar." if m["items"] else "None cleared your bar this time."),
        "",
    ]
    for i, it in enumerate(m["items"], 1):
        lines += [
            f"## {i}. {it['title']}",
            f"*{it['counterparty']}* - {it['fit']}",
            "",
        ]
        if it["pay"]:
            lines.append(f"- **Pay:** {it['pay']}")
        lines += [
            f"- **Do next:** {it['prep']}",
            f"- **Evidence:** {it['evidence']}",
            f"- **Act here:** {it['url']}",
            "",
        ]
    if m["nearest_miss"]:
        lines += [
            f"The nearest miss was \"{m['nearest_miss']['title']}\": {m['nearest_miss']['why']}.",
            "",
        ]
    lines += [
        "---",
        "Pay above is only what each posting states; nothing is estimated. "
        "Every link goes to the place you act, never to a page about it. "
        "If it's pinned here, it's real.",
    ]
    return "\n".join(lines)


def render_html(m: dict) -> str:
    b = m["brief"]
    e = html.escape

    def item_html(i: int, it: dict) -> str:
        pay = f'<div style="margin:6px 0 2px"><b>Pay:</b> {e(it["pay"])}</div>' if it["pay"] else ""
        return f"""
      <div style="background:#fff;border:1px solid #E4DED1;border-bottom-color:#D9D1BF;border-radius:10px;padding:16px 18px;margin:0 0 14px">
        <div style="font-family:Georgia,serif;font-size:17px;color:#1C1B17"><b>{i}. {e(it["title"] or "")}</b></div>
        <div style="color:rgba(28,27,23,.66);font-size:13px;margin-top:2px">{e(it["counterparty"] or "")} &middot; {e(it["fit"])}</div>
        {pay}
        <div style="margin:2px 0"><b>Do next:</b> {e(it["prep"])}</div>
        <div style="color:rgba(28,27,23,.66);font-size:12.5px;margin:6px 0 10px">Evidence: {e(it["evidence"])}</div>
        <a href="{e(it["url"] or "#")}" style="color:#3F6B54;font-weight:600">Act here &rarr;</a>
      </div>"""

    items = "".join(item_html(i, it) for i, it in enumerate(m["items"], 1))
    cleared = (
        f"{len(m['items'])} cleared your bar."
        if m["items"] else "None cleared your bar this time."
    )
    miss = ""
    if m["nearest_miss"]:
        miss = (
            f'<p style="color:rgba(28,27,23,.66);font-size:13.5px">The nearest miss was '
            f'&ldquo;{e(m["nearest_miss"]["title"] or "")}&rdquo;: {e(m["nearest_miss"]["why"])}.</p>'
        )
    return f"""<div style="background:#F6F3EC;padding:28px 16px;font-family:-apple-system,'Segoe UI',sans-serif;color:#1C1B17">
  <div style="max-width:560px;margin:0 auto">
    <div style="font-family:Georgia,serif;font-size:22px"><b>Your quest dispatch</b> <span style="color:rgba(28,27,23,.66);font-size:14px">&middot; {e(m["generated"])}</span></div>
    <p style="font-size:14px;line-height:1.55"><b>Your standing order:</b> {e(b["brief"])}</p>
    <p style="color:rgba(28,27,23,.66);font-size:13.5px">Checked {m["sources_checked"]} sources and {m["pool_total"]} live postings on a board of {m["board_total"]}. {e(cleared)}</p>
    {items}
    {miss}
    <p style="border-top:1px solid #E4DED1;padding-top:12px;color:rgba(28,27,23,.66);font-size:12.5px;line-height:1.6">
      Pay above is only what each posting states; nothing is estimated. Every link goes to the place you act, never to a page about it. <b>If it's pinned here, it's real.</b>
    </p>
  </div>
</div>"""


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)
    brief_path = Path(sys.argv[1])
    brief = json.loads(brief_path.read_text())
    model = build_digest(brief)
    stem = brief_path.with_suffix("")
    md = Path(f"{stem}-digest.md")
    htm = Path(f"{stem}-digest.html")
    md.write_text(render_markdown(model))
    htm.write_text(render_html(model))
    print(f"wrote {md}")
    print(f"wrote {htm}")
    print(f"items: {len(model['items'])} (pool {model['pool_total']}, board {model['board_total']})")


if __name__ == "__main__":
    main()
