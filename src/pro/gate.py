from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path

_PRO_FILE = Path.home() / ".local" / "share" / "claude-vault" / "pro.json"

# HMAC secret — rotate on v1.0 release
_SECRET = b"ctx-pro-mvp-2026-jaytoone"


def _compute_sig(tier_tag: str, expiry: str, seats: str) -> str:
    payload = f"{tier_tag}:{expiry}:{seats}"
    return hmac.new(_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:8]


def validate_key(key: str) -> tuple[bool, str, dict]:
    """Return (valid, error_msg, parsed_payload).

    Key format: CTX-{PRO|TEAM}-{YYYYMM}-{SEATS}-{SIG8}
    SIG8 = HMAC-SHA256(_SECRET, "{tier_tag}:{YYYYMM}:{SEATS}")[:8]
    """
    key = key.strip()
    parts = key.split("-")
    if len(parts) != 5 or parts[0] != "CTX" or parts[1] not in ("PRO", "TEAM"):
        return False, "Invalid format. Expected CTX-PRO-YYYYMM-SEATS-SIG8", {}

    tier_tag, expiry_str, seats_str, sig = parts[1], parts[2], parts[3], parts[4]

    if len(expiry_str) != 6 or not expiry_str.isdigit():
        return False, "Invalid expiry field (expected YYYYMM)", {}
    if not seats_str.isdigit():
        return False, "Invalid seats field", {}
    if len(sig) != 8:
        return False, "Invalid signature length (expected 8 hex chars)", {}

    expected_sig = _compute_sig(tier_tag, expiry_str, seats_str)
    if not hmac.compare_digest(sig.lower(), expected_sig.lower()):
        return False, "License key signature invalid", {}

    year, month = int(expiry_str[:4]), int(expiry_str[4:])
    now = datetime.now()
    if now.year > year or (now.year == year and now.month > month):
        return False, f"License expired ({expiry_str[:4]}-{expiry_str[4:]})", {}

    tier = "team" if tier_tag == "TEAM" else "pro"
    return True, "", {
        "tier": tier,
        "expiry": expiry_str,
        "seats": int(seats_str),
        "expires_display": f"{expiry_str[:4]}-{expiry_str[4:]}",
    }


def generate_key(tier_tag: str, expiry_yyyymm: str, seats: int = 5) -> str:
    """Generate a valid license key (developer use only)."""
    sig = _compute_sig(tier_tag, expiry_yyyymm, str(seats))
    return f"CTX-{tier_tag}-{expiry_yyyymm}-{seats}-{sig}"


def team_id_from_key(key: str) -> str:
    """Stable 16-char team identifier derived from the license key."""
    return hashlib.sha256(key.strip().encode()).hexdigest()[:16]


class ProGate:
    def is_active(self) -> bool:
        key = self._load().get("license_key", "")
        if not key:
            return False
        valid, _, _ = validate_key(key)
        return valid

    def tier(self) -> str:
        key = self._load().get("license_key", "")
        if not key:
            return "free"
        valid, _, payload = validate_key(key)
        return payload.get("tier", "pro") if valid else "free"

    def info(self) -> dict:
        defaults: dict = {
            "license_key": "",
            "activated_at": "",
            "tier": "free",
            "email": "",
            "team_vault_url": "",
            "team_vault_token": "",
        }
        data = {**defaults, **self._load()}
        key = data.get("license_key", "")
        if key:
            valid, _, payload = validate_key(key)
            if valid:
                data.update(payload)
            else:
                data["tier"] = "free"
        return data

    def activate(self, key: str, email: str = "") -> tuple[bool, str]:
        """Validate and store a license key. Returns (ok, error_msg)."""
        valid, err, payload = validate_key(key)
        if not valid:
            return False, err
        existing = self._load()
        existing.update({
            "license_key": key.strip(),
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "tier": payload["tier"],
            "email": email,
        })
        self._save(existing)
        return True, ""

    def deactivate(self) -> None:
        if _PRO_FILE.exists():
            _PRO_FILE.unlink()

    def set_team_vault(self, url: str, token: str) -> None:
        data = self._load()
        data["team_vault_url"] = url.rstrip("/")
        data["team_vault_token"] = token
        self._save(data)

    def _load(self) -> dict:
        if not _PRO_FILE.exists():
            return {}
        try:
            return json.loads(_PRO_FILE.read_text())
        except Exception:
            return {}

    def _save(self, data: dict) -> None:
        _PRO_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PRO_FILE.write_text(json.dumps(data, indent=2))
