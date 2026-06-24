"""
Fernet encryption/decryption functions
"""
from cryptography.fernet import Fernet
import json


def encrypt_data(data_dict: dict, key: bytes) -> bytes:
    """
    Encrypt a dictionary to bytes using Fernet symmetric encryption.

    Args:
        data_dict: Dictionary to encrypt
        key: Fernet encryption key (32 bytes, base64url-encoded)

    Returns:
        Encrypted bytes
    """
    f = Fernet(key)
    json_data = json.dumps(data_dict).encode('utf-8')
    return f.encrypt(json_data)


def decrypt_data(encrypted_bytes: bytes, key: bytes) -> dict:
    """
    Decrypt Fernet-encrypted bytes back to a dictionary.

    Args:
        encrypted_bytes: Encrypted data
        key: Fernet decryption key (32 bytes, base64url-encoded)

    Returns:
        Decrypted dictionary

    Raises:
        cryptography.fernet.InvalidToken: If decryption fails (wrong key or corrupted data)
    """
    f = Fernet(key)
    decrypted_json = f.decrypt(encrypted_bytes).decode('utf-8')
    return json.loads(decrypted_json)
