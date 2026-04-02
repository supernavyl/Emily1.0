#!/usr/bin/env python3
"""
Emily Professional Terminal Launcher

Quick launcher for the improved Emily terminal interface.
Usage: python terminal_pro.py
"""

import os
import sys

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ == "__main__":
    try:
        from ui.terminal.app_improved import run_improved_tui

        print("🚀 Starting Emily Professional Terminal...")
        run_improved_tui()
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure all dependencies are installed:")
        print("  uv add textual rich psutil")
    except KeyboardInterrupt:
        print("\n👋 Emily Terminal stopped by user")
    except Exception as e:
        print(f"❌ Error starting terminal: {e}")
        import traceback

        traceback.print_exc()
