"""
Deploy secret-vault + system-monitor API into MultiseatOS VM.
Run from host: python vm_deploy.py
"""
import paramiko
import time
import sys


def ssh_exec(ssh, cmd, timeout=120, show_all=False):
    print(f"  $ {cmd[:120]}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    rc = stdout.channel.recv_exit_status()
    lines = out.strip().split("\n") if out.strip() else []
    if show_all:
        for line in lines:
            print(f"    {line}")
    elif lines:
        for line in lines[-5:]:
            print(f"    {line}")
    if err.strip() and rc != 0:
        for line in err.strip().split("\n")[-3:]:
            print(f"    [ERR] {line}")
    return out, err, rc


def deploy_file(ssh, content, remote_path):
    sftp = ssh.open_sftp()
    with sftp.file(remote_path, "w") as f:
        f.write(content)
    sftp.close()
    print(f"    -> {remote_path}")


VAULT_SERVER = '''#!/usr/bin/env python3
"""Secret-Vault with JWT auth."""
import json, os, hashlib, secrets
from http.server import HTTPServer, BaseHTTPRequestHandler

DATA_DIR = os.path.expanduser("~/secret-vault")
VAULT_FILE = os.path.join(DATA_DIR, "vault.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
os.makedirs(DATA_DIR, exist_ok=True)

if not os.path.exists(VAULT_FILE):
    with open(VAULT_FILE, "w") as f:
        json.dump({"secrets": {
            "admin_api_key": "sk-REDBLUE-test-key-12345",
            "db_password": "REDBLUE_supersecret",
            "aws_access_key": "AKIAIOSFODNN7EXAMPLE",
            "jwt_secret": "REDBLUE_jwt_s3cr3t_k3y",
        }}, f)

if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, "w") as f:
        json.dump({
            "admin": hashlib.sha256("admin123".encode()).hexdigest(),
            "vibemind": hashlib.sha256("logitech66".encode()).hexdigest(),
            "readonly": hashlib.sha256("reader".encode()).hexdigest(),
        }, f)

TOKENS = {}

class VaultHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass
    def _send(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    def _auth(self):
        token = self.headers.get("Authorization", "").replace("Bearer ", "")
        for user, t in TOKENS.items():
            if t == token: return user
        return None
    def do_GET(self):
        if self.path == "/api/auth/status":
            self._send(200, {"status": "locked", "first_run": False, "users": list(json.load(open(USERS_FILE)).keys())})
        elif self.path == "/api/health":
            self._send(200, {"status": "ok", "service": "secret-vault"})
        elif self.path == "/api/vault/list":
            user = self._auth()
            if not user: return self._send(401, {"error": "unauthorized"})
            s = json.load(open(VAULT_FILE)).get("secrets", {})
            self._send(200, {"secrets": list(s.keys()), "count": len(s)})
        elif self.path.startswith("/api/vault/get/"):
            user = self._auth()
            if not user: return self._send(401, {"error": "unauthorized"})
            key = self.path.split("/")[-1]
            s = json.load(open(VAULT_FILE)).get("secrets", {})
            self._send(200 if key in s else 404, {"key": key, "value": s[key]} if key in s else {"error": "not found"})
        elif self.path == "/api/vault/export":
            user = self._auth()
            if user != "admin": return self._send(403, {"error": "admin only"})
            self._send(200, json.load(open(VAULT_FILE)))
        elif self.path == "/api/auth/attempts":
            total = sum(len(v) for v in LOGIN_ATTEMPTS.values())
            failed = total - len(TOKENS)
            self._send(200, {"total": total, "failed": max(0, failed), "last_failed": ""})
        else: self._send(404, {"error": "not found"})
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}
        if self.path == "/api/auth/login":
            username = body.get("username", "")
            password = body.get("password", "")
            users = json.load(open(USERS_FILE))
            if username in users and users[username] == hashlib.sha256(password.encode()).hexdigest():
                token = secrets.token_hex(32)
                TOKENS[username] = token
                self._send(200, {"token": token, "username": username})
            else: self._send(401, {"error": "invalid credentials"})
        elif self.path == "/api/auth/recover":
            username = body.get("username", "")
            if username in json.load(open(USERS_FILE)):
                self._send(200, {"hint": f"Starts with '{username[:2]}', length {len(username)+2}"})
            else: self._send(404, {"error": "user not found"})
        elif self.path == "/api/auth/revoke-all":
            count = len(TOKENS)
            TOKENS.clear()
            self._send(200, {"revoked": count})
        else: self._send(404, {"error": "not found"})

print("Secret-Vault running on 0.0.0.0:8000", flush=True)
HTTPServer(("0.0.0.0", 8000), VaultHandler).serve_forever()
'''

MONITOR_SERVER = '''#!/usr/bin/env python3
"""System Monitor API."""
import json, os, subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler

class MonitorHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass
    def _send(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    def _run(self, cmd, timeout=5):
        try: return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
        except Exception as e: return str(e)
    def do_GET(self):
        if self.path == "/api/health":
            self._send(200, {"status": "ok", "hostname": os.uname().nodename})
        elif self.path == "/api/processes":
            out = self._run(["ps", "aux", "--no-headers"])
            procs = []
            for line in out.strip().split("\\n")[:100]:
                parts = line.split(None, 10)
                if len(parts) >= 11:
                    procs.append({"user": parts[0], "pid": parts[1], "cpu": parts[2], "mem": parts[3], "cmd": parts[10][:200]})
            self._send(200, {"processes": procs, "count": len(procs)})
        elif self.path == "/api/network":
            self._send(200, {"listeners": self._run(["ss", "-tlnp"])[:3000], "connections": self._run(["ss", "-tnp"])[:3000]})
        elif self.path == "/api/system":
            self._send(200, {"memory": self._run(["free", "-h"]), "disk": self._run(["df", "-h", "/"]), "uptime": self._run(["uptime"]).strip()})
        elif self.path == "/api/users":
            self._send(200, {"logged_in": self._run(["who"]).strip()})
        elif self.path == "/api/services":
            self._send(200, {"services": self._run(["systemctl", "list-units", "--type=service", "--state=running", "--no-pager", "--no-legend"])[:5000]})
        else: self._send(404, {"error": "not found"})

print("System Monitor API running on 0.0.0.0:9090", flush=True)
HTTPServer(("0.0.0.0", 9090), MonitorHandler).serve_forever()
'''

VAULT_SERVICE = """[Unit]
Description=Secret Vault
After=network.target
[Service]
Type=simple
User=vibemind
ExecStart=/usr/bin/python3 /home/vibemind/secret-vault/server.py
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
"""

MONITOR_SERVICE = """[Unit]
Description=System Monitor API
After=network.target
[Service]
Type=simple
User=vibemind
ExecStart=/usr/bin/python3 /home/vibemind/system-monitor/server.py
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
"""


def main():
    print("=" * 60)
    print("  MultiseatOS VM - Service Deployment")
    print("=" * 60)

    print("\n[1/5] Connecting via SSH...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect("127.0.0.1", port=2222, username="vibemind", password="logitech66", timeout=10)
    print("  Connected.\n")

    print("[2/5] Deploying secret-vault...")
    ssh_exec(ssh, "mkdir -p ~/secret-vault")
    deploy_file(ssh, VAULT_SERVER, "/home/vibemind/secret-vault/server.py")
    deploy_file(ssh, VAULT_SERVICE, "/tmp/secret-vault.service")
    ssh_exec(ssh, "echo 'logitech66' | sudo -S cp /tmp/secret-vault.service /etc/systemd/system/")
    ssh_exec(ssh, "echo 'logitech66' | sudo -S systemctl daemon-reload")
    ssh_exec(ssh, "echo 'logitech66' | sudo -S systemctl restart secret-vault")
    time.sleep(2)
    out, _, _ = ssh_exec(ssh, "curl -s http://localhost:8000/api/auth/status", show_all=True)
    print(f"  -> {'OK' if 'locked' in out else 'WARN: not responding'}\n")

    print("[3/5] Deploying system-monitor API...")
    ssh_exec(ssh, "mkdir -p ~/system-monitor")
    deploy_file(ssh, MONITOR_SERVER, "/home/vibemind/system-monitor/server.py")
    deploy_file(ssh, MONITOR_SERVICE, "/tmp/system-monitor.service")
    ssh_exec(ssh, "echo 'logitech66' | sudo -S cp /tmp/system-monitor.service /etc/systemd/system/")
    ssh_exec(ssh, "echo 'logitech66' | sudo -S systemctl daemon-reload")
    ssh_exec(ssh, "echo 'logitech66' | sudo -S systemctl restart system-monitor")
    time.sleep(2)
    out, _, _ = ssh_exec(ssh, "curl -s http://localhost:9090/api/health", show_all=True)
    print(f"  -> {'OK' if 'ok' in out else 'WARN: not responding'}\n")

    print("[4/5] Service status...")
    ssh_exec(ssh, "systemctl is-active secret-vault system-monitor", show_all=True)
    ssh_exec(ssh, "ss -tlnp | grep -E '8000|9090'", show_all=True)

    print("\n[5/5] Testing login...")
    ssh_exec(ssh, "curl -s -X POST http://localhost:8000/api/auth/login -H 'Content-Type: application/json' -d '{\"username\":\"admin\",\"password\":\"admin123\"}'", show_all=True)

    ssh.close()
    print("\n  Done! Add VBox port forwarding: 8000->8000")
    print("=" * 60)


if __name__ == "__main__":
    main()
