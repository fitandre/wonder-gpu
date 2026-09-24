"""
Deliberately thin: the loop never force-pushes, never merges to base_branch,
and never deletes anything. Every task lands on its own branch; a human (or
a separate, human-triggered CI/merge step) decides what reaches base_branch.
That decision boundary is intentional -- see roadmap.md Section 0 point 4
and config.yaml's human_gate policy.
"""
from __future__ import annotations
import subprocess
from pathlib import Path


class GitOps:
    def __init__(self, repo_path: str, base_branch: str, work_branch_prefix: str):
        self.repo_path = Path(repo_path)
        self.base_branch = base_branch
        self.work_branch_prefix = work_branch_prefix

    def _run(self, *args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=self.repo_path, capture_output=True, text=True, check=True
        )
        return result.stdout.strip()

    def branch_for(self, phase: str, task_id: str) -> str:
        return f"{self.work_branch_prefix}{phase}-{task_id}"

    def start_task_branch(self, phase: str, task_id: str) -> str:
        branch = self.branch_for(phase, task_id)
        self._run("checkout", self.base_branch)
        self._run("pull", "--ff-only")
        self._run("checkout", "-b", branch)
        return branch

    def changed_paths(self) -> list[str]:
        out = self._run("status", "--porcelain")
        return [line[3:] for line in out.splitlines() if line]

    def commit_all(self, message: str) -> str:
        self._run("add", "-A")
        self._run("commit", "-m", message)
        return self._run("rev-parse", "HEAD")

    def diff_stat(self) -> str:
        return self._run("diff", "--stat", self.base_branch)
