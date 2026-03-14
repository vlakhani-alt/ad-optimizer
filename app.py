"""Ad Optimizer — AI-powered ad copy pipeline."""
from __future__ import annotations

import streamlit as st
import pandas as pd
import json
import os
from pathlib import Path
from datetime import datetime, timezone

from analyzer import detect_columns, clean_metrics, flag_underperformers, detect_fatigue
from memory import (
    load_history, save_run, generate_run_id, summarize_insights,
    extract_top_performers, RunRecord,
)
from agents import (
    generate_headlines, generate_descriptions, generate_platform_copy,
    generate_ad_sets, DEFAULT_AD_SETS,
    analyze_creative_strategy, build_dataset_summary,
    list_platforms, get_platform, detect_platform, PLATFORMS,
    FUNNEL_STAGES,
)
from platforms import MetaAdsPlatform, GoogleAdsPlatform
from clients import list_clients, load_client, save_client, create_client, delete_client, client_memory_dir, ClientConfig, CATEGORIES
from auth import check_auth, render_logout_button, get_current_role, has_permission, render_user_management, ROLES
from templates import (
    list_templates, load_template, save_template, create_template,
    delete_template, render_preview, render_all_previews,
    export_previews_zip, AdTemplate, TextSlot,
)

# ── Page Config ──────────────────────────────────────────
st.set_page_config(page_title="Ad Optimizer", page_icon="⚡", layout="wide")

# ── Auth Gate ────────────────────────────────────────────
if not check_auth():
    st.stop()

# ── CSS ──────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;0,9..40,800&family=JetBrains+Mono:wght@400;500;600&display=swap');

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

.stApp {
    font-family: 'DM Sans', sans-serif;
    background: var(--bg-deep);
    background-image:
        radial-gradient(ellipse 80% 50% at 50% -20%, rgba(232,255,71,0.03), transparent),
        radial-gradient(ellipse 60% 40% at 80% 100%, rgba(96,165,250,0.02), transparent);
}
header[data-testid="stHeader"] { background: transparent; }
div[data-testid="stToolbar"] { display: none; }
div[data-testid="stDecoration"] { display: none; }
.block-container { padding-top: 2rem; max-width: 1100px; }

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: var(--bg-surface);
    border-right: 1px solid var(--border);
}
section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] .stMarkdown li { color: var(--text-secondary); font-size: 0.85rem; }

/* ── Hero ── */
.hero {
    position: relative;
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 2.5rem 2.2rem;
    margin-bottom: 2rem;
    color: var(--text-primary);
    overflow: hidden;
}
.hero::before {
    content: '';
    position: absolute; top: 0; left: 0; right: 0; bottom: 0;
    background:
        linear-gradient(135deg, rgba(232,255,71,0.06) 0%, transparent 40%),
        linear-gradient(225deg, rgba(96,165,250,0.04) 0%, transparent 50%);
    pointer-events: none;
}
.hero::after {
    content: '';
    position: absolute; top: -1px; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, transparent, var(--accent), transparent);
    opacity: 0.6;
}
.hero h1 {
    font-size: 2rem; font-weight: 800; margin: 0 0 0.6rem 0;
    color: var(--text-primary); letter-spacing: -0.02em; position: relative;
}
.hero p { font-size: 0.95rem; color: var(--text-secondary); margin: 0; line-height: 1.6; position: relative; }

