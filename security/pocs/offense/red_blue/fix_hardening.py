"""Fix remaining hardening issues."""
import paramiko, logging
logging.getLogger("paramiko").setLevel(logging.CRITICAL)
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("127.0.0.1", port=2222, username="vibemind", password="logitech66", timeout=10, banner_timeout=15)

def sudo(cmd):
    _, out, err = ssh.exec_command(f"echo 'logitech66' | sudo -S {cmd}", timeout=15)
    return out.read().decode("utf-8", errors="replace").strip()

def run(cmd):
    _, out, _ = ssh.exec_command(cmd, timeout=15)
    return out.read().decode("utf-8", errors="replace").strip()

# Fix auditd
print("Fixing auditd...")
sudo("systemctl enable auditd")
sudo("systemctl start auditd")
print(f"  auditd: {run('systemctl is-active auditd')}")
print(f"  rules: {sudo('auditctl -l | wc -l')}")

# Fix fail2ban
print("Fixing fail2ban...")
sudo("systemctl enable fail2ban")
sudo("systemctl start fail2ban")
print(f"  fail2ban: {run('systemctl is-active fail2ban')}")

# Check vault
print(f"Vault: {run('curl -s http://localhost:8000/api/health')}")

# Verify crontab
print(f"Crontab: {sudo('lsattr /var/spool/cron/crontabs/vibemind 2>/dev/null')}")

# SUID count
print(f"SUID: {run('find / -perm -4000 -type f 2>/dev/null | wc -l')} binaries")

# Test cron backdoor blocked
print("\nTest: Cron backdoor (should fail)...")
result = run('echo "* * * * * echo test" | crontab - 2>&1')
print(f"  crontab -: {result}")

# Test log deletion blocked
print("Test: Log deletion (should fail)...")
result = sudo("truncate -s 0 /var/log/auth.log 2>&1")
print(f"  truncate auth.log: {result}")

ssh.close()
print("\nDone.")
