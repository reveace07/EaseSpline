"""
EaseSpline — License Activation
Validates Gumroad / Payhip keys, stores machine-tied activation locally.
"""

import os
import sys
import json
import hashlib
import platform
import uuid
import ssl
import urllib.request
import urllib.parse
import urllib.error
from datetime import date

def _ssl_context():
    """Return an SSL context with certifi certs if available, else default."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    # macOS: default context often fails without certifi; use unverified
    if platform.system() == "Darwin":
        return ssl._create_unverified_context()
    try:
        ctx = ssl.create_default_context()
        return ctx
    except Exception:
        pass
    # Last resort: unverified (still encrypted, just no cert check)
    ctx = ssl._create_unverified_context()
    return ctx

# ── Constants ─────────────────────────────────────────────────────────────────

GUMROAD_PERMALINK    = "EaseSpline"
PAYHIP_PRODUCT       = "VvfEb"
PAYHIP_PRODUCT_SECRET = "prod_sk_VvfEb_410b51801de0464a28df579ae0cbea198bb7c768"
MAX_ACTIVATIONS      = 3
RECHECK_DAYS         = 7

_APPDATA        = os.environ.get("APPDATA", os.path.expanduser("~"))
ACTIVATION_FILE = os.path.join(_APPDATA, "ESpline", "activation.json")

# ── Machine fingerprint ───────────────────────────────────────────────────────

def get_machine_id() -> str:
    raw = f"{platform.node()}|{uuid.getnode()}|{platform.processor()}|{platform.machine()}"
    return hashlib.sha256(raw.encode()).hexdigest()

# ── Persistence ───────────────────────────────────────────────────────────────

def _load() -> dict | None:
    try:
        with open(ACTIVATION_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return None


def _save(data: dict):
    os.makedirs(os.path.dirname(ACTIVATION_FILE), exist_ok=True)
    with open(ACTIVATION_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ── API calls ─────────────────────────────────────────────────────────────────

def _post(url: str, params: dict) -> dict:
    data = urllib.parse.urlencode(params).encode()
    req  = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=10, context=_ssl_context()) as resp:
        return json.loads(resp.read().decode())


def _verify_gumroad(key: str) -> tuple[bool, str]:
    try:
        r = _post(
            "https://api.gumroad.com/v2/licenses/verify",
            {
                "product_permalink": GUMROAD_PERMALINK,
                "product_id":        "OnFvGGH54gO6rK3bwAg29g==",
                "license_key":       key.strip(),
                "increment_uses_count": "true",
            }
        )
        if r.get("success"):
            return True, "ok"
        return False, r.get("message", "Invalid key")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
            return False, body.get("message", "Invalid license key.")
        except Exception:
            return False, f"Store error ({e.code})."
    except urllib.error.URLError:
        return False, "offline"
    except Exception as e:
        return False, str(e)


def _verify_payhip(key: str) -> tuple[bool, str]:
    if not PAYHIP_PRODUCT_SECRET:
        return False, "offline"   # not configured yet
    try:
        url = "https://payhip.com/api/v2/license/verify?" + urllib.parse.urlencode({
            "license_key": key.strip(),
        })
        req = urllib.request.Request(url, method="GET")
        req.add_header("product-secret-key", PAYHIP_PRODUCT_SECRET)
        req.add_header("User-Agent", "Mozilla/5.0")
        with urllib.request.urlopen(req, timeout=10, context=_ssl_context()) as resp:
            r = json.loads(resp.read().decode())
        data = r.get("data", {})
        if data and data.get("enabled"):
            return True, "ok"
        return False, "Invalid or disabled license key."
    except urllib.error.HTTPError as e:
        if e.code == 400:
            return False, "Invalid license key."
        try:
            body = json.loads(e.read().decode())
            return False, body.get("message", "Invalid license key.")
        except Exception:
            return False, f"Store error ({e.code})."
    except urllib.error.URLError:
        return False, "offline"
    except Exception as e:
        return False, str(e)

# ── Public API ────────────────────────────────────────────────────────────────

def activate(key: str) -> tuple[bool, str]:
    """
    Validate key against Gumroad then Payhip.
    On success, writes activation.json with machine fingerprint.
    Returns (success, message).
    """
    key = key.strip()
    if not key:
        return False, "Please enter your license key."

    print(f"[ACT] Trying Gumroad with key: {key[:8]}...")
    ok, msg = _verify_gumroad(key)
    print(f"[ACT] Gumroad result: ok={ok}, msg={msg}")
    source  = "gumroad"

    if not ok:
        if msg == "offline":
            return False, "No internet connection. Please connect to activate."
        print(f"[ACT] Trying Payhip...")
        ok2, msg2 = _verify_payhip(key)
        print(f"[ACT] Payhip result: ok={ok2}, msg={msg2}")
        if ok2:
            ok, msg, source = True, "ok", "payhip"
        elif msg2 != "offline":
            msg = msg2

    if ok:
        _save({
            "key":          key,
            "source":       source,
            "machine_id":   get_machine_id(),
            "activated_at": date.today().isoformat(),
            "last_check":   date.today().isoformat(),
        })
        return True, "Activated successfully!"

    print(f"[ACT] Final failure: {msg}")
    return False, msg or "Invalid license key."


def check_activation() -> tuple[bool, str]:
    """
    Called on every launch.
    Returns (is_valid, reason).
    reason is one of: "ok", "not_activated", "wrong_machine", "key_revoked"
    """
    data = _load()

    if not data:
        return False, "not_activated"

    # Machine lock — folder copied to another PC
    if data.get("machine_id") != get_machine_id():
        return False, "wrong_machine"

    # Periodic re-check against store API
    needs_recheck = True
    try:
        last_date     = date.fromisoformat(data.get("last_check", ""))
        needs_recheck = (date.today() - last_date).days >= RECHECK_DAYS
    except Exception:
        pass

    if needs_recheck:
        key    = data.get("key", "")
        source = data.get("source", "gumroad")
        ok, msg = (_verify_payhip if source == "payhip" else _verify_gumroad)(key)

        if ok:
            data["last_check"] = date.today().isoformat()
            _save(data)
        elif msg == "offline":
            pass  # grace — allow offline use
        else:
            # Key refunded / revoked
            try:
                os.remove(ACTIVATION_FILE)
            except Exception:
                pass
            return False, "key_revoked"

    return True, "ok"


def deactivate():
    """Remove local activation (for support/testing)."""
    try:
        os.remove(ACTIVATION_FILE)
    except Exception:
        pass