/* ── Step Pipeline ── */
.step-pipeline { display: flex; gap: 0; margin: 1.5rem 0 2rem 0; }
.step-card {
    flex: 1; padding: 1rem 1.2rem;
    background: var(--surface); border: 1px solid var(--border);
    position: relative; text-align: center;
    transition: all 0.2s ease;
}
.step-card:first-child { border-radius: 14px 0 0 14px; }
.step-card:last-child { border-radius: 0 14px 14px 0; }
.step-card.active { background: var(--accent-dim); border-color: rgba(232,255,71,0.25); }
.step-card.done { background: rgba(74,222,128,0.06); border-color: rgba(74,222,128,0.2); }
.step-num {
    display: inline-flex; align-items: center; justify-content: center;
    width: 28px; height: 28px; border-radius: 8px;
    background: rgba(255,255,255,0.06); font-size: 0.8rem; font-weight: 700;
    margin-bottom: 0.4rem; color: var(--text-muted);
    font-family: 'JetBrains Mono', monospace;
}
.step-card.active .step-num { background: var(--accent); color: #08080C; }
.step-card.done .step-num { background: var(--success); color: #08080C; }
.step-label { font-size: 0.78rem; font-weight: 600; color: var(--text-muted); }
.step-card.active .step-label { color: var(--accent); }
.step-card.done .step-label { color: var(--success); }

/* ── Section Headers ── */
.section-header { display: flex; align-items: center; gap: 0.75rem; margin: 1.5rem 0 1rem 0; }
.section-icon {
    width: 40px; height: 40px; border-radius: 10px;
    display: flex; align-items: center; justify-content: center; font-size: 1.2rem;
}
.section-icon.purple { background: var(--accent-dim); }
.section-icon.green { background: rgba(74,222,128,0.12); }
.section-icon.orange { background: rgba(251,191,36,0.12); }
.section-icon.red { background: rgba(255,107,107,0.12); }
.section-icon.blue { background: rgba(96,165,250,0.12); }
.section-title { font-size: 1.1rem; font-weight: 700; margin: 0; letter-spacing: -0.01em; }
.section-subtitle { font-size: 0.8rem; color: var(--text-muted); margin: 0; }

/* ── Stat Cards ── */
.stat-row { display: flex; gap: 1rem; margin: 1rem 0; }
.stat-card {
    flex: 1; background: var(--surface); border: 1px solid var(--border);
    border-radius: 14px; padding: 1.2rem; text-align: center;
    transition: border-color 0.2s ease;
}
.stat-card:hover { border-color: var(--border-hover); }
.stat-value {
    font-size: 1.8rem; font-weight: 800; color: var(--text-primary);
    font-family: 'JetBrains Mono', monospace; letter-spacing: -0.03em;
}
.stat-value.red { color: var(--danger); }
.stat-value.green { color: var(--success); }
.stat-value.purple { color: var(--accent); }
.stat-label {
    font-size: 0.7rem; color: var(--text-muted);
    text-transform: uppercase; letter-spacing: 0.08em; margin-top: 0.3rem; font-weight: 600;
}

/* ── Underperformer Cards ── */
.underperformer-card {
    background: rgba(255,107,107,0.04); border: 1px solid rgba(255,107,107,0.12);
    border-radius: 14px; padding: 1.2rem; margin-bottom: 0.75rem;
    transition: border-color 0.2s ease;
}
.underperformer-card:hover { border-color: rgba(255,107,107,0.25); }
.underperformer-card .ad-label { font-weight: 700; font-size: 0.95rem; margin-bottom: 0.3rem; }
.underperformer-card .ad-headline { color: var(--text-secondary); font-size: 0.85rem; margin-bottom: 0.5rem; font-style: italic; }
.reason-tag {
    display: inline-block; background: rgba(255,107,107,0.1); color: #FFA0A0;
    padding: 0.2rem 0.6rem; border-radius: 6px; font-size: 0.72rem;
    margin: 0.15rem 0.25rem 0.15rem 0; font-weight: 500;
    font-family: 'JetBrains Mono', monospace;
}
.score-badge {
    float: right; background: rgba(255,107,107,0.15); color: var(--danger);
    padding: 0.2rem 0.8rem; border-radius: 8px; font-size: 0.8rem; font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
}

/* ── Setup Cards ── */
.setup-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 16px; padding: 1.5rem; margin-bottom: 1rem;
    transition: border-color 0.2s ease;
}
.setup-card:hover { border-color: var(--border-hover); }
.setup-card h3 { margin: 0 0 0.5rem 0; font-size: 1rem; }
.setup-card p { color: var(--text-secondary); font-size: 0.85rem; line-height: 1.5; }
.setup-step-num {
    display: inline-flex; align-items: center; justify-content: center;
    width: 32px; height: 32px; border-radius: 8px;
    background: var(--accent-dim); color: var(--accent);
    font-weight: 800; font-size: 0.9rem; margin-right: 0.75rem;
    font-family: 'JetBrains Mono', monospace;
}
.check-icon { color: var(--success); font-size: 1.2rem; }

/* ── Figma Flow ── */
.figma-flow { display: flex; gap: 0.75rem; margin: 1rem 0; }
.figma-step {
    flex: 1; background: var(--surface); border: 1px solid var(--border);
    border-radius: 14px; padding: 1rem; text-align: center;
    transition: all 0.2s ease;
}
.figma-step:hover { border-color: var(--border-hover); transform: translateY(-1px); }
.figma-step .num {
    width: 32px; height: 32px; border-radius: 8px;
    background: var(--accent-dim); color: var(--accent);
    display: inline-flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: 0.85rem; margin-bottom: 0.5rem;
    font-family: 'JetBrains Mono', monospace;
}
.figma-step .label { font-size: 0.8rem; font-weight: 600; color: var(--text-secondary); }
.arrow-connector { display: flex; align-items: center; color: var(--text-muted); font-size: 1.5rem; }

/* ── Platform Cards ── */
.platform-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 16px; padding: 1.5rem; margin-bottom: 1rem;
}
.platform-card.connected { border-color: rgba(74,222,128,0.25); background: rgba(74,222,128,0.03); }
.platform-card h3 { margin: 0 0 0.3rem 0; font-size: 1.05rem; }
.platform-card .subtitle { color: var(--text-muted); font-size: 0.8rem; margin-bottom: 1rem; }
.platform-badge {
    display: inline-block; padding: 0.2rem 0.7rem; border-radius: 6px;
    font-size: 0.72rem; font-weight: 600; font-family: 'JetBrains Mono', monospace;
}
.platform-badge.meta { background: rgba(24,119,242,0.12); color: #60A5FA; }
.platform-badge.google { background: rgba(96,165,250,0.12); color: #93C5FD; }
.platform-badge.connected { background: rgba(74,222,128,0.12); color: var(--success); }
.platform-badge.paused { background: rgba(251,191,36,0.12); color: #FCD34D; }
.push-result {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 0.8rem 1rem; margin: 0.4rem 0; font-size: 0.85rem;
}
.push-result.success { border-color: rgba(74,222,128,0.25); }
.push-result.error { border-color: rgba(255,107,107,0.25); }

/* ── Streamlit Overrides ── */
div[data-testid="stMetric"] {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 14px; padding: 1rem;
}
.stTabs [data-baseweb="tab-list"] {
    gap: 2px; background: var(--surface); border-radius: 14px;
    padding: 4px; border: 1px solid var(--border);
}
.stTabs [data-baseweb="tab"] {
    border-radius: 10px; padding: 0.5rem 1.2rem; font-weight: 600; font-size: 0.83rem;
    transition: all 0.15s ease;
}
.stTabs [aria-selected="true"] {
    background: var(--accent-dim) !important;
    color: var(--accent) !important;
}
div[data-testid="stFileUploader"] {
    border: 2px dashed var(--border); border-radius: 16px; padding: 0.5rem;
    transition: border-color 0.2s ease;
}
div[data-testid="stFileUploader"]:hover { border-color: var(--accent-mid); }
.stDownloadButton > button {
    background: var(--accent-dim) !important;
    border: 1px solid rgba(232,255,71,0.2) !important;
    border-radius: 10px !important; font-weight: 600 !important;
    color: var(--accent) !important;
    transition: all 0.2s ease !important;
}
.stDownloadButton > button:hover {
    background: var(--accent-mid) !important;
    border-color: rgba(232,255,71,0.4) !important;
}
button[kind="primary"] {
    background: var(--accent) !important; color: #08080C !important;
    border: none !important; border-radius: 10px !important;
    font-weight: 700 !important; padding: 0.6rem 2rem !important;
    transition: all 0.2s ease !important;
}
button[kind="primary"]:hover {
    filter: brightness(0.9) !important;
    transform: translateY(-1px) !important;
}

/* ── Animations ── */
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(12px); }
    to { opacity: 1; transform: translateY(0); }
}
.hero { animation: fadeInUp 0.5s ease-out; }
.step-pipeline { animation: fadeInUp 0.5s ease-out 0.1s both; }
.setup-card { animation: fadeInUp 0.4s ease-out both; }
.setup-card:nth-child(1) { animation-delay: 0.05s; }
.setup-card:nth-child(2) { animation-delay: 0.1s; }
.setup-card:nth-child(3) { animation-delay: 0.15s; }
.setup-card:nth-child(4) { animation-delay: 0.2s; }
.setup-card:nth-child(5) { animation-delay: 0.25s; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }
</style>
""", unsafe_allow_html=True)

# ── Helpers ──────────────────────────────────────────────
def has_api_key():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    # Streamlit Community Cloud injects secrets via st.secrets
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

def get_step():
    if not has_api_key(): return 0
    if "underperformers" not in st.session_state: return 1
    if "all_ad_sets" not in st.session_state: return 2
    if "push_results" not in st.session_state: return 3
    return 4

def active_client() -> ClientConfig | None:
    """Return the currently selected client, or None."""
    cid = st.session_state.get("active_client_id")
    if cid:
        return load_client(cid)
    return None

def get_memory_dir():
    """Return memory dir for active client, or default."""
    c = active_client()
    if c:
        return client_memory_dir(c.client_id)
    return None

def _clear_pipeline_state():
    """Clear analysis/generation state when switching clients."""
    for key in ["all_headlines", "all_descriptions", "all_ad_sets",
                "all_slot_results", "strategy_brief", "underperformers", "df",
                "df_clean", "mapping", "push_results", "meta_connected",
                "google_connected"]:
        st.session_state.pop(key, None)

# ── Sidebar ──────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Ad Optimizer")
    st.markdown("AI-powered ad copy pipeline")
    render_logout_button()
    st.markdown("---")

    # ── Client Selector ──
    st.markdown("**Client**")
    clients = list_clients()
    client_names = ["(Select a client)"] + [c.name for c in clients] + ["+ New Client"]
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
        if new_name and st.button("Create Client", key="create_client_btn"):
            c = create_client(new_name)
            st.session_state.active_client_id = c.client_id
            _clear_pipeline_state()
            st.rerun()
    elif selected != "(Select a client)":
        chosen = next((c for c in clients if c.name == selected), None)
        if chosen and st.session_state.get("active_client_id") != chosen.client_id:
            st.session_state.active_client_id = chosen.client_id
            _clear_pipeline_state()
            # Load client's API key if saved
            if chosen.anthropic_api_key:
                os.environ["ANTHROPIC_API_KEY"] = chosen.anthropic_api_key
            st.rerun()

    cl = active_client()

    st.markdown("---")

    # ── API Key ──
    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.markdown("**API Key**")
        api_key = st.text_input("key", type="password", key="api_key", label_visibility="collapsed", placeholder="sk-ant-...")
        if api_key:
            os.environ["ANTHROPIC_API_KEY"] = api_key
            if cl:
                cl.anthropic_api_key = api_key
                save_client(cl)
            st.rerun()
    else:
        st.markdown("**API Key** &nbsp; Connected")

    st.markdown("---")

    # ── Brand Summary (compact — full brief in Setup tab) ──
    if cl and cl.brand:
        _cat = f" · {cl.category}" if cl.category else ""
        st.markdown(f"**{cl.brand}**{_cat}")
        if cl.product:
            st.caption(cl.product)
    else:
        st.markdown("**Brand** &nbsp; Not configured")
        st.caption("Set up in the Setup tab")
    # Expose brand/product for the rest of the app
    brand = cl.brand if cl else ""
    product = cl.product if cl else ""

    st.markdown("---")
    st.markdown("**Platform**")
    platform_options = {p.name: p.id for p in list_platforms()}
    # Auto-detect if we have data
    auto_detected = st.session_state.get("auto_platform_id")
    default_idx = 0
    if auto_detected:
        platform_names = list(platform_options.keys())
        for i, name in enumerate(platform_names):
            if platform_options[name] == auto_detected:
                default_idx = i
                break
    selected_platform_name = st.selectbox(
        "Ad Platform", list(platform_options.keys()), index=default_idx,
        key="platform_selector", label_visibility="collapsed",
    )
    selected_platform_id = platform_options[selected_platform_name]
    selected_platform = get_platform(selected_platform_id)

    st.markdown("---")
    st.markdown("**Generation**")
    num_ad_sets = st.slider(
        "Ad variations / underperformer",
        1, 10, DEFAULT_AD_SETS,
        key="num_ad_sets",
        help="Each variation is a complete, coherent ad set with all copy elements aligned.",
    )
    st.markdown("---")
    mem_dir = get_memory_dir()
    history = load_history(mem_dir)
    total_var = sum(len(r.generated_headlines) for r in history) if history else 0
    client_label = f" ({cl.name})" if cl else ""
    st.markdown(f"**Memory{client_label}** &nbsp; {len(history)} runs &middot; {total_var} variations" if history else f"**Memory{client_label}** &nbsp; No runs yet")

# ── Hero ─────────────────────────────────────────────────
import base64 as _b64
_logo_path = Path(__file__).parent / "egc_logo.png"
_logo_b64 = ""
if _logo_path.exists():
    _logo_b64 = _b64.b64encode(_logo_path.read_bytes()).decode()

st.markdown(f"""
<div class="hero">
    {'<img src="data:image/png;base64,' + _logo_b64 + '" style="height:36px;margin-bottom:1rem;opacity:0.9;" /><br>' if _logo_b64 else ''}
    <h1>Ad Optimizer</h1>
    <p>Upload your ad performance CSV. AI sub-agents analyze what's underperforming,
    generate optimized copy with data-driven rationale, and learn from every iteration.
    Preview on your templates and export to production.</p>
</div>
""", unsafe_allow_html=True)

# ── Step Pipeline ────────────────────────────────────────
current_step = get_step()
step_names = ["Setup", "Upload & Analyze", "Generate Copy", "Publish", "Export"]
steps_html = '<div class="step-pipeline">'
for i, name in enumerate(step_names):
    cls = "done" if i < current_step else ("active" if i == current_step else "")
    icon = "&#10003;" if i < current_step else str(i + 1)
    steps_html += f'<div class="step-card {cls}"><div class="step-num">{icon}</div><div class="step-label">{name}</div></div>'
steps_html += '</div>'
st.markdown(steps_html, unsafe_allow_html=True)

# ── Tabs ─────────────────────────────────────────────────
tab_setup, tab_templates, tab_analyze, tab_generate, tab_publish, tab_export, tab_memory = st.tabs(["Setup", "Templates", "Upload & Analyze", "Generate Copy", "Publish", "Export", "Memory"])

# ══════════════════════════════════════════════════════════
# SETUP
# ══════════════════════════════════════════════════════════
with tab_setup:
    st.markdown('<div class="section-header"><div class="section-icon purple">&#x1F527;</div><div><div class="section-title">Setup</div><div class="section-subtitle">Select or create a client, then complete the checklist</div></div></div>', unsafe_allow_html=True)

    setup_client = active_client()
    client_ok = setup_client is not None
    api_ok = has_api_key()
    brand_ok = bool(brand and product)

    st.markdown(f'''
    <div class="setup-card">
        <h3><span class="setup-step-num">1</span> Select Client {'<span class="check-icon">&#10004;</span>' if client_ok else ''}</h3>
        <p>Use the <strong>Client</strong> dropdown in the sidebar to pick an existing client or create a new one.</p>
    </div>
    <div class="setup-card">
        <h3><span class="setup-step-num">2</span> Anthropic API Key {'<span class="check-icon">&#10004;</span>' if api_ok else ''}</h3>
        <p>Required for AI copy generation. Get your key at <strong>console.anthropic.com</strong>. Paste it in the sidebar.</p>
    </div>
    ''', unsafe_allow_html=True)

    # ── Brand Brief (rich form, replaces old sidebar inputs) ──
    _brief_complete = bool(brand and product and setup_client and setup_client.category)
    st.markdown(f'''
    <div class="setup-card">
        <h3><span class="setup-step-num">3</span> Brand Brief {'<span class="check-icon">&#10004;</span>' if _brief_complete else ''}</h3>
        <p>The richer your brand brief, the more on-brand and strategically targeted the AI copy will be.</p>
    </div>
    ''', unsafe_allow_html=True)

    if setup_client:
        with st.expander("Edit Brand Brief", expanded=not _brief_complete):
            bb_col1, bb_col2 = st.columns(2)
            with bb_col1:
                _brand = st.text_input("Brand Name", value=setup_client.brand, placeholder="e.g. Anthropic", key="bb_brand")
                _product = st.text_input("Product / Service", value=setup_client.product, placeholder="e.g. Claude AI Assistant", key="bb_product")
                _cat_idx = CATEGORIES.index(setup_client.category) if setup_client.category in CATEGORIES else 0
                _category = st.selectbox("Category", CATEGORIES, index=_cat_idx, key="bb_category",
                                         format_func=lambda x: x if x else "Select a category...")
            with bb_col2:
                _brand_voice = st.text_area("Brand Voice & Tone", value=setup_client.brand_voice, key="bb_voice",
                                            placeholder="How does the brand speak? e.g. Confident but approachable. Uses clear, jargon-free language. Never sarcastic.",
                                            height=120)
                _competitors = st.text_input("Competitors", value=setup_client.competitors, placeholder="e.g. OpenAI, Google, Mistral", key="bb_competitors")

            _brand_desc = st.text_area("Brand Description", value=setup_client.brand_description, key="bb_desc",
                                       placeholder="2-3 paragraphs about the brand. Mission, story, what they stand for, market position.",
                                       height=120)
            _target = st.text_area("Target Audience & Segments", value=setup_client.target_audience, key="bb_audience",
                                   placeholder="Who buys this? Demographics, psychographics, pain points, segments. e.g. 'Primary: developers 25-40 building AI apps. Secondary: enterprise CTOs evaluating AI vendors.'",
                                   height=100)
            _diffr = st.text_area("Key Differentiators", value=setup_client.key_differentiators, key="bb_diff",
                                  placeholder="What makes this product different? USPs, competitive advantages. e.g. 'Best-in-class reasoning, honest AI that admits uncertainty, safety-first approach.'",
                                  height=80)

            # Auto-save all brand brief fields
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
                # Update module-level brand/product for downstream use
                brand = setup_client.brand
                product = setup_client.product
    else:
        st.info("Select or create a client first to configure the brand brief.")

    st.markdown(f'''
    <div class="setup-card">
        <h3><span class="setup-step-num">4</span> Ad Performance CSV</h3>
        <p>Export ads from Google Ads, Meta Ads, TikTok, LinkedIn, or any platform. Include identifiers, copy fields, and metrics.
        The platform is <strong>auto-detected</strong> from column names.</p>
    </div>
    <div class="setup-card">
        <h3><span class="setup-step-num">5</span> Platform Credentials (Optional)</h3>
        <p>To push ads directly to Meta or Google, add API credentials in the <strong>Publish</strong> tab.</p>
    </div>
    ''', unsafe_allow_html=True)

    # Client management section
    if setup_client:
        st.markdown(f'<div class="section-header" style="margin-top:2rem;"><div class="section-icon green">&#x1F464;</div><div><div class="section-title">Active Client: {setup_client.name}</div><div class="section-subtitle">Created {setup_client.created_at[:10] if setup_client.created_at else "recently"}</div></div></div>', unsafe_allow_html=True)

        with st.expander("Manage Client"):
            st.caption(f"Client ID: `{setup_client.client_id}`")
            if has_permission("delete_clients"):
                if st.button("Delete This Client", key="delete_client_btn"):
                    delete_client(setup_client.client_id)
                    st.session_state.pop("active_client_id", None)
                    _clear_pipeline_state()
                    st.rerun()
            else:
                st.caption("Only Admins can delete clients.")

    # ── User Management (Super Admin only) ──
    if has_permission("manage_users"):
        st.markdown("---")
        with st.expander("User Management (Super Admin)", expanded=False):
            render_user_management()

    st.markdown('<div class="section-header" style="margin-top:2rem;"><div class="section-icon blue">&#x1F504;</div><div><div class="section-title">How The Loop Works</div><div class="section-subtitle">The system gets smarter every cycle</div></div></div>', unsafe_allow_html=True)

    st.markdown('''
    <div class="figma-flow">
        <div class="figma-step"><div class="num">1</div><div class="label">Upload CSV<br><small style="color:rgba(255,255,255,0.4)">with performance data</small></div></div>
        <div class="arrow-connector">&rarr;</div>
        <div class="figma-step"><div class="num">2</div><div class="label">AI Analyzes<br><small style="color:rgba(255,255,255,0.4)">flags underperformers</small></div></div>
        <div class="arrow-connector">&rarr;</div>
        <div class="figma-step"><div class="num">3</div><div class="label">Sub-Agents Write<br><small style="color:rgba(255,255,255,0.4)">headlines + descriptions</small></div></div>
        <div class="arrow-connector">&rarr;</div>
        <div class="figma-step"><div class="num">4</div><div class="label">Preview &amp; Export<br><small style="color:rgba(255,255,255,0.4)">templates + Figma JSON</small></div></div>
        <div class="arrow-connector">&rarr;</div>
        <div class="figma-step"><div class="num">5</div><div class="label">Publish &amp; Measure<br><small style="color:rgba(255,255,255,0.4)">feed results back in</small></div></div>
    </div>
    <p style="text-align:center;color:rgba(255,255,255,0.4);font-size:0.8rem;margin-top:0.5rem;">
        &#8617; Memory logs every experiment. Next cycle, the AI avoids failed angles and doubles down on winners.
    </p>
    ''', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# TEMPLATES
# ══════════════════════════════════════════════════════════
with tab_templates:
    st.markdown('<div class="section-header"><div class="section-icon orange">&#x1F3A8;</div><div><div class="section-title">Template Library</div><div class="section-subtitle">Upload ad templates and define text regions for creative preview</div></div></div>', unsafe_allow_html=True)

    _tpl_client = active_client()
    if not _tpl_client:
        st.markdown('''
        <div style="text-align:center;padding:4rem 2rem;color:rgba(255,255,255,0.4);">
            <div style="font-size:2.5rem;margin-bottom:1rem;">&#x1F3A8;</div>
            <div style="font-size:1.1rem;font-weight:600;color:rgba(255,255,255,0.6);margin-bottom:0.5rem;">No client selected</div>
            <div style="font-size:0.85rem;max-width:400px;margin:0 auto;">
                Select or create a client in the <strong>Setup</strong> tab first.
                Templates are stored per-client so each brand gets its own creative library.
            </div>
        </div>
        ''', unsafe_allow_html=True)
    else:
        # ── Upload new template ──
        with st.expander("Upload New Template", expanded=False):
            _tpl_name = st.text_input("Template Name", placeholder="e.g. Meta Feed Ad 1080x1080", key="tpl_name")
            _tpl_platform = st.selectbox("Platform", ["", "Meta", "Google", "TikTok", "LinkedIn", "Other"], key="tpl_platform")
            _tpl_file = st.file_uploader("Template Image", type=["png", "jpg", "jpeg"], key="tpl_upload")

            if _tpl_name and _tpl_file and st.button("Save Template", key="save_tpl_btn"):
                tpl = create_template(_tpl_client.client_id, _tpl_name, _tpl_file, _tpl_file.name,
                                      platform=_tpl_platform)
                st.success(f"Template **{tpl.name}** saved ({tpl.width}x{tpl.height})")
                st.rerun()

        # ── List existing templates ──
        templates = list_templates(_tpl_client.client_id)
        if not templates:
            st.markdown("""
            <div style="text-align:center;padding:3rem 1rem;color:rgba(255,255,255,0.4);">
                <div style="font-size:2rem;margin-bottom:0.5rem;">&#x1F5BC;</div>
                <div>No templates yet. Upload an ad template image to get started.</div>
                <div style="font-size:0.8rem;margin-top:0.5rem;">Export your Figma/Canva designs as PNG, then define where text goes.</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            for tpl in templates:
                with st.expander(f"{tpl.name} ({tpl.width}x{tpl.height}) — {len(tpl.slots)} text slots"):
                    from templates import get_template_image_path
                    img_path = get_template_image_path(_tpl_client.client_id, tpl)

                    tc1, tc2 = st.columns([1, 1])
                    with tc1:
                        if img_path:
                            st.image(str(img_path), use_container_width=True)
                        else:
                            st.warning("Image file not found")

                    with tc2:
                        st.markdown("**Text Slots**")
                        # Show existing slots
                        for si, slot in enumerate(tpl.slots):
                            st.caption(f"**{slot.label}** → `{slot.slot_id}` at ({slot.x},{slot.y}) {slot.width}x{slot.height} — {slot.font_size}px {slot.font_color}")

                        # Add new slot form
                        st.markdown("---")
                        st.markdown("**Add Text Slot**")
                        _slot_id = st.selectbox("Maps to", ["headline", "primary_text", "link_description", "description", "ad_text", "introductory_text"],
                                                key=f"slot_id_{tpl.template_id}")
                        _slot_label = st.text_input("Label", value=_slot_id.replace("_", " ").title(), key=f"slot_label_{tpl.template_id}")

                        sc1, sc2, sc3, sc4 = st.columns(4)
                        with sc1:
                            _sx = st.number_input("X", value=60, min_value=0, max_value=tpl.width, key=f"sx_{tpl.template_id}")
                        with sc2:
                            _sy = st.number_input("Y", value=tpl.height - 200, min_value=0, max_value=tpl.height, key=f"sy_{tpl.template_id}")
                        with sc3:
                            _sw = st.number_input("Width", value=min(960, tpl.width - 120), min_value=50, key=f"sw_{tpl.template_id}")
                        with sc4:
                            _sh = st.number_input("Height", value=80, min_value=20, key=f"sh_{tpl.template_id}")

                        sf1, sf2, sf3 = st.columns(3)
                        with sf1:
                            _fs = st.number_input("Font Size", value=32, min_value=8, max_value=120, key=f"fs_{tpl.template_id}")
                        with sf2:
                            _fc = st.color_picker("Font Color", value="#FFFFFF", key=f"fc_{tpl.template_id}")
                        with sf3:
                            _fa = st.selectbox("Align", ["left", "center", "right"], key=f"fa_{tpl.template_id}")

                        if st.button("Add Slot", key=f"add_slot_{tpl.template_id}"):
                            tpl.slots.append(TextSlot(
                                slot_id=_slot_id, label=_slot_label,
                                x=int(_sx), y=int(_sy), width=int(_sw), height=int(_sh),
                                font_size=int(_fs), font_color=_fc, align=_fa,
                            ))
                            save_template(_tpl_client.client_id, tpl)
                            st.rerun()

                        # Preview with sample text
                        if tpl.slots and img_path:
                            st.markdown("---")
                            sample_copy = {s.slot_id: f"Sample {s.label} Text" for s in tpl.slots}
                            preview_img = render_preview(_tpl_client.client_id, tpl, sample_copy)
                            if preview_img:
                                st.markdown("**Preview with sample text:**")
                                import io as _io
                                buf = _io.BytesIO()
                                preview_img.save(buf, format="PNG")
                                st.image(buf.getvalue(), use_container_width=True)

                    # Delete template
                    if st.button("Delete Template", key=f"del_tpl_{tpl.template_id}"):
                        delete_template(_tpl_client.client_id, tpl.template_id)
                        st.rerun()

# ══════════════════════════════════════════════════════════
# UPLOAD & ANALYZE
# ══════════════════════════════════════════════════════════
with tab_analyze:
    st.markdown('<div class="section-header"><div class="section-icon green">&#x1F4E4;</div><div><div class="section-title">Upload &amp; Analyze</div><div class="section-subtitle">Drop your ad performance CSV &mdash; columns are auto-detected</div></div></div>', unsafe_allow_html=True)

    _has_client = bool(active_client())

    if not _has_client:
        st.markdown('''
        <div style="text-align:center;padding:4rem 2rem;color:rgba(255,255,255,0.4);">
            <div style="font-size:2.5rem;margin-bottom:1rem;">&#x1F4E4;</div>
            <div style="font-size:1.1rem;font-weight:600;color:rgba(255,255,255,0.6);margin-bottom:0.5rem;">Select a client first</div>
            <div style="font-size:0.85rem;">Go to <strong>Setup</strong> to select or create a client, then come back to upload data.</div>
        </div>
        ''', unsafe_allow_html=True)

    if _has_client:
        uploaded = st.file_uploader("Upload CSV or XLSX", type=["csv", "xlsx", "xls"], label_visibility="collapsed")

        if not uploaded and "underperformers" not in st.session_state:
            st.markdown('''
            <div style="text-align:center;padding:3rem 2rem;color:rgba(255,255,255,0.35);">
                <div style="font-size:2rem;margin-bottom:0.5rem;">&#x2B06;</div>
                <div style="font-size:0.95rem;font-weight:600;color:rgba(255,255,255,0.5);margin-bottom:0.5rem;">Drop your ad performance export above</div>
                <div style="font-size:0.82rem;max-width:500px;margin:0 auto;line-height:1.6;">
                    Supports <strong>CSV</strong> and <strong>XLSX</strong> from Meta Ads, Google Ads, TikTok, LinkedIn, or any platform.
                    Columns are auto-detected. Include ad identifiers, copy fields, and performance metrics.
                </div>
            </div>
            ''', unsafe_allow_html=True)

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

            # Auto-detect platform from columns
            detected_pid = detect_platform(list(df.columns))
            st.session_state.auto_platform_id = detected_pid
            detected_pf = get_platform(detected_pid)

            n_under = len(underperformers)
            flag_pct = n_under / len(df) * 100 if len(df) else 0

            n_fatigued = sum(1 for u in underperformers if u.fatigue_score > 0.2)
            st.markdown(f'''
            <div class="stat-row">
                <div class="stat-card"><div class="stat-value">{len(df)}</div><div class="stat-label">Total Ads</div></div>
                <div class="stat-card"><div class="stat-value red">{n_under}</div><div class="stat-label">Underperformers</div></div>
                <div class="stat-card"><div class="stat-value purple">{flag_pct:.0f}%</div><div class="stat-label">Flag Rate</div></div>
                <div class="stat-card"><div class="stat-value" style="color:#FCD34D;">{n_fatigued}</div><div class="stat-label">Fatigued</div></div>
                <div class="stat-card"><div class="stat-value green">{len(df) - n_under}</div><div class="stat-label">Healthy Ads</div></div>
            </div>
            ''', unsafe_allow_html=True)

            # Show detected platform
            st.markdown(f'''
            <div style="background:rgba(102,126,234,0.08);border:1px solid rgba(102,126,234,0.2);
                 border-radius:10px;padding:0.8rem 1rem;margin:0.5rem 0 1rem;font-size:0.85rem;">
                {detected_pf.icon} <strong>Detected platform: {detected_pf.name}</strong>
                &mdash; Copy will be generated with {detected_pf.name} formats.
                Change in the sidebar if incorrect.
            </div>
            ''', unsafe_allow_html=True)

            with st.expander("Column Detection"):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"**Identifiers:** {', '.join(mapping.identifiers) or 'None'}")
                    st.markdown(f"**Headlines:** {', '.join(mapping.headlines) or 'None detected'}")
                    st.markdown(f"**Descriptions:** {', '.join(mapping.descriptions) or 'None detected'}")
                with c2:
                    for mt, cn in mapping.metrics.items():
                        st.markdown(f"**{mt.replace('_', ' ').title()}:** {cn}")
                if not mapping.headlines and not mapping.descriptions:
                    st.info("No headline/description columns found (common with Meta/social video ads). "
                            "The AI will infer creative angles from ad names and metrics.")

            with st.expander("Raw Data", expanded=False):
                st.dataframe(df, use_container_width=True, height=250)

            if underperformers:
                # Count fatigue cases
                fatigued = [u for u in underperformers if u.fatigue_score > 0.2]
                st.markdown('<div class="section-header"><div class="section-icon red">&#x1F6A9;</div><div><div class="section-title">Underperforming Ads</div><div class="section-subtitle">Ranked by composite weakness score (higher = worse)</div></div></div>', unsafe_allow_html=True)

                if fatigued:
                    st.markdown(f'''
                    <div style="background:rgba(251,191,36,0.08);border:1px solid rgba(251,191,36,0.2);
                         border-radius:10px;padding:0.8rem 1rem;margin:0.5rem 0 1rem;font-size:0.85rem;">
                        &#x23F3; <strong>{len(fatigued)} ad{"s" if len(fatigued) != 1 else ""} showing fatigue signals</strong>
                        &mdash; These ads may have been seen too many times. The copy might not be bad &mdash; the audience is just tired of it.
                        Fresh creative angles can re-engage them.
                    </div>
                    ''', unsafe_allow_html=True)

                for u in underperformers:
                    label = next((str(u.ad_data.get(c, "")) for c in mapping.identifiers if u.ad_data.get(c)), f"Row {u.index}")
                    headline = next((str(u.ad_data.get(c, "")) for c in mapping.headlines if u.ad_data.get(c)), "")
                    reasons_html = "".join(f'<span class="reason-tag">{r}</span>' for r in u.reasons)
                    fatigue_html = ""
                    if u.fatigue_signals:
                        fatigue_tags = "".join(
                            f'<span style="display:inline-block;background:rgba(251,191,36,0.12);color:#FCD34D;padding:0.2rem 0.6rem;border-radius:6px;font-size:0.72rem;margin:0.15rem 0.25rem 0.15rem 0;font-weight:500;font-family:\'JetBrains Mono\',monospace;">&#x23F3; {s}</span>'
                            for s in u.fatigue_signals
                        )
                        fatigue_html = f'<div style="margin-top:0.4rem;">{fatigue_tags}</div>'
                    st.markdown(f'''
                    <div class="underperformer-card">
                        <div class="ad-label">{label} <span class="score-badge">{u.score}</span></div>
                        <div class="ad-headline">"{headline}"</div>
                        {reasons_html}
                        {fatigue_html}
                    </div>
                    ''', unsafe_allow_html=True)

                st.info("Head to **Generate Copy** to create AI-powered replacements.")
            else:
                st.success("All ads performing above threshold.")

