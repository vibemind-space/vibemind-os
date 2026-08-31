"""Quick SSH check for MultiseatOS VM."""
import paramiko
import time

for attempt in range(10):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect("127.0.0.1", port=2222, username="vibemind", password="logitech66", timeout=5)
        stdin, stdout, stderr = ssh.exec_command("echo SSH_READY && uname -a && hostname && df -h / && free -h")
        print(stdout.read().decode())
        print(stderr.read().decode())
        ssh.close()
        break
    except Exception as e:
        print(f"Attempt {attempt+1}: {e}")
        time.sleep(5)
