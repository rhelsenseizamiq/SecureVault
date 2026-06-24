"""
Master password storage and verification
"""
import json
from pathlib import Path
from typing import Optional
from crypto.password_hashing import hash_master_password, verify_master_password
from crypto.key_derivation import derive_encryption_key
from config import MASTER_PASSWORD_FILE


class MasterPasswordStore:
    """Manages master password storage and verification."""

    VERSION = 1  # For future format migrations

    @staticmethod
    def exists() -> bool:
        """Check if master password file exists."""
        return MASTER_PASSWORD_FILE.exists()

    @staticmethod
    def create_master_password(password: str) -> bytes:
        """
        Create and store a new master password.

        Args:
            password: The master password to store

        Returns:
            The salt used (needed for encryption key derivation)

        Raises:
            FileExistsError: If master password already exists
        """
        if MasterPasswordStore.exists():
            raise FileExistsError("Master password already exists")

        # Generate hash and salt
        password_hash, salt = hash_master_password(password)

        # Store to file
        data = {
            'version': MasterPasswordStore.VERSION,
            'hash': password_hash.hex(),
            'salt': salt.hex()
        }

        MASTER_PASSWORD_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(MASTER_PASSWORD_FILE, 'w') as f:
            json.dump(data, f)

        return salt

    @staticmethod
    def verify_master_password(password: str) -> Optional[bytes]:
        """
        Verify master password and return salt if correct.

        Args:
            password: The password to verify

        Returns:
            Salt (bytes) if password is correct, None otherwise

        Raises:
            FileNotFoundError: If master password file doesn't exist
        """
        if not MasterPasswordStore.exists():
            raise FileNotFoundError("Master password not set")

        # Load stored data
        with open(MASTER_PASSWORD_FILE, 'r') as f:
            data = json.load(f)

        stored_hash = bytes.fromhex(data['hash'])
        salt = bytes.fromhex(data['salt'])

        # Verify password
        if verify_master_password(password, stored_hash, salt):
            return salt
        return None

    @staticmethod
    def change_master_password(old_password: str, new_password: str) -> bytes:
        """
        Change the master password.

        Note: Caller is responsible for re-encrypting credentials with new key!

        Args:
            old_password: Current master password
            new_password: New master password

        Returns:
            New salt (needed for re-encryption)

        Raises:
            ValueError: If old password is incorrect
            FileNotFoundError: If master password not set
        """
        # Verify old password
        old_salt = MasterPasswordStore.verify_master_password(old_password)
        if old_salt is None:
            raise ValueError("Incorrect current password")

        # Generate new hash and salt
        new_hash, new_salt = hash_master_password(new_password)

        # Update file
        data = {
            'version': MasterPasswordStore.VERSION,
            'hash': new_hash.hex(),
            'salt': new_salt.hex()
        }

        with open(MASTER_PASSWORD_FILE, 'w') as f:
            json.dump(data, f)

        return new_salt

    @staticmethod
    def get_salt() -> bytes:
        """
        Get the salt without verifying password.
        Used for migration scenarios.

        Returns:
            The stored salt

        Raises:
            FileNotFoundError: If master password file doesn't exist
        """
        if not MasterPasswordStore.exists():
            raise FileNotFoundError("Master password not set")

        with open(MASTER_PASSWORD_FILE, 'r') as f:
            data = json.load(f)

        return bytes.fromhex(data['salt'])