# ══════════════════════════════════════════════════════════
# GENERATE
# ══════════════════════════════════════════════════════════
with tab_generate:
    gen_platform = get_platform(selected_platform_id)
    slot_summary = " · ".join(f"{s.label} ({s.char_limit} chars)" for s in gen_platform.slots)
    st.markdown(f'<div class="section-header"><div class="section-icon purple">&#x1F916;</div><div><div class="section-title">Generate Copy — {gen_platform.icon} {gen_platform.name}</div><div class="section-subtitle">{slot_summary}</div></div></div>', unsafe_allow_html=True)

    # Show copy format breakdown
    slot_html = '<div class="stat-row">'
    for s in gen_platform.slots:
        slot_html += f'<div class="stat-card"><div class="stat-value purple">{s.char_limit}</div><div class="stat-label">{s.label} (max chars)</div></div>'
    slot_html += '</div>'
    st.markdown(slot_html, unsafe_allow_html=True)

    ready = True
    _missing = []
    if not has_api_key():
        _missing.append(("&#x1F511;", "API Key", "Paste your Anthropic API key in the sidebar"))
    if not brand or not product:
        _missing.append(("&#x1F4DD;", "Brand Brief", "Fill in brand name and product in the <strong>Setup</strong> tab"))
    if "underperformers" not in st.session_state or not st.session_state.underperformers:
        _missing.append(("&#x1F4E4;", "Ad Data", "Upload a CSV/XLSX in <strong>Upload &amp; Analyze</strong>"))

    if _missing:
        ready = False
        checklist_html = '<div style="max-width:500px;margin:2rem auto;padding:2rem;">'
        checklist_html += '<div style="text-align:center;font-size:2rem;margin-bottom:1rem;">&#x1F916;</div>'
        checklist_html += '<div style="text-align:center;font-size:1rem;font-weight:600;color:rgba(255,255,255,0.6);margin-bottom:1.5rem;">Complete these steps to generate copy</div>'
        for icon, label, desc in _missing:
            checklist_html += f'''
            <div style="display:flex;align-items:flex-start;gap:0.75rem;padding:0.8rem;margin-bottom:0.5rem;
                 background:rgba(255,107,107,0.04);border:1px solid rgba(255,107,107,0.1);border-radius:10px;">
                <div style="font-size:1.2rem;flex-shrink:0;">{icon}</div>
                <div>
                    <div style="font-weight:600;font-size:0.9rem;color:rgba(255,255,255,0.7);">{label}</div>
                    <div style="font-size:0.8rem;color:rgba(255,255,255,0.4);">{desc}</div>
                </div>
            </div>'''
        checklist_html += '</div>'
        st.markdown(checklist_html, unsafe_allow_html=True)

    if ready:
        underperformers = st.session_state.underperformers
        mapping = st.session_state.mapping
        df_clean = st.session_state.df_clean

        total_ads = num_ad_sets * len(underperformers)

        st.markdown(f'''
        <div class="stat-row">
            <div class="stat-card"><div class="stat-value red">{len(underperformers)}</div><div class="stat-label">Ads to Fix</div></div>
            <div class="stat-card"><div class="stat-value purple">{num_ad_sets}</div><div class="stat-label">Variations Each</div></div>
            <div class="stat-card"><div class="stat-value green">{total_ads}</div><div class="stat-label">Total Ad Sets</div></div>
        </div>
        ''', unsafe_allow_html=True)

        st.markdown(f'''
        <div style="background:rgba(102,126,234,0.06);border:1px solid rgba(102,126,234,0.15);
             border-radius:10px;padding:0.8rem 1rem;margin:0.5rem 0 1rem;font-size:0.82rem;color:rgba(255,255,255,0.6);">
            Each variation is a <strong>complete, coherent ad</strong> — all copy elements
            ({", ".join(s.label for s in gen_platform.slots)}) share the same angle and tone.
            No random combinations.
        </div>
        ''', unsafe_allow_html=True)

        # ── Funnel Stage Selector ──
        st.markdown('<div class="section-header" style="margin-top:0.5rem;"><div class="section-icon blue">&#x1F3AF;</div><div><div class="section-title">Audience Funnel Stage</div><div class="section-subtitle">Different funnel stages need fundamentally different messaging</div></div></div>', unsafe_allow_html=True)

        _funnel_options = {"Auto-detect (no specific stage)": ""} | {v["label"]: k for k, v in FUNNEL_STAGES.items()}
        _selected_funnel_label = st.radio(
            "Funnel stage",
            list(_funnel_options.keys()),
            key="funnel_stage",
            horizontal=True,
            label_visibility="collapsed",
        )
        _selected_funnel = _funnel_options[_selected_funnel_label]

        if _selected_funnel:
            st.markdown(f'''
            <div style="background:rgba(96,165,250,0.06);border:1px solid rgba(96,165,250,0.15);
                 border-radius:10px;padding:0.8rem 1rem;margin:0.5rem 0 1rem;font-size:0.82rem;color:rgba(255,255,255,0.55);">
                {FUNNEL_STAGES[_selected_funnel]["guidance"].replace(chr(10), "<br>")}
            </div>
            ''', unsafe_allow_html=True)

        gen_history = load_history(get_memory_dir())
        if gen_history:
            st.markdown(f'<div style="background:rgba(102,126,234,0.08);border:1px solid rgba(102,126,234,0.2);border-radius:10px;padding:0.8rem 1rem;margin:0.5rem 0 1rem;font-size:0.85rem;">&#x1F9E0; <strong>Memory active</strong> &mdash; {len(gen_history)} previous runs loaded. AI will avoid failed angles.</div>', unsafe_allow_html=True)

        if st.button("Generate New Ad Copy", type="primary", use_container_width=True):
            insights = summarize_insights(gen_history)
            top_performers = extract_top_performers(df_clean, mapping)
            all_ad_sets: list[dict] = []
            total_steps = len(underperformers) + 1  # +1 for strategy analysis
            progress = st.progress(0, text="Analyzing performance data...")

            # Build brand brief dict from active client
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
                # Only pass if at least one field is populated
                if not any(_brand_brief.values()):
                    _brand_brief = None

            # ── Step 1: Run Creative Strategist agent ──
            dataset_summary = build_dataset_summary(df_clean, mapping, len(underperformers))
            strategy_brief = analyze_creative_strategy(
                platform_id=selected_platform_id,
                brand=brand,
                product=product,
                underperformers=[u.ad_data for u in underperformers],
                top_performers=top_performers,
                dataset_summary=dataset_summary,
                memory_insights=insights,
                brand_brief=_brand_brief,
                funnel_stage=_selected_funnel,
            )
            st.session_state.strategy_brief = strategy_brief
            progress.progress(1 / total_steps, text="Strategy complete. Generating copy...")

            # ── Step 2: Generate copy for each underperformer ──
            for i, u in enumerate(underperformers):
                ad_label = next((str(u.ad_data.get(c, "")) for c in mapping.identifiers if u.ad_data.get(c)), f"Row {u.index}")
                progress.progress((i + 1) / total_steps, text=f"Writing copy for: {ad_label} ({i+1}/{len(underperformers)})")

                ad_sets = generate_ad_sets(
                    platform_id=selected_platform_id,
                    brand=brand,
                    product=product,
                    underperformer=u.ad_data,
                    memory_insights=insights,
                    top_performers=top_performers,
                    num_sets=num_ad_sets,
                    strategy_brief=strategy_brief,
                    brand_brief=_brand_brief,
                    funnel_stage=_selected_funnel,
                )

                for ad_set in ad_sets:
                    ad_set["original_ad"] = ad_label
                    all_ad_sets.append(ad_set)

            progress.progress(1.0, text="Complete!")
            st.session_state.all_ad_sets = all_ad_sets
            st.session_state.gen_platform_id = selected_platform_id

            # Also store backward-compatible headline/description for Publish tab
            all_headlines = [{"original_ad": s["original_ad"], "headline": s.get("headline", ""), "char_count": len(s.get("headline", "")), "hypothesis": s.get("angle", "")} for s in all_ad_sets if s.get("headline")]
            first_body_key = next((sl.key for sl in gen_platform.slots if sl.key != "headline"), "description")
            all_descriptions = [{"original_ad": s["original_ad"], "description": s.get(first_body_key, ""), "char_count": len(s.get(first_body_key, "")), "hypothesis": s.get("angle", "")} for s in all_ad_sets if s.get(first_body_key)]
            st.session_state.all_headlines = all_headlines
            st.session_state.all_descriptions = all_descriptions
            # Also store in slot_results format for Export tab
            all_slot_results = {sl.key: [] for sl in gen_platform.slots}
            for s in all_ad_sets:
                for sl in gen_platform.slots:
                    if s.get(sl.key):
                        all_slot_results[sl.key].append({
                            sl.key: s[sl.key],
                            "original_ad": s["original_ad"],
                            "char_count": len(s[sl.key]),
                            "hypothesis": s.get("angle", ""),
                        })
            st.session_state.all_slot_results = all_slot_results

            # Save to memory
            run_id = generate_run_id()
            save_run(RunRecord(
                run_id=run_id, timestamp=datetime.now(timezone.utc).isoformat(),
                input_file="uploaded_csv", total_ads=len(df_clean),
                underperformers_count=len(underperformers),
                underperformers=[{"ad_data": u2.ad_data, "reasons": u2.reasons, "score": u2.score} for u2 in underperformers],
                generated_headlines=[{"original_ad": h["original_ad"], "headline": h["headline"], "hypothesis": h.get("hypothesis", "")} for h in all_headlines],
                generated_descriptions=[{"original_ad": d["original_ad"], "description": d["description"], "hypothesis": d.get("hypothesis", "")} for d in all_descriptions],
                top_performers=top_performers,
                notes=f"Platform: {gen_platform.name} | {num_ad_sets} sets/ad | coherent mode",
            ), memory_dir=get_memory_dir())

        if "all_ad_sets" in st.session_state:
            all_ad_sets = st.session_state.all_ad_sets
            gen_pid = st.session_state.get("gen_platform_id", selected_platform_id)
            gen_pf = get_platform(gen_pid)

            # Show strategy brief if available
            brief = st.session_state.get("strategy_brief", {})
            if brief:
                with st.expander("Creative Strategy Brief (AI analysis of your data)", expanded=False):
                    # Dataset patterns
                    patterns = brief.get("dataset_patterns", {})
                    if patterns:
                        st.markdown("**What Top Performers Share**")
                        for p in patterns.get("what_top_performers_share", []):
                            st.markdown(f"- ✅ {p}")
                        if patterns.get("key_metric_insights"):
                            st.markdown("**Key Data Insights**")
                            for p in patterns["key_metric_insights"]:
                                st.markdown(f"- 📊 {p}")

                    # Psychological analysis
                    psych = brief.get("psychological_analysis", {})
                    if psych:
                        st.markdown("**Psychological Triggers in Winners**")
                        for t in psych.get("triggers_in_winners", []):
                            st.markdown(f"- 🧠 {t}")
                        if psych.get("audience_psychology"):
                            st.markdown(f"**Audience Psychology:** {psych['audience_psychology']}")

                    # Creative strategy
                    cs = brief.get("creative_strategy", {})
                    if cs:
                        if cs.get("angles_to_test"):
                            st.markdown("**Recommended Angles**")
                            for a in cs["angles_to_test"]:
                                if isinstance(a, dict):
                                    st.markdown(f"- → **{a.get('angle', '')}**: {a.get('rationale', '')} *[{a.get('psychological_lever', '')}]*")
                                else:
                                    st.markdown(f"- → {a}")
                        if cs.get("angles_to_avoid"):
                            st.markdown("**Avoid**")
                            for a in cs["angles_to_avoid"]:
                                st.markdown(f"- ❌ {a}")
                        if cs.get("tone_recommendation"):
                            st.markdown(f"**Recommended Tone:** {cs['tone_recommendation']}")

            # Summary stats
            total_violations = 0
            for ad_set in all_ad_sets:
                for slot in gen_pf.slots:
                    if len(ad_set.get(slot.key, "")) > slot.char_limit:
                        total_violations += 1

            st.markdown(f'''
            <div class="stat-row">
                <div class="stat-card"><div class="stat-value green">{len(all_ad_sets)}</div><div class="stat-label">Complete Ad Sets</div></div>
                <div class="stat-card"><div class="stat-value green">{len(gen_pf.slots)}</div><div class="stat-label">Elements Each</div></div>
                <div class="stat-card"><div class="stat-value {"red" if total_violations else "green"}">{total_violations}</div><div class="stat-label">Char Violations</div></div>
            </div>
            ''', unsafe_allow_html=True)

            # Build display — card-style per ad set with rationale
            _has_rationale = any(ad_set.get("rationale") for ad_set in all_ad_sets)

            # Compact table view
            display_rows = []
            for ad_set in all_ad_sets:
                row = {"Source Ad": ad_set.get("original_ad", "")}
                for slot in gen_pf.slots:
                    text = ad_set.get(slot.key, "")
                    row[f"{slot.label} ({len(text)}/{slot.char_limit})"] = text
                row["Angle"] = ad_set.get("angle", "")
                display_rows.append(row)

            st.dataframe(pd.DataFrame(display_rows), use_container_width=True, height=400)

            # Rationale breakdown (expandable per ad set)
            if _has_rationale:
                with st.expander("View Rationale for Each Variation", expanded=False):
                    for idx, ad_set in enumerate(all_ad_sets):
                        rationale = ad_set.get("rationale", "")
                        if rationale:
                            st.markdown(
                                f"**{idx+1}. {ad_set.get('original_ad', 'Ad')}** "
                                f"— *{ad_set.get('angle', '')}*"
                            )
                            st.caption(rationale)
                            st.markdown("---")

            # Downloads
            st.markdown("---")
            dl1, dl2 = st.columns(2)
            with dl1:
                csv_rows = []
                for ad_set in all_ad_sets:
                    row = {"original_ad": ad_set.get("original_ad", ""), "angle": ad_set.get("angle", "")}
                    for slot in gen_pf.slots:
                        row[slot.label] = ad_set.get(slot.key, "")
                        row[f"{slot.label} chars"] = len(ad_set.get(slot.key, ""))
                    row["rationale"] = ad_set.get("rationale", "")
                    csv_rows.append(row)
                st.download_button(
                    "Download All Ad Sets",
                    pd.DataFrame(csv_rows).to_csv(index=False),
                    "ad_variations.csv", "text/csv", use_container_width=True,
                )
            with dl2:
                st.download_button(
                    "Download as JSON",
                    json.dumps(all_ad_sets, indent=2),
                    "ad_variations.json", "application/json", use_container_width=True,
                )

            # ── Template Previews ──
            _preview_client = active_client()
            _preview_templates = list_templates(_preview_client.client_id) if _preview_client else []
            _preview_templates = [t for t in _preview_templates if t.slots]  # Only templates with slots

            if _preview_templates:
                st.markdown("---")
                st.markdown('<div class="section-header"><div class="section-icon orange">&#x1F5BC;</div><div><div class="section-title">Creative Preview</div><div class="section-subtitle">See your copy on your ad templates</div></div></div>', unsafe_allow_html=True)

                _sel_tpl_name = st.selectbox(
                    "Template",
                    [t.name for t in _preview_templates],
                    key="preview_template_select",
                )
                _sel_tpl = next((t for t in _preview_templates if t.name == _sel_tpl_name), None)

                if _sel_tpl:
                    previews = render_all_previews(_preview_client.client_id, _sel_tpl, all_ad_sets)
                    if previews:
                        # Grid of previews — 3 columns
                        cols = st.columns(min(3, len(previews)))
                        for i, (label, img) in enumerate(previews):
                            with cols[i % 3]:
                                import io as _io
                                buf = _io.BytesIO()
                                img.save(buf, format="PNG")
                                st.image(buf.getvalue(), caption=label, use_container_width=True)

                        # Download all previews
                        zip_bytes = export_previews_zip(previews, template_name=_sel_tpl.template_id)
                        st.download_button(
                            "Download All Previews (ZIP)",
                            zip_bytes,
                            f"previews_{_sel_tpl.template_id}.zip",
                            "application/zip",
                            use_container_width=True,
                        )
                    else:
                        st.warning("Could not render previews — check that the template image exists.")

            st.info("Head to **Publish** or **Export** to push your new copy live.")

