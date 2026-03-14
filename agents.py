"""Platform-aware ad copy generation with specialized sub-agents.

Each ad platform has different copy formats and character limits:
- Google Search: Headlines (30 chars), Descriptions (90 chars)
- Meta/Facebook/Instagram: Primary Text (125 chars), Headline (40 chars), Description (30 chars)
- TikTok: Ad Text (100 chars), Headline (40 chars)
- LinkedIn: Introductory Text (150 chars), Headline (70 chars), Description (100 chars)
- Generic: Headlines (30 chars), Descriptions (90 chars)

Each copy slot gets its own focused sub-agent call with a tailored system prompt.
Character limits are validated and violations trigger retries.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
import anthropic

MODEL = "claude-sonnet-4-6"

# Lazy client — created on first use so the API key from the sidebar
# is already in os.environ by the time we need it.
_client = None

def _get_client() -> anthropic.Anthropic:
    global _client
    _client = anthropic.Anthropic()
    return _client


# ══════════════════════════════════════════════════════════════
# PLATFORM PROFILES
# ══════════════════════════════════════════════════════════════

@dataclass
class CopySlot:
    """A single copy field that needs to be generated."""
    key: str            # machine key, e.g. "primary_text"
    label: str          # display label, e.g. "Primary Text"
    char_limit: int     # max characters
    guidance: str       # what this slot is for (used in AI prompt)
    default_count: int  # default number of variations per ad


@dataclass
class PlatformProfile:
    """Defines the copy formats for a specific ad platform."""
    id: str
    name: str
    icon: str
    slots: list[CopySlot] = field(default_factory=list)


# ── Platform definitions ──

PLATFORMS: dict[str, PlatformProfile] = {
    "google_search": PlatformProfile(
        id="google_search",
        name="Google Search Ads (RSA)",
        icon="🔍",
        slots=[
            CopySlot(
                key="headline",
                label="Headline",
                char_limit=30,
                guidance="Short, punchy headline for Google Search results. Action-oriented, attention-grabbing.",
                default_count=5,
            ),
            CopySlot(
                key="description",
                label="Description",
                char_limit=90,
                guidance="Google Search ad description. Include a clear call-to-action. Highlight key benefits.",
                default_count=5,
            ),
        ],
    ),
    "meta": PlatformProfile(
        id="meta",
        name="Meta Ads (Facebook & Instagram)",
        icon="📘",
        slots=[
            CopySlot(
                key="primary_text",
                label="Primary Text",
                char_limit=125,
                guidance=(
                    "The main body text displayed ABOVE the ad image/video in Facebook and Instagram feeds. "
                    "This is what users read first. Hook them in the first line. "
                    "Can include emojis, questions, and storytelling. 125 chars is the visible portion before 'See More'."
                ),
                default_count=5,
            ),
            CopySlot(
                key="headline",
                label="Headline",
                char_limit=40,
                guidance=(
                    "Displayed BELOW the ad image/video, next to the CTA button. "
                    "Short and direct. Often a value proposition or key benefit."
                ),
                default_count=5,
            ),
            CopySlot(
                key="link_description",
                label="Link Description",
                char_limit=30,
                guidance=(
                    "Small supporting text below the headline on Facebook feed ads. "
                    "Very short. Reinforce the main message or add urgency."
                ),
                default_count=5,
            ),
        ],
    ),
    "tiktok": PlatformProfile(
        id="tiktok",
        name="TikTok Ads",
        icon="🎵",
        slots=[
            CopySlot(
                key="ad_text",
                label="Ad Text",
                char_limit=100,
                guidance=(
                    "The main text displayed with TikTok in-feed ads. "
                    "Conversational, casual tone. Use emojis sparingly. "
                    "Speak like a creator, not a brand. Hook in first 5 words."
                ),
                default_count=5,
            ),
            CopySlot(
                key="headline",
                label="Headline",
                char_limit=40,
                guidance="Short headline overlay for TikTok ads. Punchy, thumb-stopping, Gen-Z friendly.",
                default_count=5,
            ),
        ],
    ),
    "linkedin": PlatformProfile(
        id="linkedin",
        name="LinkedIn Ads",
        icon="💼",
        slots=[
            CopySlot(
                key="introductory_text",
                label="Introductory Text",
                char_limit=150,
                guidance=(
                    "The text above the ad image in LinkedIn feed. Professional but engaging. "
                    "150 chars is the visible portion before 'see more'. "
                    "Use data points, industry insights, or professional pain points."
                ),
                default_count=5,
            ),
            CopySlot(
                key="headline",
                label="Headline",
                char_limit=70,
                guidance=(
                    "Displayed below the ad image on LinkedIn. Professional tone. "
                    "Can be longer than other platforms. Highlight B2B value props."
                ),
                default_count=5,
            ),
            CopySlot(
                key="description",
                label="Description",
                char_limit=100,
                guidance="Supporting text below the headline on LinkedIn. Add specifics, stats, or a clear CTA.",
                default_count=5,
            ),
        ],
    ),
    "generic": PlatformProfile(
        id="generic",
        name="Generic / Multi-Platform",
        icon="📝",
        slots=[
            CopySlot(
                key="headline",
                label="Headline",
                char_limit=30,
                guidance="Short, versatile headline that works across platforms. Punchy and action-oriented.",
                default_count=5,
            ),
            CopySlot(
                key="description",
                label="Description",
                char_limit=90,
                guidance="Versatile ad description. Include a call-to-action. Works for search, social, and display.",
                default_count=5,
            ),
        ],
    ),
}

# Default number of complete ad sets to generate per underperformer.
DEFAULT_AD_SETS = 5


def get_platform(platform_id: str) -> PlatformProfile:
    """Get a platform profile by ID, falling back to generic."""
    return PLATFORMS.get(platform_id, PLATFORMS["generic"])


def list_platforms() -> list[PlatformProfile]:
    """Return all available platform profiles."""
    return list(PLATFORMS.values())


# ══════════════════════════════════════════════════════════════
# AUTO-DETECTION
# ══════════════════════════════════════════════════════════════

def detect_platform(columns: list[str]) -> str:
    """Guess the ad platform from column names in the uploaded data.

    Returns the platform ID string (e.g. 'meta', 'google_search').
    Falls back to 'generic' if unsure.
    """
    col_set = " ".join(c.lower() for c in columns)

    # Meta signals
    meta_signals = [
        "quality ranking", "engagement rate ranking", "conversion rate ranking",
        "amount spent", "purchase roas", "ad set name", "delivery",
        "reporting starts", "reporting ends",
    ]
    meta_score = sum(1 for s in meta_signals if s in col_set)

    # Google signals
    google_signals = [
        "avg. cpc", "avg. cpm", "conv. rate", "cost / conv",
        "search impr. share", "ad group", "campaign type",
        "interaction rate", "view rate",
    ]
    google_score = sum(1 for s in google_signals if s in col_set)

    # TikTok signals
    tiktok_signals = [
        "video views", "profile visits", "6-second video views",
        "cost per 1000 reached", "paid followers",
    ]
    tiktok_score = sum(1 for s in tiktok_signals if s in col_set)

    # LinkedIn signals
    linkedin_signals = [
        "sponsored", "company name", "content type", "leads",
        "lead form opens", "social actions",
    ]
    linkedin_score = sum(1 for s in linkedin_signals if s in col_set)

    scores = {
        "meta": meta_score,
        "google_search": google_score,
        "tiktok": tiktok_score,
        "linkedin": linkedin_score,
    }

    best = max(scores, key=scores.get)
    if scores[best] >= 2:
        return best
    return "generic"


# ══════════════════════════════════════════════════════════════
# COPY GENERATION
# ══════════════════════════════════════════════════════════════

def _build_system_prompt(slot: CopySlot, platform: PlatformProfile) -> str:
    """Build a focused system prompt for a specific copy slot."""
    return f"""You are an expert ad copywriter specializing in {platform.name}.

