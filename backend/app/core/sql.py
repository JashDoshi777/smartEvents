"""Small SQL helpers shared by routes."""


def escape_like(value: str) -> str:
    """Escape LIKE/ILIKE wildcards so user input is matched literally.

    Use with ``col.ilike(f"%{escape_like(q)}%", escape="\\\\")``. (Values are
    always bound parameters - this is about wildcard semantics, not injection.)
    """
    # NUL bytes are illegal in Postgres text and would raise a driver error.
    return value.replace("\x00", "").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def ilike_contains(column, value: str):
    return column.ilike(f"%{escape_like(value)}%", escape="\\")
