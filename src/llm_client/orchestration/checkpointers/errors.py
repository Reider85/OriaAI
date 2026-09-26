"""Checkpoint-related exceptions."""


class CheckpointWriteError(RuntimeError):
    """Raised when Redis checkpoint write fails after retries."""
    
    def __init__(self, message: str, original_exception: Exception | None = None) -> None:
        super().__init__(message)
        self.original_exception = original_exception