You are generating: **{slot.label}**
Platform: {platform.name}

STRICT RULES:
1. Every {slot.label.lower()} MUST be {slot.char_limit} characters or fewer (including spaces and emojis)
2. {slot.guidance}
3. Use proven direct-response copywriting techniques
4. Vary your angles: benefits, urgency, curiosity, social proof, problem/solution, emotional appeal
5. Never repeat the same structure twice in a batch

Output ONLY valid JSON — an array of objects with this exact format:
[
  {{"{slot.key}": "Your text here", "hypothesis": "brief angle description"}}
]

No markdown, no explanation, no preamble. Just the JSON array."""


def _detect_creative_type(underperformer: dict) -> str:
    """Infer the creative type from ad data fields.

    Returns 'video_influencer', 'video', 'image', or 'text'.
    """
    ad_name = str(underperformer.get("Ad name", underperformer.get("ad_name", ""))).lower()
    all_keys = " ".join(str(k).lower() for k in underperformer.keys())
    all_vals = " ".join(str(v).lower() for v in underperformer.values() if isinstance(v, str))

    # Check for video signals
    has_video = any(s in all_keys for s in ("video view", "thruplays", "thruplay", "video play"))
    # Check for influencer/UGC signals
    influencer_words = ("ugc", "influencer", "creator", "collab", "partner", "whitelisted",
                        "spark", "paid partnership")
    has_influencer = any(w in ad_name or w in all_vals for w in influencer_words)

    if has_video or has_influencer:
        return "video_influencer" if has_influencer else "video"
    return "text"


def _build_context(
    brand: str,
    product: str,
    underperformer: dict,
    memory_insights: str,
    top_performers: list[dict],
    creative_type: str = "",
) -> str:
    """Build the user message context for all agents.

    When the data has no headline/description columns (e.g. Meta video
    ad exports), the ad name and performance metrics are used to infer
    the creative concept and write better copy for new variations.
    """
    # Trim bloated metric values to keep prompt size reasonable
    trimmed = {}
    for k, v in underperformer.items():
        if isinstance(v, float) and abs(v) > 1000:
            trimmed[k] = round(v, 2)
        else:
            trimmed[k] = v

    # Auto-detect creative type if not provided
    if not creative_type:
        creative_type = _detect_creative_type(underperformer)

    lines = [
        f"Brand: {brand}",
        f"Product: {product}",
        "",
        "=== UNDERPERFORMING AD (generate better alternatives) ===",
        json.dumps(trimmed, indent=2, default=str),
    ]

    # If there's no headline/description in the data, add explicit instruction
    has_copy = any(k.lower() in ("headline", "description", "primary text", "title", "body")
                   for k in underperformer)
    if not has_copy:
        if creative_type == "video_influencer":
            lines.extend([
                "",
                "CONTEXT: These are results from INFLUENCER / UGC VIDEO ADS. The video creative",
                "was produced by an influencer or content creator, not the brand's in-house team.",
                "The 'Ad name' field describes the creator and/or creative concept.",
                "",
                "Your job: Write the TEXT COPY that accompanies these video ads in the feed —",
                "the primary text, headline, and link description that appear around the video.",
                "The copy should COMPLEMENT the video style (authentic, creator-driven, relatable)",
                "rather than sound like traditional brand advertising.",
                "",
                "Tips for influencer video ad copy:",
                "- Match the casual, authentic tone of creator content",
                "- Reference the video indirectly ('See why...', 'Watch how...', 'They tried...')",
                "- Use first-person or third-person social proof angles",
                "- Don't over-brand — let the creator's voice come through",
                "- Hook with curiosity or a relatable problem the video addresses",
            ])
        elif creative_type == "video":
            lines.extend([
                "",
                "CONTEXT: These are results from VIDEO ADS. The 'Ad name' describes the video",
                "creative concept. Write TEXT COPY that accompanies the video in the feed —",
                "primary text, headline, and link description that complement the visual content.",
                "The copy should hook viewers and reinforce the video's message.",
            ])
        else:
            lines.extend([
                "",
                "NOTE: This data is from a social ads export with no separate headline/description",
                "columns. The 'Ad name' field describes the creative concept. Use it to understand the",
                "angle and messaging, then write new text ad copy that could complement or replace this",
                "creative approach. Focus on the product category and target audience implied by the ad name.",
            ])

    if top_performers:
        # Only include key fields from top performers to save tokens
        slim_top = []
        for tp in top_performers[:3]:
            slim = {k: v for k, v in tp.items()
                    if any(x in k.lower() for x in ("name", "headline", "desc", "campaign", "roas", "ctr", "result", "purchase"))}
            slim_top.append(slim)
        lines.extend([
            "",
            "=== TOP PERFORMING ADS (use as inspiration) ===",
            json.dumps(slim_top, indent=2, default=str),
        ])

    if memory_insights and "No previous experiments" not in memory_insights:
        lines.extend(["", memory_insights])

    return "\n".join(lines)


def _parse_json_response(text: str) -> list[dict]:
    """Extract JSON array from Claude's response, handling edge cases."""
    text = text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines[1:] if not l.strip().startswith("```")]
        text = "\n".join(lines)

    return json.loads(text)


