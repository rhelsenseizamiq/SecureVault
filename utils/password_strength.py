"""
Password strength estimation and feedback
"""
import re
from typing import Tuple


# Common weak passwords (top 100 subset)
COMMON_PASSWORDS = {
    'password', '123456', '12345678', 'qwerty', 'abc123', 'monkey', '1234567',
    'letmein', 'trustno1', 'dragon', 'baseball', 'iloveyou', 'master', 'sunshine',
    'ashley', 'bailey', 'passw0rd', 'shadow', '123123', '654321', 'superman',
    'qazwsx', 'michael', 'football', 'password1', 'admin', 'welcome', 'login'
}


def estimate_password_strength(password: str) -> Tuple[int, str, str]:
    """
    Estimate password strength using rule-based heuristics.

    Returns a score from 0-4:
    - 0: Very Weak
    - 1: Weak
    - 2: Fair
    - 3: Strong
    - 4: Very Strong

    Args:
        password: The password to evaluate

    Returns:
        Tuple of (score: int, strength_label: str, feedback: str)
    """
    if not password:
        return 0, "Very Weak", "Password cannot be empty"

    score = 0
    feedback_parts = []

    # Length checks
    length = len(password)
    if length < 8:
        return 0, "Very Weak", "Password must be at least 8 characters"
    elif length >= 8:
        score += 1
    if length >= 12:
        score += 1
    if length >= 16:
        score += 1

    # Character variety checks
    has_lower = bool(re.search(r'[a-z]', password))
    has_upper = bool(re.search(r'[A-Z]', password))
    has_digit = bool(re.search(r'\d', password))
    has_special = bool(re.search(r'[^a-zA-Z0-9]', password))

    char_types = sum([has_lower, has_upper, has_digit, has_special])

    if char_types >= 3:
        score += 1
    if char_types >= 4:
        score += 1

    # Penalty for common patterns
    if password.lower() in COMMON_PASSWORDS:
        score = max(0, score - 2)
        feedback_parts.append("Avoid common passwords")

    # Penalty for repeated characters
    if re.search(r'(.)\1{2,}', password):  # 3+ repeated chars
        score = max(0, score - 1)
        feedback_parts.append("Avoid repeated characters")

    # Penalty for sequential characters
    if re.search(r'(abc|bcd|cde|123|234|345|456|567|678|789)', password.lower()):
        score = max(0, score - 1)
        feedback_parts.append("Avoid sequential patterns")

    # Cap score at 4
    score = min(4, score)

    # Generate feedback
    if not feedback_parts:
        if score < 3:
            if not has_upper:
                feedback_parts.append("Add uppercase letters")
            if not has_special:
                feedback_parts.append("Add special characters")
            if length < 12:
                feedback_parts.append("Make it longer (12+ chars)")
        elif score == 3:
            feedback_parts.append("Good password! Consider making it longer.")
        else:
            feedback_parts.append("Excellent password!")

    # Map score to label
    labels = {
        0: "Very Weak",
        1: "Weak",
        2: "Fair",
        3: "Strong",
        4: "Very Strong"
    }

    feedback = " ".join(feedback_parts) if feedback_parts else "Good password"

    return score, labels[score], feedback


def get_strength_color(score: int) -> str:
    """
    Get color for strength score (for UI display).

    Args:
        score: Strength score (0-4)

    Returns:
        Color name suitable for tkinter
    """
    colors = {
        0: "#d32f2f",  # Red
        1: "#f57c00",  # Orange
        2: "#fbc02d",  # Yellow
        3: "#7cb342",  # Light green
        4: "#388e3c"   # Dark green
    }
    return colors.get(score, "#757575")


def validate_password_strength(password: str, min_score: int = 2) -> Tuple[bool, str]:
    """
    Validate that password meets minimum strength requirement.

    Args:
        password: Password to validate
        min_score: Minimum required score (default 2 = Fair)

    Returns:
        Tuple of (valid: bool, message: str)
    """
    score, label, feedback = estimate_password_strength(password)

    if score < min_score:
        return False, f"Password is too weak ({label}). {feedback}"

    return True, f"Password strength: {label}"
