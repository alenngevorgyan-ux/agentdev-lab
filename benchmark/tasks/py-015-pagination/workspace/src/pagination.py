"""Pagination helpers."""


def paginate(items, page=1, per_page=10):
    """Return one page of ``items``.

    The result is a dict with keys: items, page, per_page, total_items,
    total_pages, has_next, has_prev.
    """
    items = list(items)
    total_items = len(items)
    total_pages = total_items // per_page

    start = (page - 1) * per_page
    end = start + per_page - 1
    window = items[start:end]

    return {
        "items": window,
        "page": page,
        "per_page": per_page,
        "total_items": total_items,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }
