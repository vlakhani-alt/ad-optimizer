from __future__ import annotations
"""Experiment logging, outcome tracking, and reinforcement learning system.

Tracks hypotheses, generated variations, and performance patterns across runs.
Each run appends to a JSON log. On subsequent runs, past insights AND outcomes
are loaded and fed to the sub-agents so the system improves over time.

Feedback loop:
  Upload Run N → detect underperformers → generate suggestions (with hypotheses)
  Upload Run N+1 → match ads against Run N → score hypotheses → feed back
  - Ads that improved → hypotheses marked VALIDATED → reinforce in future
  - Ads still underperforming → hypotheses marked FAILED → avoid in future
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from difflib import SequenceMatcher


MEMORY_DIR = Path(__file__).parent / "memory"
LOG_FILE = MEMORY_DIR / "experiment_log.json"

# Minimum similarity ratio for fuzzy ad name matching across runs
_MATCH_THRESHOLD = 0.75


@dataclass
class RunRecord:
    run_id: str
    timestamp: str
    input_file: str
    total_ads: int
    underperformers_count: int
    underperformers: list[dict]  # ad_data + reasons for each
    generated_headlines: list[dict]  # {original_ad, headline, hypothesis}
    generated_descriptions: list[dict]  # {original_ad, description, hypothesis}
    top_performers: list[dict] = field(default_factory=list)
    notes: str = ""
    # Outcome tracking (populated on next run's upload)
    outcomes: list[dict] = field(default_factory=list)
    # {ad_id, prev_score, status: "improved"|"still_bad"|"gone",
    #  hypotheses_suggested: [str], delta: float}


def _resolve_paths(memory_dir: Path | None = None) -> tuple[Path, Path]:
    """Return (dir, log_file) — uses per-client dir if provided."""
    d = memory_dir or MEMORY_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d, d / "experiment_log.json"


def load_history(memory_dir: Path | None = None) -> list[RunRecord]:
    """Load all past experiment runs."""
    _, log = _resolve_paths(memory_dir)
    if not log.exists():
        return []

    with open(log, "r") as f:
        data = json.load(f)

    records = []
    for record in data:
        # Handle missing fields for backward compatibility
        record.setdefault("outcomes", [])
        records.append(RunRecord(**record))
    return records


def save_run(record: RunRecord, memory_dir: Path | None = None):
    """Append a new run to the experiment log."""
    _, log = _resolve_paths(memory_dir)
    history = []
    if log.exists():
        with open(log, "r") as f:
            history = json.load(f)

    history.append(asdict(record))

    with open(log, "w") as f:
        json.dump(history, f, indent=2, default=str)


def _update_last_run_outcomes(outcomes: list[dict], memory_dir: Path | None = None):
    """Update the most recent run's outcomes field retroactively."""
    _, log = _resolve_paths(memory_dir)
    if not log.exists():
        return
    with open(log, "r") as f:
        history = json.load(f)
    if not history:
        return
    history[-1]["outcomes"] = outcomes
    with open(log, "w") as f:
        json.dump(history, f, indent=2, default=str)


def generate_run_id() -> str:
    """Generate a unique run ID based on timestamp."""
    return datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S")


# ══════════════════════════════════════════════════════════════
# OUTCOME TRACKING — The feedback loop
# ══════════════════════════════════════════════════════════════

def _fuzzy_match(a: str, b: str) -> float:
    """Return similarity ratio between two ad identifier strings."""
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _extract_ad_id(ad_data: dict, id_keys: list[str] | None = None) -> str:
    """Extract the best identifier string from an ad data dict."""
    if id_keys:
        for k in id_keys:
            if ad_data.get(k):
                return str(ad_data[k]).strip()
    # Fallback: try common column names
    for k in ("Ad name", "ad_name", "Ad Name", "Campaign name", "Ad ID",
              "ad_id", "name", "Name", "id", "ID"):
        if ad_data.get(k):
            return str(ad_data[k]).strip()
    # Last resort: concatenate all string values
    parts = [str(v) for v in ad_data.values() if isinstance(v, str) and len(str(v)) > 3]
    return " | ".join(parts[:3]) if parts else ""


