"""Errors shared by the reporting stack."""


class ReportError(ValueError):
    """Raised when a report cannot be produced from the given inputs."""


class UnknownFilterError(ReportError):
    """Raised when a filter name is not registered."""
