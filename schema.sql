-- Reference SQL schema for tims-ai-assistant.
-- The application creates the same tables automatically via SQLAlchemy on
-- first run, so this file is for documentation / inspection only.

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY,                -- Telegram user id
    username        TEXT,
    first_name      TEXT,
    last_name       TEXT,
    language_code   TEXT,
    is_blocked      BOOLEAN NOT NULL DEFAULT 0,
    is_admin        BOOLEAN NOT NULL DEFAULT 0,
    paused          BOOLEAN NOT NULL DEFAULT 0,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user','assistant','system')),
    content         TEXT NOT NULL,
    tokens          INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_messages_user_created ON messages(user_id, created_at);

CREATE TABLE IF NOT EXISTS memories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind            TEXT NOT NULL,    -- name | fact | preference | relationship | topic
    content         TEXT NOT NULL,
    importance      INTEGER NOT NULL DEFAULT 5,         -- 1..10
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at    TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id);

CREATE TABLE IF NOT EXISTS summaries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    content         TEXT NOT NULL,
    covers_until    TIMESTAMP NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_summaries_user ON summaries(user_id, covers_until);

CREATE TABLE IF NOT EXISTS rate_limit_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_rate_limit_user_time ON rate_limit_events(user_id, created_at);

CREATE TABLE IF NOT EXISTS bot_state (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
