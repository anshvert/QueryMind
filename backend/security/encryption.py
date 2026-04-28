"""
QueryMind — AES-256 Credential Encryption
Encrypts/decrypts datasource credentials at rest.
"""
import base64
import json
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from backend.core.config import settings


def _get_key() -> bytes:
    """Derive 32-byte AES key from config."""
    key = settings.CREDENTIAL_ENCRYPTION_KEY
    if not key:
        # In dev with no key set, generate a random one (not persistent across restarts!)
        return os.urandom(32)
    raw = base64.b64decode(key)
    assert len(raw) == 32, "CREDENTIAL_ENCRYPTION_KEY must be a 32-byte base64-encoded string"
    return raw


def encrypt_credentials(credentials: dict) -> str:
    """Encrypt credentials dict to base64 string."""
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    plaintext = json.dumps(credentials).encode()
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    # Store nonce + ciphertext together, base64-encoded
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt_credentials(encrypted: str) -> dict:
    """Decrypt base64 string back to credentials dict."""
    key = _get_key()
    aesgcm = AESGCM(key)
    raw = base64.b64decode(encrypted)
    nonce, ciphertext = raw[:12], raw[12:]
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return json.loads(plaintext)
