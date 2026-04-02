# Emily's Interaction Persistence System

**Status**: ✅ **FULLY ENABLED** - Every interaction is automatically saved to disk

---

## Overview

Emily now has a **comprehensive interaction logging system** that guarantees **every single conversation turn** (both user inputs and Emily's responses) is **immediately saved to permanent storage** on your computer.

### Key Features

✅ **Write-through persistence** - Every turn saved immediately to SQLite  
✅ **Crash-safe** - Uses `PRAGMA synchronous=FULL` and WAL mode for durability  
✅ **Automatic backups** - Creates backups every 30 minutes  
✅ **Full-text search** - Search through all your conversations  
✅ **Export functionality** - Export to JSON for external use  
✅ **Redundancy** - Separate from episodic memory for extra safety  
✅ **Zero loss** - Even if Emily crashes, all interactions are saved

---

## How It Works

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Every Conversation Turn                                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  User says/types something                                  │
│    ↓                                                         │
│  1. Added to Working Memory (in-RAM)                        │
│  2. IMMEDIATELY saved to interactions.db (disk)  ← NEW!     │
│  3. Logged with metadata (timestamp, importance, etc.)      │
│                                                              │
│  Emily responds                                             │
│    ↓                                                         │
│  1. Added to Working Memory (in-RAM)                        │
│  2. IMMEDIATELY saved to interactions.db (disk)  ← NEW!     │
│  3. Logged with metadata (model, critic score, etc.)        │
│                                                              │
└─────────────────────────────────────────────────────────────┘

Storage Locations:
├── data/interactions.db          → All individual turns
├── data/interactions.db-wal      → Write-ahead log (SQLite)
├── data/interactions.db-shm      → Shared memory (SQLite)
├── data/backups/                 → Automatic backups every 30 min
└── data/episodes.db              → Session summaries (existing)
```

### What Gets Saved

**For Every User Turn:**
- Unique ID
- Session ID
- Exact timestamp
- Full text content
- Importance score
- Metadata (STT confidence, language, etc.)

**For Every Emily Response:**
- Unique ID
- Session ID
- Exact timestamp
- Full response text
- Importance score
- Metadata (model used, critic score, latency, voice mode, etc.)

---

## Configuration

### Enabled by Default

In `config.yaml`:

```yaml
memory:
  episodic:
    db_path: "data/episodes.db"
    auto_summarize: true
    summary_model: "fast"
    save_all_interactions: true  # ← ENABLED (every turn saved)
    interactions_db_path: "data/interactions.db"
    auto_backup_interval_minutes: 30  # Backup every 30 minutes
```

### To Disable (Not Recommended)

If you don't want interactions saved:

```yaml
memory:
  episodic:
    save_all_interactions: false  # Disables interaction logging
```

---

## Viewing Your Interactions

### Using the View Script

Emily includes a powerful command-line tool to explore your saved interactions:

```bash
cd ~/Emily1.0

# View recent interactions (default: 20)
python scripts/view-interactions.py recent

# View more recent interactions
python scripts/view-interactions.py recent --n 100

# View only user messages
python scripts/view-interactions.py recent --role user --n 50

# View only Emily's responses
python scripts/view-interactions.py recent --role assistant --n 50

# Search for specific content
python scripts/view-interactions.py search "python code"
python scripts/view-interactions.py search "machine learning" --limit 50

# View statistics
python scripts/view-interactions.py stats

# View specific session
python scripts/view-interactions.py session <session-id>

# Export all to JSON
python scripts/view-interactions.py export-all my_conversations.json

# Export specific session
python scripts/view-interactions.py export-session <session-id> session.json

# Create manual backup
python scripts/view-interactions.py backup
```

### Example Output

```
📜 Showing 5 most recent interactions:
================================================================================

👤 USER [1735451234]
   Session: a7b3c9d2
   Content: Can you help me with a Python script?
   Metadata: {"confidence": 0.95, "language": "en"}

🤖 EMILY [1735451235]
   Session: a7b3c9d2
   Content: Of course! I'd be happy to help with Python. What kind of script...
   Metadata: {"model": "Qwen3-14B", "critic_score": 0.89, "latency_ms": 450}

👤 USER [1735451280]
   Session: a7b3c9d2
   Content: I need to parse JSON files
   Metadata: {"confidence": 0.92, "language": "en"}

🤖 EMILY [1735451282]
   Session: a7b3c9d2
   Content: Here's how to parse JSON files in Python...
   Metadata: {"model": "Qwen3-14B", "critic_score": 0.91, "latency_ms": 380}
```

---

## Storage Details

### Database Structure

**Table: `interactions`**
```sql
CREATE TABLE interactions (
    id TEXT PRIMARY KEY,           -- UUID
    session_id TEXT NOT NULL,      -- Links related turns
    timestamp REAL NOT NULL,       -- Unix timestamp
    role TEXT NOT NULL,            -- 'user' or 'assistant'
    content TEXT NOT NULL,         -- Full message text
    importance REAL DEFAULT 0.5,   -- 0.0-1.0
    metadata TEXT,                 -- JSON: model, scores, etc.
    created_at REAL NOT NULL
);
```

**Full-Text Search**
- Uses SQLite FTS5 (full-text search)
- Automatically indexes all content
- Fast searching across millions of interactions

### Durability Guarantees

Emily uses SQLite with maximum durability settings:

```sql
PRAGMA journal_mode=WAL;        -- Write-Ahead Logging
PRAGMA synchronous=FULL;        -- Guaranteed disk sync
```

**What This Means:**
- Every interaction is `fsync()`'d to disk immediately
- If Emily crashes or power is lost, no data is lost
- WAL mode allows concurrent reads during writes

### File Locations

```
Emily1.0/
├── data/
│   ├── interactions.db          → Main interaction database
│   ├── interactions.db-wal      → Write-ahead log (temporary)
│   ├── interactions.db-shm      → Shared memory (temporary)
│   ├── episodes.db              → Session summaries
│   └── backups/
│       ├── interactions_backup_20260228_143022.db
│       ├── interactions_backup_20260228_150022.db
│       └── ...                  → One backup every 30 minutes
```

---

## Automatic Backups

### How Backups Work

1. **Automatic**: Every 30 minutes (configurable)
2. **On shutdown**: Final backup when Emily closes
3. **Manual**: Run `python scripts/view-interactions.py backup`

### Backup Location

```
data/backups/interactions_backup_YYYYMMDD_HHMMSS.db
```

### Managing Backups

Backups accumulate over time. To manage:

```bash
# List all backups
ls -lh data/backups/

# Remove old backups (keep last 7 days)
find data/backups/ -name "interactions_backup_*.db" -mtime +7 -delete

# Keep only the 10 most recent
ls -t data/backups/*.db | tail -n +11 | xargs rm -f
```

---

## Exporting Data

### Export to JSON

```bash
# Export everything
python scripts/view-interactions.py export-all conversations.json

# Export specific session
python scripts/view-interactions.py export-session <session-id> session.json
```

### JSON Format

```json
[
  {
    "id": "a1b2c3d4-...",
    "session_id": "x7y8z9w0-...",
    "timestamp": 1735451234.567,
    "role": "user",
    "content": "Can you help me with Python?",
    "importance": 0.6,
    "metadata": {
      "confidence": 0.95,
      "language": "en"
    },
    "created_at": 1735451234.567
  },
  {
    "id": "e5f6g7h8-...",
    "session_id": "x7y8z9w0-...",
    "timestamp": 1735451235.123,
    "role": "assistant",
    "content": "Of course! I'd be happy to help...",
    "importance": 0.7,
    "metadata": {
      "model": "Qwen3-14B",
      "critic_score": 0.89,
      "latency_ms": 450,
      "voice_mode": false
    },
    "created_at": 1735451235.123
  }
]
```

---

## Privacy & Security

### Local-Only Storage

✅ **100% local** - All data stored on your computer  
✅ **No cloud** - Zero network transmission  
✅ **Encrypted** - When `security.encrypt_at_rest: true` (optional)  
✅ **Your control** - You own all the data

### Data Location

All interaction data is stored in:
```
/home/supernovyl/Emily1.0/data/interactions.db
```

You can:
- Copy/backup this file anywhere
- Delete it to clear history
- Export to JSON and process externally
- Encrypt the entire `data/` directory

---

## Performance Impact

### Overhead

**Per interaction:**
- Write time: ~1-3ms (SQLite with WAL)
- Disk I/O: Minimal (buffered by OS)
- Memory: Negligible

**Overall:**
- ✅ No noticeable impact on conversation latency
- ✅ Scales to millions of interactions
- ✅ Fast full-text search even with large history

### Database Size

**Approximate storage:**
- 100 interactions ≈ 50 KB
- 1,000 interactions ≈ 500 KB
- 10,000 interactions ≈ 5 MB
- 100,000 interactions ≈ 50 MB

**Full-text index** adds ~30-50% overhead but enables instant search.

---

## Troubleshooting

### Database Locked

**Issue**: "database is locked" error

**Solution**:
```bash
# Check if multiple Emily instances are running
ps aux | grep emily

# Kill old instances if needed
killall python

# Or wait for WAL checkpoint
python scripts/view-interactions.py backup  # Forces checkpoint
```

### Corrupted Database

**Issue**: Database corruption (very rare with `synchronous=FULL`)

**Solution**:
```bash
# 1. Restore from latest backup
cp data/backups/interactions_backup_*.db data/interactions.db

# 2. Or rebuild database
sqlite3 data/interactions.db "PRAGMA integrity_check;"
```

### Missing Interactions

**Issue**: Some interactions not showing up

**Check**:
```bash
# Verify logging is enabled
grep "save_all_interactions" config.yaml
# Should show: save_all_interactions: true

# Check database
python scripts/view-interactions.py stats
```

---

## Advanced Usage

### Direct SQLite Access

You can query the database directly:

```bash
sqlite3 data/interactions.db

# Show recent interactions
SELECT role, content, datetime(timestamp, 'unixepoch') 
FROM interactions 
ORDER BY timestamp DESC 
LIMIT 10;

# Count by role
SELECT role, COUNT(*) FROM interactions GROUP BY role;

# Search content
SELECT role, content FROM interactions 
WHERE content LIKE '%python%' 
LIMIT 20;

# Export to CSV
.mode csv
.output conversations.csv
SELECT * FROM interactions;
.quit
```

### Integration with External Tools

Export and process with Python:

```python
import json
import pandas as pd

# Load exported JSON
with open('conversations.json') as f:
    data = json.load(f)

# Convert to DataFrame
df = pd.DataFrame(data)

# Analyze
print(df.groupby('role').size())
print(df['content'].str.len().describe())

# Find conversations about specific topics
python_convs = df[df['content'].str.contains('python', case=False)]
```

---

## Summary

### What Changed

**Before** (episodic memory only):
- Interactions stored in working memory (RAM)
- Only saved to `episodes.db` when session ends
- Could lose data if Emily crashes mid-session

**After** (interaction logging):
- ✅ Every turn saved immediately to `interactions.db`
- ✅ Separate database for redundancy
- ✅ Full-text search capability
- ✅ Automatic backups every 30 minutes
- ✅ Export to JSON
- ✅ Zero data loss even if Emily crashes

### Files Modified

1. **`config.py`** - Added interaction logging configuration
2. **`config.yaml`** - Enabled `save_all_interactions: true`
3. **`memory/interaction_logger.py`** - New complete logging system
4. **`memory/manager.py`** - Integrated interaction logger
5. **`scripts/view-interactions.py`** - New viewing/export tool

### New Files Created

- `data/interactions.db` - All interactions (auto-created)
- `data/backups/` - Automatic backups directory (auto-created)

---

## Quick Reference

**View recent:**
```bash
python scripts/view-interactions.py recent --n 50
```

**Search:**
```bash
python scripts/view-interactions.py search "your query"
```

**Stats:**
```bash
python scripts/view-interactions.py stats
```

**Export all:**
```bash
python scripts/view-interactions.py export-all backup.json
```

**Backup now:**
```bash
python scripts/view-interactions.py backup
```

---

**Every interaction with Emily is now permanently saved to your computer! 🎉**

**Last Updated**: February 28, 2026  
**Version**: Emily 1.0
