#!/usr/bin/env bash
pkill -fi brave 2>/dev/null && echo "✗ Brave killed" || echo "• Brave not running"
pkill -fi discord 2>/dev/null && echo "✗ Discord killed" || echo "• Discord not running"
echo ""
free -h | grep Mem
