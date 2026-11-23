"""TOTP (RFC 6238) with the standard library only: HMAC-SHA1, 30 s step, 6 digits."""
import base64
import hashlib
import hmac
import secrets
import struct
import time


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = mac[-1] & 0x0F
    n = (struct.unpack(">I", mac[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{n:06d}"


def at(secret: str, ts: float | None = None) -> str:
    return _code(secret, int((ts if ts is not None else time.time()) // 30))


def verify(secret: str, code: str, ts: float | None = None, window: int = 1) -> bool:
    code = (code or "").strip().replace(" ", "")
    if len(code) != 6 or not code.isdigit():
        return False
    c = int((ts if ts is not None else time.time()) // 30)
    return any(hmac.compare_digest(_code(secret, c + d), code) for d in range(-window, window + 1))


def uri(secret: str, account: str, issuer: str = "PROPERM") -> str:
    from urllib.parse import quote
    return f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret}&issuer={quote(issuer)}&digits=6&period=30"


def new_backup_codes(n: int = 8) -> list[str]:
    return [f"{secrets.randbelow(10**8):08d}" for _ in range(n)]


def hash_code(c: str) -> str:
    return hashlib.sha256(c.encode()).hexdigest()
