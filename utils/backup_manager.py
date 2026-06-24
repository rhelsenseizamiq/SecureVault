"""
Backup manager for exporting and importing credentials
"""
import json
import base64
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Dict, Tuple, Optional
from models.credential import Credential
from crypto.encryption import encrypt_data, decrypt_data
from crypto.key_derivation import derive_encryption_key


class BackupManager:
    """Manages credential backup and restore operations."""

    BACKUP_VERSION = "1.1"
    BACKUP_EXTENSION = ".svbackup"

    @staticmethod
    def export_credentials(
        credentials: Dict[str, Credential],
        master_password: str,
        salt: bytes,
        parent_window=None
    ) -> Tuple[bool, str]:
        if not credentials:
            return False, "No credentials to export."

        try:
            filename = filedialog.asksaveasfilename(
                parent=parent_window,
                title="Export Credentials",
                defaultextension=BackupManager.BACKUP_EXTENSION,
                filetypes=[
                    ("SecureVault Backup", f"*{BackupManager.BACKUP_EXTENSION}"),
                    ("All Files", "*.*")
                ],
                initialfile="securevault_backup"
            )

            if not filename:
                return False, "Export cancelled."

            backup_data = {
                "version": BackupManager.BACKUP_VERSION,
                "app_name": "SecureVault",
                "credentials": {
                    service: {
                        "service_name": cred.service_name,
                        "username": cred.username,
                        "password": cred.password,
                        "website_url": cred.website_url
                    }
                    for service, cred in credentials.items()
                }
            }

            # Derive key then encrypt
            encryption_key = derive_encryption_key(master_password, salt)
            encrypted = encrypt_data(backup_data, encryption_key)
            encoded = base64.b64encode(encrypted).decode('utf-8')

            with open(filename, 'w') as f:
                f.write(encoded)

            return True, f"Successfully exported {len(credentials)} credentials to:\n{filename}"

        except Exception as e:
            return False, f"Export failed: {str(e)}"

    @staticmethod
    def import_credentials(
        master_password: str,
        salt: bytes,
        parent_window=None
    ) -> Tuple[bool, Optional[Dict[str, Credential]], str]:
        try:
            filename = filedialog.askopenfilename(
                parent=parent_window,
                title="Import Credentials",
                filetypes=[
                    ("SecureVault Backup", f"*{BackupManager.BACKUP_EXTENSION}"),
                    ("All Files", "*.*")
                ]
            )

            if not filename:
                return False, None, "Import cancelled."

            with open(filename, 'r') as f:
                encoded = f.read()

            encrypted = base64.b64decode(encoded.encode('utf-8'))

            try:
                encryption_key = derive_encryption_key(master_password, salt)
                backup_data = decrypt_data(encrypted, encryption_key)
            except Exception:
                return False, None, "Failed to decrypt backup. Incorrect master password or corrupted file."

            if not isinstance(backup_data, dict) or 'credentials' not in backup_data:
                return False, None, "Invalid backup file format."

            imported_credentials = {}
            for service_name, cred_data in backup_data['credentials'].items():
                imported_credentials[service_name] = Credential(
                    service_name=cred_data['service_name'],
                    username=cred_data['username'],
                    password=cred_data['password'],
                    website_url=cred_data.get('website_url', '')
                )

            count = len(imported_credentials)
            return True, imported_credentials, f"Successfully imported {count} credentials from backup."

        except FileNotFoundError:
            return False, None, "Backup file not found."
        except Exception as e:
            return False, None, f"Import failed: {str(e)}"

    @staticmethod
    def merge_credentials(
        existing: Dict[str, Credential],
        imported: Dict[str, Credential],
        parent_window=None
    ) -> Tuple[Dict[str, Credential], str]:
        conflicts = set(existing.keys()) & set(imported.keys())

        if conflicts:
            message = (
                f"Found {len(conflicts)} duplicate(s):\n\n"
                f"{', '.join(list(conflicts)[:5])}"
                f"{'...' if len(conflicts) > 5 else ''}\n\n"
                f"Yes = overwrite existing\n"
                f"No  = keep existing, skip duplicates\n"
                f"Cancel = abort import"
            )
            response = messagebox.askyesnocancel(
                "Duplicate Credentials Found", message, parent=parent_window
            )

            if response is None:
                return existing, "Import cancelled."
            elif response:
                merged = {**existing, **imported}
                return merged, f"Imported {len(imported)} credentials (overwrote {len(conflicts)} duplicates)."
            else:
                merged = {**imported, **existing}
                new_count = len(imported) - len(conflicts)
                return merged, f"Imported {new_count} new credentials (skipped {len(conflicts)} duplicates)."
        else:
            merged = {**existing, **imported}
            return merged, f"Imported {len(imported)} new credentials."
