from __future__ import annotations
"""Multi-client management for agency use.

Each client has their own brand context, platform credentials,
and experiment memory. Stored as JSON files under clients/.
"""

import json
import re
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


CLIENTS_DIR = Path(__file__).parent / "clients"


def _slugify(name: str) -> str:
    """Convert a display name to a filesystem-safe slug."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "default"


CATEGORIES = [
    "", "SaaS", "E-commerce/DTC", "Finance/Fintech", "Healthcare/Wellness",
    "Education/EdTech", "Real Estate", "Travel/Hospitality", "Food & Beverage",
    "Fashion/Beauty", "Technology/Electronics", "Entertainment/Media",
    "Automotive", "B2B Services", "Non-profit", "Other",
]


@dataclass
class ClientConfig:
    client_id: str
    name: str
    brand: str = ""
    product: str = ""
    # Brand brief (rich context for AI)
    category: str = ""
    brand_description: str = ""
    target_audience: str = ""
    brand_voice: str = ""
    key_differentiators: str = ""
    competitors: str = ""
    # Anthropic (optional per-client override)
    anthropic_api_key: str = ""
    # Meta Ads
    meta_token: str = ""
    meta_account_id: str = ""
    # Google Ads
    google_dev_token: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""
    google_customer_id: str = ""
    google_login_customer_id: str = ""
    # Metadata
    created_at: str = ""
    updated_at: str = ""


def _client_file(client_id: str) -> Path:
    return CLIENTS_DIR / f"{client_id}.json"


def list_clients() -> list[ClientConfig]:
    """Return all saved clients, sorted by name."""
    CLIENTS_DIR.mkdir(parents=True, exist_ok=True)
    clients = []
    for f in sorted(CLIENTS_DIR.glob("*.json")):
        try:
            with open(f) as fh:
                data = json.load(fh)
            clients.append(ClientConfig(**{k: v for k, v in data.items() if k in ClientConfig.__dataclass_fields__}))
        except Exception:
            continue
    return clients


def load_client(client_id: str) -> ClientConfig | None:
    """Load a single client by ID."""
    path = _client_file(client_id)
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)
    return ClientConfig(**{k: v for k, v in data.items() if k in ClientConfig.__dataclass_fields__})


def save_client(client: ClientConfig):
    """Save a client config to disk."""
    CLIENTS_DIR.mkdir(parents=True, exist_ok=True)
    client.updated_at = datetime.now(timezone.utc).isoformat()
    if not client.created_at:
        client.created_at = client.updated_at
    with open(_client_file(client.client_id), "w") as f:
        json.dump(asdict(client), f, indent=2)


def delete_client(client_id: str):
    """Delete a client config file."""
    path = _client_file(client_id)
    if path.exists():
        path.unlink()


def create_client(name: str) -> ClientConfig:
    """Create a new client with a generated slug ID."""
    slug = _slugify(name)
    # Ensure unique
    existing = {c.client_id for c in list_clients()}
    final_id = slug
    counter = 2
    while final_id in existing:
        final_id = f"{slug}-{counter}"
        counter += 1
    client = ClientConfig(client_id=final_id, name=name)
    save_client(client)
    return client


def client_memory_dir(client_id: str) -> Path:
    """Return the memory directory for a specific client."""
    d = Path(__file__).parent / "memory" / client_id
    d.mkdir(parents=True, exist_ok=True)
    return d