def detect_outcomes(
    current_underperformer_ids: set[str],
    current_top_ids: set[str],
    all_current_ids: set[str],
    history: list[RunRecord],
) -> list[dict]:
    """Compare current performance data against the LAST run to track outcomes.

    For each ad that was underperforming in the previous run:
    - If it's now a top performer → IMPROVED (hypothesis validated)
    - If it's still underperforming → STILL_BAD (hypothesis failed)
    - If it's in the data but not flagged → IMPROVED (no longer underperforming)
    - If it's gone from the data → GONE (can't evaluate)

    Returns list of outcome dicts for the previous run.
    """
    if not history:
        return []

    last_run = history[-1]
    outcomes = []

    for prev_under in last_run.underperformers:
        prev_id = _extract_ad_id(prev_under.get("ad_data", prev_under))
        if not prev_id:
            continue

        prev_score = prev_under.get("score", 0)

        # Collect hypotheses that were suggested for this ad
        hypotheses = []
        for h in last_run.generated_headlines:
            if _fuzzy_match(h.get("original_ad", ""), prev_id) > _MATCH_THRESHOLD:
                if h.get("hypothesis"):
                    hypotheses.append(h["hypothesis"])
        for d in last_run.generated_descriptions:
            if _fuzzy_match(d.get("original_ad", ""), prev_id) > _MATCH_THRESHOLD:
                if d.get("hypothesis"):
                    hypotheses.append(d["hypothesis"])
        hypotheses = list(set(hypotheses))  # deduplicate

        # Match against current data
        best_match = None
        best_ratio = 0
        for cid in all_current_ids:
            ratio = _fuzzy_match(prev_id, cid)
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = cid

        if best_ratio < _MATCH_THRESHOLD:
            outcomes.append({
                "ad_id": prev_id,
                "prev_score": prev_score,
                "status": "gone",
                "hypotheses_suggested": hypotheses,
                "detail": "Ad no longer in dataset",
            })
            continue

        if best_match in current_top_ids:
            outcomes.append({
                "ad_id": prev_id,
                "prev_score": prev_score,
                "status": "improved",
                "hypotheses_suggested": hypotheses,
                "detail": "Now a top performer!",
            })
        elif best_match in current_underperformer_ids:
            outcomes.append({
                "ad_id": prev_id,
                "prev_score": prev_score,
                "status": "still_bad",
                "hypotheses_suggested": hypotheses,
                "detail": "Still underperforming",
            })
        else:
            # In dataset but not flagged = no longer underperforming
            outcomes.append({
                "ad_id": prev_id,
                "prev_score": prev_score,
                "status": "improved",
                "hypotheses_suggested": hypotheses,
                "detail": "No longer flagged",
            })

    return outcomes


def score_hypotheses(history: list[RunRecord]) -> dict:
    """Aggregate hypothesis outcomes across all runs.

    Returns:
        {
            "validated": {"hypothesis_text": count, ...},
            "failed": {"hypothesis_text": count, ...},
            "untested": {"hypothesis_text": count, ...},
        }
    """
    validated: dict[str, int] = {}
    failed: dict[str, int] = {}
    all_suggested: dict[str, int] = {}

    for run in history:
        # Track all suggested hypotheses
        for h in run.generated_headlines + run.generated_descriptions:
            hyp = h.get("hypothesis", "")
            if hyp:
                all_suggested[hyp] = all_suggested.get(hyp, 0) + 1

        # Score from outcomes
        for outcome in run.outcomes:
            for hyp in outcome.get("hypotheses_suggested", []):
                if not hyp:
                    continue
                if outcome["status"] == "improved":
                    validated[hyp] = validated.get(hyp, 0) + 1
                elif outcome["status"] == "still_bad":
                    failed[hyp] = failed.get(hyp, 0) + 1

    # Untested = suggested but never evaluated
    untested = {}
    for hyp, count in all_suggested.items():
        if hyp not in validated and hyp not in failed:
            untested[hyp] = count

    return {"validated": validated, "failed": failed, "untested": untested}


def outcome_summary(history: list[RunRecord]) -> dict:
    """Compute high-level outcome stats across all runs.

    Returns:
        {
            "total_tracked": int,
            "improved_count": int,
            "still_bad_count": int,
            "gone_count": int,
            "improvement_rate": float (0-1),
            "latest_outcomes": list[dict],  # from most recent run
        }
    """
    total = improved = still_bad = gone = 0
    latest_outcomes = []

    for run in history:
        for o in run.outcomes:
            total += 1
            if o["status"] == "improved":
                improved += 1
            elif o["status"] == "still_bad":
                still_bad += 1
            elif o["status"] == "gone":
                gone += 1

    if history and history[-1].outcomes:
        latest_outcomes = history[-1].outcomes

    evaluated = improved + still_bad
    return {
        "total_tracked": total,
        "improved_count": improved,
        "still_bad_count": still_bad,
        "gone_count": gone,
        "improvement_rate": improved / evaluated if evaluated > 0 else 0,
        "latest_outcomes": latest_outcomes,
    }


# ══════════════════════════════════════════════════════════════
# INSIGHT SYNTHESIS — Feeds the reinforcement loop into prompts
# ══════════════════════════════════════════════════════════════

