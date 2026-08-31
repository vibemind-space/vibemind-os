"""Test shared folder guard by simulating an attack from the VM."""
import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("127.0.0.1", port=2222, username="vibemind", password="logitech66", timeout=10)

# Check if shared folder is mounted
_, out, _ = ssh.exec_command("ls /media/sf_shared/ 2>/dev/null || echo NOT_MOUNTED")
content = out.read().decode()
print(f"Shared folder content:\n{content}")

if "NOT_MOUNTED" in content:
    print("Shared folder not mounted in VM. Trying /mnt/shared...")
    _, out, _ = ssh.exec_command("mount | grep shared")
    print(out.read().decode())
    # Try to find it
    _, out, _ = ssh.exec_command("find /media /mnt -maxdepth 2 -name 'sf_*' 2>/dev/null")
    print(f"Found: {out.read().decode()}")
else:
    print("\nSimulating attack: writing to shared folder from VM...")
    _, out, _ = ssh.exec_command("echo 'ATTACKER_WAS_HERE' > /media/sf_shared/HACKED.txt 2>&1")
    err = out.read().decode()
    if err:
        print(f"Write result: {err}")
    else:
        print("File written! Check if guard detects it.")

    time.sleep(2)

    # Check from VM side
    _, out, _ = ssh.exec_command("ls -la /media/sf_shared/HACKED.txt 2>/dev/null")
    print(f"VM sees: {out.read().decode()}")

ssh.close()
