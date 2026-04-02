#!/usr/bin/env python3
"""Quick import chain test — verifies core modules are importable."""

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    print("Attempting to import memory.manager...")
    from memory.manager import MemoryManager  # noqa: F401

    print("✓ Successfully imported MemoryManager")
except Exception as e:
    print(f"✗ Failed: {e}")
    print("\nFull traceback:")
    traceback.print_exc()
    sys.exit(1)

try:
    print("\nAttempting to import agents.base...")
    from agents.base import BaseAgent  # noqa: F401

    print("✓ Successfully imported BaseAgent")
except Exception as e:
    print(f"✗ Failed: {e}")
    print("\nFull traceback:")
    traceback.print_exc()
    sys.exit(1)

try:
    print("\nAttempting to import core.bootstrap...")
    from core.bootstrap import Bootstrap  # noqa: F401

    print("✓ Successfully imported Bootstrap")
except Exception as e:
    print(f"✗ Failed: {e}")
    print("\nFull traceback:")
    traceback.print_exc()
    sys.exit(1)

print("\n✓✓✓ All imports successful! Ready to start voice.")
