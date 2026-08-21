"""Immutable content-block views crossing the model boundary."""

from .content_views import content_view, request_view, text_blocks, with_active_text

__all__ = ["content_view", "request_view", "text_blocks", "with_active_text"]