# ══════════════════════════════════════════════════════════
# PUBLISH
# ══════════════════════════════════════════════════════════
with tab_publish:
    st.markdown('<div class="section-header"><div class="section-icon orange">&#x1F680;</div><div><div class="section-title">Publish to Ad Platforms</div><div class="section-subtitle">Push generated ad variations directly to Meta Ads and Google Ads</div></div></div>', unsafe_allow_html=True)

    if "all_ad_sets" not in st.session_state and "all_headlines" not in st.session_state:
        st.markdown('''
        <div style="text-align:center;padding:4rem 2rem;color:rgba(255,255,255,0.4);">
            <div style="font-size:2.5rem;margin-bottom:1rem;">&#x1F680;</div>
            <div style="font-size:1.1rem;font-weight:600;color:rgba(255,255,255,0.6);margin-bottom:0.5rem;">No copy generated yet</div>
            <div style="font-size:0.85rem;max-width:400px;margin:0 auto;">
                Generate ad copy in the <strong>Generate Copy</strong> tab first, then come back here to push it live to Meta or Google Ads.
            </div>
        </div>
        ''', unsafe_allow_html=True)
    else:
        pub_meta, pub_google = st.tabs(["Meta Ads", "Google Ads"])

        # ── Meta Ads ────────────────────────────────────────
        with pub_meta:
            st.markdown("""
            <div class="platform-card">
                <h3><span class="platform-badge meta">META</span> &nbsp; Facebook & Instagram Ads</h3>
                <div class="subtitle">Push ad creatives directly to your Meta ad account</div>
            </div>
            """, unsafe_allow_html=True)

            with st.expander("How to get your Meta credentials", expanded=False):
                st.markdown("""
1. Go to **[Meta Business Suite](https://business.facebook.com)** → Settings → Business Info
2. Copy your **Ad Account ID** (numeric, e.g. `123456789`)
3. Go to **[Meta for Developers](https://developers.facebook.com)** → Your App → Tools → Graph API Explorer
4. Generate a **User Access Token** with these permissions:
   - `ads_management`
   - `pages_read_engagement`
5. Paste both values below
                """)

            _cl = active_client()
            mc1, mc2 = st.columns(2)
            with mc1:
                meta_token = st.text_input("Access Token", type="password", key="meta_token", value=_cl.meta_token if _cl else "", placeholder="EAAx...")
            with mc2:
                meta_acct = st.text_input("Ad Account ID", key="meta_acct", value=_cl.meta_account_id if _cl else "", placeholder="123456789")
            # Auto-save to client
            if _cl and (meta_token != _cl.meta_token or meta_acct != _cl.meta_account_id):
                _cl.meta_token = meta_token
                _cl.meta_account_id = meta_acct
                save_client(_cl)

            # Connection test
            meta_connected = False
            meta_platform = None
            if meta_token and meta_acct:
                meta_platform = MetaAdsPlatform(meta_token, meta_acct)
                if st.button("Test Meta Connection", key="meta_test"):
                    with st.spinner("Connecting to Meta..."):
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
                st.markdown("---")

                # Campaign / Ad Set selection
                try:
                    campaigns = meta_platform.list_campaigns()
                    if not campaigns:
                        st.warning("No campaigns found. Create one in Meta Ads Manager first.")
                    else:
                        campaign_names = {c["name"]: c["id"] for c in campaigns}
                        selected_campaign = st.selectbox("Campaign", list(campaign_names.keys()), key="meta_campaign")
                        campaign_id = campaign_names[selected_campaign]

                        adsets = meta_platform.list_adsets(campaign_id)
                        if not adsets:
                            st.warning("No ad sets in this campaign.")
                        else:
                            adset_names = {a["name"]: a["id"] for a in adsets}
                            selected_adset = st.selectbox("Ad Set", list(adset_names.keys()), key="meta_adset")
                            adset_id = adset_names[selected_adset]

                            # Page selection
                            try:
                                pages = meta_platform.list_pages()
                                if pages:
                                    page_names = {p["name"]: p["id"] for p in pages}
                                    selected_page = st.selectbox("Facebook Page", list(page_names.keys()), key="meta_page")
                                    page_id = page_names[selected_page]
                                else:
                                    page_id = st.text_input("Facebook Page ID", key="meta_page_id", placeholder="Enter Page ID manually")
                            except Exception:
                                page_id = st.text_input("Facebook Page ID", key="meta_page_id_fallback", placeholder="Enter Page ID manually")

                            link = st.text_input("Destination URL", key="meta_link", placeholder="https://yourbrand.com/landing")

                            # Build the ads to push
                            all_h = st.session_state.all_headlines
                            all_d = st.session_state.all_descriptions
                            combos = []
                            for h in all_h:
                                matching_descs = [d for d in all_d if d["original_ad"] == h["original_ad"]]
                                if matching_descs:
                                    combos.append({"headline": h["headline"], "description": matching_descs[0]["description"]})

                            st.markdown(f"**{len(combos)} ad variations** ready to push (all created as **PAUSED**)")

                            if st.button("Push to Meta Ads", type="primary", key="meta_push"):
                                with st.spinner(f"Pushing {len(combos)} ads to Meta..."):
                                    result = meta_platform.push_ads(
                                        combos, campaign_id, adset_id,
                                        page_id=page_id, link=link,
                                    )

                                if result.ads_pushed > 0:
                                    st.session_state.setdefault("push_results", []).append(result)
                                    st.markdown(f'<div class="push-result success">Pushed <strong>{result.ads_pushed}</strong> ads to Meta (PAUSED). Activate them in Ads Manager.</div>', unsafe_allow_html=True)
                                for detail in result.details[:5]:
                                    st.markdown(f'- `{detail["ad_id"]}` — {detail["headline"]}')
                                for err in result.errors:
                                    st.markdown(f'<div class="push-result error">{err}</div>', unsafe_allow_html=True)

                except Exception as e:
                    st.error(f"Error loading campaigns: {e}")

            # Pull performance
            if meta_connected and meta_platform:
                st.markdown("---")
                st.markdown("**Pull Performance Data**")
                meta_range = st.selectbox("Date Range", ["last_7d", "last_14d", "last_30d", "last_90d"], index=2, key="meta_range")
                if st.button("Pull from Meta", key="meta_pull"):
                    with st.spinner("Fetching performance data..."):
                        try:
                            perf = meta_platform.pull_performance(meta_range)
                            if perf:
                                st.dataframe(pd.DataFrame(perf), use_container_width=True, height=300)
                                csv_data = pd.DataFrame(perf).to_csv(index=False)
                                st.download_button("Download as CSV", csv_data, "meta_performance.csv", "text/csv")
                            else:
                                st.info("No performance data for this range.")
                        except Exception as e:
                            st.error(f"Failed to pull data: {e}")

        # ── Google Ads ──────────────────────────────────────
        with pub_google:
            st.markdown("""
            <div class="platform-card">
                <h3><span class="platform-badge google">GOOGLE</span> &nbsp; Google Search & Display Ads</h3>
                <div class="subtitle">Push Responsive Search Ads to your Google Ads account</div>
            </div>
            """, unsafe_allow_html=True)

            with st.expander("How to get your Google Ads credentials", expanded=False):
                st.markdown("""
1. **Developer Token**: Google Ads → Tools → API Center → Apply for access
2. **OAuth Credentials**: [Google Cloud Console](https://console.cloud.google.com) → APIs & Services → Credentials → Create OAuth Client ID (Desktop app)
3. **Refresh Token**: Use Google's [OAuth Playground](https://developers.google.com/oauthplayground) or run the `google-ads` auth flow
4. **Customer ID**: Your 10-digit Google Ads account number (found in top right of Google Ads)
5. **Login Customer ID** (optional): Only needed if managing through an MCC account
                """)

            _cl2 = active_client()
            gc1, gc2 = st.columns(2)
            with gc1:
                g_dev_token = st.text_input("Developer Token", type="password", key="g_dev_token", value=_cl2.google_dev_token if _cl2 else "")
                g_client_id = st.text_input("OAuth Client ID", key="g_client_id", value=_cl2.google_client_id if _cl2 else "", placeholder="xxxx.apps.googleusercontent.com")
                g_client_secret = st.text_input("OAuth Client Secret", type="password", key="g_client_secret", value=_cl2.google_client_secret if _cl2 else "")
            with gc2:
                g_refresh = st.text_input("Refresh Token", type="password", key="g_refresh", value=_cl2.google_refresh_token if _cl2 else "")
                g_customer = st.text_input("Customer ID", key="g_customer", value=_cl2.google_customer_id if _cl2 else "", placeholder="123-456-7890")
                g_login_customer = st.text_input("Login Customer ID (MCC)", key="g_login_customer", value=_cl2.google_login_customer_id if _cl2 else "", placeholder="Optional")
            # Auto-save to client
            if _cl2:
                changed = (g_dev_token != _cl2.google_dev_token or g_client_id != _cl2.google_client_id
                           or g_client_secret != _cl2.google_client_secret or g_refresh != _cl2.google_refresh_token
                           or g_customer != _cl2.google_customer_id or g_login_customer != _cl2.google_login_customer_id)
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
                google_platform = GoogleAdsPlatform(
                    g_dev_token, g_client_id, g_client_secret,
                    g_refresh, g_customer, g_login_customer,
                )
                if st.button("Test Google Connection", key="google_test"):
                    with st.spinner("Connecting to Google Ads..."):
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
                st.markdown("---")

                try:
                    campaigns = google_platform.list_campaigns()
                    if not campaigns:
                        st.warning("No campaigns found. Create one in Google Ads first.")
                    else:
                        campaign_names = {c["name"]: c for c in campaigns}
                        selected_campaign = st.selectbox("Campaign", list(campaign_names.keys()), key="g_campaign")
                        campaign = campaign_names[selected_campaign]

                        ad_groups = google_platform.list_ad_groups(campaign["id"])
                        if not ad_groups:
                            st.warning("No ad groups in this campaign.")
                        else:
                            ag_names = {a["name"]: a for a in ad_groups}
                            selected_ag = st.selectbox("Ad Group", list(ag_names.keys()), key="g_adgroup")
                            ad_group = ag_names[selected_ag]

                            final_url = st.text_input("Final URL", key="g_final_url", placeholder="https://yourbrand.com/landing")

                            # Group headlines + descriptions per original ad for RSA
                            all_h = st.session_state.all_headlines
                            all_d = st.session_state.all_descriptions
                            grouped = {}
                            for h in all_h:
                                grouped.setdefault(h["original_ad"], {"headlines": [], "descriptions": []})
                                grouped[h["original_ad"]]["headlines"].append(h["headline"])
                            for d in all_d:
                                grouped.setdefault(d["original_ad"], {"headlines": [], "descriptions": []})
                                grouped[d["original_ad"]]["descriptions"].append(d["description"])

                            rsa_count = len(grouped)
                            st.markdown(f"**{rsa_count} Responsive Search Ads** ready to push (all created as **PAUSED**)")
                            st.caption("Each RSA combines multiple headlines + descriptions from the same source ad.")

                            if st.button("Push to Google Ads", type="primary", key="google_push"):
                                rsa_ads = [
                                    {"headlines": g["headlines"][:15], "descriptions": g["descriptions"][:4]}
                                    for g in grouped.values()
                                ]
                                with st.spinner(f"Pushing {len(rsa_ads)} RSAs to Google Ads..."):
                                    result = google_platform.push_ads(
                                        rsa_ads, campaign["resource_name"],
                                        ad_group["resource_name"],
                                        final_url=final_url,
                                    )

                                if result.ads_pushed > 0:
                                    st.session_state.setdefault("push_results", []).append(result)
                                    st.markdown(f'<div class="push-result success">Pushed <strong>{result.ads_pushed}</strong> RSAs to Google Ads (PAUSED). Activate in Google Ads.</div>', unsafe_allow_html=True)
                                for detail in result.details[:5]:
                                    st.markdown(f'- `{detail["resource"]}` — {detail["headline"]}')
                                for err in result.errors:
                                    st.markdown(f'<div class="push-result error">{err}</div>', unsafe_allow_html=True)

                except Exception as e:
                    st.error(f"Error loading campaigns: {e}")

            # Pull performance
            if google_connected and google_platform:
                st.markdown("---")
                st.markdown("**Pull Performance Data**")
                g_range = st.selectbox("Date Range", ["LAST_7_DAYS", "LAST_14_DAYS", "LAST_30_DAYS", "LAST_90_DAYS"], index=2, key="g_range")
                if st.button("Pull from Google", key="google_pull"):
                    with st.spinner("Fetching performance data..."):
                        try:
                            perf = google_platform.pull_performance(g_range)
                            if perf:
                                st.dataframe(pd.DataFrame(perf), use_container_width=True, height=300)
                                csv_data = pd.DataFrame(perf).to_csv(index=False)
                                st.download_button("Download as CSV", csv_data, "google_ads_performance.csv", "text/csv")
                            else:
                                st.info("No performance data for this range.")
                        except Exception as e:
                            st.error(f"Failed to pull data: {e}")