def generate_slot_copy(
    slot: CopySlot,
    platform: PlatformProfile,
    brand: str,
    product: str,
    underperformer: dict,
    memory_insights: str,
    top_performers: list[dict],
    num_variations: int | None = None,
    max_retries: int = 2,
) -> list[dict]:
    """Generate copy variations for a single slot of a platform profile.

    Returns list of {slot.key: str, "hypothesis": str} dicts,
    all validated against the slot's character limit.
    """
    count = num_variations or slot.default_count
    system = _build_system_prompt(slot, platform)
    context = _build_context(brand, product, underperformer, memory_insights, top_performers)
    prompt = (
        f"Generate {count} {slot.label.lower()} variations "
        f"(each ≤{slot.char_limit} characters) for this underperforming ad:\n\n{context}"
    )

    for attempt in range(max_retries + 1):
        response = _get_client().messages.create(
            model=MODEL,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )

        try:
            results = _parse_json_response(response.content[0].text)
        except (json.JSONDecodeError, IndexError):
            if attempt < max_retries:
                continue
            return []

        # Validate character limits
        valid = [r for r in results if len(r.get(slot.key, "")) <= slot.char_limit]
        violations = [r for r in results if len(r.get(slot.key, "")) > slot.char_limit]

        if violations and attempt < max_retries:
            violation_text = "\n".join(
                f'  "{r[slot.key]}" = {len(r[slot.key])} chars (TOO LONG, limit {slot.char_limit})'
                for r in violations
                if slot.key in r
            )
            prompt = (
                f"Some {slot.label.lower()} exceeded {slot.char_limit} characters. Fix these:\n{violation_text}\n\n"
                f"Also generate {count - len(valid)} more valid {slot.label.lower()} (≤{slot.char_limit} chars).\n\n{context}"
            )
            continue

        return valid

    return []


