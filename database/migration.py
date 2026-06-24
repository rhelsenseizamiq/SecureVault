"""
Migration from legacy key.key system to master password system
"""
import os
import shutil
from pathlib import Path
from typing import Optional
from crypto.encryption import decrypt_data, encrypt_data
from crypto.key_derivation import derive_encryption_key
from database.master_password_store import MasterPasswordStore
from config import LEGACY_KEY_FILE, LEGACY_STORE_FILE, CREDENTIALS_FILE


class LegacyMigration:
    """Handles migration from old key.key system to master password."""

    @staticmethod
    def needs_migration() -> bool:
        """
        Check if migration is needed.

        Returns:
            True if legacy key.key exists but master password not set
        """
        has_legacy_key = os.path.exists(LEGACY_KEY_FILE)
        has_master_password = MasterPasswordStore.exists()

        return has_legacy_key and not has_master_password

    @staticmethod
    def get_legacy_credentials() -> Optional[dict]:
        """
        Load credentials using legacy key.key file.

        Returns:
            Dictionary of credentials in old format, or None if files don't exist
        """
        if not os.path.exists(LEGACY_KEY_FILE):
            return None

        if not os.path.exists(LEGACY_STORE_FILE):
            return {}

        # Load legacy key
        with open(LEGACY_KEY_FILE, 'rb') as f:
            legacy_key = f.read()

        # Load and decrypt credentials
        with open(LEGACY_STORE_FILE, 'rb') as f:
            encrypted_data = f.read()

        return decrypt_data(encrypted_data, legacy_key)

    @staticmethod
    def migrate_to_master_password(master_password: str) -> tuple[bool, str]:
        """
        Migrate from legacy key.key system to master password.

        Steps:
        1. Load credentials with legacy key
        2. Create master password
        3. Re-encrypt credentials with new key
        4. Backup legacy key.key
        5. Move credentials to new location

        Args:
            master_password: New master password to use

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Step 1: Load legacy credentials
            legacy_credentials = LegacyMigration.get_legacy_credentials()
            if legacy_credentials is None:
                return False, "Legacy key.key file not found"

            # Step 2: Create master password
            salt = MasterPasswordStore.create_master_password(master_password)

            # Step 3: Re-encrypt credentials with new key
            if legacy_credentials:  # Only if there are credentials
                new_key = derive_encryption_key(master_password, salt)
                encrypted_data = encrypt_data(legacy_credentials, new_key)

                # Ensure new directory exists
                CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)

                # Write to new location
                with open(CREDENTIALS_FILE, 'wb') as f:
                    f.write(encrypted_data)

            # Step 4: Backup legacy key
            backup_path = LEGACY_KEY_FILE + ".old"
            shutil.copy2(LEGACY_KEY_FILE, backup_path)

            # Step 5: Clean up legacy files (optional - keep for safety)
            # We'll just rename instead of deleting
            if os.path.exists(LEGACY_STORE_FILE):
                shutil.move(LEGACY_STORE_FILE, LEGACY_STORE_FILE + ".old")

            return True, f"Migration successful! {len(legacy_credentials)} credentials migrated.\n" \
                        f"Legacy key backed up to {backup_path}"

        except Exception as e:
            return False, f"Migration failed: {str(e)}"

    @staticmethod
    def cleanup_legacy_files() -> None:
        """
        Clean up legacy backup files after successful migration.
        Only call this after user confirms migration worked.
        """
        backup_files = [
            LEGACY_KEY_FILE + ".old",
            LEGACY_STORE_FILE + ".old"
        ]

        for backup_file in backup_files:
            if os.path.exists(backup_file):
                os.remove(backup_file)
