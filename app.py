"""Ad Optimizer — AI-powered ad copy pipeline.

Reimagined UX: sidebar navigation, split-pane optimize workspace,
compact header, zero-chrome-before-content philosophy.
"""
from __future__ import annotations

__version__ = "0.7.0"

import streamlit as st
import pandas as pd
import json
import os
import io
import base64 as _b64
from pathlib import Path
from datetime import datetime, timezone

from analyzer import detect_columns, clean_metrics, flag_underperformers, detect_fatigue
from memory import (
    load_history, save_run, generate_run_id, summarize_insights,
    extract_top_performers, RunRecord, detect_outcomes,
    _update_last_run_outcomes, _extract_ad_id, outcome_summary,
    score_hypotheses,
)
from agents import (
    generate_ad_sets, DEFAULT_AD_SETS,
    analyze_creative_strategy, build_dataset_summary,
    list_platforms, get_platform, detect_platform,
    FUNNEL_STAGES,
)
from export import build_export_workbook
from platforms import MetaAdsPlatform, GoogleAdsPlatform
from clients import (
    list_clients, load_client, save_client, create_client,
    delete_client, client_memory_dir, ClientConfig, CATEGORIES,
)
from auth import (
    check_auth, render_logout_button, get_current_role,
    has_permission, render_user_management, ROLES,
)
from templates import (
    list_templates, load_template, save_template, create_template,
    delete_template, render_preview, render_all_previews,
    export_previews_zip, AdTemplate, TextSlot, get_template_image_path,
)

# ── Page Config ──────────────────────────────────────────
st.set_page_config(page_title="Ad Optimizer", page_icon="⚡", layout="wide")

# ── Auth Gate ────────────────────────────────────────────
if not check_auth():
    st.stop()

# ══════════════════════════════════════════════════════════
# CSS — minimal, functional, fast
# ══════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,600;9..40,700;9..40,800&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --accent: #E8FF47;
    --accent-dim: rgba(232,255,71,0.12);
    --accent-mid: rgba(232,255,71,0.25);
    --surface: rgba(255,255,255,0.025);
    --border: rgba(255,255,255,0.07);
    --border-hover: rgba(255,255,255,0.15);
    --text-primary: #F0F0F0;
    --text-secondary: rgba(255,255,255,0.5);
    --text-muted: rgba(255,255,255,0.3);
    --danger: #FF6B6B;
    --success: #4ADE80;
    --info: #60A5FA;
    --bg-deep: #08080C;
    --bg-surface: #0E0E14;
}

.stApp { font-family: 'DM Sans', sans-serif; background: var(--bg-deep); }
header[data-testid="stHeader"] { background: transparent; }
div[data-testid="stToolbar"] { display: none; }
div[data-testid="stDecoration"] { display: none; }
.block-container { padding-top: 1rem; max-width: 1400px; }

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: var(--bg-surface);
    border-right: 1px solid var(--border);
}
section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] .stMarkdown li {
    color: var(--text-secondary); font-size: 0.85rem;
}

/* ── Nav buttons in sidebar ── */
.nav-btn {
    display: block; width: 100%; padding: 0.6rem 0.9rem;
    background: transparent; border: 1px solid transparent;
    border-radius: 8px; text-align: left; cursor: pointer;
    color: var(--text-secondary); font-size: 0.85rem; font-weight: 500;
    transition: all 0.15s ease; margin-bottom: 2px;
    font-family: 'DM Sans', sans-serif; text-decoration: none;
}
.nav-btn:hover { background: var(--surface); border-color: var(--border); color: var(--text-primary); }
.nav-btn.active {
    background: var(--accent-dim); border-color: rgba(232,255,71,0.2);
    color: var(--accent); font-weight: 600;
}

/* ── Page header ── */
.page-header {
    display: flex; align-items: center; gap: 0.75rem;
    padding-bottom: 1rem; margin-bottom: 1.5rem;
    border-bottom: 1px solid var(--border);
}
.page-header .icon {
    width: 36px; height: 36px; border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.1rem; flex-shrink: 0;
}
.page-header .title { font-size: 1.15rem; font-weight: 700; letter-spacing: -0.01em; }
.page-header .sub { font-size: 0.8rem; color: var(--text-muted); }

/* ── Stat row ── */
.stat-row { display: flex; gap: 0.75rem; margin: 0.75rem 0; }
.stat-card {
    flex: 1; background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 1rem; text-align: center;
}
.stat-card:hover { border-color: var(--border-hover); }
.stat-value {
    font-size: 1.6rem; font-weight: 800; color: var(--text-primary);
    font-family: 'JetBrains Mono', monospace; letter-spacing: -0.03em;
}
.stat-value.red { color: var(--danger); }
.stat-value.green { color: var(--success); }
.stat-value.accent { color: var(--accent); }
.stat-value.amber { color: #FCD34D; }
.stat-value.green { color: #4ADE80; }
.stat-label {
    font-size: 0.68rem; color: var(--text-muted);
    text-transform: uppercase; letter-spacing: 0.08em; margin-top: 0.2rem; font-weight: 600;
}

/* ── Ad cards ── */
.ad-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 1rem; margin-bottom: 0.6rem;
    transition: all 0.15s ease;
}
.ad-card:hover { border-color: var(--border-hover); }
.ad-card.selected { border-color: var(--accent); background: var(--accent-dim); }
.ad-card.bad { border-left: 3px solid var(--danger); }
.ad-card.fatigued { border-left: 3px solid #FCD34D; }
.ad-card .name { font-weight: 600; font-size: 0.9rem; margin-bottom: 0.2rem; overflow: hidden; }
.ad-card .meta { font-size: 0.75rem; color: var(--text-muted); }
.ad-card .score {
    float: right; background: rgba(255,107,107,0.12); color: var(--danger);
    padding: 0.15rem 0.5rem; border-radius: 6px; font-size: 0.75rem;
    font-weight: 700; font-family: 'JetBrains Mono', monospace;
}
.ad-card .fatigue-badge {
    display: inline-block; background: rgba(251,191,36,0.12); color: #FCD34D;
    padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.68rem;
    font-weight: 500; margin-top: 0.3rem;
}
.reason-tags { margin-top: 0.3rem; display: flex; flex-wrap: wrap; gap: 0.2rem; }
.reason-tag {
    background: rgba(255,107,107,0.1); color: #FFA0A0;
    padding: 0.15rem 0.5rem; border-radius: 5px; font-size: 0.7rem;
    font-weight: 500; font-family: 'JetBrains Mono', monospace;
}

/* ── Generated copy cards ── */
.gen-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 1.2rem; margin-bottom: 0.75rem;
}
.gen-card .angle {
    font-size: 0.72rem; font-weight: 600; color: var(--accent);
    text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 0.5rem;
}
.gen-card .copy-field {
    background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.05);
    border-radius: 8px; padding: 0.6rem 0.8rem; margin-bottom: 0.4rem;
    font-size: 0.88rem; line-height: 1.5;
}
.gen-card .copy-label {
    font-size: 0.68rem; color: var(--text-muted); text-transform: uppercase;
    letter-spacing: 0.06em; margin-bottom: 0.2rem; font-weight: 600;
}
.gen-card .char-count {
    float: right; font-size: 0.68rem; font-family: 'JetBrains Mono', monospace;
    color: var(--text-muted);
}
.gen-card .char-count.over { color: var(--danger); }
.gen-card .rationale {
    margin-top: 0.6rem; padding: 0.6rem 0.8rem;
    background: rgba(96,165,250,0.04); border-left: 2px solid rgba(96,165,250,0.3);
    border-radius: 0 6px 6px 0; font-size: 0.8rem; color: var(--text-secondary);
    line-height: 1.5;
}

/* ── Empty states ── */
.empty-state {
    text-align: center; padding: 3rem 2rem; color: var(--text-muted);
}
.empty-state .icon { font-size: 2.2rem; margin-bottom: 0.75rem; }
.empty-state .title {
    font-size: 1rem; font-weight: 600; color: var(--text-secondary); margin-bottom: 0.4rem;
}
.empty-state .desc {
    font-size: 0.82rem; max-width: 400px; margin: 0 auto; line-height: 1.6;
}

/* ── Checklist items ── */
.checklist-item {
    display: flex; align-items: flex-start; gap: 0.6rem; padding: 0.6rem 0.8rem;
    margin-bottom: 0.4rem; background: var(--surface);
    border: 1px solid var(--border); border-radius: 8px;
}
.checklist-item.done { border-color: rgba(74,222,128,0.2); background: rgba(74,222,128,0.03); }
.checklist-item .check { flex-shrink: 0; font-size: 1rem; }
.checklist-item .label { font-weight: 600; font-size: 0.85rem; }
.checklist-item .hint { font-size: 0.78rem; color: var(--text-muted); }

