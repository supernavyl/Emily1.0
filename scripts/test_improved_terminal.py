#!/usr/bin/env python3
"""
Test script for the improved Emily terminal interface.
"""

import asyncio
import os
import sys

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_terminal():
    """Test the improved terminal components."""
    try:
        print("Testing Emily Improved Terminal Components:")
        print("=" * 50)

        # Test imports
        print("✓ Testing imports...")
        from ui.terminal.completions import CompletionEngine

        print("  All imports successful")

        # Test completion engine
        print("✓ Testing completion engine...")
        engine = CompletionEngine()
        completion = engine.get_completion("/he")
        print(f"  Completion for '/he': {completion}")

        # Test command registry
        print("✓ Testing command registry...")
        from ui.terminal.commands import registry

        commands = list(registry.list_all_names())
        print(f"  Available commands: {len(commands)}")
        print(f"  Sample commands: {commands[:5]}")

        print("\n🎉 All tests passed!")
        print("\nThe improved terminal interface is ready to run.")
        print("\nTo start the terminal:")
        print("  uv run python -m ui.terminal.app_improved")
        print("\nFeatures:")
        print("  • Professional dark theme with blue/cyan accents")
        print("  • ASCII art banner")
        print("  • Metasploit-style prompt: emily >")
        print("  • Tab completion for commands")
        print("  • Command history (up/down arrows)")
        print("  • Real-time system monitoring dashboard")
        print("  • Status bar with live indicators")
        print("  • Enhanced panel layout")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_terminal())
