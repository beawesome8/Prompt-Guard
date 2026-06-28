"""
Initialises the SQLite database and creates the eval_runs table if it does not exist.
Run once before the first eval. Safe to re-run — uses CREATE TABLE IF NOT EXISTS.
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "runs.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS eval_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            prompt_version TEXT NOT NULL,
            run_type TEXT NOT NULL,
            case_id TEXT NOT NULL,
            schema_valid INTEGER NOT NULL,
            sentiment_correct INTEGER,
            urgency_correct INTEGER,
            latency_ms REAL,
            cost_usd REAL,
            input_tokens INTEGER,
            output_tokens INTEGER,
            raw_output TEXT,
            parsed_sentiment TEXT,
            parsed_urgency TEXT,
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    print(f"Database ready at: {DB_PATH}")


if __name__ == "__main__":
    init_db()
