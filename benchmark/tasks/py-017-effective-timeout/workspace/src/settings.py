"""Runtime settings."""

#: Seconds a single HTTP request may take before being abandoned.
HTTP_TIMEOUT_SECONDS = 5

#: Seconds an idle pooled connection is kept before being closed.
POOL_IDLE_TIMEOUT_SECONDS = 5

#: Seconds between health-check probes.
HEALTHCHECK_INTERVAL_SECONDS = 5
