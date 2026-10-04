"""Checkpoint-related exceptions."""

__all__ = [
    "CheckpointError",
    "CheckpointFatalError",
    "CheckpointRecoveryError",
    "CheckpointWriteError",
    "PostgresCheckpointWriteError",
    "RedisCheckpointWriteError",
]


class CheckpointError(RuntimeError):
    """Base exception for checkpoint-related failures."""


class CheckpointWriteError(CheckpointError):
    """Raised when checkpoint write fails after retries."""

    def __init__(self, message: str, original_exception: Exception | None = None) -> None:
        super().__init__(message)
        self.original_exception = original_exception


class RedisCheckpointWriteError(CheckpointWriteError):
    """Raised when Redis checkpoint write fails after retries."""


class PostgresCheckpointWriteError(CheckpointWriteError):
    """Raised when PostgreSQL checkpoint write fails after retries."""


class CheckpointFatalError(CheckpointError):
    """Raised when the flusher fails consecutively and cannot recover."""

    def __init__(self, message: str, consecutive_failures: int) -> None:
        super().__init__(message)
        self.consecutive_failures = consecutive_failures


class CheckpointRecoveryError(CheckpointError):
    """Raised when a thread's state cannot be recovered (B-5).

    A thread that ends up in this state is *not* replayed automatically: ADR-010
    marks it "needs human review" so a human can inspect the forensic stream
    before any state is overwritten. ``recover()`` never propagates this — it
    records the thread and keeps recovering the rest.
    """

    def __init__(
        self,
        message: str,
        *,
        thread_id: str,
        reason: str,
    ) -> None:
        super().__init__(message)
        self.thread_id = thread_id
        self.reason = reason
