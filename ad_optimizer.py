#!/usr/bin/env python3
from __future__ import annotations
"""Ad Optimization Pipeline - CLI Orchestrator.

Analyzes ad performance CSVs, generates new copy with specialized sub-agents,
and maintains a learning memory across iterations.

Usage:
    python ad_optimizer.py --input ads.csv --brand "Your Brand" --product "Your Product"
    python ad_optimizer.py --input ads.csv --brand "Acme" --product "Widget" --variations 10
    python ad_optimizer.py --show-memory  # View experiment history
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from analyzer import load_and_analyze
from memory import (
    load_history, save_run, generate_run_id, summarize_insights,
    extract_top_performers, RunRecord,
)
from agents import generate_headlines, generate_descriptions


def run_pipeline(
    input_csv: str,
    brand: str,
    product: str,
    output_csv: str | None = None,
    headline_variations: int = 8,
    description_variations: int = 5,
):
    """Run the full ad optimization pipeline."""

    # 1. Load and analyze CSV
    print("=" * 60)
    print("STEP 1: Analyzing ad performance data")
    print("=" * 60)
    df, mapping, underperformers = load_and_analyze(input_csv)

    if not underperformers:
        print("\nNo underperformers found! All ads are performing well.")
        return

    # 2. Load memory from previous runs
    print("\n" + "=" * 60)
    print("STEP 2: Loading experiment memory")
    print("=" * 60)
    history = load_history()
    insights = summarize_insights(history)
    print(f"Previous runs: {len(history)}")
    if history:
        total_h = sum(len(r.generated_headlines) for r in history)
        total_d = sum(len(r.generated_descriptions) for r in history)
        print(f"Total past variations: {total_h} headlines, {total_d} descriptions")

    # Extract top performers for context
    top_performers = extract_top_performers(df, mapping)

    # 3. Run sub-agents on each underperformer
    print("\n" + "=" * 60)
    print("STEP 3: Generating new ad variations")
    print("=" * 60)

    all_headlines = []
    all_descriptions = []

    for i, underperformer in enumerate(underperformers):
        ad_label = next(
            (str(underperformer.ad_data.get(c, "")) for c in mapping.identifiers if underperformer.ad_data.get(c)),
            f"Row {underperformer.index}",
        )
        print(f"\n  [{i+1}/{len(underperformers)}] Processing: {ad_label}")
        print(f"  Reasons: {', '.join(underperformer.reasons[:3])}")

        # Headline agent
        print(f"  Generating {headline_variations} headlines (≤30 chars)...", end=" ", flush=True)
        headlines = generate_headlines(
            brand=brand,
            product=product,
            underperformer=underperformer.ad_data,
            memory_insights=insights,
            top_performers=top_performers,
            num_variations=headline_variations,
        )
        print(f"got {len(headlines)}")

        for h in headlines:
            h["original_ad"] = ad_label
            h["char_count"] = len(h["headline"])
            all_headlines.append(h)

        # Description agent
        print(f"  Generating {description_variations} descriptions (≤90 chars)...", end=" ", flush=True)
        descriptions = generate_descriptions(
            brand=brand,
            product=product,
            underperformer=underperformer.ad_data,
            memory_insights=insights,
            top_performers=top_performers,
            num_variations=description_variations,
        )
        print(f"got {len(descriptions)}")

        for d in descriptions:
            d["original_ad"] = ad_label
            d["char_count"] = len(d["description"])
            all_descriptions.append(d)

    # 4. Build output CSV with all combinations
    print("\n" + "=" * 60)
    print("STEP 4: Building output")
    print("=" * 60)

    output_rows = []
    for h in all_headlines:
        for d in all_descriptions:
            if h["original_ad"] == d["original_ad"]:
                output_rows.append({
                    "original_ad": h["original_ad"],
                    "headline": h["headline"],
                    "headline_chars": h["char_count"],
                    "headline_hypothesis": h.get("hypothesis", ""),
                    "description": d["description"],
                    "description_chars": d["char_count"],
                    "description_hypothesis": d.get("hypothesis", ""),
                })

    # Also output standalone lists (not just combinations)
    standalone_rows = []
    for h in all_headlines:
        standalone_rows.append({
            "original_ad": h["original_ad"],
            "type": "headline",
            "text": h["headline"],
            "char_count": h["char_count"],
            "hypothesis": h.get("hypothesis", ""),
        })
    for d in all_descriptions:
        standalone_rows.append({
            "original_ad": d["original_ad"],
            "type": "description",
            "text": d["description"],
            "char_count": d["char_count"],
            "hypothesis": d.get("hypothesis", ""),
        })

    # Save outputs
    if output_csv is None:
        stem = Path(input_csv).stem
        output_csv = f"{stem}_variations.csv"

    combo_path = output_csv
    standalone_path = output_csv.replace(".csv", "_standalone.csv")

    pd.DataFrame(output_rows).to_csv(combo_path, index=False)
    pd.DataFrame(standalone_rows).to_csv(standalone_path, index=False)

    print(f"Combinations:  {len(output_rows)} rows -> {combo_path}")
    print(f"Standalone:    {len(standalone_rows)} rows -> {standalone_path}")

    # 5. Update memory
    print("\n" + "=" * 60)
    print("STEP 5: Updating experiment memory")
    print("=" * 60)

    run_id = generate_run_id()
    record = RunRecord(
        run_id=run_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        input_file=input_csv,
        total_ads=len(df),
        underperformers_count=len(underperformers),
        underperformers=[
            {"ad_data": u.ad_data, "reasons": u.reasons, "score": u.score}
            for u in underperformers
        ],
        generated_headlines=[
            {"original_ad": h["original_ad"], "headline": h["headline"], "hypothesis": h.get("hypothesis", "")}
            for h in all_headlines
        ],
        generated_descriptions=[
            {"original_ad": d["original_ad"], "description": d["description"], "hypothesis": d.get("hypothesis", "")}
            for d in all_descriptions
        ],
        top_performers=top_performers,
    )
    save_run(record)
    print(f"Saved run: {run_id}")

    # 6. Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Ads analyzed:           {len(df)}")
    print(f"Underperformers found:  {len(underperformers)}")
    print(f"Headlines generated:    {len(all_headlines)}")
    print(f"Descriptions generated: {len(all_descriptions)}")
    print(f"Ad combinations:        {len(output_rows)}")
    print(f"Output files:           {combo_path}, {standalone_path}")
    print(f"Memory updated:         {run_id}")

    # Validate char limits
    h_violations = [h for h in all_headlines if h["char_count"] > 30]
    d_violations = [d for d in all_descriptions if d["char_count"] > 90]
    if h_violations:
        print(f"\n  WARNING: {len(h_violations)} headlines exceed 30 chars")
    if d_violations:
        print(f"\n  WARNING: {len(d_violations)} descriptions exceed 90 chars")
    if not h_violations and not d_violations:
        print(f"\n  All character limits validated.")


def show_memory():
    """Display experiment history."""
    history = load_history()
    if not history:
        print("No experiment history yet. Run the pipeline first.")
        return

    print(f"\n{'='*60}")
    print(f"EXPERIMENT HISTORY ({len(history)} runs)")
    print(f"{'='*60}")

    for run in history:
        print(f"\n--- {run.run_id} ({run.timestamp}) ---")
        print(f"  Input: {run.input_file}")
        print(f"  Ads: {run.total_ads} total, {run.underperformers_count} underperformers")
        print(f"  Generated: {len(run.generated_headlines)} headlines, {len(run.generated_descriptions)} descriptions")

    print(f"\n{'='*60}")
    print("ACCUMULATED INSIGHTS")
    print(f"{'='*60}")
    print(summarize_insights(history))


def main():
    parser = argparse.ArgumentParser(
        description="Ad Optimization Pipeline - analyze ads, generate better copy, learn over time"
    )
    parser.add_argument("--input", "-i", help="Path to CSV file with ad data")
    parser.add_argument("--brand", "-b", help="Brand name for copy context")
    parser.add_argument("--product", "-p", help="Product/service description")
    parser.add_argument("--output", "-o", help="Output CSV path (default: {input}_variations.csv)")
    parser.add_argument("--headlines", type=int, default=8, help="Headline variations per ad (default: 8)")
    parser.add_argument("--descriptions", type=int, default=5, help="Description variations per ad (default: 5)")
    parser.add_argument("--show-memory", action="store_true", help="Show experiment history and exit")

    args = parser.parse_args()

    if args.show_memory:
        show_memory()
        return

    if not args.input:
        parser.error("--input is required (unless using --show-memory)")
    if not args.brand:
        parser.error("--brand is required")
    if not args.product:
        parser.error("--product is required")

    if not Path(args.input).exists():
        print(f"Error: File not found: {args.input}")
        sys.exit(1)

    run_pipeline(
        input_csv=args.input,
        brand=args.brand,
        product=args.product,
        output_csv=args.output,
        headline_variations=args.headlines,
        description_variations=args.descriptions,
    )


if __name__ == "__main__":
    main()
