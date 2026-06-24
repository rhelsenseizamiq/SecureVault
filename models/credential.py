"""
Credential data model
"""
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Credential:
    """
    Represents a single credential entry (service, username, password, optional URL).
    Extra fields (notes, tags, favorite, last_used) default safely so older
    vault files without them keep loading unchanged.
    """
    service_name: str
    username: str
    password: str
    website_url: str = ""
    notes: str = ""
    tags: List[str] = field(default_factory=list)
    favorite: bool = False
    last_used: float = 0.0          # epoch seconds; 0 = never used

    def to_dict(self) -> dict:
        """Convert to dictionary format."""
        return {
            'username': self.username,
            'password': self.password,
            'website_url': self.website_url,
            'notes': self.notes,
            'tags': list(self.tags),
            'favorite': self.favorite,
            'last_used': self.last_used,
        }

    @classmethod
    def from_dict(cls, service_name: str, data: dict) -> 'Credential':
        """Create Credential from dictionary format (backward-compatible)."""
        return cls(
            service_name=service_name,
            username=data['username'],
            password=data['password'],
            website_url=data.get('website_url', ''),
            notes=data.get('notes', ''),
            tags=list(data.get('tags', []) or []),
            favorite=bool(data.get('favorite', False)),
            last_used=float(data.get('last_used', 0.0) or 0.0),
        )


def credentials_to_storage_format(credentials: Dict[str, Credential]) -> dict:
    """
    Convert credentials dictionary to storage format.

    Args:
        credentials: Dict mapping service_name to Credential

    Returns:
        Dict in format {service_name: {username: str, password: str}}
    """
    return {
        service_name: cred.to_dict()
        for service_name, cred in credentials.items()
    }


def credentials_from_storage_format(storage_data: dict) -> Dict[str, Credential]:
    """
    Convert storage format to credentials dictionary.

    Args:
        storage_data: Dict in format {service_name: {username: str, password: str}}

    Returns:
        Dict mapping service_name to Credential
    """
    return {
        service_name: Credential.from_dict(service_name, data)
        for service_name, data in storage_data.items()
    }
