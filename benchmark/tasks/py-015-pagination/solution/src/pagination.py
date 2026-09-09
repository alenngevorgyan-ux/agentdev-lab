"""Pagination helpers."""


def paginate(items, page=1, per_page=10):
    """Return one page of ``items``.

    The result is a dict with keys: items, page, per_page, total_items,
    total_pages, has_next, has_prev.
    """
    if page < 1:
        raise ValueError("page must be at least 1")
    if per_page < 1:
        raise ValueError("per_page must be at least 1")

    items = list(items)
    total_items = len(items)
    # An empty collection is still one (empty) page, which is what callers
    # rendering "page 1 of 1" expect.
    total_pages = max(1, -(-total_items // per_page))

    start = (page - 1) * per_page
    window = items[start : start + per_page]

    return {
        "items": window,
        "page": page,
        "per_page": per_page,
        "total_items": total_items,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }
