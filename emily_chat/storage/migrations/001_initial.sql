-- Emily Chat — Initial schema (Phase 2-3)
-- conversations, messages, FTS5 index, skills, settings

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS conversations (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    model           TEXT,
    provider        TEXT,
    skill_id        TEXT,
    pinned          INTEGER DEFAULT 0,
    archived        INTEGER DEFAULT 0,
    tags            JSON    DEFAULT '[]',
    total_tokens_in       INTEGER DEFAULT 0,
    total_tokens_out      INTEGER DEFAULT 0,
    total_thinking_tokens INTEGER DEFAULT 0,
    total_cost_usd        REAL    DEFAULT 0.0,
    total_messages        INTEGER DEFAULT 0,
    parent_id               TEXT,
    branch_from_message_id  TEXT,
    metadata        JSON    DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS messages (
    id                TEXT PRIMARY KEY,
    conversation_id   TEXT    NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role              TEXT    NOT NULL,
    content           TEXT    NOT NULL,
    content_raw       TEXT,
    thinking_content  TEXT,
    thinking_phases   JSON,
    model             TEXT,
    provider          TEXT,
    tokens_in         INTEGER DEFAULT 0,
    tokens_out        INTEGER DEFAULT 0,
    tokens_thinking   INTEGER DEFAULT 0,
    cost_usd          REAL    DEFAULT 0.0,
    latency_ms        INTEGER,
    first_token_ms    INTEGER,
    created_at        TEXT    NOT NULL,
    edited            INTEGER DEFAULT 0,
    edit_history      JSON    DEFAULT '[]',
    stopped           INTEGER DEFAULT 0,
    rating            INTEGER DEFAULT 0,
    web_search_queries JSON,
    sources           JSON,
    attachments       JSON,
    version           INTEGER DEFAULT 1,
    parent_message_id TEXT,
    metadata          JSON    DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation
    ON messages(conversation_id, created_at);

-- Full-text search across message content and thinking traces
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    thinking_content,
    content='messages',
    content_rowid='rowid'
);

-- Keep FTS index in sync with messages table
CREATE TRIGGER IF NOT EXISTS messages_fts_insert
AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content, thinking_content)
    VALUES (new.rowid, new.content, new.thinking_content);
END;

CREATE TRIGGER IF NOT EXISTS messages_fts_delete
AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content, thinking_content)
    VALUES ('delete', old.rowid, old.content, old.thinking_content);
END;

CREATE TRIGGER IF NOT EXISTS messages_fts_update
AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content, thinking_content)
    VALUES ('delete', old.rowid, old.content, old.thinking_content);
    INSERT INTO messages_fts(rowid, content, thinking_content)
    VALUES (new.rowid, new.content, new.thinking_content);
END;

CREATE TABLE IF NOT EXISTS skills (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    icon          TEXT,
    description   TEXT,
    system_prompt_addition TEXT,
    config        JSON    DEFAULT '{}',
    built_in      INTEGER DEFAULT 0,
    created_at    TEXT    NOT NULL,
    use_count     INTEGER DEFAULT 0,
    last_used     TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Schema version tracker
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_version(version, applied_at)
VALUES (1, datetime('now'));
