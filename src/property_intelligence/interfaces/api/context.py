"""Request-scoped context used by logging and error responses."""

from contextvars import ContextVar

request_id_context: ContextVar[str] = ContextVar("request_id", default="-")
