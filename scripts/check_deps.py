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
    ("yaml", "YAML parsing (pyyaml package)"),
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

# Extra checks specific to Orpheus TTS (primary voice path as of 2026-04-19)
print("\nOrpheus TTS readiness:")
print("=" * 60)

orpheus_ok = True

try:
    from llama_cpp import llama_supports_gpu_offload

    if llama_supports_gpu_offload():
        print("✓ llama-cpp-python built with CUDA (GPU offload available)")
    else:
        print("✗ llama-cpp-python built WITHOUT CUDA (CPU-only — Orpheus will be slow)")
        print("  Rebuild: CUDA_HOME=/opt/cuda CMAKE_ARGS='-DGGML_CUDA=on' \\")
        print("    .venv/bin/python -m pip install llama-cpp-python \\")
        print("    --force-reinstall --no-cache-dir --no-deps")
        orpheus_ok = False
except ImportError:
    print("✗ llama-cpp-python not importable")
    orpheus_ok = False

from pathlib import Path

gguf_path = Path("models/orpheus-3b-0.1-ft-q4_k_m.gguf")
if gguf_path.exists():
    size_gb = gguf_path.stat().st_size / (1024**3)
    print(f"✓ Orpheus GGUF present ({size_gb:.1f} GB)")
else:
    print(f"✗ Orpheus GGUF missing at {gguf_path}")
    print("  Download from: https://huggingface.co/canopylabs/orpheus-3b-0.1-ft (GGUF Q4_K_M)")
    orpheus_ok = False

if not orpheus_ok:
    print("\n⚠  Orpheus will fall back to Kokoro. See ABLITERATED_SETUP.md.")
    # Not exit(1) — Kokoro fallback is valid.
