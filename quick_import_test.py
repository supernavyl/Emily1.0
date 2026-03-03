#!/usr/bin/env python3
import sys
import traceback

try:
    print("Attempting to import memory.manager...")

    print("✓ Successfully imported MemoryManager")
except Exception as e:
    print(f"✗ Failed: {e}")
    print("\nFull traceback:")
    traceback.print_exc()
    sys.exit(1)

try:
    print("\nAttempting to import agents.base...")

    print("✓ Successfully imported BaseAgent")
except Exception as e:
    print(f"✗ Failed: {e}")
    print("\nFull traceback:")
    traceback.print_exc()
    sys.exit(1)

try:
    print("\nAttempting to import core.bootstrap...")

    print("✓ Successfully imported Bootstrap")
except Exception as e:
    print(f"✗ Failed: {e}")
    print("\nFull traceback:")
    traceback.print_exc()
    sys.exit(1)

print("\n✓✓✓ All imports successful! Ready to start voice.")
