#!/usr/bin/env python3
"""Check if critical dependencies are installed and importable."""

import sys

critical_deps = [
    ("aiosqlite", "Database support"),
    ("tiktoken", "Token counting for LLM"),
    ("qdrant_client", "Vector database"),
    ("prometheus_client", "Observability"),
    ("structlog", "Structured logging"),
    ("pydantic", "Config validation"),
    ("pyyaml", "YAML parsing"),
    ("llama_cpp", "LLM inference (llama-cpp-python)"),
    ("snac", "SNAC neural codec (Orpheus TTS)"),
    ("kokoro", "Kokoro TTS (fallback)"),
]

print("Checking critical dependencies...")
print("=" * 60)

missing = []
failed = []

for module_name, description in critical_deps:
    try:
        __import__(module_name.replace("-", "_"))
        print(f"✓ {module_name:<20} - {description}")
    except ImportError as e:
        print(f"✗ {module_name:<20} - {description}")
        print(f"  Error: {e}")
        missing.append(module_name)
    except Exception as e:
        print(f"✗ {module_name:<20} - {description}")
        print(f"  Unexpected error: {e}")
        failed.append((module_name, str(e)))

print("=" * 60)

if missing:
    print(f"\n❌ Missing {len(missing)} dependencies:")
    for dep in missing:
        print(f"  - {dep}")
    print("\nFix with: uv sync")
    sys.exit(1)

if failed:
    print(f"\n❌ {len(failed)} dependencies failed to load:")
    for dep, err in failed:
        print(f"  - {dep}: {err[:100]}")
    sys.exit(1)

print("\n✓ All critical dependencies are available!")
