"""Join codes: how students find their course, like "7K4Q-M2XP"."""

import secrets

# No 0/O, 1/I/L or U/V, so a code read aloud or copied by hand comes out right.
ALPHABET = "23456789ABCDEFGHJKMNPQRSTWXYZ"
GROUP_LENGTH = 4
JOIN_CODE_LENGTH = GROUP_LENGTH * 2 + 1


def new_join_code() -> str:
    """A random code in two groups of four, such as 7K4Q-M2XP."""
    chars = "".join(secrets.choice(ALPHABET) for _ in range(GROUP_LENGTH * 2))
    return f"{chars[:GROUP_LENGTH]}-{chars[GROUP_LENGTH:]}"


def normalize_join_code(raw: str) -> str:
    """Accept what students type: any case, with or without the dash or spaces."""
    chars = "".join(ch for ch in raw.upper() if ch.isalnum())
    return (
        f"{chars[:GROUP_LENGTH]}-{chars[GROUP_LENGTH:]}"
        if len(chars) == GROUP_LENGTH * 2
        else chars
    )