def generate_platform_copy(
    platform_id: str,
    brand: str,
    product: str,
    underperformer: dict,
    memory_insights: str,
    top_performers: list[dict],
    slot_counts: dict[str, int] | None = None,
) -> dict[str, list[dict]]:
    """Generate all copy slots for a platform independently.

    DEPRECATED: Use generate_ad_sets() instead for coherent ad variations
    where all copy slots are thematically aligned.

    Args:
        platform_id: e.g. "meta", "google_search"
        slot_counts: optional override for how many variations per slot

    Returns:
        dict mapping slot key -> list of generated variations
    """
    platform = get_platform(platform_id)
    slot_counts = slot_counts or {}
    results = {}

    for slot in platform.slots:
        count = slot_counts.get(slot.key, slot.default_count)
        variations = generate_slot_copy(
            slot=slot,
            platform=platform,
            brand=brand,
            product=product,
            underperformer=underperformer,
            memory_insights=memory_insights,
            top_performers=top_performers,
            num_variations=count,
        )
        results[slot.key] = variations

    return results


# ══════════════════════════════════════════════════════════════
# CREATIVE STRATEGIST — DATA ANALYSIS BEFORE COPY GENERATION
# ══════════════════════════════════════════════════════════════

_STRATEGIST_SYSTEM = """You are a performance marketing strategist who combines data science,
consumer psychology, and direct-response expertise. You analyze ad performance data
to produce actionable creative briefs.

Your job is NOT to write ad copy. Your job is to ANALYZE the data and produce a
strategic brief that a copywriter will use to generate better ads.

You think in three layers:
1. DATA ANALYST — What do the numbers say? Which metrics differentiate winners from losers?
2. CONSUMER PSYCHOLOGIST — What cognitive triggers are working? (Loss aversion, social proof,
   curiosity gap, identity signaling, fear of missing out, anchoring, reciprocity, authority,
   scarcity, commitment/consistency, liking, unity)
3. CREATIVE STRATEGIST — Given the data and psychology, what specific angles should we test?

Output format: Return ONLY valid JSON with this structure:
{
  "dataset_patterns": {
    "what_top_performers_share": ["pattern1", "pattern2"],
    "what_underperformers_share": ["pattern1", "pattern2"],
    "key_metric_insights": ["insight1", "insight2"]
  },
  "psychological_analysis": {
    "triggers_in_winners": ["trigger: explanation"],
    "triggers_missing_in_losers": ["trigger: explanation"],
    "audience_psychology": "What the data tells us about the target audience's decision drivers"
  },
  "creative_strategy": {
    "angles_to_test": [
      {"angle": "name", "rationale": "why this angle based on data", "psychological_lever": "which trigger"},
    ],
    "angles_to_avoid": ["angle: reason based on data"],
    "tone_recommendation": "recommended tone based on what's working"
  },
  "per_underperformer_briefs": {
    "ad_name_or_id": {
      "why_failing": "specific diagnosis based on its metrics vs dataset",
      "recommended_angles": ["angle1", "angle2"],
      "key_insight": "one-sentence strategic direction"
    }
  }
}

No markdown, no explanation, no preamble. Just the JSON."""


