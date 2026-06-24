"""
Derive Fernet-compatible encryption key from master password
"""
import base64
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from config import PBKDF2_ITERATIONS, KEY_LENGTH


def derive_encryption_key(master_password: str, salt: bytes) -> bytes:
    """
    Derive a Fernet-compatible encryption key from a master password.

    Uses PBKDF2-HMAC-SHA256 to derive a 32-byte key, then base64url-encodes it
    for Fernet compatibility.

    Args:
        master_password: The master password
        salt: Salt for key derivation (must be same salt used for password hashing)

    Returns:
        Base64url-encoded 32-byte key compatible with Fernet
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_LENGTH,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
        backend=default_backend()
    )

    # Derive raw key bytes
    raw_key = kdf.derive(master_password.encode('utf-8'))

    # Fernet requires base64url-encoded key
    return base64.urlsafe_b64encode(raw_key)
