"""
Safety Layer — operation classification and confirmation prompts.
"""

from enum import Enum


class OpType(Enum):
    AUTONOMOUS = "autonomous"
    CONFIRM = "confirm"
    DELETE = "delete"


AUTONOMOUS_OPS = {"list", "view", "search", "label_create", "label_add", "comment", "labels_list"}
CONFIRM_OPS = {"merge", "close", "approve", "release_create", "workflow_run", "secret_set", "pr_review"}
DELETE_OPS = {"delete", "repo_delete", "issue_delete"}


class SafetyGuard:
    def __init__(self, delete_whitelist: list[str] = None, auto_approve: bool = False, dry_run: bool = False):
        self.delete_whitelist = delete_whitelist or []
        self.auto_approve = auto_approve
        self.dry_run = dry_run

    def classify(self, operation: str) -> OpType:
        if operation in DELETE_OPS:
            return OpType.DELETE
        if operation in CONFIRM_OPS:
            return OpType.CONFIRM
        return OpType.AUTONOMOUS

    def check_delete(self, repo: str) -> tuple[bool, str]:
        if repo in self.delete_whitelist:
            return True, "repo in delete whitelist"
        return False, f"{repo} not in delete whitelist"

    def confirm(self, message: str) -> bool:
        if self.auto_approve:
            return True
        try:
            answer = input(f"\n  [CONFIRM] {message} [y/N]: ").strip().lower()
            return answer == "y"
        except (EOFError, KeyboardInterrupt):
            return False

    def can_execute(self, operation: str, repo: str = "") -> bool:
        op_type = self.classify(operation)

        if op_type == OpType.AUTONOMOUS:
            return True

        if self.dry_run:
            print(f"  [DRY-RUN] Would execute: {operation} on {repo}")
            return False

        if op_type == OpType.DELETE:
            allowed, reason = self.check_delete(repo)
            if not allowed:
                print(f"  [BLOCKED] {reason}")
                return False
            return self.confirm(f"DELETE {operation} on {repo}?")

        if op_type == OpType.CONFIRM:
            return self.confirm(f"{operation} on {repo}?")

        return False
