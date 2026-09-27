"""Checkpoint-related exceptions."""

__all__ = [
    "CheckpointError",
    "CheckpointFatalError",
    "CheckpointWriteError",
    "PostgresCheckpointWriteError",
    "RedisCheckpointWriteError",
]


class CheckpointError(RuntimeError):
    """Base exception for checkpoint-related failures."""
    pass


class CheckpointWriteError(CheckpointError):
    """Raised when checkpoint write fails after retries."""
    
    def __init__(self, message: str, original_exception: Exception | None = None) -> None:
        super().__init__(message)
        self.original_exception = original_exception


class RedisCheckpointWriteError(CheckpointWriteError):
    """Raised when Redis checkpoint write fails after retries."""
    pass


class PostgresCheckpointWriteError(CheckpointWriteError):
    """Raised when PostgreSQL checkpoint write fails after retries."""
    pass


class CheckpointFatalError(CheckpointError):
    """Raised when the flusher fails consecutively and cannot recover."""
    
    def __init__(self, message: str, consecutive_failures: int) -> None:
        super().__init__(message)
        self.consecutive_failures = consecutive_failures
