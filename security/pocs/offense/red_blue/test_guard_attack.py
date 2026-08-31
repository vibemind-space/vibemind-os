"""Simulate 3 attacks from VM against shared folder — watch your monitor!"""
import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("127.0.0.1", port=2222, username="vibemind", password="logitech66", timeout=10)

print("[1/3] Angriff: Neue Datei im Shared Folder...")
ssh.exec_command("echo 'ATTACKER_WAS_HERE' > /media/sf_shared/HACKED.txt")
time.sleep(6)

print("[2/3] Angriff: Honeypot credentials.txt lesen + kopieren...")
ssh.exec_command("cp /media/sf_shared/credentials.txt /tmp/stolen_creds.txt")
time.sleep(6)

print("[3/3] Angriff: Honeypot modifizieren (CRITICAL — sollte VM killen!)...")
ssh.exec_command("echo 'PWNED' >> /media/sf_shared/credentials.txt")
time.sleep(3)

print("Done. Schau auf dein Monitor-Terminal!")
ssh.close()
