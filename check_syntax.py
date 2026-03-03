#!/usr/bin/env python3
"""Check all Python files for syntax errors."""

import py_compile
import sys
from pathlib import Path

errors = []

# Check memory/ directory
memory_dir = Path("memory")
for py_file in sorted(memory_dir.glob("*.py")):
    if py_file.name.startswith("_"):
        continue
    try:
        py_compile.compile(str(py_file), doraise=True)
        print(f"✓ {py_file.name}")
    except py_compile.PyCompileError as e:
        print(f"✗ {py_file.name}: {e}")
        errors.append((py_file.name, str(e)))

# Check key modules in the import chain
key_modules = [
    "config.py",
    "observability/logger.py",
    "observability/brain_tap.py",
    "core/brain_hub.py",
    "core/bus.py",
]

for mod_path in key_modules:
    try:
        py_compile.compile(mod_path, doraise=True)
        print(f"✓ {mod_path}")
    except py_compile.PyCompileError as e:
        print(f"✗ {mod_path}: {e}")
        errors.append((mod_path, str(e)))

if errors:
    print(f"\n❌ Found {len(errors)} syntax errors:")
    for name, err in errors:
        print(f"\n{name}:\n{err}")
    sys.exit(1)
else:
    print("\n✓ All files have valid syntax!")
