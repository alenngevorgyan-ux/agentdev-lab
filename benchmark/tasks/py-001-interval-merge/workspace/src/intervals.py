"""Interval utilities."""


def merge_intervals(intervals):
    """Merge overlapping [start, end] intervals into a minimal sorted list."""
    if not intervals:
        return []

    merged = [list(intervals[0])]
    for start, end in intervals[1:]:
        last = merged[-1]
        if start < last[1]:
            last[1] = max(last[1], end)
        else:
            merged.append([start, end])
    return merged
