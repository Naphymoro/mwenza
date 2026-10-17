-- Neurons used per UTC day, for the daily cap (src/index.ts).
CREATE TABLE IF NOT EXISTS ai_usage (
  day TEXT PRIMARY KEY,
  requests INTEGER NOT NULL DEFAULT 0,
  neurons REAL NOT NULL DEFAULT 0
);
