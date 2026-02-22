"""
Application bootstrap (thin wrapper around main).

Kept for symmetry with the spec; the real logic lives in main.py.
"""

from emily_chat.main import main

__all__ = ["main"]
