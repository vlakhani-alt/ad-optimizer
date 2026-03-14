from __future__ import annotations
"""CSV/XLSX ingestion, column auto-detection, and underperformer flagging.

Handles exports from Meta Ads, Google Ads, TikTok Ads, and generic
platforms. Supports both numeric metrics and Meta-style qualitative
ranking columns (Quality, Engagement, Conversion rate rankings).
"""

import pandas as pd
import re
from dataclasses import dataclass, field


# ── Column Detection ────────────────────────────────────────
#
# Patterns are tested against the full column name (lowercased).
# Order within each category matters — first match wins.
# Negative lookaheads prevent false matches (e.g. CPM matching "impressions").

COLUMN_PATTERNS: dict[str, list[str]] = {
    # Identifiers
    "identifier": [
        r"^campaign[\s_]?name$",
        r"^ad[\s_]?set[\s_]?name$",
        r"^ad[\s_]?group",
        r"^ad[\s_]?name$",
        r"^ad[\s_]?id$",
        r"^account",
        r"^label$",
    ],
    # Copy columns (text creative)
    "headline": [
        r"^headline",
        r"^title$",
        r"^heading",
    ],
    "description": [
        r"^description",
        r"^primary[\s_]?text",
        r"^body$",
        r"^copy$",
    ],
    # ── Metrics (order matters: specific patterns before broad ones) ──
    # Higher-is-better metrics
    "impressions": [r"^impressions?$"],
    "reach": [r"^reach$"],
    "clicks": [r"^clicks?\s*\(all\)$", r"^total[\s_]?clicks$", r"^clicks?$"],
    "link_clicks": [r"link[\s_]?clicks?"],
    "ctr": [r"^ctr\b", r"click[\s_]?through[\s_]?rate"],
    "conversions": [r"^conversions?$", r"^results?$"],
    "purchases": [r"^purchases?$"],
    "conversion_rate": [r"^conversion[\s_]?rate$", r"^conv[\s_]?rate$"],
    "roas": [r"\broas\b", r"return[\s_]?on[\s_]?ad"],
    # Lower-is-better metrics
    "spend": [r"^amount[\s_]?spent", r"^spend$", r"^cost$"],
    "cpa": [r"^cpa$", r"^cost[\s_]?per[\s_]?result", r"cost[\s_]?per[\s_]?acq",
            r"cost[\s_]?per[\s_]?conv", r"cost[\s_]?per[\s_]?action"],
    "cpc": [r"^cpc\s*\(all\)", r"^cpc\s*\(cost per link", r"^cpc$", r"cost[\s_]?per[\s_]?click"],
    "cpm": [r"\bcpm\b", r"cost[\s_]?per[\s_]?1[,.]?000"],
    "frequency": [r"^frequency$"],
    # Qualitative rankings (Meta-specific, text columns)
    "quality_ranking": [r"quality[\s_]?rank"],
    "engagement_ranking": [r"engagement[\s_]?rate?[\s_]?rank"],
    "conversion_ranking": [r"conversion[\s_]?rate?[\s_]?rank"],
}

# Which metrics mean "higher = better" vs "lower = better"
HIGHER_BETTER = {"ctr", "conversions", "conversion_rate", "roas", "clicks",
                 "link_clicks", "impressions", "reach", "purchases",
                 "quality_ranking", "engagement_ranking", "conversion_ranking"}
LOWER_BETTER = {"cpa", "cpc", "cpm", "frequency"}

# Meta qualitative ranking → numeric score (higher = better)
META_RANKING_SCORES = {
    "above average": 1.0,
    "average": 0.5,
    "below average (bottom 35% of ads)": 0.25,
    "below average - bottom 35% of ads": 0.25,
    "below average (bottom 20% of ads)": 0.15,
    "below average - bottom 20% of ads": 0.15,
    "below average (bottom 10% of ads)": 0.05,
    "below average - bottom 10% of ads": 0.05,
}


@dataclass
class ColumnMapping:
    identifiers: list[str] = field(default_factory=list)
    headlines: list[str] = field(default_factory=list)
    descriptions: list[str] = field(default_factory=list)
    metrics: dict[str, str] = field(default_factory=dict)  # metric_type -> col_name


@dataclass
class UnderperformerResult:
    index: int
    ad_data: dict
    reasons: list[str]
    score: float  # 0-1, higher = worse performer


def detect_columns(df: pd.DataFrame) -> ColumnMapping:
    """Auto-detect column types by matching against known patterns.

    Each column is tested against every category's patterns.
    The first category with a matching pattern wins.
    Duplicate column names (e.g. 'Ad set name.1') are skipped.
    """
    mapping = ColumnMapping()
    seen_cols = set()  # track originals to skip dupes like "Ad set name.1"

    for col in df.columns:
        col_lower = col.lower().strip()

        # Skip duplicate columns (pandas adds .1, .2 suffixes)
        base_name = re.sub(r"\.\d+$", "", col_lower)
        if base_name in seen_cols:
            continue
        seen_cols.add(base_name)

        for category, patterns in COLUMN_PATTERNS.items():
            if any(re.search(p, col_lower) for p in patterns):
                if category == "identifier":
                    mapping.identifiers.append(col)
                elif category == "headline":
                    mapping.headlines.append(col)
                elif category == "description":
                    mapping.descriptions.append(col)
                else:
                    # Only keep the first match per metric type
                    if category not in mapping.metrics:
                        mapping.metrics[category] = col
                break

    return mapping


def parse_percentage(series: pd.Series) -> pd.Series:
    """Convert percentage strings like '2.5%' to float 0.025."""
    if series.dtype == object:
        return (
            series.astype(str)
            .str.replace("%", "", regex=False)
            .str.replace(",", "", regex=False)
            .str.strip()
            .apply(lambda x: float(x) / 100 if x and x != "nan" else None)
        )
    return series


