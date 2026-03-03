#!/usr/bin/env python3
"""
Emily Quick Diagnostics — Find the exact import error.

Run this script to identify which module is failing and why.
"""

import sys
import traceback
from pathlib import Path


def main():
    print("\n" + "=" * 80)
    print("EMILY IMPORT DIAGNOSTICS")
    print("=" * 80)

    # Step 1: Check dependencies
    print("\n[Step 1/4] Checking critical dependencies...")
    deps_ok = check_deps()
    if not deps_ok:
        print("❌ Missing dependencies. Run: uv sync")
        return False

    # Step 2: Check syntax
    print("\n[Step 2/4] Checking Python syntax...")
    syntax_ok = check_syntax()
    if not syntax_ok:
        print("❌ Syntax errors found. Fix them above.")
        return False

    # Step 3: Test import chain
    print("\n[Step 3/4] Testing import chain step-by-step...")
    chain_ok = test_import_chain()
    if not chain_ok:
        print("❌ Import chain failed. See errors above.")
        return False

    # Step 4: Try full startup
    print("\n[Step 4/4] Testing full Emily import...")
    startup_ok = test_full_import()
    if not startup_ok:
        print("❌ Full startup import failed.")
        return False

    print("\n" + "=" * 80)
    print("✓ ALL DIAGNOSTICS PASSED")
    print("=" * 80)
    print("\nYou can now run: python main.py")
    return True


def check_deps():
    """Check if critical dependencies are installed."""
    deps = [
        "aiosqlite",
        "tiktoken",
        "qdrant_client",
        "prometheus_client",
        "structlog",
        "pydantic",
        "pyyaml",
    ]

    missing = []
    for dep in deps:
        try:
            __import__(dep.replace("-", "_"))
            print(f"  ✓ {dep}")
        except ImportError:
            print(f"  ✗ {dep} - MISSING")
            missing.append(dep)

    return len(missing) == 0


def check_syntax():
    """Check Python files for syntax errors."""
    import py_compile

    files_to_check = [
        "config.py",
        "memory/manager.py",
        "memory/episodic.py",
        "memory/working.py",
        "memory/procedural.py",
        "memory/interaction_logger.py",
        "agents/base.py",
        "agents/registry.py",
        "core/bootstrap.py",
    ]

    errors = []
    for file_path in files_to_check:
        if not Path(file_path).exists():
            print(f"  ⚠ {file_path} - NOT FOUND")
            continue
        try:
            py_compile.compile(file_path, doraise=True)
            print(f"  ✓ {file_path}")
        except py_compile.PyCompileError as e:
            print(f"  ✗ {file_path} - SYNTAX ERROR")
            errors.append((file_path, str(e)))

    if errors:
        for file_path, err in errors:
            print(f"\n  {file_path}:\n  {err[:200]}")
        return False

    return True


def test_import_chain():
    """Test each import step-by-step."""
    chain = [
        ("config", "from config import get_settings"),
        ("observability.logger", "from observability.logger import get_logger"),
        ("memory.sensory_buffer", "from memory.sensory_buffer import SensoryBuffer"),
        ("memory.interaction_logger", "from memory.interaction_logger import InteractionLogger"),
        ("memory.working", "from memory.working import WorkingMemory"),
        ("memory.procedural", "from memory.procedural import ProceduralMemory"),
        ("memory.episodic", "from memory.episodic import EpisodicMemory"),
        ("memory.manager", "from memory.manager import MemoryManager"),
    ]

    for name, stmt in chain:
        try:
            exec(stmt)
            print(f"  ✓ {name}")
        except Exception as e:
            print(f"  ✗ {name}")
            print(f"    {type(e).__name__}: {str(e)[:150]}")
            print("\n  Full traceback:")
            traceback.print_exc()
            return False

    return True


def test_full_import():
    """Test full Emily import."""
    try:
        print("  ✓ Full Bootstrap import successful")
        return True
    except Exception as e:
        print("  ✗ Bootstrap import failed")
        print(f"    {type(e).__name__}: {str(e)[:150]}")
        print("\n  Full traceback:")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
