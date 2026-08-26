"""Make a value safe to store in a text column."""

NUL = "\x00"


def fit(value: str, max_length: int) -> str:
    """Cut a value down to what the column can hold.

    A subject or an address longer than its column is a database error on
    PostgreSQL and MySQL, and silent truncation on SQLite. Neither is worth
    losing the log over.
    """
    return clean(value)[:max_length]


def clean(value: str) -> str:
    """Drop what a text column cannot hold: PostgreSQL rejects NUL bytes."""
    return value.replace(NUL, "") if NUL in value else value
