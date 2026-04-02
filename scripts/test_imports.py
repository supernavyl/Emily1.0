#!/usr/bin/env python3
"""Minimal import test to isolate the exact failure point."""

import sys
import traceback

print("=" * 80)
print("Testing Emily import chain...")
print("=" * 80)

# Test each import step by step
tests = [
    ("config", "from config import get_settings"),
    ("observability.logger", "from observability.logger import get_logger"),
    ("memory.sensory_buffer", "from memory.sensory_buffer import SensoryBuffer"),
    ("memory.working", "from memory.working import WorkingMemory"),
    ("memory.procedural", "from memory.procedural import ProceduralMemory"),
    ("memory.episodic", "from memory.episodic import EpisodicMemory"),
    ("memory.interaction_logger", "from memory.interaction_logger import InteractionLogger"),
    ("memory.manager", "from memory.manager import MemoryManager"),
    ("llm.fleet", "from llm.fleet import LLMFleet"),
    ("core.bus", "from core.bus import AgentBus"),
    ("agents.base", "from agents.base import BaseAgent"),
    ("agents.registry", "from agents.registry import AgentRegistry"),
    ("core.bootstrap", "from core.bootstrap import Bootstrap"),
]

for module_name, import_stmt in tests:
    print(f"\n[TEST] {module_name}")
    print(f"  Running: {import_stmt}")
    try:
        exec(import_stmt)
        print("  ✓ SUCCESS")
    except Exception as e:
        print(f"  ✗ FAILED: {type(e).__name__}")
        print(f"  Error: {str(e)[:200]}")
        print("\n  Full traceback:")
        traceback.print_exc()
        print("\n" + "=" * 80)
        print("STOPPING AT FIRST FAILURE")
        print("=" * 80)
        sys.exit(1)

print("\n" + "=" * 80)
print("✓ All imports successful!")
print("=" * 80)