def parse_currency(series: pd.Series) -> pd.Series:
    """Convert currency strings like '$1,234.56' to float."""
    if series.dtype == object:
        return (
            series.astype(str)
            .str.replace(r"[$€£¥,]", "", regex=True)
            .str.strip()
            .apply(lambda x: float(x) if x and x != "nan" else None)
        )
    return series


def parse_meta_ranking(series: pd.Series) -> pd.Series:
    """Convert Meta qualitative ranking strings to numeric scores."""
    def _to_score(val):
        if pd.isna(val):
            return None
        s = str(val).strip().lower()
        if s in ("-", "", "nan", "none"):
            return None
        # Exact match first
        if s in META_RANKING_SCORES:
            return META_RANKING_SCORES[s]
        # Fuzzy match
        for key, score in META_RANKING_SCORES.items():
            if key in s:
                return score
        return None

    return series.apply(_to_score)


def clean_metrics(df: pd.DataFrame, mapping: ColumnMapping) -> pd.DataFrame:
    """Parse percentage, currency, and ranking columns into numeric values."""
    df = df.copy()

    pct_metrics = {"ctr", "conversion_rate"}
    currency_metrics = {"spend", "cpa", "cpc", "cpm", "roas"}
    ranking_metrics = {"quality_ranking", "engagement_ranking", "conversion_ranking"}

    for metric_type, col in mapping.metrics.items():
        if metric_type in ranking_metrics:
            df[col] = parse_meta_ranking(df[col])
        elif metric_type in pct_metrics:
            df[col] = parse_percentage(df[col])
        elif metric_type in currency_metrics:
            df[col] = parse_currency(df[col])
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def flag_underperformers(
    df: pd.DataFrame, mapping: ColumnMapping
) -> list[UnderperformerResult]:
    """Flag ads performing below thresholds using percentile-based scoring.

    Works with both numeric metrics and Meta-style qualitative rankings.
    Ads with very little data (zero impressions/spend) are excluded.
    """
    results = []
    n = len(df)
    if n < 2:
        return results

    # Filter out ads with no real data
    imp_col = mapping.metrics.get("impressions")
    spend_col = mapping.metrics.get("spend")
    active_mask = pd.Series(True, index=df.index)
    if imp_col and imp_col in df.columns:
        active_mask &= pd.to_numeric(df[imp_col], errors="coerce").fillna(0) > 100
    if spend_col and spend_col in df.columns:
        active_mask &= pd.to_numeric(df[spend_col], errors="coerce").fillna(0) > 0.1

    df_active = df[active_mask]
    if len(df_active) < 2:
        return results

    scores = pd.DataFrame(index=df_active.index)

    for metric_type, col in mapping.metrics.items():
        if col not in df_active.columns:
            continue

        series = pd.to_numeric(df_active[col], errors="coerce")
        if series.isna().all() or series.nunique() < 2:
            continue

        pct_rank = series.rank(pct=True)

        if metric_type in HIGHER_BETTER:
            scores[metric_type] = 1 - pct_rank  # low rank = bad
        elif metric_type in LOWER_BETTER:
            scores[metric_type] = pct_rank  # high rank = bad (high CPA is bad)

    if scores.empty:
        return results

    # Composite score: average of all metric scores (higher = worse)
    composite = scores.mean(axis=1)

    for idx in df_active.index:
        score = composite.get(idx, 0)
        if pd.isna(score) or score <= 0.65:
            continue

        reasons = []
        for metric_type in scores.columns:
            metric_score = scores.at[idx, metric_type]
            if pd.isna(metric_score) or metric_score <= 0.7:
                continue

            col = mapping.metrics[metric_type]
            val = df_active.at[idx, col]
            label = metric_type.replace("_", " ").title()

            if metric_type in HIGHER_BETTER:
                reasons.append(f"Low {label}: {val}")
            else:
                reasons.append(f"High {label}: {val}")

        ad_data = {}
        for id_col in mapping.identifiers:
            ad_data[id_col] = str(df.at[idx, id_col])
        for h_col in mapping.headlines:
            ad_data[h_col] = str(df.at[idx, h_col])
        for d_col in mapping.descriptions:
            ad_data[d_col] = str(df.at[idx, d_col])
        for mt, col in mapping.metrics.items():
            ad_data[col] = df.at[idx, col]

        results.append(UnderperformerResult(
            index=idx, ad_data=ad_data, reasons=reasons, score=round(score, 3)
        ))

    results.sort(key=lambda r: r.score, reverse=True)
    return results


def load_and_analyze(path: str) -> tuple[pd.DataFrame, ColumnMapping, list[UnderperformerResult]]:
    """Full pipeline: load file, detect columns, clean data, flag underperformers."""
    if path.endswith(".xlsx") or path.endswith(".xls"):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)

    mapping = detect_columns(df)

    print(f"\n--- Column Detection ---")
    print(f"Identifiers:  {mapping.identifiers}")
    print(f"Headlines:    {mapping.headlines}")
    print(f"Descriptions: {mapping.descriptions}")
    print(f"Metrics:      {mapping.metrics}")

    df = clean_metrics(df, mapping)
    underperformers = flag_underperformers(df, mapping)

    print(f"\n--- Analysis ---")
    print(f"Total ads:        {len(df)}")
    print(f"Underperformers:  {len(underperformers)}")

    for i, u in enumerate(underperformers[:10]):
        label = u.ad_data.get(mapping.identifiers[0], f"Row {u.index}") if mapping.identifiers else f"Row {u.index}"
        print(f"  [{i+1}] {label} (score: {u.score})")
        for r in u.reasons:
            print(f"      - {r}")

    return df, mapping, underperformers
