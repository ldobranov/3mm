"""Core-issued guest proof, scoped to one reviewed form and process generation."""
import hashlib
import hmac
import json
import secrets
import time

from packages.protocol.public_forms import GUEST_COOKIE, GUEST_TTL_SECONDS, PublicFormGuest


_KEY = secrets.token_bytes(32)


def _mac(scope, guest_id, expires_at):
    body = json.dumps(['3mm:public-form-guest:v1', *scope, guest_id, expires_at],
                      ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return hmac.new(_KEY, body, hashlib.sha256).hexdigest()


def issue(scope):
    guest = PublicFormGuest(secrets.token_hex(16), int(time.time()) + GUEST_TTL_SECONDS)
    signature = _mac(scope, guest.guest_id, guest.expires_at)
    return guest, f'{guest.guest_id}.{guest.expires_at}.{signature}'


def resolve(scope, token):
    match = GUEST_COOKIE.fullmatch(token) if isinstance(token, str) else None
    if match is None:
        return None
    guest_id, raw_expiry, signature = match.groups()
    expires_at = int(raw_expiry)
    now = int(time.time())
    if not now < expires_at <= now + GUEST_TTL_SECONDS:
        return None
    if not hmac.compare_digest(signature, _mac(scope, guest_id, expires_at)):
        return None
    return PublicFormGuest(guest_id, expires_at)
