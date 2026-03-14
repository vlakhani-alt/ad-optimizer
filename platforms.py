from __future__ import annotations
"""Platform integrations for pushing generated ads to Meta and Google Ads.

Uses REST APIs directly (no heavy SDKs) to keep dependencies light.
All ads are created as PAUSED for safety — user activates manually.
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import requests


@dataclass
class PushResult:
    platform: str
    success: bool
    ads_pushed: int
    errors: list[str] = field(default_factory=list)
    details: list[dict] = field(default_factory=list)


class PlatformBase(ABC):
    """Base class for ad platform integrations."""

    name: str = "Unknown"

    @abstractmethod
    def test_connection(self) -> tuple[bool, str]:
        """Returns (success, message)."""
        ...

    @abstractmethod
    def list_campaigns(self) -> list[dict]:
        ...

    @abstractmethod
    def push_ads(self, ads: list[dict], campaign_id: str, ad_group_id: str, **kw) -> PushResult:
        ...

    @abstractmethod
    def pull_performance(self, date_range: str) -> list[dict]:
        ...


# ══════════════════════════════════════════════════════════════
# META ADS (Facebook Marketing API v21.0)
# ══════════════════════════════════════════════════════════════

class MetaAdsPlatform(PlatformBase):
    """Meta (Facebook/Instagram) Ads integration.

    Requires:
      - Access Token (from Meta Business Suite → Settings → Advanced)
      - Ad Account ID (numeric, with or without 'act_' prefix)
    """

    name = "Meta Ads"
    BASE = "https://graph.facebook.com/v21.0"

    def __init__(self, access_token: str, ad_account_id: str):
        self.token = access_token.strip()
        acct = ad_account_id.strip()
        self.ad_account_id = acct if acct.startswith("act_") else f"act_{acct}"

    # -- helpers --

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        params = params or {}
        params["access_token"] = self.token
        r = requests.get(f"{self.BASE}/{endpoint}", params=params, timeout=30)
        data = r.json()
        if "error" in data:
            raise Exception(data["error"].get("message", json.dumps(data["error"])))
        return data

    def _post(self, endpoint: str, payload: dict) -> dict:
        payload["access_token"] = self.token
        r = requests.post(f"{self.BASE}/{endpoint}", data=payload, timeout=30)
        data = r.json()
        if "error" in data:
            raise Exception(data["error"].get("message", json.dumps(data["error"])))
        return data

    # -- public API --

    def test_connection(self) -> tuple[bool, str]:
        try:
            data = self._get(self.ad_account_id, {"fields": "name,account_status"})
            name = data.get("name", "Unknown")
            status_map = {1: "Active", 2: "Disabled", 3: "Unsettled", 7: "Pending Review", 100: "Pending Closure", 101: "Closed", 201: "Temp Unavailable"}
            status = status_map.get(data.get("account_status"), "Unknown")
            return True, f"{name} ({status})"
        except Exception as e:
            return False, str(e)

    def list_campaigns(self) -> list[dict]:
        data = self._get(
            f"{self.ad_account_id}/campaigns",
            {"fields": "id,name,status,objective", "limit": "100"},
        )
        return data.get("data", [])

    def list_adsets(self, campaign_id: str) -> list[dict]:
        data = self._get(
            f"{campaign_id}/adsets",
            {"fields": "id,name,status,targeting", "limit": "100"},
        )
        return data.get("data", [])

    def list_pages(self) -> list[dict]:
        """List Facebook Pages the user can use for ads."""
        data = self._get("me/accounts", {"fields": "id,name", "limit": "50"})
        return data.get("data", [])

    def push_ads(
        self,
        ads: list[dict],
        campaign_id: str,
        ad_group_id: str,
        page_id: str = "",
        link: str = "",
        **kw,
    ) -> PushResult:
        """Push ads to Meta. Each dict needs 'headline' and 'description'.

        All ads are created as PAUSED.
        """
        result = PushResult(platform="Meta Ads", success=True, ads_pushed=0)

        for ad in ads:
            try:
                headline = ad.get("headline", "")
                description = ad.get("description", "")

                # 1) Create ad creative
                creative_spec = {
                    "page_id": page_id,
                    "link_data": {
                        "message": description,
                        "name": headline,
                        "link": link or "https://example.com",
                        "call_to_action": {"type": "LEARN_MORE"},
                    },
                }
                creative = self._post(
                    f"{self.ad_account_id}/adcreatives",
                    {
                        "name": f"AO | {headline[:40]}",
                        "object_story_spec": json.dumps(creative_spec),
                    },
                )
                creative_id = creative["id"]

                # 2) Create the ad (PAUSED)
                ad_resp = self._post(
                    f"{self.ad_account_id}/ads",
                    {
                        "name": f"AO | {headline[:40]}",
                        "adset_id": ad_group_id,
                        "creative": json.dumps({"creative_id": creative_id}),
                        "status": "PAUSED",
                    },
                )

                result.ads_pushed += 1
                result.details.append({
                    "ad_id": ad_resp["id"],
                    "creative_id": creative_id,
                    "headline": headline,
                    "status": "PAUSED",
                })

            except Exception as e:
                result.errors.append(f"{headline[:30]}: {e}")

        result.success = result.ads_pushed > 0
        return result

    def pull_performance(self, date_range: str = "last_30d") -> list[dict]:
        data = self._get(
            f"{self.ad_account_id}/insights",
            {
                "fields": "ad_id,ad_name,impressions,clicks,ctr,spend,actions,cost_per_action_type",
                "date_preset": date_range,
                "level": "ad",
                "limit": "500",
            },
        )
        return data.get("data", [])


# ══════════════════════════════════════════════════════════════
# GOOGLE ADS (REST API v18)
# ══════════════════════════════════════════════════════════════

class GoogleAdsPlatform(PlatformBase):
    """Google Ads integration via REST API.

    Requires:
      - Developer Token (from Google Ads API Center)
      - OAuth Client ID + Secret (from Google Cloud Console)
      - Refresh Token (generated via OAuth flow)
      - Customer ID (10-digit, with or without dashes)
      - Login Customer ID (optional, for MCC accounts)
    """

    name = "Google Ads"
    API_VERSION = "v18"

    def __init__(
        self,
        developer_token: str,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        customer_id: str,
        login_customer_id: str = "",
    ):
        self.developer_token = developer_token.strip()
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.refresh_token = refresh_token.strip()
        self.customer_id = customer_id.replace("-", "").strip()
        self.login_customer_id = login_customer_id.replace("-", "").strip() or None
        self._access_token: str | None = None

    # -- helpers --

    def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token
        r = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=15,
        )
        data = r.json()
        if "error" in data:
            raise Exception(data.get("error_description", data["error"]))
        self._access_token = data["access_token"]
        return self._access_token

    def _headers(self) -> dict:
        h = {
            "Authorization": f"Bearer {self._get_access_token()}",
            "developer-token": self.developer_token,
            "Content-Type": "application/json",
        }
        if self.login_customer_id:
            h["login-customer-id"] = self.login_customer_id
        return h

    def _gaql(self, query: str) -> list[dict]:
        url = (
            f"https://googleads.googleapis.com/{self.API_VERSION}"
            f"/customers/{self.customer_id}/googleAds:searchStream"
        )
        r = requests.post(url, headers=self._headers(), json={"query": query}, timeout=30)
        if r.status_code != 200:
            err = r.json().get("error", {}).get("message", r.text[:300])
            raise Exception(err)
        rows = []
        for batch in r.json():
            rows.extend(batch.get("results", []))
        return rows

    def _mutate(self, resource: str, operations: list[dict]) -> dict:
        url = (
            f"https://googleads.googleapis.com/{self.API_VERSION}"
            f"/customers/{self.customer_id}/{resource}:mutate"
        )
        r = requests.post(
            url, headers=self._headers(), json={"operations": operations}, timeout=30,
        )
        if r.status_code != 200:
            err = r.json().get("error", {}).get("message", r.text[:300])
            raise Exception(err)
        return r.json()

    # -- public API --

    def test_connection(self) -> tuple[bool, str]:
        try:
            rows = self._gaql(
                "SELECT customer.descriptive_name, customer.id FROM customer LIMIT 1"
            )
            if rows:
                name = rows[0].get("customer", {}).get("descriptiveName", "Unknown")
                return True, f"{name}"
            return True, "Connected"
        except Exception as e:
            return False, str(e)

    def list_campaigns(self) -> list[dict]:
        rows = self._gaql(
            "SELECT campaign.id, campaign.name, campaign.status, campaign.resource_name "
            "FROM campaign WHERE campaign.status != 'REMOVED' "
            "ORDER BY campaign.name"
        )
        return [
            {
                "id": str(r["campaign"]["id"]),
                "name": r["campaign"]["name"],
                "status": r["campaign"]["status"],
                "resource_name": r["campaign"]["resourceName"],
            }
            for r in rows
        ]

    def list_ad_groups(self, campaign_resource: str) -> list[dict]:
        cid = campaign_resource.split("/")[-1] if "/" in campaign_resource else campaign_resource
        rows = self._gaql(
            f"SELECT ad_group.id, ad_group.name, ad_group.status, ad_group.resource_name "
            f"FROM ad_group WHERE campaign.id = {cid} AND ad_group.status != 'REMOVED'"
        )
        return [
            {
                "id": str(r["adGroup"]["id"]),
                "name": r["adGroup"]["name"],
                "status": r["adGroup"]["status"],
                "resource_name": r["adGroup"]["resourceName"],
            }
            for r in rows
        ]

    def push_ads(
        self,
        ads: list[dict],
        campaign_id: str,
        ad_group_id: str,
        final_url: str = "",
        **kw,
    ) -> PushResult:
        """Push Responsive Search Ads. Each dict needs 'headlines' (list) and 'descriptions' (list).

        All ads created as PAUSED.
        """
        result = PushResult(platform="Google Ads", success=True, ads_pushed=0)

        # ad_group_id should be a resource name like customers/123/adGroups/456
        if not ad_group_id.startswith("customers/"):
            ad_group_id = f"customers/{self.customer_id}/adGroups/{ad_group_id}"

        for ad in ads:
            try:
                headlines = ad.get("headlines", [ad.get("headline", "")])
                descriptions = ad.get("descriptions", [ad.get("description", "")])

                # Google RSA needs at least 3 headlines and 2 descriptions
                h_assets = [{"text": h} for h in headlines[:15] if h]
                d_assets = [{"text": d} for d in descriptions[:4] if d]

                if len(h_assets) < 3:
                    result.errors.append(f"Need 3+ headlines, got {len(h_assets)}")
                    continue
                if len(d_assets) < 2:
                    result.errors.append(f"Need 2+ descriptions, got {len(d_assets)}")
                    continue

                op = {
                    "create": {
                        "adGroup": ad_group_id,
                        "status": "PAUSED",
                        "ad": {
                            "responsiveSearchAd": {
                                "headlines": h_assets,
                                "descriptions": d_assets,
                            },
                            "finalUrls": [final_url or "https://example.com"],
                        },
                    }
                }

                resp = self._mutate("adGroupAds", [op])
                rn = resp.get("results", [{}])[0].get("resourceName", "")
                result.ads_pushed += 1
                result.details.append({
                    "resource": rn,
                    "headline": headlines[0] if headlines else "",
                    "status": "PAUSED",
                })

            except Exception as e:
                label = (headlines[0] if headlines else "?")[:30]
                result.errors.append(f"{label}: {e}")

        result.success = result.ads_pushed > 0
        return result

    def pull_performance(self, date_range: str = "LAST_30_DAYS") -> list[dict]:
        rows = self._gaql(
            "SELECT ad_group_ad.ad.id, ad_group_ad.ad.name, "
            "ad_group_ad.ad.responsive_search_ad.headlines, "
            "ad_group_ad.ad.responsive_search_ad.descriptions, "
            "metrics.impressions, metrics.clicks, metrics.ctr, "
            "metrics.conversions, metrics.cost_micros "
            f"FROM ad_group_ad WHERE segments.date DURING {date_range} "
            "ORDER BY metrics.impressions DESC LIMIT 500"
        )
        return rows
