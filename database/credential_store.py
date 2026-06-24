"""
Credential storage and retrieval with encryption
"""
from typing import Dict
from pathlib import Path
from crypto.encryption import encrypt_data, decrypt_data
from crypto.key_derivation import derive_encryption_key
from models.credential import Credential, credentials_to_storage_format, credentials_from_storage_format
from config import CREDENTIALS_FILE


class CredentialStore:
    """Manages encrypted credential storage."""

    @staticmethod
    def load_credentials(master_password: str, salt: bytes) -> Dict[str, Credential]:
        """
        Load and decrypt credentials from encrypted file.

        Args:
            master_password: Master password for key derivation
            salt: Salt for key derivation

        Returns:
            Dictionary mapping service_name to Credential

        Raises:
            FileNotFoundError: If credentials file doesn't exist (returns empty dict)
            cryptography.fernet.InvalidToken: If decryption fails
        """
        if not CREDENTIALS_FILE.exists():
            return {}

        # Derive encryption key
        encryption_key = derive_encryption_key(master_password, salt)

        # Load and decrypt
        with open(CREDENTIALS_FILE, 'rb') as f:
            encrypted_data = f.read()

        storage_data = decrypt_data(encrypted_data, encryption_key)
        return credentials_from_storage_format(storage_data)

    @staticmethod
    def save_credentials(credentials: Dict[str, Credential], master_password: str, salt: bytes) -> None:
        """
        Encrypt and save credentials to file.

        Args:
            credentials: Dictionary mapping service_name to Credential
            master_password: Master password for key derivation
            salt: Salt for key derivation
        """
        # Derive encryption key
        encryption_key = derive_encryption_key(master_password, salt)

        # Convert to storage format and encrypt
        storage_data = credentials_to_storage_format(credentials)
        encrypted_data = encrypt_data(storage_data, encryption_key)

        # Ensure directory exists
        CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Write to file
        with open(CREDENTIALS_FILE, 'wb') as f:
            f.write(encrypted_data)

    @staticmethod
    def add_credential(credential: Credential, credentials: Dict[str, Credential],
                      master_password: str, salt: bytes) -> Dict[str, Credential]:
        """
        Add a new credential and save.

        Args:
            credential: The credential to add
            credentials: Current credentials dictionary
            master_password: Master password for encryption
            salt: Salt for key derivation

        Returns:
            Updated credentials dictionary

        Raises:
            ValueError: If service_name already exists
        """
        if credential.service_name in credentials:
            raise ValueError(f"Credential for '{credential.service_name}' already exists")

        credentials[credential.service_name] = credential
        CredentialStore.save_credentials(credentials, master_password, salt)
        return credentials

    @staticmethod
    def update_credential(credential: Credential, old_service_name: str,
                         credentials: Dict[str, Credential],
                         master_password: str, salt: bytes) -> Dict[str, Credential]:
        """
        Update an existing credential and save.

        Args:
            credential: The updated credential
            old_service_name: The original service name (may have changed)
            credentials: Current credentials dictionary
            master_password: Master password for encryption
            salt: Salt for key derivation

        Returns:
            Updated credentials dictionary

        Raises:
            ValueError: If old service doesn't exist or new name conflicts
        """
        if old_service_name not in credentials:
            raise ValueError(f"Credential '{old_service_name}' not found")

        # If service name changed, check for conflicts
        if credential.service_name != old_service_name:
            if credential.service_name in credentials:
                raise ValueError(f"Credential for '{credential.service_name}' already exists")
            # Remove old entry
            del credentials[old_service_name]

        credentials[credential.service_name] = credential
        CredentialStore.save_credentials(credentials, master_password, salt)
        return credentials

    @staticmethod
    def delete_credential(service_name: str, credentials: Dict[str, Credential],
                         master_password: str, salt: bytes) -> Dict[str, Credential]:
        """
        Delete a credential and save.

        Args:
            service_name: Service name to delete
            credentials: Current credentials dictionary
            master_password: Master password for encryption
            salt: Salt for key derivation

        Returns:
            Updated credentials dictionary

        Raises:
            ValueError: If service doesn't exist
        """
        if service_name not in credentials:
            raise ValueError(f"Credential '{service_name}' not found")

        del credentials[service_name]
        CredentialStore.save_credentials(credentials, master_password, salt)
        return credentials