def summarize_insights(history: list[RunRecord]) -> str:
    """Synthesize learnings from all past runs into a prompt-friendly summary.

    This is the key piece — it turns raw experiment logs AND outcome data
    into actionable context that makes the sub-agents smarter each cycle.
    Validated hypotheses are reinforced; failed ones are flagged to avoid.
    """
    if not history:
        return "No previous experiments. This is the first run."

    total_runs = len(history)
    total_headlines = sum(len(r.generated_headlines) for r in history)
    total_descriptions = sum(len(r.generated_descriptions) for r in history)

    # Score hypotheses from outcome data
    scores = score_hypotheses(history)
    outcome_stats = outcome_summary(history)

    # Collect all hypotheses tried
    all_hypotheses = set()
    for run in history:
        for h in run.generated_headlines:
            if h.get("hypothesis"):
                all_hypotheses.add(h["hypothesis"])
        for d in run.generated_descriptions:
            if d.get("hypothesis"):
                all_hypotheses.add(d["hypothesis"])

    # Collect recurring underperformer patterns
    underperformer_reasons: dict[str, int] = {}
    for run in history:
        for u in run.underperformers:
            for reason in u.get("reasons", []):
                underperformer_reasons[reason] = underperformer_reasons.get(reason, 0) + 1

    # Collect top performer patterns
    top_performer_copy = []
    for run in history:
        for tp in run.top_performers:
            headlines = [v for k, v in tp.items() if "headline" in k.lower()]
            descriptions = [v for k, v in tp.items() if "description" in k.lower() or "desc" in k.lower()]
            if headlines or descriptions:
                top_performer_copy.append({"headlines": headlines, "descriptions": descriptions})

    # ── Build summary ──
    lines = [
        f"=== EXPERIMENT MEMORY ({total_runs} previous runs) ===",
        f"Total variations generated: {total_headlines} headlines, {total_descriptions} descriptions",
    ]

    # ── REINFORCEMENT SECTION (the key feedback loop) ──
    if outcome_stats["total_tracked"] > 0:
        rate = outcome_stats["improvement_rate"]
        lines.extend([
            "",
            f"=== PERFORMANCE FEEDBACK ({outcome_stats['total_tracked']} ads tracked across runs) ===",
            f"Improvement rate: {rate:.0%} ({outcome_stats['improved_count']} improved, "
            f"{outcome_stats['still_bad_count']} still underperforming, {outcome_stats['gone_count']} removed)",
        ])

    if scores["validated"]:
        lines.extend(["", "✅ VALIDATED STRATEGIES (these WORKED — use more of these):"])
        for hyp, count in sorted(scores["validated"].items(), key=lambda x: -x[1]):
            lines.append(f"  ✓ {hyp} (validated {count}x)")
        lines.extend(["", "IMPORTANT: Double down on validated strategies. They have proven results."])

    if scores["failed"]:
        lines.extend(["", "❌ FAILED STRATEGIES (these DID NOT improve performance — avoid):"])
        for hyp, count in sorted(scores["failed"].items(), key=lambda x: -x[1]):
            lines.append(f"  ✗ {hyp} (failed {count}x)")
        lines.extend(["", "WARNING: Do NOT repeat failed strategies. Try fundamentally different angles."])

    # ── Standard sections ──
    if all_hypotheses:
        # Separate untested from tested
        tested = set(scores["validated"].keys()) | set(scores["failed"].keys())
        untested = all_hypotheses - tested
        if untested:
            lines.extend(["", "HYPOTHESES TESTED BUT NOT YET EVALUATED:"])
            for h in sorted(untested):
                lines.append(f"  - {h}")
            lines.extend(["", "Try NEW angles that haven't been tested yet."])

    if underperformer_reasons:
        lines.extend(["", "RECURRING UNDERPERFORMER PATTERNS:"])
        for reason, count in sorted(underperformer_reasons.items(), key=lambda x: -x[1])[:10]:
            lines.append(f"  - {reason} (seen {count}x)")

    if top_performer_copy:
        lines.extend(["", "WHAT WORKED (top performer copy from past runs):"])
        for tp in top_performer_copy[:5]:
            if tp["headlines"]:
                lines.append(f"  Headlines: {', '.join(str(h) for h in tp['headlines'])}")
            if tp["descriptions"]:
                lines.append(f"  Descriptions: {', '.join(str(d) for d in tp['descriptions'])}")
        lines.append("Build on these winning patterns while exploring new angles.")

    # Include recent generated headlines for reference (avoid exact repeats)
    recent_headlines = set()
    for run in history[-3:]:
        for h in run.generated_headlines:
            recent_headlines.add(h.get("headline", ""))

    if recent_headlines:
        lines.extend(["", "RECENTLY GENERATED HEADLINES (avoid repeating these):"])
        for h in sorted(recent_headlines)[:20]:
            if h:
                lines.append(f"  - {h}")

    return "\n".join(lines)


def extract_top_performers(df, mapping, n: int = 5) -> list[dict]:
    """Extract the top N performing ads from the dataset for memory context."""
    if not mapping.metrics:
        return []

    # Use CTR or conversion rate as primary sort if available
    sort_col = None
    for preferred in ("ctr", "conversion_rate", "conversions", "clicks"):
        if preferred in mapping.metrics:
            sort_col = mapping.metrics[preferred]
            break

    if sort_col is None:
        return []

    import pandas as pd
    sorted_df = df.sort_values(sort_col, ascending=False).head(n)

    results = []
    for idx in sorted_df.index:
        ad_data = {}
        for col in mapping.identifiers + mapping.headlines + mapping.descriptions:
            ad_data[col] = str(df.at[idx, col])
        for metric_type, col in mapping.metrics.items():
            ad_data[col] = df.at[idx, col]
        results.append(ad_data)

    return results
