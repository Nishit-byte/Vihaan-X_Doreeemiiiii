"""Sandbox execution package for VivaVoce M2: pytest runner sandboxed with a timeout, plus process-tree cleanup."""

try:
    from ..ingestion.models import SandboxResult
except ImportError:
    from ingestion.models import SandboxResult

from .sandbox_runner import (
    execute_verification,
    execute_verification_async,
    warm_up_sandbox,
)
from .multi_language import execute_multi_language_sandbox

__all__ = [
    "execute_verification",
    "execute_verification_async",
    "execute_multi_language_sandbox",
    "warm_up_sandbox",
    "SandboxResult",
]
