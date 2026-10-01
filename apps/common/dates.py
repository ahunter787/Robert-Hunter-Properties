"""Small shared helpers that do not belong to one domain."""


def ordinal(number: int) -> str:
    """Render a day of the month as an ordinal: 1 → "1st", 22 → "22nd"."""
    if 10 <= number % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(number % 10, "th")
    return f"{number}{suffix}"
