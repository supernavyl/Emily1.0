#!/usr/bin/env bash
# free_ram.sh — Show top RAM consumers and kill heavy ones
set -euo pipefail

echo "══════════════════════════════════════════════════════════"
echo "  RAM USAGE REPORT"
echo "══════════════════════════════════════════════════════════"
echo ""
free -h
echo ""

echo "══════════════════════════════════════════════════════════"
echo "  TOP 25 RAM CONSUMERS"
echo "══════════════════════════════════════════════════════════"
echo ""
ps aux --sort=-%mem | head -26 | awk '{printf "%-8s %-6s %5s%%  %s\n", $1, $2, $4, $11}'
echo ""

echo "══════════════════════════════════════════════════════════"
echo "  QUICK KILLS (safe to stop)"
echo "══════════════════════════════════════════════════════════"
echo ""

# Kill common RAM hogs — browsers, electron apps, unused services
killed=0

# Snap store / update daemons
for proc in snapd snap-store update-notifier packagekitd; do
    if pgrep -x "$proc" >/dev/null 2>&1; then
        echo "  Killing $proc..."
        pkill -x "$proc" 2>/dev/null && ((killed++)) || true
    fi
done

# Baloo (KDE file indexer)
if pgrep -f "baloo_file" >/dev/null 2>&1; then
    echo "  Killing baloo_file (KDE indexer)..."
    pkill -f "baloo_file" 2>/dev/null && ((killed++)) || true
fi

# Tracker (GNOME file indexer)
if pgrep -f "tracker-miner" >/dev/null 2>&1; then
    echo "  Killing tracker-miner (GNOME indexer)..."
    pkill -f "tracker-miner" 2>/dev/null && ((killed++)) || true
fi

# Evolution data server (GNOME calendar/contacts — eats ~200MB)
if pgrep -f "evolution-data" >/dev/null 2>&1; then
    echo "  Killing evolution-data-server..."
    pkill -f "evolution-data" 2>/dev/null && ((killed++)) || true
fi

# Unused Electron apps (slack, discord, teams, spotify, vscode if not in use)
for app in slack teams spotify discord; do
    if pgrep -fi "$app" >/dev/null 2>&1; then
        echo "  Killing $app..."
        pkill -fi "$app" 2>/dev/null && ((killed++)) || true
    fi
done

# Drop filesystem caches (safe, frees pagecache/dentries/inodes)
echo ""
echo "  Dropping filesystem caches..."
sync
echo 3 | sudo tee /proc/sys/vm/drop_caches >/dev/null 2>&1 && echo "  ✓ Caches dropped" || echo "  ⚠ Need sudo for cache drop — run: sudo sh -c 'echo 3 > /proc/sys/vm/drop_caches'"

# Clear systemd journal if huge
journal_size=$(journalctl --disk-usage 2>/dev/null | grep -oP '[\d.]+[GM]' || echo "0")
echo "  Journal size: $journal_size"
sudo journalctl --vacuum-size=100M 2>/dev/null && echo "  ✓ Journal trimmed to 100M" || true

echo ""
echo "══════════════════════════════════════════════════════════"
echo "  RESULT"
echo "══════════════════════════════════════════════════════════"
echo "  Killed $killed processes"
echo ""
free -h
echo ""
echo "  To kill a specific PID:  kill -9 <PID>"
echo "  To kill by name:         pkill -f <name>"
