"""
Input validation utilities
"""
import re
from typing import Tuple, Set
from config import MIN_PASSWORD_LENGTH, MIN_MASTER_PASSWORD_LENGTH


def validate_password_strength(password: str, is_master: bool = False) -> Tuple[bool, str]:
    """
    Validate password meets minimum requirements.

    Args:
        password: Password to validate
        is_master: True if this is a master password (stricter requirements)

    Returns:
        Tuple of (valid: bool, error_message: str)
    """
    min_length = MIN_MASTER_PASSWORD_LENGTH if is_master else MIN_PASSWORD_LENGTH

    if not password:
        return False, "Password cannot be empty"

    if len(password) < min_length:
        return False, f"Password must be at least {min_length} characters"

    # Master password requires more complexity
    if is_master:
        has_upper = bool(re.search(r'[A-Z]', password))
        has_lower = bool(re.search(r'[a-z]', password))
        has_digit = bool(re.search(r'\d', password))

        if not (has_upper and has_lower and has_digit):
            return False, "Master password must contain uppercase, lowercase, and digits"

    return True, ""


def validate_service_name(name: str, existing_names: Set[str],
                         allow_existing: bool = False) -> Tuple[bool, str]:
    """
    Validate service name.

    Args:
        name: Service name to validate
        existing_names: Set of existing service names
        allow_existing: If True, allow duplicate names (for editing)

    Returns:
        Tuple of (valid: bool, error_message: str)
    """
    if not name or not name.strip():
        return False, "Service name cannot be empty"

    name = name.strip()

    if len(name) > 100:
        return False, "Service name too long (max 100 characters)"

    if not allow_existing and name in existing_names:
        return False, f"Service '{name}' already exists"

    return True, ""


def validate_username(username: str) -> Tuple[bool, str]:
    """
    Validate username.

    Args:
        username: Username to validate

    Returns:
        Tuple of (valid: bool, error_message: str)
    """
    if not username or not username.strip():
        return False, "Username cannot be empty"

    if len(username) > 200:
        return False, "Username too long (max 200 characters)"

    return True, ""


def sanitize_input(text: str) -> str:
    """
    Sanitize user input by stripping leading/trailing whitespace.

    Args:
        text: Text to sanitize

    Returns:
        Sanitized text
    """
    return text.strip() if text else ""


def validate_timeout(value: str, min_val: int = 1, max_val: int = 120) -> Tuple[bool, int, str]:
    """
    Validate timeout value (in minutes).

    Args:
        value: String value to validate
        min_val: Minimum allowed value
        max_val: Maximum allowed value

    Returns:
        Tuple of (valid: bool, parsed_value: int, error_message: str)
    """
    try:
        timeout = int(value)
        if timeout < min_val or timeout > max_val:
            return False, 0, f"Timeout must be between {min_val} and {max_val} minutes"
        return True, timeout, ""
    except ValueError:
        return False, 0, "Invalid number"
