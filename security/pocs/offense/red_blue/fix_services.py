"""Restart VM services after reboot/kill."""
import paramiko, logging
logging.getLogger("paramiko").setLevel(logging.CRITICAL)
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("127.0.0.1", port=2222, username="vibemind", password="logitech66", timeout=10)
for cmd in [
    "echo 'logitech66' | sudo -S systemctl restart secret-vault system-monitor",
    "systemctl is-active secret-vault system-monitor",
    "curl -s http://localhost:8000/api/health",
    "curl -s http://localhost:9090/api/health",
]:
    _, out, _ = ssh.exec_command(cmd, timeout=15)
    print(out.read().decode().strip())
ssh.close()
