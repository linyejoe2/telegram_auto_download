"""
library/auth.py — Password login for the web library (it can be reached from the internet).

The password is stored only as a PBKDF2 hash (WEB_PASSWORD_HASH in .env); sessions are HMAC-signed
cookies (WEB_SECRET, generated once). Wrong passwords are rate limited per client address.
"""

import base64
import hashlib
import hmac
import os
import secrets
import time
from typing import Dict, Optional, Tuple

PBKDF2_ITERATIONS = 310_000
SESSION_SECONDS = 30 * 24 * 3600
MAX_FAILURES = 5          # wrong passwords before a client is locked out
LOCKOUT_SECONDS = 15 * 60


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, digest = stored.split('$')
        if algo != 'pbkdf2_sha256':
            return False
        check = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(check.hex(), digest)
    except Exception:
        return False


def new_secret() -> str:
    return secrets.token_hex(32)


class Sessions:
    def __init__(self, secret: str, password_hash_version: str):
        # the hash is part of the key: changing the password logs every session out
        self._key = hashlib.sha256((secret + '|' + password_hash_version).encode('utf-8')).digest()
        self._failures: Dict[str, Tuple[int, float]] = {}   # client -> (count, first failure time)

    def issue(self) -> str:
        expires = int(time.time()) + SESSION_SECONDS
        payload = f"{expires}.{secrets.token_hex(8)}"
        sig = hmac.new(self._key, payload.encode('ascii'), hashlib.sha256).digest()
        return payload + '.' + base64.urlsafe_b64encode(sig).decode('ascii').rstrip('=')

    def valid(self, token: Optional[str]) -> bool:
        if not token or token.count('.') != 2:
            return False
        expires, nonce, sig = token.split('.')
        payload = f"{expires}.{nonce}"
        expected = base64.urlsafe_b64encode(
            hmac.new(self._key, payload.encode('ascii'), hashlib.sha256).digest()).decode('ascii').rstrip('=')
        return hmac.compare_digest(sig, expected) and expires.isdigit() and int(expires) > time.time()

    # ── brute-force protection ──

    def locked_for(self, client: str) -> int:
        """Seconds this client still has to wait, 0 if it may try."""
        count, since = self._failures.get(client, (0, 0.0))
        if count >= MAX_FAILURES:
            left = int(since + LOCKOUT_SECONDS - time.time())
            if left > 0:
                return left
            self._failures.pop(client, None)
        return 0

    def failed(self, client: str):
        count, since = self._failures.get(client, (0, time.time()))
        if time.time() - since > LOCKOUT_SECONDS:
            count, since = 0, time.time()
        self._failures[client] = (count + 1, since)

    def succeeded(self, client: str):
        self._failures.pop(client, None)
