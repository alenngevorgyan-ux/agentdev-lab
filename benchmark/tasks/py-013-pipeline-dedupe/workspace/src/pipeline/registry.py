"""The ordered stage registry.

Stages run in the order listed here. Adding, removing or reordering a stage
is a deliberate change to the pipeline contract.
"""

from .stages import (
    s01_strip_whitespace,
    s02_drop_empty_rows,
    s03_lowercase_emails,
    s04_parse_amounts,
    s05_normalise_currency,
    s06_tag_source,
    s07_dedupe_by_id,
    s08_resolve_account,
    s09_group_by_account,
    s10_enrich_region,
    s11_flag_large,
    s12_apply_fx,
    s13_sort_records,
    s14_aggregate_totals,
    s15_build_output,
    s16_validate_output,
)

STAGES = (
    s01_strip_whitespace,
    s02_drop_empty_rows,
    s03_lowercase_emails,
    s04_parse_amounts,
    s05_normalise_currency,
    s06_tag_source,
    s07_dedupe_by_id,
    s08_resolve_account,
    s09_group_by_account,
    s10_enrich_region,
    s11_flag_large,
    s12_apply_fx,
    s13_sort_records,
    s14_aggregate_totals,
    s15_build_output,
    s16_validate_output,
)


def stage_names():
    return [stage.__name__.rsplit(".", 1)[-1] for stage in STAGES]
