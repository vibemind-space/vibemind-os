"""Fix ALL VM services — aggressive restart."""
import paramiko, logging, time
logging.getLogger("paramiko").setLevel(logging.CRITICAL)

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("127.0.0.1", port=2222, username="vibemind", password="logitech66", timeout=10, banner_timeout=15)

def sudo(cmd, t=30):
    _, out, err = ssh.exec_command(f"echo 'logitech66' | sudo -S bash -c '{cmd}'", timeout=t)
    o = out.read().decode("utf-8", errors="replace").strip()
    e = err.read().decode("utf-8", errors="replace").strip()
    return o, e

def run(cmd):
    _, out, _ = ssh.exec_command(cmd, timeout=15)
    return out.read().decode("utf-8", errors="replace").strip()

print("=== Installing missing packages ===")
sudo("apt-get update -qq", t=60)
sudo("DEBIAN_FRONTEND=noninteractive apt-get install -y -qq auditd audispd-plugins fail2ban", t=120)
time.sleep(2)

print("\n=== Starting services ===")
services = [
    "auditd",
    "fail2ban",
    "secret-vault",
    "system-monitor",
    "vm-security-monitor",
    "dbus-session-helper",
    "rsyslog",
    "cron",
]

for svc in services:
    sudo(f"systemctl enable {svc} 2>/dev/null")
    sudo(f"systemctl restart {svc} 2>/dev/null")

time.sleep(3)

# Load auditd rules manually
print("\n=== Loading auditd rules ===")
sudo("auditctl -R /etc/audit/rules.d/hardening.rules 2>/dev/null")
rules = run("echo 'logitech66' | sudo -S auditctl -l 2>/dev/null | wc -l")
print(f"  Rules: {rules}")

# Start desktop manager
print("\n=== Starting desktop ===")
sudo("systemctl start gdm3 2>/dev/null || systemctl start lightdm 2>/dev/null")

# Final status
print("\n=== FINAL STATUS ===")
for svc in services:
    s = run(f"systemctl is-active {svc} 2>/dev/null")
    icon = "OK" if "active" == s.strip() else "!!"
    print(f"  [{icon}] {svc:25s} {s}")

# Test endpoints
print("\n=== Endpoints ===")
print(f"  Vault:   {run('curl -s http://localhost:8000/api/health')}")
print(f"  Monitor: {run('curl -s http://localhost:9090/api/health')}")

ssh.close()
print("\nDone.")