def analyze_creative_strategy(
    platform_id: str,
    brand: str,
    product: str,
    underperformers: list[dict],
    top_performers: list[dict],
    dataset_summary: dict,
    memory_insights: str = "",
    creative_type: str = "",
) -> dict:
    """Run the Creative Strategist agent to analyze performance data.

    This runs ONCE per generation batch (not per underperformer). It produces
    a structured strategy brief that feeds into every copy generation call.

    Args:
        underperformers: list of ad_data dicts for flagged ads
        top_performers: list of ad_data dicts for best-performing ads
        dataset_summary: {total_ads, metrics_available, median_values, etc.}
        memory_insights: accumulated experiment memory string

    Returns:
        dict with dataset_patterns, psychological_analysis, creative_strategy,
        and per_underperformer_briefs. Returns empty dict on failure.
    """
    if not creative_type and underperformers:
        creative_type = _detect_creative_type(underperformers[0])

    # Build a compact data payload for the strategist
    # Trim underperformers to key fields
    trimmed_under = []
    for u in underperformers[:15]:  # Cap at 15 to stay within token limits
        trimmed = {}
        for k, v in u.items():
            if isinstance(v, float) and abs(v) > 1000:
                trimmed[k] = round(v, 2)
            else:
                trimmed[k] = v
        trimmed_under.append(trimmed)

    # Trim top performers similarly
    trimmed_top = []
    for t in top_performers[:10]:
        trimmed = {}
        for k, v in t.items():
            if isinstance(v, float) and abs(v) > 1000:
                trimmed[k] = round(v, 2)
            else:
                trimmed[k] = v
        trimmed_top.append(trimmed)

    creative_context = ""
    if creative_type == "video_influencer":
        creative_context = (
            "\nCONTEXT: These are INFLUENCER / UGC VIDEO ADS. The video creative is "
            "produced by content creators. The copy you're strategizing for accompanies "
            "the video in the feed (primary text, headline, link description)."
        )
    elif creative_type == "video":
        creative_context = (
            "\nCONTEXT: These are VIDEO ADS. The copy accompanies the video in the feed."
        )

    platform = get_platform(platform_id)
    prompt = f"""Analyze this ad performance data and produce a strategic creative brief.

Brand: {brand}
Product: {product}
Platform: {platform.name}
{creative_context}

=== DATASET SUMMARY ===
{json.dumps(dataset_summary, indent=2, default=str)}

=== TOP PERFORMING ADS (what's working) ===
{json.dumps(trimmed_top, indent=2, default=str)}

=== UNDERPERFORMING ADS (what needs fixing) ===
{json.dumps(trimmed_under, indent=2, default=str)}
"""

    if memory_insights and "No previous experiments" not in memory_insights:
        prompt += f"\n=== EXPERIMENT HISTORY ===\n{memory_insights}\n"

    prompt += """
Analyze this data as a data scientist + consumer psychologist. Identify:
1. Statistical patterns: What metrics differentiate winners from losers?
2. Psychological triggers: What cognitive biases are at play in the winning ads?
3. Creative angles: What specific angles should the copywriter test, and which should they avoid?
4. Per-underperformer diagnosis: Why is each specific ad failing and what angle would fix it?

Be SPECIFIC — reference actual numbers and ad names from the data. Don't be generic."""

    try:
        response = _get_client().messages.create(
            model=MODEL,
            max_tokens=4096,
            system=_STRATEGIST_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return _parse_json_response(response.content[0].text)
    except Exception:
        return {}


def build_dataset_summary(
    df_clean,
    mapping,
    underperformers_count: int,
) -> dict:
    """Build a compact dataset summary for the strategist agent.

    Args:
        df_clean: the cleaned DataFrame
        mapping: ColumnMapping from analyzer
        underperformers_count: how many ads were flagged

    Returns:
        dict with key dataset statistics
    """
    import pandas as pd

    summary = {
        "total_ads": len(df_clean),
        "underperformers": underperformers_count,
        "healthy_ads": len(df_clean) - underperformers_count,
        "metrics_available": list(mapping.metrics.keys()),
    }

    # Add median, mean, p25, p75 for each numeric metric
    metric_stats = {}
    for metric_type, col in mapping.metrics.items():
        series = pd.to_numeric(df_clean[col], errors="coerce").dropna()
        if len(series) < 2:
            continue
        metric_stats[metric_type] = {
            "column": col,
            "median": round(float(series.median()), 4),
            "mean": round(float(series.mean()), 4),
            "p25": round(float(series.quantile(0.25)), 4),
            "p75": round(float(series.quantile(0.75)), 4),
            "min": round(float(series.min()), 4),
            "max": round(float(series.max()), 4),
        }
    summary["metric_statistics"] = metric_stats

    return summary


# ══════════════════════════════════════════════════════════════
# COHERENT AD SET GENERATION
# ══════════════════════════════════════════════════════════════

def _build_ad_set_system_prompt(platform: PlatformProfile, creative_type: str = "text") -> str:
    """Build a system prompt that generates complete, coherent ad sets."""
    slot_specs = "\n".join(
        f'    - "{s.key}": {s.label} — max {s.char_limit} chars. {s.guidance}'
        for s in platform.slots
    )

    # Add creative-type-specific guidance
    creative_guidance = ""
    if creative_type == "video_influencer":
        creative_guidance = """
IMPORTANT CONTEXT: You are writing TEXT COPY to accompany INFLUENCER / UGC VIDEO ADS.
The video is the main creative — filmed by a content creator, not a polished brand production.
Your copy appears around the video in the feed (above it, below it, next to the CTA).

Guidelines for influencer video companion copy:
- Match the authentic, relatable tone of creator content — NOT corporate brand-speak
- Reference the video indirectly ("See why...", "Watch how...", "They tried...")
- Use social proof angles ("10K+ people switched", "creators love this")
- Hook with curiosity or a relatable problem the video addresses
- Keep it conversational — like a friend recommending something
- Don't over-brand or be overly promotional — the video does the selling
"""
    elif creative_type == "video":
        creative_guidance = """
IMPORTANT CONTEXT: You are writing TEXT COPY to accompany VIDEO ADS.
The video is the main creative. Your copy appears around the video in the feed.
Hook viewers and reinforce the video's message. Reference the visual content indirectly.
"""

    return f"""You are an expert ad copywriter specializing in {platform.name}.

You generate COMPLETE AD VARIATIONS where every copy element works together
as a coherent set — same angle, same tone, mutually reinforcing.

PLATFORM: {platform.name}
COPY ELEMENTS PER VARIATION:
{slot_specs}
{creative_guidance}
STRICT RULES:
1. Each variation is ONE COMPLETE AD — all elements share the same angle/theme.
2. Character limits are HARD — every element must respect its limit (including spaces and emojis).
3. Vary the ANGLE across variations: benefits, urgency, curiosity, social proof, problem/solution, emotional.
4. Use proven direct-response copywriting techniques.
5. Never repeat the same angle twice in a batch.

Output ONLY valid JSON — an array of objects. Each object is one complete ad variation:
[
  {{
{chr(10).join(f'    "{s.key}": "text here",' for s in platform.slots)}
    "angle": "brief angle description (e.g. urgency, social proof, pain point)"
  }}
]

No markdown, no explanation, no preamble. Just the JSON array."""


def generate_ad_sets(
    platform_id: str,
    brand: str,
    product: str,
    underperformer: dict,
    memory_insights: str,
    top_performers: list[dict],
    num_sets: int = DEFAULT_AD_SETS,
    max_retries: int = 2,
    strategy_brief: dict | None = None,
) -> list[dict]:
    """Generate complete, coherent ad variations for an underperforming ad.

    Unlike generate_platform_copy() which generates each slot independently
    (leading to incoherent combinations), this generates complete ad sets
    where all copy elements are thematically aligned.

    Args:
        num_sets: Number of complete ad variations to generate (default: 5)
        strategy_brief: Output from analyze_creative_strategy(). Contains
            data-driven patterns, psychological analysis, and per-ad briefs.
            When provided, the copywriter uses this analysis instead of
            guessing from raw data.

    Returns:
        list of dicts, each containing all slot keys + "angle".
        e.g. [
            {"primary_text": "...", "headline": "...", "link_description": "...", "angle": "urgency"},
            ...
        ]
    """
    platform = get_platform(platform_id)
    creative_type = _detect_creative_type(underperformer)
    system = _build_ad_set_system_prompt(platform, creative_type=creative_type)
    context = _build_context(brand, product, underperformer, memory_insights, top_performers,
                             creative_type=creative_type)

    # Inject strategy brief into context if available
    if strategy_brief:
        strategy_lines = ["\n=== CREATIVE STRATEGY BRIEF (data-driven analysis) ==="]

        # Dataset-level patterns
        patterns = strategy_brief.get("dataset_patterns", {})
        if patterns.get("what_top_performers_share"):
            strategy_lines.append("TOP PERFORMER PATTERNS:")
            for p in patterns["what_top_performers_share"]:
                strategy_lines.append(f"  + {p}")
        if patterns.get("key_metric_insights"):
            strategy_lines.append("KEY DATA INSIGHTS:")
            for p in patterns["key_metric_insights"]:
                strategy_lines.append(f"  • {p}")

        # Psychological analysis
        psych = strategy_brief.get("psychological_analysis", {})
        if psych.get("triggers_in_winners"):
            strategy_lines.append("PSYCHOLOGICAL TRIGGERS IN WINNERS:")
            for t in psych["triggers_in_winners"]:
                strategy_lines.append(f"  ✓ {t}")
        if psych.get("triggers_missing_in_losers"):
            strategy_lines.append("WHAT LOSERS ARE MISSING:")
            for t in psych["triggers_missing_in_losers"]:
                strategy_lines.append(f"  ✗ {t}")
        if psych.get("audience_psychology"):
            strategy_lines.append(f"AUDIENCE: {psych['audience_psychology']}")

        # Creative strategy
        cs = strategy_brief.get("creative_strategy", {})
        if cs.get("angles_to_test"):
            strategy_lines.append("RECOMMENDED ANGLES:")
            for a in cs["angles_to_test"]:
                if isinstance(a, dict):
                    strategy_lines.append(f"  → {a.get('angle', '')}: {a.get('rationale', '')} [{a.get('psychological_lever', '')}]")
                else:
                    strategy_lines.append(f"  → {a}")
        if cs.get("angles_to_avoid"):
            strategy_lines.append("AVOID:")
            for a in cs["angles_to_avoid"]:
                strategy_lines.append(f"  ✗ {a}")
        if cs.get("tone_recommendation"):
            strategy_lines.append(f"TONE: {cs['tone_recommendation']}")

        # Per-underperformer brief (find this specific ad)
        briefs = strategy_brief.get("per_underperformer_briefs", {})
        ad_name = next(
            (str(underperformer.get(k, "")) for k in ("Ad name", "ad_name", "Ad Name") if underperformer.get(k)),
            "",
        )
        if ad_name and briefs:
            # Try exact match, then partial match
            ad_brief = briefs.get(ad_name)
            if not ad_brief:
                for key, val in briefs.items():
                    if key.lower() in ad_name.lower() or ad_name.lower() in key.lower():
                        ad_brief = val
                        break
            if ad_brief and isinstance(ad_brief, dict):
                strategy_lines.append(f"\nSPECIFIC BRIEF FOR THIS AD ({ad_name}):")
                if ad_brief.get("why_failing"):
                    strategy_lines.append(f"  Diagnosis: {ad_brief['why_failing']}")
                if ad_brief.get("recommended_angles"):
                    strategy_lines.append(f"  Try: {', '.join(ad_brief['recommended_angles'])}")
                if ad_brief.get("key_insight"):
                    strategy_lines.append(f"  Direction: {ad_brief['key_insight']}")

        context += "\n" + "\n".join(strategy_lines)

    # Build the slot spec for the prompt
    limits = ", ".join(f"{s.label} ≤{s.char_limit}" for s in platform.slots)
    prompt = (
        f"Generate {num_sets} complete ad variations for this underperforming ad.\n"
        f"Each variation must include all elements: {limits}.\n"
        f"All elements in one variation should share the same angle/theme.\n\n"
        f"{context}"
    )

    for attempt in range(max_retries + 1):
        response = _get_client().messages.create(
            model=MODEL,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )

        try:
            results = _parse_json_response(response.content[0].text)
        except (json.JSONDecodeError, IndexError):
            if attempt < max_retries:
                continue
            return []

        # Validate ALL slots in each set against character limits
        valid = []
        violations = []
        for r in results:
            all_ok = True
            for slot in platform.slots:
                text = r.get(slot.key, "")
                if len(text) > slot.char_limit:
                    all_ok = False
                    break
            if all_ok:
                valid.append(r)
            else:
                violations.append(r)

        if violations and attempt < max_retries:
            violation_lines = []
            for r in violations:
                for slot in platform.slots:
                    text = r.get(slot.key, "")
                    if len(text) > slot.char_limit:
                        violation_lines.append(
                            f'  {slot.label}: "{text}" = {len(text)} chars (limit {slot.char_limit})'
                        )
            violation_text = "\n".join(violation_lines)
            prompt = (
                f"Some elements exceeded character limits. Fix these violations:\n{violation_text}\n\n"
                f"Generate {num_sets - len(valid)} more COMPLETE ad variations ({limits}).\n\n{context}"
            )
            continue

        return valid

    return []


# ══════════════════════════════════════════════════════════════
# BACKWARD-COMPATIBLE WRAPPERS
# ══════════════════════════════════════════════════════════════
# These keep the old API working for any code that still calls them.

def generate_headlines(
    brand: str,
    product: str,
    underperformer: dict,
    memory_insights: str,
    top_performers: list[dict],
    num_variations: int = 8,
    max_retries: int = 2,
    platform_id: str = "generic",
) -> list[dict]:
    """Backward-compatible headline generation.

    Uses the 'headline' slot from the specified platform.
    """
    platform = get_platform(platform_id)
    headline_slot = next((s for s in platform.slots if s.key == "headline"), None)
    if not headline_slot:
        # Fallback to generic
        headline_slot = PLATFORMS["generic"].slots[0]
        platform = PLATFORMS["generic"]

    return generate_slot_copy(
        slot=headline_slot,
        platform=platform,
        brand=brand,
        product=product,
        underperformer=underperformer,
        memory_insights=memory_insights,
        top_performers=top_performers,
        num_variations=num_variations,
        max_retries=max_retries,
    )


def generate_descriptions(
    brand: str,
    product: str,
    underperformer: dict,
    memory_insights: str,
    top_performers: list[dict],
    num_variations: int = 5,
    max_retries: int = 2,
    platform_id: str = "generic",
) -> list[dict]:
    """Backward-compatible description generation.

    Uses the 'description' slot from the specified platform.
    Falls back to the first non-headline slot if no 'description' slot exists.
    """
    platform = get_platform(platform_id)
    desc_slot = next((s for s in platform.slots if s.key == "description"), None)
    if not desc_slot:
        # Use first non-headline slot
        desc_slot = next((s for s in platform.slots if s.key != "headline"), None)
    if not desc_slot:
        desc_slot = PLATFORMS["generic"].slots[1]
        platform = PLATFORMS["generic"]

    return generate_slot_copy(
        slot=desc_slot,
        platform=platform,
        brand=brand,
        product=product,
        underperformer=underperformer,
        memory_insights=memory_insights,
        top_performers=top_performers,
        num_variations=num_variations,
        max_retries=max_retries,
    )
