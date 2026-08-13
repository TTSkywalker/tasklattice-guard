"""Public boundary for adapting NeMo generation results into product decisions.

The implementation remains private to ``runtime`` so it can evolve with the
NeMo logging schema; callers consume only ``ProtectionDecision``.
"""

from .runtime import NeMoGuardrailsEngine

__all__ = ["NeMoGuardrailsEngine"]
