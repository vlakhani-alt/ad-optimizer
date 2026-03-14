from __future__ import annotations
"""Experiment logging and learning system.

Tracks hypotheses, generated variations, and performance patterns across runs.
Each run appends to a JSON log. On subsequent runs, past insights are loaded
and fed to the sub-agents so the system improves over time.
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict


MEMORY_DIR = Path(__file__).parent / "memory"
LOG_FILE = MEMORY_DIR / "experiment_log.json"


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
    top_performers: list[dict] = field(default_factory=list)  # ads that were doing well
    notes: str = ""


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

    return [RunRecord(**record) for record in data]


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


def generate_run_id() -> str:
    """Generate a unique run ID based on timestamp."""
    return datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S")


def summarize_insights(history: list[RunRecord]) -> str:
    """Synthesize learnings from all past runs into a prompt-friendly summary.

    This is the key piece - it turns raw experiment logs into actionable
    context that makes the sub-agents smarter each cycle.
    """
    if not history:
        return "No previous experiments. This is the first run."

    total_runs = len(history)
    total_headlines = sum(len(r.generated_headlines) for r in history)
    total_descriptions = sum(len(r.generated_descriptions) for r in history)

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
    underperformer_reasons = {}
    for run in history:
        for u in run.underperformers:
            for reason in u.get("reasons", []):
                underperformer_reasons[reason] = underperformer_reasons.get(reason, 0) + 1

    # Collect top performer patterns (if tagged in subsequent runs)
    top_performer_copy = []
    for run in history:
        for tp in run.top_performers:
            headlines = [v for k, v in tp.items() if "headline" in k.lower()]
            descriptions = [v for k, v in tp.items() if "description" in k.lower() or "desc" in k.lower()]
            if headlines or descriptions:
                top_performer_copy.append({"headlines": headlines, "descriptions": descriptions})

    # Build summary
    lines = [
        f"=== EXPERIMENT MEMORY ({total_runs} previous runs) ===",
        f"Total variations generated: {total_headlines} headlines, {total_descriptions} descriptions",
        "",
    ]

    if all_hypotheses:
        lines.append("HYPOTHESES ALREADY TESTED:")
        for h in sorted(all_hypotheses):
            lines.append(f"  - {h}")
        lines.append("")
        lines.append("IMPORTANT: Try NEW angles that haven't been tested yet.")
        lines.append("")

    if underperformer_reasons:
        lines.append("RECURRING UNDERPERFORMER PATTERNS:")
        for reason, count in sorted(underperformer_reasons.items(), key=lambda x: -x[1])[:10]:
            lines.append(f"  - {reason} (seen {count}x)")
        lines.append("")

    if top_performer_copy:
        lines.append("WHAT WORKED (top performer copy from past runs):")
        for tp in top_performer_copy[:5]:
            if tp["headlines"]:
                lines.append(f"  Headlines: {', '.join(str(h) for h in tp['headlines'])}")
            if tp["descriptions"]:
                lines.append(f"  Descriptions: {', '.join(str(d) for d in tp['descriptions'])}")
        lines.append("")
        lines.append("Build on these winning patterns while exploring new angles.")

    # Include recent generated headlines for reference (avoid exact repeats)
    recent_headlines = set()
    for run in history[-3:]:  # Last 3 runs
        for h in run.generated_headlines:
            recent_headlines.add(h.get("headline", ""))

    if recent_headlines:
        lines.append("")
        lines.append("RECENTLY GENERATED HEADLINES (avoid repeating these):")
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
