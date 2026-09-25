import sqlite3
import yaml
import json
import os
from datetime import datetime

PROJECT_ROOT = os.path.expanduser("~/projects/wonder-gpu/orchestrator")
LEDGER_DB = os.path.join(PROJECT_ROOT, "token_ledger.sqlite3")
TASK_GRAPH = os.path.join(PROJECT_ROOT, "task_graph.yaml")
OUTPUT_JSON = os.path.expanduser("~/projects/wonder-gpu/www/status.json")

def get_ledger_data():
    if not os.path.exists(LEDGER_DB):
        return []
    conn = sqlite3.connect(LEDGER_DB)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT model_id, SUM(input_tokens) as input, SUM(output_tokens) as output, SUM(cache_read_tokens) as cache, SUM(cost_usd) as cost FROM token_usage GROUP BY model_id")
        return [dict(row) for row in cursor.fetchall()]
    except Exception:
        return []
    finally:
        conn.close()

def get_tasks_data():
    if not os.path.exists(TASK_GRAPH):
        return {"phases": [], "tasks": []}
    with open(TASK_GRAPH, "r") as f:
        return yaml.safe_load(f)

def main():
    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    
    data = {
        "last_updated": datetime.now().isoformat(),
        "ledger": get_ledger_data(),
        "graph": get_tasks_data(),
        "total_cost": sum(item["cost"] for item in get_ledger_data())
    }
    
    with open(OUTPUT_JSON, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Status exported to {OUTPUT_JSON}")

if __name__ == "__main__":
    main()
