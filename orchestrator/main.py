#!/usr/bin/env python3
"""
Kayfabe roadmap loop -- driver.
Functional version for Wonder GPU.
"""
from __future__ import annotations
import argparse
import sys
import yaml
import os

from git_ops import GitOps
from model_router import ModelRouter, Task
from token_ledger import TokenLedger
from vertex_client import VertexGeminiClient

MAX_ITERATIONS_PER_TASK = 8

def load_config(path: str = "config.yaml") -> dict:
    if os.path.exists("config.local.yaml"):
        path = "config.local.yaml"
    with open(path) as f:
        return yaml.safe_load(f)

def load_tasks_for_phase(graph: dict, phase_id: str) -> list[Task]:
    real = [t for t in graph.get("tasks", []) if t.get("phase") == phase_id]
    if real:
        return [Task(**t) for t in real]
    return []

def update_task_status(task_id: str, status: str):
    with open("task_graph.yaml", "r") as f:
        graph = yaml.safe_load(f)
    for t in graph.get("tasks", []):
        if t["id"] == task_id:
            t["status"] = status
    with open("task_graph.yaml", "w") as f:
        yaml.dump(graph, f)

def run_phase(phase_id: str, cfg: dict, graph: dict):
    tasks = load_tasks_for_phase(graph, phase_id)
    if not tasks:
        print(f"No tasks for phase {phase_id}")
        return

    router = ModelRouter(
        cfg["routing"], cfg["routing"]["escalate_after_failures"],
        cfg["human_gate_required_for_paths"],
    )
    git = GitOps(cfg["repo"]["path"], cfg["repo"]["base_branch"], cfg["repo"]["work_branch_prefix"])
    ledger = TokenLedger()
    vertex = VertexGeminiClient(cfg["gcp"]["project_id"], cfg["gcp"]["vertex_region"])

    for task in tasks:
        print(f"\n=== {task.id}: {task.title} ({task.kind}) ===")
        update_task_status(task.id, "in_progress")
        
        branch = git.start_task_branch(task.phase, task.id)
        
        # Simulating analysis loop for the first task
        # In a full impl, we would use vertex.call() here.
        model_key = router.model_for(task)
        
        # System prompt based on ANALYSIS.md and repo rules
        system_prompt = "You are the Wonder GPU architect. Build production-grade GPU virtualization."
        user_prompt = f"Task: {task.title}\nContext: {task.context}"
        
        print(f"  Calling {model_key}...")
        result = vertex.call(model_key, system=system_prompt, user_content=user_prompt)
        ledger.record(result, task.phase, task.id)
        
        # For analysis tasks, we write the result to a doc file
        output_file = os.path.join(cfg["repo"]["path"], f"docs/analysis_{task.id}.md")
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, "w") as f:
            f.write(result.text)
        
        git.commit_all(f"[{task.phase}/{task.id}] {task.title} - Analysis complete")
        update_task_status(task.id, "completed")

    print("\n" + ledger.report())

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run")
    p_run.add_argument("--phase", required=True)
    sub.add_parser("status")
    
    args = ap.parse_args()
    cfg = load_config()
    with open("task_graph.yaml") as f:
        graph = yaml.safe_load(f)

    if args.cmd == "run":
        run_phase(args.phase, cfg, graph)
    elif args.cmd == "status":
        ledger = TokenLedger()
        print(ledger.report())

if __name__ == "__main__":
    main()
