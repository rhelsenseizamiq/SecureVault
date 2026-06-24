"""
Master password hashing using PBKDF2-HMAC-SHA256
"""
import os
import hmac
import hashlib
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from config import PBKDF2_ITERATIONS, SALT_LENGTH


def hash_master_password(password: str, salt: bytes = None) -> tuple[bytes, bytes]:
    """
    Hash a master password using PBKDF2-HMAC-SHA256.

    Args:
        password: The master password to hash
        salt: Optional salt (generates new random salt if not provided)

    Returns:
        Tuple of (hash, salt) where both are bytes
    """
    if salt is None:
        salt = os.urandom(SALT_LENGTH)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,  # 32 bytes = 256 bits
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
        backend=default_backend()
    )

    password_hash = kdf.derive(password.encode('utf-8'))
    return password_hash, salt


def verify_master_password(password: str, stored_hash: bytes, salt: bytes) -> bool:
    """
    Verify a master password against a stored hash using constant-time comparison.

    Args:
        password: The password to verify
        stored_hash: The stored hash to compare against
        salt: The salt used to create the stored hash

    Returns:
        True if password matches, False otherwise
    """
    computed_hash, _ = hash_master_password(password, salt)
    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(computed_hash, stored_hash)
