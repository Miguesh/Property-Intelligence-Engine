"""Application-level failures translated by delivery adapters."""


class ApplicationError(Exception):
    """Base exception for expected application failures."""


class GenerationUnavailableError(ApplicationError):
    """Raised when generated content is required but no provider is available."""


class RetrievalUnavailableError(ApplicationError):
    """Raised when knowledge retrieval is required but unavailable."""
