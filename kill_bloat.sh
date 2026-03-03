#!/usr/bin/env bash
# kill_bloat.sh — Kill useless processes eating RAM on Arch Linux
set -uo pipefail

echo ""
echo "  BEFORE:"
free -h | grep Mem
echo ""
echo "══════════════════════════════════════"
echo "  TOP RAM CONSUMERS"
echo "══════════════════════════════════════"
ps aux --sort=-%mem | head -20 | awk '{printf "%5s%%  %-8s PID=%-7s %s\n", $4, $1, $2, $11}'
echo ""
echo "══════════════════════════════════════"
echo "  KILLING BLOAT..."
echo "══════════════════════════════════════"

killed=0

# File indexers
for p in baloo_file tracker-miner tracker-extract tracker3; do
    pkill -f "$p" 2>/dev/null && echo "  ✗ $p" && ((killed++)) || true
done

# GNOME/KDE bloat
for p in evolution-data goa-daemon gnome-software gnome-shell-calendar gvfsd-metadata zeitgeist; do
    pkill -f "$p" 2>/dev/null && echo "  ✗ $p" && ((killed++)) || true
done

# Snap (if present)
for p in snapd snap-store; do
    pkill -x "$p" 2>/dev/null && echo "  ✗ $p" && ((killed++)) || true
done

# Browsers (comment out if you need them)
# for p in firefox chrome chromium brave vivaldi; do
#     pkill -fi "$p" 2>/dev/null && echo "  ✗ $p" && ((killed++)) || true
# done

# Chat / social / media apps
for p in slack discord telegram teams spotify; do
    pkill -fi "$p" 2>/dev/null && echo "  ✗ $p" && ((killed++)) || true
done

# Electron apps eating RAM
for p in electron; do
    pkill -f "$p" 2>/dev/null && echo "  ✗ $p" && ((killed++)) || true
done

# Print spoolers
pkill -f cupsd 2>/dev/null && echo "  ✗ cupsd (print)" && ((killed++)) || true

# Bluetooth (if not using)
pkill -f bluetoothd 2>/dev/null && echo "  ✗ bluetoothd" && ((killed++)) || true

# Accessibility
pkill -f at-spi 2>/dev/null && echo "  ✗ at-spi" && ((killed++)) || true

# Packagekit
pkill -f packagekitd 2>/dev/null && echo "  ✗ packagekitd" && ((killed++)) || true

# Geoclue (location)
pkill -f geoclue 2>/dev/null && echo "  ✗ geoclue" && ((killed++)) || true

# Xdg portals (desktop portals — respawn but clears RAM temporarily)
pkill -f "xdg-desktop-portal" 2>/dev/null && echo "  ✗ xdg-desktop-portal" && ((killed++)) || true

# Drop caches
sync
echo 3 | sudo tee /proc/sys/vm/drop_caches >/dev/null 2>&1 && echo "  ✓ Caches dropped" || echo "  ⚠ Run with sudo for cache drop"

# Trim journal
sudo journalctl --vacuum-size=50M >/dev/null 2>&1 && echo "  ✓ Journal trimmed" || true

echo ""
echo "  Killed $killed processes"
echo ""
echo "  AFTER:"
free -h | grep Mem
echo ""
