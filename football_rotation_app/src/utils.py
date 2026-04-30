"""Small shared helpers for the football rotation app."""

from __future__ import annotations

POSITIONS = [
    "Unassigned",
    "Goalkeeper",
    "Centre Back",
    "Left Back",
    "Right Back",
    "Left Wing Back",
    "Right Wing Back",
    "Defensive Midfielder",
    "Central Midfielder",
    "Attacking Midfielder",
    "Left Midfielder",
    "Right Midfielder",
    "Left Winger",
    "Right Winger",
    "Striker",
    "Centre Forward",
]

SECONDARY_POSITIONS = [""] + POSITIONS[1:]

PREFERRED_ROLES = ["Starter", "Rotation", "Bench"]

ROLE_LABELS = {
    "starter": "Starter",
    "substitute": "Substitute",
    "sit_out": "Sit-out",
    "unavailable": "Unavailable",
}


def clean_text(value: str | None) -> str:
    """Return trimmed text, or an empty string for missing values."""
    return (value or "").strip()


def optional_text(value: str | None) -> str | None:
    """Store blank optional text fields as NULL in SQLite."""
    cleaned = clean_text(value)
    return cleaned if cleaned else None


def yes_no(value: int | bool) -> str:
    """Convert SQLite integer booleans into coach-friendly labels."""
    return "Yes" if bool(value) else "No"


def role_label(role: str) -> str:
    """Return a readable label for a stored match role."""
    return ROLE_LABELS.get(role, role.replace("_", " ").title())


def player_position_text(primary: str, secondary: str | None) -> str:
    """Format a player's positions for display."""
    if primary == "Unassigned" and not secondary:
        return "Position to be added"
    return f"{primary} / {secondary}" if secondary else primary
