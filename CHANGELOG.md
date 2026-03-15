# Changelog

All notable changes to the Ad Optimizer pipeline are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

---

## [0.6.0] — 2026-03-15

### Added
- **Reinforcement learning loop** — system now tracks whether its past suggestions actually improved ad performance on subsequent uploads
- `detect_outcomes()` fuzzy-matches ads across runs to score hypotheses as validated or failed
- `score_hypotheses()` aggregates win/loss data across all runs
- `summarize_insights()` feeds validated/failed strategies into agent prompts so the AI doubles down on what works and avoids what doesn't
- Memory page shows improvement rate, validated vs failed strategies, and per-run outcome badges
- Toast notifications on upload when feedback loop detects improvements or persistent issues

### Changed
- **Generation is now parallelized** — uses `ThreadPoolExecutor` (up to 8 workers) instead of sequential API calls; ~5x speedup for large datasets
- `RunRecord` gains `outcomes` field (backward compatible with existing logs)

---

## [0.5.2] — 2026-03-15

### Fixed
- **HTML rendering on Streamlit Cloud** — root cause was indented HTML (4+ spaces) being treated as Markdown code blocks; all card HTML now written as flat single-line strings
- Switched from CSS-based scroll to `st.container(height=500)` for underperformer list

### Changed
- Platform selection required before file upload (not just before generation)
- Page shows "Select a platform to begin" empty state until platform is chosen

---

## [0.5.1] — 2026-03-15

### Fixed
- Reason tags rendering as raw HTML (`<span class="reason-tag">`) on Streamlit Cloud

### Changed
- Moved variations slider from header row to above Generate button
- Added "Score:" label to performance score badges
- Added explanation caption to funnel stage radio buttons
- Underperformer cards now in scrollable container

---

## [0.5.0] — 2026-03-15

### Added
- Login rate limiting (5 attempts, 5-minute lockout)
- Password change form for logged-in users
- Admin password reset for managed users
- Confirmation dialogs for "Delete Client" and "Clear All Memory"

### Fixed
- Anthropic client not cached — `_get_client()` was creating new client on every call
- Stale pipeline state on client switch (missing keys in `_clear_pipeline_state()`)
- SSO-aware user management (password disabled when Google SSO active)

---

## [0.4.2] — 2026-03-14

### Fixed
- Logout button not showing for backdoor login sessions

---

## [0.4.1] — 2026-03-14

### Fixed
- Google OAuth config path in `auth.py`

---

## [0.4.0] — 2026-03-14

### Added
- **Authentication system** — bootstrap flow, local password auth, Google SSO, backdoor admin
- User management with role-based access (admin/user)
- `users.json`-based credential storage with bcrypt hashing
- `_google_auth_available()` checks all 4 OIDC fields before calling `st.login("google")`

---

## [0.3.0] — 2026-03-14

### Changed
- **UX reimagined** — replaced 7-tab wizard with sidebar-nav workspace
- Single-page Optimize view: Upload → Analyze → Generate in one pane
- Split-pane layout: underperformers (left) | generated copy (right)
- Dark theme with custom CSS variables
- Sidebar: client selector, navigation, settings access

---

## [0.2.0] — 2026-03-13

### Added
- Creative fatigue detection (frequency, spend, impression-based signals)
- Funnel stage targeting (Cold/Warm/Hot with tailored prompts)
- Role-based access control groundwork
- Empty states for all pages
- Trend charts on Memory page (flag rate over time, variations per run)
- Platform auto-detection from CSV column names

---

## [0.1.0] — 2026-03-13

### Added
- Initial release of the Ad Optimizer pipeline
- CSV/XLSX upload with auto-column detection
- Percentile-based underperformer flagging
- Claude-powered ad copy generation (headlines, descriptions)
- Multi-platform support (Meta Ads, Google Ads, TikTok, LinkedIn, Generic)
- Experiment memory system with per-client logging
- Creative Strategist agent (analyzes data patterns before copy generation)
- Top performer extraction for context
- Dev container configuration
