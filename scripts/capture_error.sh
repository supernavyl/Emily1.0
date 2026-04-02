#!/bin/bash
# Capture full error output from Emily startup
uv run python main.py --no-gui 2>&1 | head -200
