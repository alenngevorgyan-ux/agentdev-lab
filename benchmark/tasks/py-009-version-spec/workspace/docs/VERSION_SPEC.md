# Version specification

A version string has the form `MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]`.

## Parsing

1. `MAJOR`, `MINOR` and `PATCH` are non-negative integers written without
   leading zeroes. `1.0.0` is valid; `01.0.0` and `1.00.3` are not.
2. All three numeric components are mandatory. `1.2` is invalid.
3. `PRERELEASE`, when present, follows a single `-` and is one or more
   dot-separated identifiers. Each identifier is non-empty and contains only
   ASCII letters, digits and hyphens.
4. A numeric pre-release identifier (digits only) must not have leading
   zeroes: `1.0.0-alpha.1` is valid, `1.0.0-alpha.01` is not.
5. `BUILD`, when present, follows a single `+` and has the same character
   rules as a pre-release identifier set. Leading zeroes are permitted here.
6. Any input that violates the above raises `InvalidVersion`, whose message
   includes the offending input.

## Comparison

7. Compare `MAJOR`, then `MINOR`, then `PATCH`, numerically.
8. Build metadata is ignored entirely for comparison purposes. `1.0.0+a` and
   `1.0.0+b` are equal.
9. A version with a pre-release has *lower* precedence than the same version
   without one: `1.0.0-alpha` < `1.0.0`.
10. When both have a pre-release, compare identifiers left to right:
    * identifiers consisting only of digits compare numerically;
    * identifiers with letters compare lexically by ASCII order;
    * a numeric identifier has lower precedence than an alphanumeric one;
    * if all preceding identifiers are equal, the version with more
      identifiers has higher precedence.
11. `compare_versions(a, b)` returns `-1` when `a < b`, `0` when equal and
    `1` when `a > b`, accepting either strings or parsed versions.
