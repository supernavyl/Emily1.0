#!/bin/bash
# Capture full error output from Emily startup
python main.py --no-gui 2>&1 | head -200
