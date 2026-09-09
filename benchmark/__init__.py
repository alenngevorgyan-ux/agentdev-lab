"""AgentDev Lab: a reproducible benchmark harness for AI coding agents.

The package is intentionally standard-library only. A benchmark that needs a
package index to run is a benchmark that stops being reproducible the moment
that index changes.
"""

__version__ = "0.1.0"

# Bumped whenever a change alters measured outcomes (sandbox semantics, scoring
# rules, tamper detection). Results carry this value so runs produced by
# different harness semantics are never silently compared.
HARNESS_PROTOCOL_VERSION = 1
