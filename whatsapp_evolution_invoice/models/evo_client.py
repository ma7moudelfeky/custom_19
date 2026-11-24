"""Thin helper around the Evolution API v2 REST endpoints + phone normalisation."""
import logging
import re

import requests

_logger = logging.getLogger(__name__)

TIMEOUT = 60


class EvolutionError(Exception):
    """Raised for any failure talking to Evolution API (message is user-readable)."""


def normalize_phone(raw, country_code="20"):
    """Return an international number with digits only (e.g. 201001234567) or False.

    Rules (Egypt by default):
      +201001234567 / 00201001234567 / 201001234567 -> 201001234567
      01001234567  (11 digits, local mobile)        -> 201001234567
      1001234567   (10 digits, leading 0 dropped)   -> 201001234567
    """
    if not raw:
        return False
    cc = re.sub(r"\D", "", country_code or "20")
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return False
    if digits.startswith("00"):
        digits = digits[2:]
    elif cc == "20" and digits.startswith("01") and len(digits) == 11:
        digits = cc + digits[1:]
    elif cc == "20" and digits.startswith("1") and len(digits) == 10:
        digits = cc + digits
    elif digits.startswith("0") and not raw.strip().startswith("+"):
        digits = cc + digits[1:]
    # Egyptian mobiles: 20 + 1[0125] + 8 digits = 12 digits
    if digits.startswith("201") and len(digits) != 12:
        return False
    if len(digits) < 8 or len(digits) > 15:
        return False
    return digits


def media_type_for(mimetype):
    mimetype = mimetype or ""
    if mimetype.startswith("image/"):
        return "image"
    if mimetype.startswith("video/"):
        return "video"
    return "document"


class EvolutionClient:
    def __init__(self, url, api_key, instance):
        if not (url and api_key and instance):
            raise EvolutionError("Evolution API is not configured (URL / API key / instance).")
        self.url = url.rstrip("/")
        self.instance = instance
        self.headers = {"apikey": api_key, "Content-Type": "application/json"}

    def _request(self, method, path, payload=None):
        try:
            resp = requests.request(
                method, f"{self.url}{path}", headers=self.headers, json=payload, timeout=TIMEOUT
            )
        except requests.RequestException as exc:
            raise EvolutionError(f"Cannot reach Evolution API: {exc}") from exc
        if resp.status_code >= 400:
            raise EvolutionError(f"Evolution API error {resp.status_code}: {resp.text[:500]}")
        try:
            return resp.json()
        except ValueError:
            return {}

    def connection_state(self):
        data = self._request("GET", f"/instance/connectionState/{self.instance}")
        return (data.get("instance") or {}).get("state") or data.get("state") or "unknown"

    def has_whatsapp(self, number):
        """True / False, or None when the check itself could not be done."""
        try:
            data = self._request(
                "POST", f"/chat/whatsappNumbers/{self.instance}", {"numbers": [number]}
            )
        except EvolutionError as exc:
            _logger.warning("WhatsApp number check failed for %s: %s", number, exc)
            return None
        if isinstance(data, list) and data:
            return bool(data[0].get("exists"))
        return None

    def send_text(self, number, text, typing_delay_ms=0):
        payload = {"number": number, "text": text}
        if typing_delay_ms:
            payload["delay"] = int(typing_delay_ms)
        data = self._request("POST", f"/message/sendText/{self.instance}", payload)
        return (data.get("key") or {}).get("id") or ""

    def send_media(self, number, b64, file_name, mimetype, caption="", typing_delay_ms=0):
        payload = {
            "number": number,
            "mediatype": media_type_for(mimetype),
            "mimetype": mimetype or "application/octet-stream",
            "media": b64,
            "fileName": file_name,
            "caption": caption or "",
        }
        if typing_delay_ms:
            payload["delay"] = int(typing_delay_ms)
        data = self._request("POST", f"/message/sendMedia/{self.instance}", payload)
        return (data.get("key") or {}).get("id") or ""
