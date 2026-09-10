"""Backward-compatible entry point.

New code should import :func:`freebox_pop_remote.main.main`.
"""

from .main import main

__all__ = ["main"]
