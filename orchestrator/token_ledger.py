"""
Authoritative, append-only record of real token usage and spend.

estimate_cost.py answers "what should this roughly cost before we start."
This module answers "what did it actually cost" -- always trust this over
the planning estimate once the loop has run.
"""
from __future__ import annotations
import sqlite3
import time
from contextlib import closing

from pricing import PRICING
from vertex_client import CallResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    phase TEXT,
    task_id TEXT,
    model_key TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cache_creation_input_tokens INTEGER NOT NULL,
    cache_read_input_tokens INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    latency_s REAL,
    stop_reason TEXT
);
"""


def _cost_for(model_key: str, input_tokens: int, output_tokens: int,
              cache_creation_input_tokens: int, cache_read_input_tokens: int) -> float:
    p = PRICING[model_key]
    # input_tokens from the API already EXCLUDES cache_read/cache_creation
    # tokens -- those are billed at their own rates, this is not double-counted.
    return (
        input_tokens * p.input_per_mtok
        + cache_creation_input_tokens * p.cache_write_5m_per_mtok
        + cache_read_input_tokens * p.cache_read_per_mtok
        + output_tokens * p.output_per_mtok
    ) / 1_000_000


class TokenLedger:
    def __init__(self, db_path: str = "token_ledger.sqlite3"):
        self.db_path = db_path
        with closing(sqlite3.connect(self.db_path)) as con:
            con.execute(SCHEMA)
            con.commit()

    def record(self, result: CallResult, phase: str, task_id: str) -> float:
        cost = _cost_for(
            result.model_key, result.input_tokens, result.output_tokens,
            result.cache_creation_input_tokens, result.cache_read_input_tokens,
        )
        with closing(sqlite3.connect(self.db_path)) as con:
            con.execute(
                "INSERT INTO calls (ts, phase, task_id, model_key, input_tokens, "
                "output_tokens, cache_creation_input_tokens, cache_read_input_tokens, "
                "cost_usd, latency_s, stop_reason) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (time.time(), phase, task_id, result.model_key, result.input_tokens,
                 result.output_tokens, result.cache_creation_input_tokens,
                 result.cache_read_input_tokens, cost, result.latency_s, result.stop_reason),
            )
            con.commit()
        return cost

    def report(self) -> str:
        with closing(sqlite3.connect(self.db_path)) as con:
            rows = con.execute(
                "SELECT model_key, COUNT(*), SUM(input_tokens), SUM(output_tokens), "
                "SUM(cache_read_input_tokens), SUM(cost_usd) FROM calls GROUP BY model_key"
            ).fetchall()
            total = con.execute("SELECT SUM(cost_usd) FROM calls").fetchone()[0] or 0.0

        lines = [f"{'Model':<12}{'Calls':>8}{'Input tok':>14}{'Output tok':>14}"
                 f"{'Cache reads':>14}{'Cost (USD)':>13}"]
        for model_key, calls, in_tok, out_tok, cache_reads, cost in rows:
            lines.append(f"{model_key:<12}{calls:>8,}{in_tok or 0:>14,}{out_tok or 0:>14,}"
                          f"{cache_reads or 0:>14,}{cost or 0:>13,.2f}")
        lines.append("-" * 75)
        lines.append(f"ACTUAL TOTAL SPEND: ${total:,.2f}")
        return "\n".join(lines)


if __name__ == "__main__":
    print(TokenLedger().report())
