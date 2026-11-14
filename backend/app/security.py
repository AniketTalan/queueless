import hashlib
import secrets


def new_api_key() -> str:
    """Returned to the business exactly once; only its hash is stored."""
    return "ql_" + secrets.token_urlsafe(32)


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def new_code() -> str:
    """Short unguessable code used in QR links and customer token URLs."""
    return secrets.token_urlsafe(6)