/* ── Platform cards ── */
.platform-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 14px; padding: 1.2rem; margin-bottom: 0.75rem;
}
.platform-card.connected { border-color: rgba(74,222,128,0.25); background: rgba(74,222,128,0.03); }
.platform-card h3 { margin: 0 0 0.3rem 0; font-size: 1rem; }
.platform-badge {
    display: inline-block; padding: 0.15rem 0.5rem; border-radius: 5px;
    font-size: 0.7rem; font-weight: 600; font-family: 'JetBrains Mono', monospace;
}
.platform-badge.meta { background: rgba(24,119,242,0.12); color: #60A5FA; }
.platform-badge.google { background: rgba(96,165,250,0.12); color: #93C5FD; }
.platform-badge.connected { background: rgba(74,222,128,0.12); color: var(--success); }
.push-result {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 0.6rem 0.8rem; margin: 0.3rem 0; font-size: 0.82rem;
}
.push-result.success { border-color: rgba(74,222,128,0.25); }
.push-result.error { border-color: rgba(255,107,107,0.25); }

/* ── Figma flow ── */
.figma-flow { display: flex; gap: 0.5rem; margin: 0.75rem 0; }
.figma-step {
    flex: 1; background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 0.75rem; text-align: center;
}
.figma-step .num {
    width: 28px; height: 28px; border-radius: 7px;
    background: var(--accent-dim); color: var(--accent);
    display: inline-flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: 0.8rem; margin-bottom: 0.3rem;
    font-family: 'JetBrains Mono', monospace;
}
.figma-step .label { font-size: 0.75rem; font-weight: 600; color: var(--text-secondary); }
.arrow-connector { display: flex; align-items: center; color: var(--text-muted); font-size: 1.2rem; }

/* ── Streamlit overrides ── */
div[data-testid="stFileUploader"] {
    border: 2px dashed var(--border); border-radius: 12px; padding: 0.3rem;
}
div[data-testid="stFileUploader"]:hover { border-color: var(--accent-mid); }
.stTabs [data-baseweb="tab-list"] {
    gap: 2px; background: var(--surface); border-radius: 10px;
    padding: 3px; border: 1px solid var(--border);
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px; padding: 0.4rem 1rem; font-weight: 600; font-size: 0.8rem;
}
.stTabs [aria-selected="true"] {
    background: var(--accent-dim) !important; color: var(--accent) !important;
}
.stDownloadButton > button {
    background: var(--accent-dim) !important;
    border: 1px solid rgba(232,255,71,0.2) !important;
    border-radius: 8px !important; font-weight: 600 !important;
    color: var(--accent) !important;
}
.stDownloadButton > button:hover {
    background: var(--accent-mid) !important;
    border-color: rgba(232,255,71,0.4) !important;
}
button[kind="primary"] {
    background: var(--accent) !important; color: #08080C !important;
    border: none !important; border-radius: 8px !important;
    font-weight: 700 !important; padding: 0.5rem 1.8rem !important;
}
button[kind="primary"]:hover { filter: brightness(0.9) !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════
def has_api_key():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    try:
        secret = st.secrets.get("ANTHROPIC_API_KEY", "")
        if secret:
            os.environ["ANTHROPIC_API_KEY"] = secret
            return True
    except Exception:
        pass
    if "api_key" in st.session_state and st.session_state.api_key:
        os.environ["ANTHROPIC_API_KEY"] = st.session_state.api_key
        return True
    return False

def active_client() -> ClientConfig | None:
    cid = st.session_state.get("active_client_id")
    if cid:
        return load_client(cid)
    return None

def get_memory_dir():
    c = active_client()
    if c:
        return client_memory_dir(c.client_id)
    return None

def _clear_pipeline_state():
    for key in ["all_headlines", "all_descriptions", "all_ad_sets",
                "all_slot_results", "strategy_brief", "underperformers", "df",
                "df_clean", "mapping", "push_results", "meta_connected",
                "google_connected", "gen_platform_id", "auto_platform_id",
                "meta_account_name", "google_account_name"]:
        st.session_state.pop(key, None)

# ══════════════════════════════════════════════════════════
# SIDEBAR — Navigation + Client + Controls
# ══════════════════════════════════════════════════════════
PAGES = {
    "optimize": "Optimize",
    "publish": "Publish & Export",
    "settings": "Settings",
    "templates": "Templates",
    "memory": "Memory",
}
PAGE_ICONS = {
    "optimize": "⚡",
    "publish": "🚀",
    "settings": "⚙️",
    "templates": "🎨",
    "memory": "🧠",
}

if "page" not in st.session_state:
    st.session_state.page = "optimize"

with st.sidebar:
    # Logo + title
    _logo_path = Path(__file__).parent / "egc_logo.png"
    if _logo_path.exists():
        _logo_b64 = _b64.b64encode(_logo_path.read_bytes()).decode()
        st.markdown(f'<img src="data:image/png;base64,{_logo_b64}" style="height:28px;margin-bottom:0.5rem;opacity:0.85;" />', unsafe_allow_html=True)
    st.markdown("**Ad Optimizer**")
    render_logout_button()

    st.markdown("---")

    # ── Client Selector ──
    clients = list_clients()
    client_names = ["Select a client..."] + [c.name for c in clients] + ["+ New Client"]
    current_idx = 0
    if "active_client_id" in st.session_state:
        for i, c in enumerate(clients):
            if c.client_id == st.session_state.active_client_id:
                current_idx = i + 1
                break

    selected = st.selectbox("Client", client_names, index=current_idx,
                            key="client_selector", label_visibility="collapsed")

    if selected == "+ New Client":
        new_name = st.text_input("Client name", key="new_client_name", placeholder="e.g. Acme Corp")
        if new_name and st.button("Create", key="create_client_btn", use_container_width=True):
            c = create_client(new_name)
            st.session_state.active_client_id = c.client_id
            _clear_pipeline_state()
            st.rerun()
    elif selected != "Select a client...":
        chosen = next((c for c in clients if c.name == selected), None)
        if chosen and st.session_state.get("active_client_id") != chosen.client_id:
            st.session_state.active_client_id = chosen.client_id
            _clear_pipeline_state()
            if chosen.anthropic_api_key:
                os.environ["ANTHROPIC_API_KEY"] = chosen.anthropic_api_key
            else:
                os.environ.pop("ANTHROPIC_API_KEY", None)
            st.rerun()

    cl = active_client()
    if cl and cl.brand:
        _cat = f" · {cl.category}" if cl.category else ""
        st.caption(f"{cl.brand}{_cat}")

    st.markdown("---")

    # ── Navigation ──
    for page_id, page_label in PAGES.items():
        icon = PAGE_ICONS[page_id]
        is_active = st.session_state.page == page_id
        if st.button(
            f"{icon}  {page_label}",
            key=f"nav_{page_id}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            st.session_state.page = page_id
            st.rerun()

    # ── Status indicators ──
    st.markdown("---")
    if has_api_key():
        st.markdown('<span style="font-size:0.78rem;color:rgba(74,222,128,0.8);">✓ API Key</span>', unsafe_allow_html=True)
    elif cl:
        st.markdown('<span style="font-size:0.78rem;color:rgba(255,107,107,0.8);">⚠ No API Key → Settings</span>', unsafe_allow_html=True)

    # ── Memory summary ──
    mem_dir = get_memory_dir()
    history = load_history(mem_dir)
    total_var = sum(len(r.generated_headlines) for r in history) if history else 0
    if history:
        st.caption(f"🧠 {len(history)} runs · {total_var} variations")
    else:
        st.caption("🧠 No runs yet")

    st.markdown(f'<div style="position:fixed;bottom:0.8rem;font-size:0.65rem;color:rgba(255,255,255,0.25);font-family:monospace;">v{__version__}</div>', unsafe_allow_html=True)

# Get common values
brand = cl.brand if cl else ""
product = cl.product if cl else ""
current_page = st.session_state.page


# ══════════════════════════════════════════════════════════
# PAGE: OPTIMIZE — The core workspace
# ══════════════════════════════════════════════════════════
def render_optimize():
    # ── No client gate ──
    if not cl:
        st.markdown('''
        <div class="empty-state">
            <div class="icon">⚡</div>
            <div class="title">Select a client to start</div>
            <div class="desc">Pick a client from the sidebar dropdown, or create a new one. Each client has its own brand context, experiment memory, and credentials.</div>
        </div>
        ''', unsafe_allow_html=True)
        return

    # ── Platform selection (required first) ──
    _hdr_col, _plat_col = st.columns([5, 2])
    with _plat_col:
        platform_options = {p.name: p.id for p in list_platforms()}
        platform_names = list(platform_options.keys())
        # Check for auto-detected platform from previous upload
        auto_detected = st.session_state.get("auto_platform_id")
        if auto_detected:
            default_idx = 0
            for i, name in enumerate(platform_names):
                if platform_options[name] == auto_detected:
                    default_idx = i
                    break
            selected_platform_name = st.selectbox(
                "Platform", platform_names, index=default_idx,
                key="platform_selector",
            )
            selected_platform_id = platform_options[selected_platform_name]
        else:
            _opts = ["Select a platform…"] + platform_names
            selected_platform_name = st.selectbox(
                "Platform", _opts, index=0,
                key="platform_selector",
            )
            selected_platform_id = platform_options.get(selected_platform_name)

    gen_platform = get_platform(selected_platform_id) if selected_platform_id else None

    # ── Page header ──
    with _hdr_col:
        _plat_label = f"{gen_platform.icon} {gen_platform.name} · " if gen_platform else ""
        st.markdown(f'<div class="page-header"><div class="icon" style="background:var(--accent-dim);">⚡</div><div><div class="title">Optimize — {cl.name}</div><div class="sub">{_plat_label}Upload → Analyze → Generate in one view</div></div></div>', unsafe_allow_html=True)

    # ── Gate: platform must be selected before upload ──
    if not selected_platform_id:
        st.markdown('<div class="empty-state"><div class="icon">🎯</div><div class="title">Select a platform to begin</div><div class="desc">Choose Meta Ads, Google Ads, TikTok, LinkedIn, or another platform above. This informs how your ad data is analyzed and how new copy is generated.</div></div>', unsafe_allow_html=True)
        return

    # ── File Upload (compact, at top) ──
    uploaded = st.file_uploader(f"Drop {gen_platform.name} performance CSV or XLSX",
                                type=["csv", "xlsx", "xls"],
                                key="file_upload",
                                label_visibility="collapsed")

    if uploaded:
        if uploaded.name.endswith((".xlsx", ".xls")):
            df = pd.read_excel(uploaded)
        else:
            df = pd.read_csv(uploaded)
        st.session_state.df = df
        mapping = detect_columns(df)
        st.session_state.mapping = mapping
        df_clean = clean_metrics(df, mapping)
        st.session_state.df_clean = df_clean
        underperformers = flag_underperformers(df_clean, mapping)
        underperformers = detect_fatigue(df_clean, mapping, underperformers)
        st.session_state.underperformers = underperformers

        # Auto-detect platform from columns (may override selection)
        detected_pid = detect_platform(list(df.columns))
        if detected_pid:
            st.session_state.auto_platform_id = detected_pid

        # ── Feedback loop: track outcomes from previous run ──
        _mem_dir = get_memory_dir()
        _prev_history = load_history(_mem_dir)
        if _prev_history:
            # Build current ad ID sets for matching
            _under_ids = set()
            for u in underperformers:
                _uid = _extract_ad_id(u.ad_data, mapping.identifiers)
                if _uid:
                    _under_ids.add(_uid)
            _top = extract_top_performers(df_clean, mapping, n=10)
            _top_ids = set()
            for t in _top:
                _tid = _extract_ad_id(t, mapping.identifiers)
                if _tid:
                    _top_ids.add(_tid)
            _all_ids = set()
            for idx in df_clean.index:
                for col in mapping.identifiers:
                    val = str(df_clean.at[idx, col]).strip()
                    if val and val != "nan":
                        _all_ids.add(val)
                        break
            outcomes = detect_outcomes(_under_ids, _top_ids, _all_ids, _prev_history)
            if outcomes:
                _update_last_run_outcomes(outcomes, _mem_dir)
                st.session_state.latest_outcomes = outcomes
                n_improved = sum(1 for o in outcomes if o["status"] == "improved")
                n_bad = sum(1 for o in outcomes if o["status"] == "still_bad")
                if n_improved > 0:
                    st.toast(f"🔄 Feedback loop: {n_improved} ads improved since last run!", icon="✅")
                if n_bad > 0:
                    st.toast(f"🔄 {n_bad} ads still underperforming — adjusting strategy", icon="⚠️")

    # ── If no data yet, show guidance ──
    if "underperformers" not in st.session_state:
        st.markdown('''
        <div class="empty-state">
            <div class="icon">📂</div>
            <div class="title">Upload your ad performance data</div>
            <div class="desc">Export from Meta Ads, Google Ads, TikTok, LinkedIn, or any platform. Include ad identifiers, copy fields (headlines, descriptions), and performance metrics (CTR, CPC, conversions, etc). Columns are auto-detected.</div>
        </div>
        ''', unsafe_allow_html=True)
        return

    # ── Data is loaded — show the split workspace ──
    underperformers = st.session_state.underperformers
    mapping = st.session_state.mapping
    df_clean = st.session_state.df_clean
    n_under = len(underperformers)
    n_fatigued = sum(1 for u in underperformers if u.fatigue_score > 0.2)
    flag_pct = n_under / len(df_clean) * 100 if len(df_clean) else 0

    # Stats bar
    st.markdown(f'''
    <div class="stat-row">
        <div class="stat-card"><div class="stat-value">{len(df_clean)}</div><div class="stat-label">Total Ads</div></div>
        <div class="stat-card"><div class="stat-value red">{n_under}</div><div class="stat-label">Underperforming</div></div>
        <div class="stat-card"><div class="stat-value amber">{n_fatigued}</div><div class="stat-label">Fatigued</div></div>
        <div class="stat-card"><div class="stat-value accent">{flag_pct:.0f}%</div><div class="stat-label">Flag Rate</div></div>
    </div>
    ''', unsafe_allow_html=True)

    # Column detection (collapsed)
    with st.expander("Column Detection & Raw Data"):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Identifiers:** {', '.join(mapping.identifiers) or 'None'}")
            st.markdown(f"**Headlines:** {', '.join(mapping.headlines) or 'None detected'}")
            st.markdown(f"**Descriptions:** {', '.join(mapping.descriptions) or 'None detected'}")
        with c2:
            for mt, cn in mapping.metrics.items():
                st.markdown(f"**{mt.replace('_', ' ').title()}:** {cn}")
        st.dataframe(df_clean, use_container_width=True, height=200)

    if not underperformers:
        st.success("All ads performing above threshold — nothing to optimize.")
        return

    # ══════════════════════════════════════════════════════
    # SPLIT PANE: Underperformers (left) | Generated Copy (right)
    # ══════════════════════════════════════════════════════
    col_left, col_right = st.columns([2, 3])

    with col_left:
        st.markdown(f"**Underperformers** ({n_under})")
        _scroll = st.container(height=500)
        with _scroll:
            for i, u in enumerate(underperformers):
                label = next((str(u.ad_data.get(c, "")) for c in mapping.identifiers if u.ad_data.get(c)), f"Row {u.index}")
                headline = next((str(u.ad_data.get(c, "")) for c in mapping.headlines if u.ad_data.get(c)), "")
                reasons = "".join(f'<div class="reason-tag">{r}</div>' for r in u.reasons)
                fatigue = ""
                if u.fatigue_signals:
                    fatigue = "".join(f'<div class="fatigue-badge">\u23f3 {s}</div>' for s in u.fatigue_signals)
                meta = f'<div class="meta">{headline[:60]}</div>' if headline else ""
                card_class = "fatigued" if u.fatigue_score > 0.2 else "bad"
                st.markdown(f'<div class="ad-card {card_class}"><div class="name">{label} <div class="score">Score: {u.score}</div></div>{meta}<div class="reason-tags">{reasons}</div>{fatigue}</div>', unsafe_allow_html=True)

    with col_right:
        # ── Generation controls ──
        st.caption("🎯 **Funnel stage** — controls the tone and intent of generated copy")
        _funnel_options = {"Auto": ""} | {v["label"]: k for k, v in FUNNEL_STAGES.items()}
        _selected_funnel_label = st.radio(
            "Funnel stage", list(_funnel_options.keys()),
            key="funnel_stage", horizontal=True, label_visibility="collapsed",
        )
        _selected_funnel = _funnel_options[_selected_funnel_label]

        # ── Variations slider ──
        num_ad_sets = st.slider("Variations per ad", 1, 10, DEFAULT_AD_SETS, key="num_ad_sets")

        # ── Readiness check ──
        _ready = has_api_key() and brand and product
        if not _ready:
            missing_parts = []
            if not has_api_key():
                missing_parts.append("API key")
            if not brand or not product:
                missing_parts.append("brand brief")
            st.warning(f"Missing: {', '.join(missing_parts)}. Configure in Settings.")

        # ── Generate button ──
        if _ready and st.button("Generate Ad Copy", type="primary", use_container_width=True):
            gen_history = load_history(get_memory_dir())
            insights = summarize_insights(gen_history)
            top_performers = extract_top_performers(df_clean, mapping)
            all_ad_sets: list[dict] = []
            total_steps = len(underperformers) + 1
            progress = st.progress(0, text="Analyzing performance data...")

            _gen_client = active_client()
            _brand_brief = None
            if _gen_client:
                _brand_brief = {
                    "category": _gen_client.category,
                    "brand_description": _gen_client.brand_description,
                    "target_audience": _gen_client.target_audience,
                    "brand_voice": _gen_client.brand_voice,
                    "key_differentiators": _gen_client.key_differentiators,
                    "competitors": _gen_client.competitors,
                }
                if not any(_brand_brief.values()):
                    _brand_brief = None

            dataset_summary = build_dataset_summary(df_clean, mapping, len(underperformers))
            strategy_brief = analyze_creative_strategy(
                platform_id=selected_platform_id,
                brand=brand, product=product,
                underperformers=[u.ad_data for u in underperformers],
                top_performers=top_performers,
                dataset_summary=dataset_summary,
                memory_insights=insights,
                brand_brief=_brand_brief,
                funnel_stage=_selected_funnel,
            )
            st.session_state.strategy_brief = strategy_brief
            progress.progress(1 / total_steps, text="Strategy complete. Generating copy...")

            # Parallel generation — run all underperformers concurrently
            from concurrent.futures import ThreadPoolExecutor, as_completed
            _ad_labels = []
            _futures = {}

            def _gen_one(u_data, label):
                return label, generate_ad_sets(
                    platform_id=selected_platform_id,
                    brand=brand, product=product,
                    underperformer=u_data,
                    memory_insights=insights,
                    top_performers=top_performers,
                    num_sets=num_ad_sets,
                    strategy_brief=strategy_brief,
                    brand_brief=_brand_brief,
                    funnel_stage=_selected_funnel,
                )

            max_workers = min(8, len(underperformers))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for u in underperformers:
                    ad_label = next((str(u.ad_data.get(c, "")) for c in mapping.identifiers if u.ad_data.get(c)), f"Row {u.index}")
                    fut = executor.submit(_gen_one, u.ad_data, ad_label)
                    _futures[fut] = ad_label

                done_count = 0
                for fut in as_completed(_futures):
                    done_count += 1
                    lbl = _futures[fut]
                    progress.progress((done_count + 1) / total_steps, text=f"Generated: {lbl} ({done_count}/{len(underperformers)})")
                    try:
                        label, ad_sets = fut.result()
                        for ad_set in ad_sets:
                            ad_set["original_ad"] = label
                            all_ad_sets.append(ad_set)
                    except Exception as e:
                        st.warning(f"Failed to generate for {lbl}: {e}")

            progress.progress(1.0, text="Done!")
            st.session_state.all_ad_sets = all_ad_sets
            st.session_state.gen_platform_id = selected_platform_id

            # Backward-compatible storage
            all_headlines = [{"original_ad": s["original_ad"], "headline": s.get("headline", ""), "char_count": len(s.get("headline", "")), "hypothesis": s.get("angle", "")} for s in all_ad_sets if s.get("headline")]
            first_body_key = next((sl.key for sl in gen_platform.slots if sl.key != "headline"), "description")
            all_descriptions = [{"original_ad": s["original_ad"], "description": s.get(first_body_key, ""), "char_count": len(s.get(first_body_key, "")), "hypothesis": s.get("angle", "")} for s in all_ad_sets if s.get(first_body_key)]
            st.session_state.all_headlines = all_headlines
            st.session_state.all_descriptions = all_descriptions
            all_slot_results = {sl.key: [] for sl in gen_platform.slots}
            for s in all_ad_sets:
                for sl in gen_platform.slots:
                    if s.get(sl.key):
                        all_slot_results[sl.key].append({sl.key: s[sl.key], "original_ad": s["original_ad"], "char_count": len(s[sl.key]), "hypothesis": s.get("angle", "")})
            st.session_state.all_slot_results = all_slot_results

            run_id = generate_run_id()
            save_run(RunRecord(
                run_id=run_id, timestamp=datetime.now(timezone.utc).isoformat(),
                input_file="uploaded_csv", total_ads=len(df_clean),
                underperformers_count=len(underperformers),
                underperformers=[{"ad_data": u2.ad_data, "reasons": u2.reasons, "score": u2.score} for u2 in underperformers],
                generated_headlines=[{"original_ad": h["original_ad"], "headline": h["headline"], "hypothesis": h.get("hypothesis", "")} for h in all_headlines],
                generated_descriptions=[{"original_ad": d["original_ad"], "description": d["description"], "hypothesis": d.get("hypothesis", "")} for d in all_descriptions],
                top_performers=top_performers,
                notes=f"Platform: {gen_platform.name} | {num_ad_sets} sets/ad",
            ), memory_dir=get_memory_dir())

        # ── Show generated results ──
        if "all_ad_sets" in st.session_state:
            all_ad_sets = st.session_state.all_ad_sets
            gen_pid = st.session_state.get("gen_platform_id", selected_platform_id)
            gen_pf = get_platform(gen_pid)

            st.markdown(f"**Generated Copy** ({len(all_ad_sets)} variations)")

            # Strategy brief toggle
            brief = st.session_state.get("strategy_brief", {})
            if brief:
                with st.expander("Strategy Brief"):
                    patterns = brief.get("dataset_patterns", {})
                    if patterns:
                        for p in patterns.get("what_top_performers_share", []):
                            st.markdown(f"- {p}")
                    cs = brief.get("creative_strategy", {})
                    if cs and cs.get("angles_to_test"):
                        st.markdown("**Angles:**")
                        for a in cs["angles_to_test"]:
                            if isinstance(a, dict):
                                st.markdown(f"- **{a.get('angle', '')}**: {a.get('rationale', '')}")
                            else:
                                st.markdown(f"- {a}")

            # Render each generated ad set as a card
            for idx, ad_set in enumerate(all_ad_sets):
                angle = ad_set.get("angle", "Variation")
                source = ad_set.get("original_ad", "")

                copy_fields_html = ""
                for slot in gen_pf.slots:
                    text = ad_set.get(slot.key, "")
                    if not text:
                        continue
                    char_len = len(text)
                    over_class = "over" if char_len > slot.char_limit else ""
                    copy_fields_html += f'''
                    <div class="copy-label">{slot.label} <span class="char-count {over_class}">{char_len}/{slot.char_limit}</span></div>
                    <div class="copy-field">{text}</div>
                    '''

                rationale_html = ""
                if ad_set.get("rationale"):
                    rationale_html = f'<div class="rationale">{ad_set["rationale"]}</div>'

                st.markdown(f'''
                <div class="gen-card">
                    <div class="angle">{angle} · {source}</div>
                    {copy_fields_html}
                    {rationale_html}
                </div>
                ''', unsafe_allow_html=True)

            # Downloads
            st.markdown("---")
            _xlsx_bytes = build_export_workbook(
                client_name=cl.name if cl else "Unknown",
                platform_name=gen_pf.name,
                platform_icon=gen_pf.icon,
                slots=gen_pf.slots,
                ad_sets=all_ad_sets,
                underperformers=underperformers,
                strategy_brief=st.session_state.get("strategy_brief"),
                brand=brand, product=product,
                total_ads=len(df_clean),
                num_underperformers=len(underperformers),
            )
            _client_slug = (cl.name if cl else "export").replace(" ", "_").lower()
            _date_slug = datetime.now().strftime("%Y%m%d")
            dl1, dl2, dl3 = st.columns(3)
            with dl1:
                st.download_button(
                    "Download Excel", _xlsx_bytes,
                    f"{_client_slug}_ad_variations_{_date_slug}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True, type="primary",
                )
            with dl2:
                csv_rows = []
                for ad_set in all_ad_sets:
                    row = {"source_ad": ad_set.get("original_ad", ""), "angle": ad_set.get("angle", "")}
                    for slot in gen_pf.slots:
                        row[slot.label] = ad_set.get(slot.key, "")
                    row["rationale"] = ad_set.get("rationale", "")
                    csv_rows.append(row)
                st.download_button("Download CSV", pd.DataFrame(csv_rows).to_csv(index=False),
                                   "ad_variations.csv", "text/csv", use_container_width=True)
            with dl3:
                st.download_button("Download JSON", json.dumps(all_ad_sets, indent=2),
                                   "ad_variations.json", "application/json", use_container_width=True)

            # Template previews
            _preview_templates = list_templates(cl.client_id) if cl else []
            _preview_templates = [t for t in _preview_templates if t.slots]
            if _preview_templates:
                st.markdown("---")
                st.markdown("**Template Preview**")
                _sel_tpl_name = st.selectbox("Template", [t.name for t in _preview_templates], key="preview_tpl")
                _sel_tpl = next((t for t in _preview_templates if t.name == _sel_tpl_name), None)
                if _sel_tpl:
                    previews = render_all_previews(cl.client_id, _sel_tpl, all_ad_sets)
                    if previews:
                        cols = st.columns(min(3, len(previews)))
                        for i, (label, img) in enumerate(previews):
                            with cols[i % 3]:
                                buf = io.BytesIO()
                                img.save(buf, format="PNG")
                                st.image(buf.getvalue(), caption=label, use_container_width=True)
                        zip_bytes = export_previews_zip(previews, template_name=_sel_tpl.template_id)
                        st.download_button("Download Previews (ZIP)", zip_bytes,
                                           f"previews_{_sel_tpl.template_id}.zip", "application/zip",
                                           use_container_width=True)
        elif not _ready:
            pass  # warning already shown above
        else:
            st.markdown('''
            <div class="empty-state" style="padding:2rem 1rem;">
                <div class="icon">🤖</div>
                <div class="title">Ready to generate</div>
                <div class="desc">Click <strong>Generate Ad Copy</strong> to create AI-powered replacements for the underperformers shown on the left.</div>
            </div>
            ''', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════
# PAGE: PUBLISH & EXPORT
# ══════════════════════════════════════════════════════════
def render_publish():
    st.markdown('''
    <div class="page-header">
        <div class="icon" style="background:rgba(96,165,250,0.12);">🚀</div>
        <div>
            <div class="title">Publish & Export</div>
            <div class="sub">Push to ad platforms or download for Figma/Sheets</div>
        </div>
    </div>
    ''', unsafe_allow_html=True)

    if "all_ad_sets" not in st.session_state and "all_headlines" not in st.session_state:
        st.markdown('''
        <div class="empty-state">
            <div class="icon">🚀</div>
            <div class="title">No copy generated yet</div>
            <div class="desc">Go to <strong>Optimize</strong>, upload ad data, and generate copy first. Then come back here to push live or export files.</div>
        </div>
        ''', unsafe_allow_html=True)
        return

    tab_publish, tab_export = st.tabs(["Publish", "Export & Figma"])

    # ── PUBLISH TAB ──
    with tab_publish:
        pub_meta, pub_google = st.tabs(["Meta Ads", "Google Ads"])

        with pub_meta:
            st.markdown('''<div class="platform-card">
                <h3><span class="platform-badge meta">META</span> &nbsp; Facebook & Instagram Ads</h3>
            </div>''', unsafe_allow_html=True)

            with st.expander("How to get Meta credentials"):
                st.markdown("""
1. Go to **Meta Business Suite** → Settings → Business Info
2. Copy your **Ad Account ID** (numeric)
3. Go to **Meta for Developers** → Your App → Graph API Explorer
4. Generate a **User Access Token** with `ads_management` + `pages_read_engagement`
                """)

            _cl = active_client()
            mc1, mc2 = st.columns(2)
            with mc1:
                meta_token = st.text_input("Access Token", type="password", key="meta_token", value=_cl.meta_token if _cl else "", placeholder="EAAx...")
            with mc2:
                meta_acct = st.text_input("Ad Account ID", key="meta_acct", value=_cl.meta_account_id if _cl else "")
            if _cl and (meta_token != _cl.meta_token or meta_acct != _cl.meta_account_id):
                _cl.meta_token = meta_token
                _cl.meta_account_id = meta_acct
                save_client(_cl)

            meta_connected = False
            meta_platform = None
            if meta_token and meta_acct:
                meta_platform = MetaAdsPlatform(meta_token, meta_acct)
                if st.button("Test Connection", key="meta_test"):
                    with st.spinner("Connecting..."):
                        ok, msg = meta_platform.test_connection()
                    if ok:
                        st.session_state.meta_connected = True
                        st.session_state.meta_account_name = msg
                        st.success(f"Connected: {msg}")
                    else:
                        st.session_state.meta_connected = False
                        st.error(f"Failed: {msg}")
                meta_connected = st.session_state.get("meta_connected", False)

            if meta_connected and meta_platform:
                st.markdown(f'<span class="platform-badge connected">Connected: {st.session_state.get("meta_account_name", "")}</span>', unsafe_allow_html=True)
                try:
                    campaigns = meta_platform.list_campaigns()
                    if campaigns:
                        campaign_names = {c["name"]: c["id"] for c in campaigns}
                        selected_campaign = st.selectbox("Campaign", list(campaign_names.keys()), key="meta_campaign")
                        campaign_id = campaign_names[selected_campaign]
                        adsets = meta_platform.list_adsets(campaign_id)
                        if adsets:
                            adset_names = {a["name"]: a["id"] for a in adsets}
                            selected_adset = st.selectbox("Ad Set", list(adset_names.keys()), key="meta_adset")
                            adset_id = adset_names[selected_adset]
                            try:
                                pages = meta_platform.list_pages()
                                page_names = {p["name"]: p["id"] for p in pages} if pages else {}
                                page_id = st.selectbox("Page", list(page_names.keys()), key="meta_page") if page_names else st.text_input("Page ID", key="meta_page_id")
                                if page_names:
                                    page_id = page_names[page_id]
                            except Exception:
                                page_id = st.text_input("Page ID", key="meta_page_id_fb")
                            link = st.text_input("Destination URL", key="meta_link", placeholder="https://...")
                            all_h = st.session_state.all_headlines
                            all_d = st.session_state.all_descriptions
                            combos = []
                            for h in all_h:
                                matching = [d for d in all_d if d["original_ad"] == h["original_ad"]]
                                if matching:
                                    combos.append({"headline": h["headline"], "description": matching[0]["description"]})
                            st.markdown(f"**{len(combos)} ads** ready (created as PAUSED)")
                            if st.button("Push to Meta Ads", type="primary", key="meta_push"):
                                with st.spinner(f"Pushing {len(combos)} ads..."):
                                    result = meta_platform.push_ads(combos, campaign_id, adset_id, page_id=page_id, link=link)
                                if result.ads_pushed > 0:
                                    st.session_state.setdefault("push_results", []).append(result)
                                    st.markdown(f'<div class="push-result success">Pushed <strong>{result.ads_pushed}</strong> ads</div>', unsafe_allow_html=True)
                                for err in result.errors:
                                    st.markdown(f'<div class="push-result error">{err}</div>', unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Error: {e}")

            if meta_connected and meta_platform:
                st.markdown("---")
                meta_range = st.selectbox("Date Range", ["last_7d", "last_14d", "last_30d", "last_90d"], index=2, key="meta_range")
                if st.button("Pull Performance", key="meta_pull"):
                    with st.spinner("Fetching..."):
                        try:
                            perf = meta_platform.pull_performance(meta_range)
                            if perf:
                                st.dataframe(pd.DataFrame(perf), use_container_width=True, height=250)
                        except Exception as e:
                            st.error(str(e))

        with pub_google:
            st.markdown('''<div class="platform-card">
                <h3><span class="platform-badge google">GOOGLE</span> &nbsp; Google Search & Display Ads</h3>
            </div>''', unsafe_allow_html=True)

            with st.expander("How to get Google Ads credentials"):
                st.markdown("""
1. **Developer Token**: Google Ads → Tools → API Center
2. **OAuth Credentials**: Google Cloud Console → Credentials → OAuth Client ID
3. **Refresh Token**: Use OAuth Playground
4. **Customer ID**: Your 10-digit account number
                """)

            _cl2 = active_client()
            gc1, gc2 = st.columns(2)
            with gc1:
                g_dev_token = st.text_input("Developer Token", type="password", key="g_dev_token", value=_cl2.google_dev_token if _cl2 else "")
                g_client_id = st.text_input("OAuth Client ID", key="g_client_id", value=_cl2.google_client_id if _cl2 else "")
                g_client_secret = st.text_input("OAuth Client Secret", type="password", key="g_client_secret", value=_cl2.google_client_secret if _cl2 else "")
            with gc2:
                g_refresh = st.text_input("Refresh Token", type="password", key="g_refresh", value=_cl2.google_refresh_token if _cl2 else "")
                g_customer = st.text_input("Customer ID", key="g_customer", value=_cl2.google_customer_id if _cl2 else "")
                g_login_customer = st.text_input("Login Customer ID (MCC)", key="g_login_customer", value=_cl2.google_login_customer_id if _cl2 else "")
            if _cl2:
                changed = any(getattr(_cl2, attr) != val for attr, val in [
                    ("google_dev_token", g_dev_token), ("google_client_id", g_client_id),
                    ("google_client_secret", g_client_secret), ("google_refresh_token", g_refresh),
                    ("google_customer_id", g_customer), ("google_login_customer_id", g_login_customer),
                ])
                if changed:
                    _cl2.google_dev_token = g_dev_token
                    _cl2.google_client_id = g_client_id
                    _cl2.google_client_secret = g_client_secret
                    _cl2.google_refresh_token = g_refresh
                    _cl2.google_customer_id = g_customer
                    _cl2.google_login_customer_id = g_login_customer
                    save_client(_cl2)

            google_connected = False
            google_platform = None
            all_fields = g_dev_token and g_client_id and g_client_secret and g_refresh and g_customer
            if all_fields:
                google_platform = GoogleAdsPlatform(g_dev_token, g_client_id, g_client_secret, g_refresh, g_customer, g_login_customer)
                if st.button("Test Connection", key="google_test"):
                    with st.spinner("Connecting..."):
                        ok, msg = google_platform.test_connection()
                    if ok:
                        st.session_state.google_connected = True
                        st.session_state.google_account_name = msg
                        st.success(f"Connected: {msg}")
                    else:
                        st.session_state.google_connected = False
                        st.error(f"Failed: {msg}")
                google_connected = st.session_state.get("google_connected", False)

            if google_connected and google_platform:
                st.markdown(f'<span class="platform-badge connected">Connected: {st.session_state.get("google_account_name", "")}</span>', unsafe_allow_html=True)
                try:
                    campaigns = google_platform.list_campaigns()
                    if campaigns:
                        campaign_names = {c["name"]: c for c in campaigns}
                        selected_campaign = st.selectbox("Campaign", list(campaign_names.keys()), key="g_campaign")
                        campaign = campaign_names[selected_campaign]
                        ad_groups = google_platform.list_ad_groups(campaign["id"])
                        if ad_groups:
                            ag_names = {a["name"]: a for a in ad_groups}
                            selected_ag = st.selectbox("Ad Group", list(ag_names.keys()), key="g_adgroup")
                            ad_group = ag_names[selected_ag]
                            final_url = st.text_input("Final URL", key="g_final_url", placeholder="https://...")
                            all_h = st.session_state.all_headlines
                            all_d = st.session_state.all_descriptions
                            grouped = {}
                            for h in all_h:
                                grouped.setdefault(h["original_ad"], {"headlines": [], "descriptions": []})
                                grouped[h["original_ad"]]["headlines"].append(h["headline"])
                            for d in all_d:
                                grouped.setdefault(d["original_ad"], {"headlines": [], "descriptions": []})
                                grouped[d["original_ad"]]["descriptions"].append(d["description"])
                            st.markdown(f"**{len(grouped)} RSAs** ready (PAUSED)")
                            if st.button("Push to Google Ads", type="primary", key="google_push"):
                                rsa_ads = [{"headlines": g["headlines"][:15], "descriptions": g["descriptions"][:4]} for g in grouped.values()]
                                with st.spinner(f"Pushing {len(rsa_ads)} RSAs..."):
                                    result = google_platform.push_ads(rsa_ads, campaign["resource_name"], ad_group["resource_name"], final_url=final_url)
                                if result.ads_pushed > 0:
                                    st.session_state.setdefault("push_results", []).append(result)
                                    st.markdown(f'<div class="push-result success">Pushed <strong>{result.ads_pushed}</strong> RSAs</div>', unsafe_allow_html=True)
                                for err in result.errors:
                                    st.markdown(f'<div class="push-result error">{err}</div>', unsafe_allow_html=True)
                except Exception as e:
                    st.error(str(e))

    # ── EXPORT TAB ──
    with tab_export:
        gen_pid = st.session_state.get("gen_platform_id") or st.session_state.get("platform_selector", "meta")
        # Resolve display name to ID if needed
        if gen_pid and gen_pid not in [p.id for p in list_platforms()]:
            gen_pid = {p.name: p.id for p in list_platforms()}.get(gen_pid, "meta")
        gen_pf = get_platform(gen_pid)

        st.markdown('''
        <div class="figma-flow">
            <div class="figma-step"><div class="num">1</div><div class="label">Download JSON</div></div>
            <div class="arrow-connector">&rarr;</div>
            <div class="figma-step"><div class="num">2</div><div class="label">Open Figma</div></div>
            <div class="arrow-connector">&rarr;</div>
            <div class="figma-step"><div class="num">3</div><div class="label">Import & Swap</div></div>
            <div class="arrow-connector">&rarr;</div>
            <div class="figma-step"><div class="num">4</div><div class="label">Export Ads</div></div>
        </div>
        ''', unsafe_allow_html=True)

        with st.expander("Figma Template Setup"):
            st.markdown("""
Name your text layers: `#headline`, `#description`, `#cta`

The plugin duplicates each frame for every variation. Recommended plugins:
- **Content Reel** — Figma's text/image population tool
- **Google Sheets Sync** — sync text layers from spreadsheet data
            """)

        if "all_ad_sets" in st.session_state:
            ad_sets = st.session_state.all_ad_sets
            figma_data = {
                "_meta": {
                    "generator": "ad-optimizer",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "brand": brand, "product": product, "platform": gen_pf.name,
                },
                "variations": [],
            }
            for vid, ad_set in enumerate(ad_sets, 1):
                variation = {"id": vid, "source_ad": ad_set.get("original_ad", ""), "angle": ad_set.get("angle", "")}
                for slot in gen_pf.slots:
                    variation[f"#{slot.key}"] = ad_set.get(slot.key, "")
                variation["#cta"] = "Try Free" if "free" in product.lower() else "Learn More"
                figma_data["variations"].append(variation)

            st.markdown(f'''
            <div class="stat-row">
                <div class="stat-card"><div class="stat-value accent">{len(ad_sets)}</div><div class="stat-label">Variations</div></div>
                <div class="stat-card"><div class="stat-value">{len(set(s.get("original_ad","") for s in ad_sets))}</div><div class="stat-label">Source Ads</div></div>
            </div>
            ''', unsafe_allow_html=True)

            # Export Excel (primary)
            _pub_client = active_client()
            _ex_xlsx = build_export_workbook(
                client_name=_pub_client.name if _pub_client else "Unknown",
                platform_name=gen_pf.name,
                platform_icon=gen_pf.icon,
                slots=gen_pf.slots,
                ad_sets=ad_sets,
                underperformers=st.session_state.get("underperformers"),
                strategy_brief=st.session_state.get("strategy_brief"),
                brand=brand, product=product,
                total_ads=len(st.session_state.get("df_clean", [])),
                num_underperformers=len(st.session_state.get("underperformers", [])),
            )
            _ex_slug = (_pub_client.name if _pub_client else "export").replace(" ", "_").lower()
            _ex_date = datetime.now().strftime("%Y%m%d")
            st.download_button(
                "Download Excel Report", _ex_xlsx,
                f"{_ex_slug}_ad_variations_{_ex_date}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True, type="primary",
            )

            dl1, dl2, dl3 = st.columns(3)
            with dl1:
                st.download_button("Figma JSON", json.dumps(figma_data, indent=2), "figma_ad_variations.json", "application/json", use_container_width=True)
            with dl2:
                if gen_pid == "meta":
                    bulk = [{"Ad Name": f"V{v['id']}_{v['source_ad'][:30]}", "Primary Text": v.get("#primary_text", ""), "Headline": v.get("#headline", ""), "Description": v.get("#link_description", "")} for v in figma_data["variations"]]
                elif gen_pid == "google_search":
                    bulk = [{"Headline": v.get("#headline", ""), "Description": v.get("#description", ""), "Source": v["source_ad"]} for v in figma_data["variations"]]
                else:
                    bulk = [{"source_ad": v["source_ad"]} | {slot.label: v.get(f"#{slot.key}", "") for slot in gen_pf.slots} for v in figma_data["variations"]]
                st.download_button("Bulk Upload CSV", pd.DataFrame(bulk).to_csv(index=False), "bulk_upload.csv", "text/csv", use_container_width=True)
            with dl3:
                st.download_button("Raw JSON", json.dumps(ad_sets, indent=2), "ad_variations_raw.json", "application/json", use_container_width=True)


# ══════════════════════════════════════════════════════════
# PAGE: SETTINGS
# ══════════════════════════════════════════════════════════
def render_settings():
    st.markdown('''
    <div class="page-header">
        <div class="icon" style="background:rgba(255,255,255,0.05);">⚙️</div>
        <div>
            <div class="title">Settings</div>
            <div class="sub">Brand brief, client config, user management</div>
        </div>
    </div>
    ''', unsafe_allow_html=True)

    setup_client = active_client()
    if not setup_client:
        st.markdown('''
        <div class="empty-state">
            <div class="icon">⚙️</div>
            <div class="title">Select a client first</div>
            <div class="desc">Pick or create a client from the sidebar to configure its brand brief and credentials.</div>
        </div>
        ''', unsafe_allow_html=True)
        return

    # ── Brand Brief ──
    st.markdown(f"### Brand Brief — {setup_client.name}")

    bb_col1, bb_col2 = st.columns(2)
    with bb_col1:
        _brand = st.text_input("Brand Name", value=setup_client.brand, placeholder="e.g. Anthropic", key="bb_brand")
        _product = st.text_input("Product / Service", value=setup_client.product, placeholder="e.g. Claude AI Assistant", key="bb_product")
        _cat_idx = CATEGORIES.index(setup_client.category) if setup_client.category in CATEGORIES else 0
        _category = st.selectbox("Category", CATEGORIES, index=_cat_idx, key="bb_category",
                                 format_func=lambda x: x if x else "Select a category...")
    with bb_col2:
        _brand_voice = st.text_area("Brand Voice & Tone", value=setup_client.brand_voice, key="bb_voice",
                                    placeholder="How does the brand speak?", height=120)
        _competitors = st.text_input("Competitors", value=setup_client.competitors, placeholder="e.g. OpenAI, Google", key="bb_competitors")

    _brand_desc = st.text_area("Brand Description", value=setup_client.brand_description, key="bb_desc",
                               placeholder="2-3 paragraphs about the brand.", height=100)
    _target = st.text_area("Target Audience", value=setup_client.target_audience, key="bb_audience",
                           placeholder="Who buys this? Demographics, psychographics, pain points.", height=80)
    _diffr = st.text_area("Key Differentiators", value=setup_client.key_differentiators, key="bb_diff",
                          placeholder="What makes this product different?", height=80)

    # Auto-save
    _changed = False
    for attr, val in [("brand", _brand), ("product", _product), ("category", _category),
                      ("brand_description", _brand_desc), ("target_audience", _target),
                      ("brand_voice", _brand_voice), ("key_differentiators", _diffr),
                      ("competitors", _competitors)]:
        if getattr(setup_client, attr) != val:
            setattr(setup_client, attr, val)
            _changed = True
    if _changed:
        save_client(setup_client)

    # ── API Key ──
    st.markdown("---")
    st.markdown("### API Key")
    st.caption("Anthropic API key for AI-powered ad generation. Stored per-client.")

    _current_key = setup_client.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if _current_key and len(_current_key) > 10:
        st.markdown(
            f'<span style="font-size:0.82rem;color:rgba(74,222,128,0.8);">'
            f'✓ Key set: <code>sk-ant-...{_current_key[-6:]}</code></span>',
            unsafe_allow_html=True,
        )
    elif _current_key:
        st.markdown(
            '<span style="font-size:0.82rem;color:rgba(74,222,128,0.8);">✓ Key set</span>',
            unsafe_allow_html=True,
        )

    _kc1, _kc2 = st.columns([3, 1])
    with _kc1:
        _new_key = st.text_input(
            "Anthropic API Key", type="password", key="settings_api_key",
            placeholder="sk-ant-api03-...",
            help="Get your key from console.anthropic.com",
        )
    with _kc2:
        st.markdown("&nbsp;", unsafe_allow_html=True)  # vertical spacer
        if st.button("Clear Key", key="clear_api_key"):
            setup_client.anthropic_api_key = ""
            save_client(setup_client)
            os.environ.pop("ANTHROPIC_API_KEY", None)
            st.rerun()

    if _new_key and _new_key != setup_client.anthropic_api_key:
        setup_client.anthropic_api_key = _new_key
        os.environ["ANTHROPIC_API_KEY"] = _new_key
        save_client(setup_client)
        st.success("API key saved for this client.")
        st.rerun()

    # ── Client Management ──
    st.markdown("---")
    with st.expander("Client Management"):
        st.caption(f"ID: `{setup_client.client_id}` · Created {setup_client.created_at[:10] if setup_client.created_at else 'recently'}")
        if has_permission("delete_clients"):
            if "confirm_delete_client" not in st.session_state:
                st.session_state.confirm_delete_client = False

            if not st.session_state.confirm_delete_client:
                if st.button("Delete Client", key="delete_client_btn"):
                    st.session_state.confirm_delete_client = True
                    st.rerun()
            else:
                st.warning(f"Permanently delete **{setup_client.name}** and all its data (templates, memory, credentials)?")
                dc1, dc2 = st.columns(2)
                with dc1:
                    if st.button("Yes, Delete", type="primary", key="confirm_delete_yes"):
                        delete_client(setup_client.client_id)
                        st.session_state.pop("active_client_id", None)
                        st.session_state.confirm_delete_client = False
                        _clear_pipeline_state()
                        st.rerun()
                with dc2:
                    if st.button("Cancel", key="confirm_delete_no"):
                        st.session_state.confirm_delete_client = False
                        st.rerun()
        else:
            st.caption("Only admins can delete clients.")

    # ── User Management ──
    if has_permission("manage_users"):
        st.markdown("---")
        st.markdown("### User Management")
        render_user_management()


# ══════════════════════════════════════════════════════════
# PAGE: TEMPLATES
# ══════════════════════════════════════════════════════════
def render_templates():
    st.markdown('''
    <div class="page-header">
        <div class="icon" style="background:rgba(251,191,36,0.12);">🎨</div>
        <div>
            <div class="title">Template Library</div>
            <div class="sub">Upload ad templates and define text slot positions</div>
        </div>
    </div>
    ''', unsafe_allow_html=True)

    _tpl_client = active_client()
    if not _tpl_client:
        st.markdown('''
        <div class="empty-state">
            <div class="icon">🎨</div>
            <div class="title">No client selected</div>
            <div class="desc">Templates are stored per-client. Select one from the sidebar first.</div>
        </div>
        ''', unsafe_allow_html=True)
        return

    with st.expander("Upload New Template"):
        _tpl_name = st.text_input("Template Name", placeholder="e.g. Meta Feed 1080x1080", key="tpl_name")
        _tpl_platform = st.selectbox("Platform", ["", "Meta", "Google", "TikTok", "LinkedIn", "Other"], key="tpl_platform")
        _tpl_file = st.file_uploader("Template Image", type=["png", "jpg", "jpeg"], key="tpl_upload")
        if _tpl_name and _tpl_file and st.button("Save Template", key="save_tpl_btn"):
            tpl = create_template(_tpl_client.client_id, _tpl_name, _tpl_file, _tpl_file.name, platform=_tpl_platform)
            st.success(f"Saved **{tpl.name}** ({tpl.width}x{tpl.height})")
            st.rerun()

    templates = list_templates(_tpl_client.client_id)
    if not templates:
        st.markdown('''
        <div class="empty-state">
            <div class="icon">🖼️</div>
            <div class="title">No templates yet</div>
            <div class="desc">Upload an ad template image (PNG/JPG from Figma or Canva) and define text slot positions.</div>
        </div>
        ''', unsafe_allow_html=True)
    else:
        for tpl in templates:
            with st.expander(f"{tpl.name} ({tpl.width}x{tpl.height}) — {len(tpl.slots)} slots"):
                img_path = get_template_image_path(_tpl_client.client_id, tpl)
                tc1, tc2 = st.columns([1, 1])
                with tc1:
                    if img_path:
                        st.image(str(img_path), use_container_width=True)
                    else:
                        st.warning("Image not found")
                with tc2:
                    for slot in tpl.slots:
                        st.caption(f"**{slot.label}** → `{slot.slot_id}` ({slot.x},{slot.y}) {slot.font_size}px")
                    st.markdown("---")
                    st.markdown("**Add Slot**")
                    _slot_id = st.selectbox("Maps to", ["headline", "primary_text", "link_description", "description"], key=f"slot_id_{tpl.template_id}")
                    _slot_label = st.text_input("Label", value=_slot_id.replace("_", " ").title(), key=f"slot_label_{tpl.template_id}")
                    sc1, sc2, sc3, sc4 = st.columns(4)
                    with sc1: _sx = st.number_input("X", value=60, min_value=0, key=f"sx_{tpl.template_id}")
                    with sc2: _sy = st.number_input("Y", value=tpl.height - 200, min_value=0, key=f"sy_{tpl.template_id}")
                    with sc3: _sw = st.number_input("W", value=min(960, tpl.width - 120), min_value=50, key=f"sw_{tpl.template_id}")
                    with sc4: _sh = st.number_input("H", value=80, min_value=20, key=f"sh_{tpl.template_id}")
                    sf1, sf2, sf3 = st.columns(3)
                    with sf1: _fs = st.number_input("Font", value=32, min_value=8, key=f"fs_{tpl.template_id}")
                    with sf2: _fc = st.color_picker("Color", value="#FFFFFF", key=f"fc_{tpl.template_id}")
                    with sf3: _fa = st.selectbox("Align", ["left", "center", "right"], key=f"fa_{tpl.template_id}")
                    if st.button("Add Slot", key=f"add_slot_{tpl.template_id}"):
                        tpl.slots.append(TextSlot(slot_id=_slot_id, label=_slot_label, x=int(_sx), y=int(_sy), width=int(_sw), height=int(_sh), font_size=int(_fs), font_color=_fc, align=_fa))
                        save_template(_tpl_client.client_id, tpl)
                        st.rerun()
                    if tpl.slots and img_path:
                        st.markdown("---")
                        sample_copy = {s.slot_id: f"Sample {s.label}" for s in tpl.slots}
                        preview_img = render_preview(_tpl_client.client_id, tpl, sample_copy)
                        if preview_img:
                            buf = io.BytesIO()
                            preview_img.save(buf, format="PNG")
                            st.image(buf.getvalue(), caption="Preview", use_container_width=True)
                if st.button("Delete Template", key=f"del_tpl_{tpl.template_id}"):
                    delete_template(_tpl_client.client_id, tpl.template_id)
                    st.rerun()


# ══════════════════════════════════════════════════════════
# PAGE: MEMORY
# ══════════════════════════════════════════════════════════
def render_memory():
    mem_client = active_client()
    mem_label = f" — {mem_client.name}" if mem_client else ""

    st.markdown(f'<div class="page-header"><div class="icon" style="background:rgba(96,165,250,0.12);">🧠</div><div><div class="title">Experiment Memory{mem_label}</div><div class="sub">Every run is logged. The AI learns from past results each cycle.</div></div></div>', unsafe_allow_html=True)

    history = load_history(get_memory_dir())
    if not history:
        st.markdown('<div class="empty-state"><div class="icon">🧠</div><div class="title">No experiments yet</div><div class="desc">Run the Optimize pipeline to start building memory. Each run is logged. The more you run it, the smarter it gets.</div></div>', unsafe_allow_html=True)
        return

    th = sum(len(r.generated_headlines) for r in history)
    td = sum(len(r.generated_descriptions) for r in history)
    o_stats = outcome_summary(history)

    # ── Stats bar ──
    st.markdown(f'<div class="stat-row"><div class="stat-card"><div class="stat-value accent">{len(history)}</div><div class="stat-label">Runs</div></div><div class="stat-card"><div class="stat-value">{th + td}</div><div class="stat-label">Variations</div></div><div class="stat-card"><div class="stat-value">{sum(r.total_ads for r in history)}</div><div class="stat-label">Ads Analyzed</div></div><div class="stat-card"><div class="stat-value {"green" if o_stats["improvement_rate"] > 0.5 else "red"}">{o_stats["improvement_rate"]:.0%}</div><div class="stat-label">Improvement Rate</div></div></div>', unsafe_allow_html=True)

    # ── Feedback Loop Section ──
    if o_stats["total_tracked"] > 0:
        st.markdown("### 🔄 Feedback Loop")
        fl1, fl2, fl3 = st.columns(3)
        with fl1:
            st.metric("Ads Improved", o_stats["improved_count"],
                       delta=f"{o_stats['improvement_rate']:.0%} success rate")
        with fl2:
            st.metric("Still Underperforming", o_stats["still_bad_count"],
                       delta=f"-{o_stats['still_bad_count']}" if o_stats["still_bad_count"] else "0",
                       delta_color="inverse")
        with fl3:
            st.metric("Ads Removed/Paused", o_stats["gone_count"])

        # Show validated vs failed strategies
        scores = score_hypotheses(history)
        if scores["validated"] or scores["failed"]:
            sv1, sv2 = st.columns(2)
            with sv1:
                st.markdown("**✅ Validated Strategies**")
                if scores["validated"]:
                    for hyp, count in sorted(scores["validated"].items(), key=lambda x: -x[1])[:8]:
                        st.markdown(f"- ✓ **{hyp}** ×{count}")
                else:
                    st.caption("No validated strategies yet")
            with sv2:
                st.markdown("**❌ Failed Strategies**")
                if scores["failed"]:
                    for hyp, count in sorted(scores["failed"].items(), key=lambda x: -x[1])[:8]:
                        st.markdown(f"- ✗ ~~{hyp}~~ ×{count}")
                else:
                    st.caption("No failed strategies yet")

    # ── Trends ──
    if len(history) >= 2:
        st.markdown("### 📈 Trends")
        trend_data = []
        for run in history:
            trend_data.append({
                "Date": run.timestamp[:10],
                "Flag Rate (%)": round(run.underperformers_count / run.total_ads * 100, 1) if run.total_ads > 0 else 0,
                "Headlines": len(run.generated_headlines),
                "Descriptions": len(run.generated_descriptions),
            })
        trend_df = pd.DataFrame(trend_data)
        tc1, tc2 = st.columns(2)
        with tc1:
            st.markdown("**Flag Rate Over Time**")
            st.area_chart(trend_df.set_index("Date")["Flag Rate (%)"], color="#FF6B6B", height=180)
        with tc2:
            st.markdown("**Variations Per Run**")
            st.bar_chart(trend_df.set_index("Date")[["Headlines", "Descriptions"]], color=["#E8FF47", "#60A5FA"], height=180)

        if len(trend_data) >= 2:
            first_flag = trend_data[0]["Flag Rate (%)"]
            last_flag = trend_data[-1]["Flag Rate (%)"]
            delta = last_flag - first_flag
            if delta < -5:
                st.success(f"Flag rate dropped {first_flag}% → {last_flag}% — optimizations are working.")
            elif delta > 5:
                st.warning(f"Flag rate increased {first_flag}% → {last_flag}% — try new creative angles.")
            else:
                st.info(f"Flag rate stable around {last_flag}%.")

    st.markdown("### 📋 Accumulated Insights")
    st.code(summarize_insights(history), language="text")

    st.markdown("### 📁 Run History")
    for run in reversed(history):
        _run_outcomes = run.outcomes if run.outcomes else []
        _improved = sum(1 for o in _run_outcomes if o["status"] == "improved")
        _badge = f" · ✅ {_improved} improved" if _improved else ""
        with st.expander(f"{run.run_id} — {run.timestamp[:10]} — {len(run.generated_headlines)} headlines{_badge}"):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Ads:** {run.total_ads} · **Flagged:** {run.underperformers_count}")
            with c2:
                st.markdown(f"**Headlines:** {len(run.generated_headlines)} · **Descriptions:** {len(run.generated_descriptions)}")
            if _run_outcomes:
                st.markdown("**Outcomes (from next run):**")
                for o in _run_outcomes[:10]:
                    _icon = "✅" if o["status"] == "improved" else "❌" if o["status"] == "still_bad" else "⏸️"
                    _hyps = ", ".join(o.get("hypotheses_suggested", [])[:2]) or "no specific hypothesis"
                    st.markdown(f"- {_icon} **{o['ad_id'][:50]}** — {o['detail']} (strategy: _{_hyps}_)")
            if run.generated_headlines:
                st.markdown("**Generated:**")
                for h in run.generated_headlines[:5]:
                    st.markdown(f"- `{h.get('headline', '')}` — _{h.get('hypothesis', '')}_")

    st.markdown("---")
    if "confirm_clear_memory" not in st.session_state:
        st.session_state.confirm_clear_memory = False

    if not st.session_state.confirm_clear_memory:
        if st.button("Clear All Memory", key="clear_mem_btn"):
            st.session_state.confirm_clear_memory = True
            st.rerun()
    else:
        st.warning("This will permanently delete all experiment history for this client. This cannot be undone.")
        cc1, cc2 = st.columns(2)
        with cc1:
            if st.button("Yes, Delete All Memory", type="primary", key="confirm_clear_yes"):
                _mdir = get_memory_dir()
                if _mdir:
                    mem_file = _mdir / "experiment_log.json"
                else:
                    mem_file = Path(__file__).parent / "memory" / "experiment_log.json"
                if mem_file.exists():
                    mem_file.unlink()
                for key in ["all_headlines", "all_descriptions", "all_ad_sets",
                            "all_slot_results", "underperformers", "df", "df_clean", "mapping"]:
                    st.session_state.pop(key, None)
                st.session_state.confirm_clear_memory = False
                st.rerun()
        with cc2:
            if st.button("Cancel", key="confirm_clear_no"):
                st.session_state.confirm_clear_memory = False
                st.rerun()


# ══════════════════════════════════════════════════════════
# ROUTER
# ══════════════════════════════════════════════════════════
if current_page == "optimize":
    render_optimize()
elif current_page == "publish":
    render_publish()
elif current_page == "settings":
    render_settings()
elif current_page == "templates":
    render_templates()
elif current_page == "memory":
    render_memory()
