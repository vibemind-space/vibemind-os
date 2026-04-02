"""
GitHub CLI Wrapper — thin subprocess layer around `gh`.
"""

import json
import subprocess


class GhClientError(Exception):
    pass


class GhClient:
    def __init__(self, owner: str = "Flissel", skip_repos: list[str] = None, timeout: int = 30):
        self.owner = owner
        self.skip_repos = skip_repos or []
        self.timeout = timeout

    def _run(self, args: list[str], parse_json: bool = True):
        """Run a gh command and return parsed output."""
        cmd = ["gh"] + args
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise GhClientError(f"gh {' '.join(args[:3])}: {result.stderr.strip()[:200]}")
        if parse_json and result.stdout.strip():
            return json.loads(result.stdout)
        return result.stdout.strip()

    def repos_list(self) -> list[dict]:
        repos = self._run([
            "repo", "list", self.owner,
            "--json", "name,nameWithOwner,description,isPrivate,updatedAt",
            "--limit", "200",
        ])
        return [r for r in repos if r["name"] not in self.skip_repos]

    def issues_list(self, repo: str, state: str = "open", limit: int = 50) -> list[dict]:
        return self._run([
            "issue", "list", "-R", repo, "--state", state,
            "--json", "number,title,body,labels,author,createdAt,comments",
            "--limit", str(limit),
        ])

    def issue_edit(self, repo: str, number: int, **kwargs) -> str:
        args = ["issue", "edit", "-R", repo, str(number)]
        if "add_labels" in kwargs:
            for label in kwargs["add_labels"]:
                args.extend(["--add-label", label])
        if "title" in kwargs:
            args.extend(["--title", kwargs["title"]])
        return self._run(args, parse_json=False)

    def issue_close(self, repo: str, number: int) -> str:
        return self._run(["issue", "close", "-R", repo, str(number)], parse_json=False)

    def issue_comment(self, repo: str, number: int, body: str) -> str:
        return self._run(["issue", "comment", "-R", repo, str(number), "--body", body], parse_json=False)

    def labels_list(self, repo: str) -> list[dict]:
        return self._run(["label", "list", "-R", repo, "--json", "name,color,description"])

    def label_create(self, repo: str, name: str, color: str = "ededed", description: str = "") -> str:
        args = ["label", "create", "-R", repo, name, "--color", color]
        if description:
            args.extend(["--description", description])
        args.append("--force")
        return self._run(args, parse_json=False)

    def pr_list(self, repo: str, state: str = "open", limit: int = 50) -> list[dict]:
        return self._run([
            "pr", "list", "-R", repo, "--state", state,
            "--json", "number,title,body,author,createdAt,headRefName,baseRefName,additions,deletions,files,reviews",
            "--limit", str(limit),
        ])

    def pr_diff(self, repo: str, number: int) -> str:
        return self._run(["pr", "diff", "-R", repo, str(number)], parse_json=False)

    def pr_review(self, repo: str, number: int, body: str, event: str = "COMMENT") -> str:
        return self._run([
            "pr", "review", "-R", repo, str(number), "--body", body, f"--{event.lower()}",
        ], parse_json=False)

    def pr_merge(self, repo: str, number: int, method: str = "squash") -> str:
        return self._run([
            "pr", "merge", "-R", repo, str(number), f"--{method}", "--auto",
        ], parse_json=False)

    def workflow_list(self, repo: str) -> list[dict]:
        return self._run(["workflow", "list", "-R", repo, "--json", "name,id,state"])

    def run_list(self, repo: str, limit: int = 10) -> list[dict]:
        return self._run([
            "run", "list", "-R", repo,
            "--json", "databaseId,name,status,conclusion,headBranch,createdAt",
            "--limit", str(limit),
        ])

    def workflow_run(self, repo: str, workflow: str, ref: str = "main") -> str:
        return self._run([
            "workflow", "run", "-R", repo, workflow, "--ref", ref,
        ], parse_json=False)

    def release_list(self, repo: str, limit: int = 5) -> list[dict]:
        return self._run([
            "release", "list", "-R", repo,
            "--json", "tagName,name,publishedAt,isPrerelease",
            "--limit", str(limit),
        ])

    def release_create(self, repo: str, tag: str, title: str, notes: str = "") -> str:
        args = ["release", "create", "-R", repo, tag, "--title", title]
        if notes:
            args.extend(["--notes", notes])
        return self._run(args, parse_json=False)

    def secret_set(self, repo: str, name: str, value: str) -> str:
        cmd = ["gh", "secret", "set", "-R", repo, name]
        result = subprocess.run(cmd, input=value, capture_output=True, text=True, timeout=self.timeout, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise GhClientError(f"secret set: {result.stderr.strip()[:200]}")
        return "ok"

    def project_list(self) -> list[dict]:
        return self._run(["project", "list", "--owner", self.owner, "--format", "json"], parse_json=True)

    def api(self, endpoint: str, method: str = "GET") -> dict:
        args = ["api", endpoint]
        if method != "GET":
            args.extend(["--method", method])
        return self._run(args)