# ══════════════════════════════════════════════════════════
# EXPORT
# ══════════════════════════════════════════════════════════
with tab_export:
    st.markdown('<div class="section-header"><div class="section-icon orange">&#x1F3A8;</div><div><div class="section-title">Export &amp; Figma</div><div class="section-subtitle">Download files or auto-swap copy into your Figma ad templates</div></div></div>', unsafe_allow_html=True)

    st.markdown('''
    <div class="figma-flow">
        <div class="figma-step"><div class="num">1</div><div class="label">Download JSON</div></div>
        <div class="arrow-connector">&rarr;</div>
        <div class="figma-step"><div class="num">2</div><div class="label">Open Figma Plugin</div></div>
        <div class="arrow-connector">&rarr;</div>
        <div class="figma-step"><div class="num">3</div><div class="label">Select Templates</div></div>
        <div class="arrow-connector">&rarr;</div>
        <div class="figma-step"><div class="num">4</div><div class="label">Import JSON</div></div>
        <div class="arrow-connector">&rarr;</div>
        <div class="figma-step"><div class="num">5</div><div class="label">Export Ads</div></div>
    </div>
    ''', unsafe_allow_html=True)

    st.markdown('''
    <div class="setup-card">
        <h3>Figma Template Setup</h3>
        <p>Name your text layers with these conventions so the plugin knows where to swap copy:</p>
        <p>
        <code style="background:rgba(255,255,255,0.1);padding:2px 8px;border-radius:4px;">#headline</code> &mdash; headline text layer<br>
        <code style="background:rgba(255,255,255,0.1);padding:2px 8px;border-radius:4px;">#description</code> &mdash; description text layer<br>
        <code style="background:rgba(255,255,255,0.1);padding:2px 8px;border-radius:4px;">#cta</code> &mdash; call-to-action button text
        </p>
        <p>Create one master ad frame per platform (Google Display, Facebook Feed, Instagram Story, etc).
        The plugin duplicates each frame for every variation.</p>
    </div>
    <div class="setup-card">
        <h3>Recommended Figma Plugins</h3>
        <p>
        <strong>Content Reel</strong> &mdash; Figma's official text/image population tool<br>
        <strong>Google Sheets Sync</strong> &mdash; sync text layers from spreadsheet data<br>
        <strong>Batch Styler</strong> &mdash; bulk edit and duplicate frames with data
        </p>
    </div>
    ''', unsafe_allow_html=True)

    if "all_ad_sets" in st.session_state:
        ad_sets = st.session_state.all_ad_sets
        gen_pid = st.session_state.get("gen_platform_id", selected_platform_id)
        gen_pf = get_platform(gen_pid)

        st.markdown(f'<div class="section-header"><div class="section-icon green">&#x1F4E6;</div><div><div class="section-title">Export Files — {gen_pf.icon} {gen_pf.name}</div><div class="section-subtitle">Download in the format that fits your workflow</div></div></div>', unsafe_allow_html=True)

        # Count unique source ads
        source_ads = set(s.get("original_ad", "unknown") for s in ad_sets)

        # Build figma-compatible JSON from coherent ad sets (no cartesian product)
        figma_data = {
            "_meta": {
                "generator": "ad-optimizer",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "brand": brand,
                "product": product,
                "platform": gen_pf.name,
            },
            "variations": [],
        }

        for vid, ad_set in enumerate(ad_sets, 1):
            variation = {
                "id": vid,
                "source_ad": ad_set.get("original_ad", "unknown"),
                "angle": ad_set.get("angle", ""),
            }
            for slot in gen_pf.slots:
                variation[f"#{slot.key}"] = ad_set.get(slot.key, "")
            variation["#cta"] = "Try Free" if "free" in product.lower() else "Learn More"
            figma_data["variations"].append(variation)

        st.markdown(f'''
        <div class="stat-row">
            <div class="stat-card"><div class="stat-value purple">{len(ad_sets)}</div><div class="stat-label">Ad Variations</div></div>
            <div class="stat-card"><div class="stat-value">{len(source_ads)}</div><div class="stat-label">Source Ads</div></div>
        </div>
        ''', unsafe_allow_html=True)

        with st.expander("Preview JSON (first 3)"):
            st.json({"_meta": figma_data["_meta"], "variations": figma_data["variations"][:3]})

        dl1, dl2, dl3 = st.columns(3)
        with dl1:
            st.download_button("Figma JSON", json.dumps(figma_data, indent=2), "figma_ad_variations.json", "application/json", use_container_width=True)
        with dl2:
            # Sheet-friendly CSV with all slot values + angle
            sheet_rows = []
            for v in figma_data["variations"]:
                row = {"id": v["id"], "source_ad": v["source_ad"], "angle": v.get("angle", "")}
                for slot in gen_pf.slots:
                    row[slot.label] = v.get(f"#{slot.key}", "")
                row["cta"] = v.get("#cta", "")
                sheet_rows.append(row)
            st.download_button("Google Sheets CSV", pd.DataFrame(sheet_rows).to_csv(index=False), "ad_variations.csv", "text/csv", use_container_width=True)
        with dl3:
            # Platform-specific bulk upload CSV
            if gen_pid == "meta":
                bulk_rows = []
                for v in figma_data["variations"]:
                    bulk_rows.append({
                        "Ad Name": f"V{v['id']}_{v['source_ad'][:30]}",
                        "Primary Text": v.get("#primary_text", ""),
                        "Headline": v.get("#headline", ""),
                        "Description": v.get("#link_description", ""),
                        "Call to Action": v.get("#cta", ""),
                    })
                st.download_button("Meta Ads Bulk CSV", pd.DataFrame(bulk_rows).to_csv(index=False), "meta_ads_bulk.csv", "text/csv", use_container_width=True)
            elif gen_pid == "google_search":
                bulk_rows = []
                for v in figma_data["variations"]:
                    bulk_rows.append({
                        "Headline": v.get("#headline", ""),
                        "Description": v.get("#description", ""),
                        "Source Ad": v["source_ad"],
                    })
                st.download_button("Google Ads Bulk CSV", pd.DataFrame(bulk_rows).to_csv(index=False), "google_ads_bulk.csv", "text/csv", use_container_width=True)
            else:
                bulk_rows = []
                for v in figma_data["variations"]:
                    row = {"source_ad": v["source_ad"]}
                    for slot in gen_pf.slots:
                        row[slot.label] = v.get(f"#{slot.key}", "")
                    bulk_rows.append(row)
                st.download_button("Bulk Upload CSV", pd.DataFrame(bulk_rows).to_csv(index=False), "bulk_upload.csv", "text/csv", use_container_width=True)
    else:
        st.markdown('''
        <div style="text-align:center;padding:4rem 2rem;color:rgba(255,255,255,0.4);">
            <div style="font-size:2.5rem;margin-bottom:1rem;">&#x1F3A8;</div>
            <div style="font-size:1.1rem;font-weight:600;color:rgba(255,255,255,0.6);margin-bottom:0.5rem;">Nothing to export yet</div>
            <div style="font-size:0.85rem;max-width:400px;margin:0 auto;">
                Generate ad copy in the <strong>Generate Copy</strong> tab. Then come back for
                Figma JSON, Google Sheets CSV, and platform-specific bulk upload files.
            </div>
        </div>
        ''', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# MEMORY
# ══════════════════════════════════════════════════════════
with tab_memory:
    mem_client = active_client()
    mem_label = f" — {mem_client.name}" if mem_client else ""
    st.markdown(f'<div class="section-header"><div class="section-icon blue">&#x1F9E0;</div><div><div class="section-title">Experiment Memory{mem_label}</div><div class="section-subtitle">Every run is logged. The AI learns from past results each cycle.</div></div></div>', unsafe_allow_html=True)

    history = load_history(get_memory_dir())
    if not history:
        st.markdown('''
        <div style="text-align:center;padding:4rem 2rem;color:rgba(255,255,255,0.4);">
            <div style="font-size:2.5rem;margin-bottom:1rem;">&#x1F9E0;</div>
            <div style="font-size:1.1rem;font-weight:600;color:rgba(255,255,255,0.6);margin-bottom:0.5rem;">No experiments yet</div>
            <div style="font-size:0.85rem;max-width:450px;margin:0 auto;line-height:1.6;">
                Run the pipeline (Upload &rarr; Generate) to start building memory.
                Each run is logged. On subsequent runs, the AI references past experiments
                to avoid failed angles and double down on what worked.
                <br><br>
                <strong>The more you run it, the smarter it gets.</strong>
            </div>
        </div>
        ''', unsafe_allow_html=True)
    else:
        th = sum(len(r.generated_headlines) for r in history)
        td = sum(len(r.generated_descriptions) for r in history)
        st.markdown(f'''
        <div class="stat-row">
            <div class="stat-card"><div class="stat-value purple">{len(history)}</div><div class="stat-label">Total Runs</div></div>
            <div class="stat-card"><div class="stat-value">{th}</div><div class="stat-label">Headlines</div></div>
            <div class="stat-card"><div class="stat-value">{td}</div><div class="stat-label">Descriptions</div></div>
            <div class="stat-card"><div class="stat-value">{sum(r.total_ads for r in history)}</div><div class="stat-label">Ads Analyzed</div></div>
        </div>
        ''', unsafe_allow_html=True)

        # ── Performance Trends ──
        if len(history) >= 2:
            st.markdown('<div class="section-header"><div class="section-icon green">&#x1F4C8;</div><div><div class="section-title">Optimization Trends</div><div class="section-subtitle">Are your optimizations improving performance over cycles?</div></div></div>', unsafe_allow_html=True)

            trend_data = []
            for run in history:
                row = {
                    "Run": run.run_id.replace("run_", "").replace("_", " "),
                    "Date": run.timestamp[:10],
                    "Ads Analyzed": run.total_ads,
                    "Underperformers": run.underperformers_count,
                    "Flag Rate (%)": round(run.underperformers_count / run.total_ads * 100, 1) if run.total_ads > 0 else 0,
                    "Headlines Generated": len(run.generated_headlines),
                    "Descriptions Generated": len(run.generated_descriptions),
                }
                trend_data.append(row)

            trend_df = pd.DataFrame(trend_data)

            tc1, tc2 = st.columns(2)
            with tc1:
                st.markdown("**Underperformer Flag Rate Over Time**")
                st.area_chart(trend_df.set_index("Date")["Flag Rate (%)"], color="#FF6B6B", height=200)
            with tc2:
                st.markdown("**Variations Generated Per Run**")
                gen_df = trend_df.set_index("Date")[["Headlines Generated", "Descriptions Generated"]]
                st.bar_chart(gen_df, color=["#E8FF47", "#60A5FA"], height=200)

            # Trend direction indicator
            if len(trend_data) >= 2:
                first_flag = trend_data[0]["Flag Rate (%)"]
                last_flag = trend_data[-1]["Flag Rate (%)"]
                delta = last_flag - first_flag
                if delta < -5:
                    trend_msg = f"Flag rate dropped from {first_flag}% to {last_flag}% — your optimizations are working."
                    trend_color = "rgba(74,222,128,0.12)"
                    trend_border = "rgba(74,222,128,0.25)"
                    trend_icon = "&#x2705;"
                elif delta > 5:
                    trend_msg = f"Flag rate increased from {first_flag}% to {last_flag}% — consider new creative angles."
                    trend_color = "rgba(255,107,107,0.08)"
                    trend_border = "rgba(255,107,107,0.2)"
                    trend_icon = "&#x26A0;"
                else:
                    trend_msg = f"Flag rate is stable around {last_flag}%. Keep iterating to find breakthrough angles."
                    trend_color = "rgba(96,165,250,0.08)"
                    trend_border = "rgba(96,165,250,0.2)"
                    trend_icon = "&#x2139;"

                st.markdown(f'''
                <div style="background:{trend_color};border:1px solid {trend_border};
                     border-radius:10px;padding:0.8rem 1rem;margin:0.5rem 0 1.5rem;font-size:0.85rem;">
                    {trend_icon} {trend_msg}
                </div>
                ''', unsafe_allow_html=True)

        st.markdown("**Accumulated Insights**")
        st.code(summarize_insights(history), language="text")

        st.markdown("**Run History**")
        for run in reversed(history):
            with st.expander(f"{run.run_id} — {run.timestamp[:10]} — {len(run.generated_headlines)} headlines"):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"**Input:** {run.input_file}")
                    st.markdown(f"**Total ads:** {run.total_ads}")
                with c2:
                    st.markdown(f"**Headlines:** {len(run.generated_headlines)}")
                    st.markdown(f"**Descriptions:** {len(run.generated_descriptions)}")
                if run.generated_headlines:
                    st.markdown("**Samples:**")
                    for h in run.generated_headlines[:5]:
                        st.markdown(f"- `{h.get('headline', '')}` — _{h.get('hypothesis', '')}_")

        st.markdown("---")
        if st.button("Clear All Memory"):
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
            st.rerun()
