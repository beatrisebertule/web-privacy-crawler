"""
Printout wording shared by analysis scripts.
"""


def counted(count: int, noun: str) -> str:
    """
    Plural or singular based on count

    example: (1, "website") -> "1 website", (3, "website") -> "3 websites"
    """
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"
