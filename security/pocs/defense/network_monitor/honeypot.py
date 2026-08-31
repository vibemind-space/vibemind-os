"""
Network Honeypot — Fake Services with Realistic Data
=======================================================
Deploys fake database/service listeners that:
1. Look real to an attacker scanning the network
2. Serve convincing fake data when queried
3. Log every connection attempt with timestamp + IP
4. Alert when someone connects (= intruder in the network!)

Services:
  - Fake PostgreSQL (5433) — fake user database
  - Fake Redis (6399) — fake session store
  - Fake HTTP API (8888) — fake REST API with user data
  - Fake SSH (2222) — banner grab trap
  - Fake FTP (2121) — fake file server
"""

import asyncio
import json
import random
import socket
import time
from datetime import datetime, timedelta
from pathlib import Path


class AntiDetection:
    """Make the honeypot indistinguishable from a real service."""

    @staticmethod
    async def realistic_delay(service="db"):
        """Simulate realistic response latency."""
        delays = {
            "db": (0.005, 0.08),
            "redis": (0.001, 0.005),
            "http": (0.01, 0.15),
            "ssh": (0.05, 0.3),
            "ftp": (0.02, 0.1),
        }
        lo, hi = delays.get(service, (0.01, 0.1))
        if random.random() < 0.05:
            hi *= 5
        await asyncio.sleep(random.uniform(lo, hi))

    @staticmethod
    def add_imperfections(data):
        """Add realistic imperfections — real DBs have messy data."""
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    AntiDetection._mess_up(item)
        elif isinstance(data, dict):
            AntiDetection._mess_up(data)
        return data

    @staticmethod
    def _mess_up(record):
        """Human-like imperfections in a record."""
        # 10%: null/empty field
        if random.random() < 0.10:
            keys = [k for k in record if k not in ("id", "email")]
            if keys:
                record[random.choice(keys)] = random.choice([None, "", "N/A"])

        # 5%: typo in name
        if "first_name" in record and random.random() < 0.05:
            n = record["first_name"]
            if len(n) > 3:
                p = random.randint(1, len(n)-2)
                record["first_name"] = n[:p] + n[p+1] + n[p] + n[p+2:]

        # 15%: inconsistent date format
        if "created_at" in record and random.random() < 0.15:
            record["created_at"] = record["created_at"].replace("T", " ").replace("-", "/")

        # 7%: extra whitespace
        for key in list(record.keys()):
            if isinstance(record[key], str) and random.random() < 0.07:
                record[key] = "  " + record[key] + " "

        # 2%: legacy field
        if random.random() < 0.02:
            record["_legacy_id"] = random.randint(10000, 99999)

    @staticmethod
    def db_error():
        """Occasionally return DB error instead of data — 3% chance."""
        if random.random() < 0.03:
            return random.choice([
                b"ERROR: connection to server was reset\n",
                b"ERROR: deadlock detected\nDETAIL: Process 12345 waits for ShareLock\n",
                b"ERROR: canceling statement due to statement timeout\n",
                b"FATAL: too many connections for role \"app_service\"\n",
                b"ERROR: relation \"users_backup\" does not exist\n",
            ])
        return None

    @staticmethod
    def vary_count():
        """Different record count each time — real DBs grow."""
        return random.randint(3, 25)

    @staticmethod
    def track_mac(ip):
        """Track attacker by MAC for IP-hoppers."""
        try:
            out = subprocess.check_output(["arp", "-a", ip], timeout=2, stderr=subprocess.DEVNULL
            ).decode("utf-8", errors="replace")
            import re as _re
            m = _re.search(r'([0-9a-f]{2}[-:][0-9a-f]{2}[-:][0-9a-f]{2}[-:][0-9a-f]{2}[-:][0-9a-f]{2}[-:][0-9a-f]{2})', out, _re.I)
            return m.group(1) if m else None
        except Exception:
            return None


class FakeDataGenerator:
    """Generate realistic-looking fake data for honeypots."""

    FIRST_NAMES = ["Emma", "Liam", "Olivia", "Noah", "Ava", "Elijah", "Sophia", "Lucas",
                   "Mia", "Alexander", "Charlotte", "Benjamin", "Amelia", "James", "Harper",
                   "Sebastian", "Evelyn", "Daniel", "Luna", "Matthew", "Ella", "Henry",
                   "Scarlett", "Michael", "Victoria", "Thomas", "Grace", "David", "Chloe",
                   "Felix", "Marie", "Leon", "Anna", "Paul", "Laura", "Max", "Julia",
                   "Lukas", "Sophie", "Jonas", "Lena", "Tim", "Sarah", "Jan", "Lisa"]

    LAST_NAMES = ["Mueller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner",
                  "Becker", "Schulz", "Hoffmann", "Koch", "Richter", "Klein", "Wolf",
                  "Neumann", "Schwarz", "Braun", "Krueger", "Hofmann", "Hartmann",
                  "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
                  "Davis", "Rodriguez", "Martinez", "Anderson", "Taylor", "Thomas"]

    COMPANIES = ["TechVenture GmbH", "DataFlow AG", "CloudNine Solutions", "SecureNet Ltd",
                 "InnovateTech", "DigitalWorks", "CyberShield", "ByteForge",
                 "NeuralPath GmbH", "QuantumLeap AG", "AlphaStream", "CoreLogic"]

    DEPARTMENTS = ["Engineering", "Sales", "Marketing", "Finance", "HR", "Legal",
                   "Operations", "Support", "Research", "Management"]

    def fake_user(self, user_id):
        first = random.choice(self.FIRST_NAMES)
        last = random.choice(self.LAST_NAMES)
        company = random.choice(self.COMPANIES)
        dept = random.choice(self.DEPARTMENTS)
        created = datetime.now() - timedelta(days=random.randint(30, 1500))

        return {
            "id": user_id,
            "email": f"{first.lower()}.{last.lower()}@{company.lower().replace(' ', '').replace('gmbh','').replace('ag','')}.de",
            "first_name": first,
            "last_name": last,
            "password_hash": f"$2b$12${self._random_hash()}",
            "role": random.choice(["admin", "user", "manager", "viewer"]),
            "department": dept,
            "company": company,
            "phone": f"+49 {random.randint(151,179)} {random.randint(1000000,9999999)}",
            "created_at": created.isoformat()[:19],
            "last_login": (datetime.now() - timedelta(hours=random.randint(1, 720))).isoformat()[:19],
            "is_active": random.random() > 0.1,
            "mfa_enabled": random.random() > 0.6,
            "api_key": f"sk_{self._random_hex(32)}",
        }

    def fake_session(self):
        return {
            "session_id": self._random_hex(32),
            "user_id": random.randint(1, 500),
            "ip": f"{random.randint(10,192)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}",
            "user_agent": random.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/131.0.0.0",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X) Safari/605.1.15",
                "Mozilla/5.0 (X11; Linux x86_64) Firefox/134.0",
            ]),
            "created": (datetime.now() - timedelta(minutes=random.randint(1, 1440))).isoformat()[:19],
            "expires": (datetime.now() + timedelta(hours=random.randint(1, 24))).isoformat()[:19],
        }

    def fake_transaction(self, tx_id):
        return {
            "id": tx_id,
            "user_id": random.randint(1, 500),
            "amount": round(random.uniform(9.99, 4999.99), 2),
            "currency": random.choice(["EUR", "USD", "GBP", "CHF"]),
            "status": random.choice(["completed", "pending", "failed", "refunded"]),
            "payment_method": random.choice(["credit_card", "paypal", "bank_transfer", "crypto"]),
            "card_last4": f"{random.randint(1000,9999)}",
            "created_at": (datetime.now() - timedelta(days=random.randint(1, 365))).isoformat()[:19],
        }

    def fake_config(self):
        return {
            "database": {
                "host": "db-primary.internal",
                "port": 5432,
                "name": "production",
                "user": "app_service",
                "password": f"Pr0d_{self._random_hex(16)}!",
            },
            "redis": {"host": "redis.internal", "port": 6379, "password": self._random_hex(24)},
            "aws": {
                "access_key": f"AKIA{self._random_hex(16).upper()}",
                "secret_key": self._random_hex(40),
                "region": "eu-central-1",
                "s3_bucket": "prod-data-backups",
            },
            "stripe": {"secret_key": f"sk_live_{self._random_hex(24)}"},
            "jwt_secret": self._random_hex(64),
            "encryption_key": self._random_hex(32),
        }

    @staticmethod
    def _random_hash():
        return ''.join(random.choices("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789./", k=53))

    @staticmethod
    def _random_hex(length):
        return ''.join(random.choices("0123456789abcdef", k=length))


class HoneypotServer:
    """Runs fake services and logs all connection attempts."""

    # Escalation levels per IP
    IMMUNE_LEVELS = {
        1: "TROLL",      # First contact — fun message + log
        2: "BLOCK",      # Second attempt — firewall block + notification
        3: "RECON",      # Third attempt — reverse scan the attacker
        5: "COUNTER",    # Persistent — active counter-measures
    }

    def __init__(self, log_dir=None, notify=True):
        self.log_dir = Path(log_dir or "honeypot_logs")
        self.log_dir.mkdir(exist_ok=True)
        self.alerts = []
        self.connections = []
        self.fake_data = FakeDataGenerator()
        self.running = False
        self.notify = notify
        self._alerted_ips = set()
        self._ip_attempt_count = {}  # IP → number of connection attempts

    def _log_connection(self, service, client_addr, data_sent=0):
        """Log a connection attempt — this is the ALERT."""
        entry = {
            "timestamp": datetime.now().isoformat()[:19],
            "service": service,
            "client_ip": client_addr[0],
            "client_port": client_addr[1],
            "data_sent": data_sent,
        }
        self.connections.append(entry)
        self.alerts.append(entry)

        ip = client_addr[0]

        # Whitelist — these are NOT intruders
        whitelisted = (
            ip in ("127.0.0.1", "::1")                    # Localhost
            or ip.startswith("172.17.")                     # Docker default bridge
            or ip.startswith("172.18.")                     # Docker network
            or ip.startswith("172.19.")                     # Docker network
            or ip.startswith("172.20.")                     # Docker/WSL
            or ip.startswith("172.21.")                     # Docker network
            or ip.startswith("100.64.")                     # VPN internal (CGNAT)
            or ip.startswith("192.168.56.")                 # VirtualBox host-only
            or ip == "0.0.0.0"
        )

        if whitelisted:
            return  # Silent — don't log, don't alert, don't block

        is_localhost = False  # Already filtered above
        print(f"  [HONEYPOT] !! {service} connection from {ip}:{client_addr[1]}", flush=True)

        # Append to log file
        log_file = self.log_dir / f"honeypot_{datetime.now().strftime('%Y%m%d')}.json"
        try:
            existing = json.loads(log_file.read_text()) if log_file.exists() else []
            existing.append(entry)
            log_file.write_text(json.dumps(existing, indent=2))
        except Exception:
            pass

        # Track attempts per IP + MAC and escalate response
        if not is_localhost:
            ip = client_addr[0]

            # Also track by MAC (catches IP-hoppers)
            mac = AntiDetection.track_mac(ip)
            if mac:
                entry["client_mac"] = mac
                # If we've seen this MAC before under different IP — same attacker!
                for prev in self.connections[:-1]:
                    if prev.get("client_mac") == mac and prev["client_ip"] != ip:
                        old_count = self._ip_attempt_count.get(prev["client_ip"], 0)
                        self._ip_attempt_count[ip] = self._ip_attempt_count.get(ip, 0) + old_count
                        print(f"  [IMMUNE] IP-HOPPER detected! {ip} = {prev['client_ip']} (MAC {mac})", flush=True)
                        break

            self._ip_attempt_count[ip] = self._ip_attempt_count.get(ip, 0) + 1
            attempts = self._ip_attempt_count[ip]

            # Determine immune level
            level = 1
            for threshold in sorted(self.IMMUNE_LEVELS.keys()):
                if attempts >= threshold:
                    level = threshold

            level_name = self.IMMUNE_LEVELS.get(level, "TROLL")
            entry["immune_level"] = level_name
            entry["attempt_number"] = attempts

            if level_name == "TROLL" or ip not in self._alerted_ips:
                print(f"  [IMMUNE] Level {level_name} for {ip} (attempt #{attempts})", flush=True)

            if ip not in self._alerted_ips:
                self._alerted_ips.add(ip)
                asyncio.ensure_future(self._send_notification(entry))
            elif level_name == "COUNTER" and attempts == 5:
                # Escalate to counter on 5th attempt
                asyncio.ensure_future(self._counter_exploit(entry))

    IMMUNE_RESPONSES = [
        # Friendly
        "Hi whats happening mate? :) Driving Motor cycles must be fun :) you might want to invest in me. :)",
        "Hey there! Nice port scan. Want a coffee while you wait? I already know your IP btw ;)",
        "Welcome! You've reached the honeypot. Your visit has been logged, timestamped, and forwarded. Have a great day!",
        "Oh hey! Looking for something? All the data here is fake. But your IP in my logs is very real :)",
        "Knock knock. Who's there? Your IP address. Your IP address who? Your IP address that's now in my security report :D",
        # Trolling
        "ERROR 418: I'm a teapot. Also I'm a honeypot. Your move.",
        "Congratulations! You're the 1,000,000th hacker! Click here to claim your prize: [LOGGED]",
        "sudo make me a sandwich. Oh wait, this is MY server. Your sandwich is being forwarded to CERT.",
        "All your base are belong to us. JK, all YOUR base (IP) are belong to our logs now.",
        "Fun fact: The average honeypot catches 3 script kiddies per day. You're today's lucky number!",
        # Sassy
        "I see you found my PostgreSQL. The password is 'try-harder'. The data is faker than my ex's promises.",
        "Nice nmap skills! Did you learn that from a YouTube tutorial? Asking for my incident report.",
        "You're scanning ports like it's 2005. At least use Rust-based tools, we're in 2026.",
        "Pro tip: Real databases don't greet you with fake AWS keys. But thanks for the connection metadata!",
        "Your IP has been added to my 'people who owe me a beer' list. Payment in Monero accepted.",
    ]

    def _get_immune_response(self, service):
        """Get a fun response for the attacker based on service type."""
        base = random.choice(self.IMMUNE_RESPONSES)

        # Add service-specific flavor
        extras = {
            "PostgreSQL": "\n\n-- PS: SELECT * FROM real_hackers WHERE skill_level > 'script_kiddie'; -- 0 rows returned",
            "Redis": "\r\n+BTW your IP is now cached forever. No TTL. No EXPIRE. Just vibes.\r\n",
            "SSH": "\r\nPermission denied (publickey,honeypot,laughter).\r\n",
            "FTP": "\r\n230-Oh you actually logged in? Everything here is fake. Including this message. Or is it?\r\n",
            "HTTP": "\n\n{\"message\": \"All data on this server is generated. Your visit is not.\", \"your_ip\": \"LOGGED\"}",
        }

        for svc_key, extra in extras.items():
            if svc_key in service:
                return base + extra

        return base

    async def _send_notification(self, entry):
        """Send alert via all configured channels (Telegram, Slack, Desktop)."""
        service = entry["service"]
        ip = entry["client_ip"]
        ts = entry["timestamp"]

        title = f"HONEYPOT ALERT: {service} intrusion from {ip}"
        details = (
            f"Service: {service}\n"
            f"Attacker IP: {ip}:{entry['client_port']}\n"
            f"Time: {ts}\n"
            f"Data sent: {entry.get('data_sent', 0)} bytes\n\n"
            f"Someone is probing your network!"
        )

        # 1. Try Telegram/Slack via alerter
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent / "alerter"))
            from alerter import send_alert
            await send_alert("CRITICAL", title, details, source="Honeypot")
            print(f"  [NOTIFY] Alert sent via Telegram/Slack", flush=True)
        except Exception as e:
            print(f"  [NOTIFY] Alerter not available: {e}", flush=True)

        # 2. Windows Toast notification (always works)
        try:
            import subprocess
            subprocess.Popen(
                ["powershell", "-Command",
                 f'[System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms") | Out-Null; '
                 f'$n = New-Object System.Windows.Forms.NotifyIcon; '
                 f'$n.Icon = [System.Drawing.SystemIcons]::Warning; '
                 f'$n.Visible = $true; '
                 f'$n.ShowBalloonTip(10000, "HONEYPOT ALERT", '
                 f'"{service} connection from {ip}", '
                 f'[System.Windows.Forms.ToolTipIcon]::Error); '
                 f'Start-Sleep -Seconds 12; $n.Dispose()'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            print(f"  [NOTIFY] Windows toast notification sent", flush=True)
        except Exception:
            pass

        # 3. AUTO-BLOCK — Add attacker IP to Windows Firewall
        try:
            rule_name = f"HONEYPOT_BLOCK_{ip.replace('.', '_')}"
            subprocess.run(
                ["netsh", "advfirewall", "firewall", "add", "rule",
                 f"name={rule_name}",
                 "dir=in", "action=block",
                 f"remoteip={ip}",
                 "protocol=any",
                 "enable=yes"],
                timeout=5, capture_output=True,
            )
            print(f"  [IMMUNE] BLOCKED {ip} in Windows Firewall (rule: {rule_name})", flush=True)

            # Also block outbound to prevent data exfil to attacker
            subprocess.run(
                ["netsh", "advfirewall", "firewall", "add", "rule",
                 f"name={rule_name}_OUT",
                 "dir=out", "action=block",
                 f"remoteip={ip}",
                 "protocol=any",
                 "enable=yes"],
                timeout=5, capture_output=True,
            )
        except Exception as e:
            print(f"  [IMMUNE] Firewall block failed (need admin): {e}", flush=True)

        # 4. REVERSE RECON — gather info about the attacker (passive, no exploit)
        try:
            recon = {"ip": ip}

            # Reverse DNS
            try:
                hostname = socket.gethostbyaddr(ip)[0]
                recon["hostname"] = hostname
                print(f"  [IMMUNE] Attacker hostname: {hostname}", flush=True)
            except Exception:
                recon["hostname"] = "unknown"

            # MAC address from ARP
            try:
                arp_out = subprocess.check_output(
                    ["arp", "-a", ip], timeout=3, stderr=subprocess.DEVNULL,
                ).decode("utf-8", errors="replace")
                import re
                mac_match = re.search(r'([0-9a-f]{2}[-:][0-9a-f]{2}[-:][0-9a-f]{2}[-:][0-9a-f]{2}[-:][0-9a-f]{2}[-:][0-9a-f]{2})', arp_out, re.I)
                if mac_match:
                    recon["mac"] = mac_match.group(1)
                    # MAC vendor lookup (first 3 octets)
                    mac_prefix = recon["mac"][:8].upper().replace("-", ":")
                    print(f"  [IMMUNE] Attacker MAC: {recon['mac']} (prefix {mac_prefix})", flush=True)
            except Exception:
                pass

            # Quick port scan — see what the attacker has open (top 5 ports only)
            open_ports = []
            for port in [22, 80, 443, 3389, 8080]:
                try:
                    s = socket.socket()
                    s.settimeout(0.5)
                    if s.connect_ex((ip, port)) == 0:
                        open_ports.append(port)
                    s.close()
                except Exception:
                    pass
            if open_ports:
                recon["open_ports"] = open_ports
                print(f"  [IMMUNE] Attacker open ports: {open_ports}", flush=True)

            # NetBIOS name (Windows machines)
            try:
                nb_out = subprocess.check_output(
                    ["nbtstat", "-A", ip], timeout=3, stderr=subprocess.DEVNULL,
                ).decode("utf-8", errors="replace")
                for line in nb_out.split("\n"):
                    if "<00>" in line and "UNIQUE" in line:
                        nb_name = line.split("<")[0].strip()
                        recon["netbios_name"] = nb_name
                        print(f"  [IMMUNE] Attacker NetBIOS name: {nb_name}", flush=True)
                        break
            except Exception:
                pass

            # Save recon data
            entry["attacker_recon"] = recon

            # Log recon to file
            recon_file = self.log_dir / f"attacker_{ip.replace('.', '_')}.json"
            recon_file.write_text(json.dumps(recon, indent=2))
            print(f"  [IMMUNE] Recon saved to {recon_file}", flush=True)

        except Exception:
            pass

        # 5. Console beep
        try:
            print("\a", end="", flush=True)
        except Exception:
            pass

    async def _counter_exploit(self, entry):
        """Level COUNTER — active counter-measures against persistent attacker.
        Only triggered after 5+ attempts from the same IP (they're not giving up)."""
        ip = entry["client_ip"]
        print(f"\n  [COUNTER] !! ESCALATING against persistent attacker {ip} !!", flush=True)

        import subprocess
        result = {"ip": ip, "actions": []}

        # 1. Full port scan of attacker
        print(f"  [COUNTER] Full port scan of {ip}...", flush=True)
        open_ports = []
        for port in [21, 22, 23, 25, 53, 80, 110, 135, 139, 143, 443, 445,
                     993, 995, 1433, 1521, 3306, 3389, 5432, 5900, 6379,
                     8080, 8443, 9200, 27017]:
            try:
                s = socket.socket()
                s.settimeout(0.3)
                if s.connect_ex((ip, port)) == 0:
                    open_ports.append(port)
                s.close()
            except Exception:
                pass

        if open_ports:
            result["actions"].append(f"Port scan: {open_ports}")
            print(f"  [COUNTER] Open ports on attacker: {open_ports}", flush=True)

        # 2. Banner grab on open ports
        for port in open_ports[:5]:
            try:
                s = socket.socket()
                s.settimeout(2)
                s.connect((ip, port))
                if port in (80, 8080, 8443):
                    s.send(b"GET / HTTP/1.0\r\nHost: target\r\n\r\n")
                elif port == 22:
                    pass  # SSH sends banner automatically
                elif port == 21:
                    pass  # FTP sends banner automatically
                banner = s.recv(1024).decode("utf-8", errors="replace").strip()[:200]
                s.close()
                if banner:
                    result["actions"].append(f"Banner port {port}: {banner[:100]}")
                    print(f"  [COUNTER] Banner {port}: {banner[:80]}", flush=True)
            except Exception:
                pass

        # 3. SMB/NetBIOS probe (Windows machine identification)
        try:
            nb_out = subprocess.check_output(
                ["nbtstat", "-A", ip], timeout=5, stderr=subprocess.DEVNULL,
            ).decode("utf-8", errors="replace")
            names = []
            for line in nb_out.split("\n"):
                if "<" in line and ">" in line:
                    names.append(line.strip()[:60])
            if names:
                result["actions"].append(f"NetBIOS names: {names[:5]}")
                print(f"  [COUNTER] NetBIOS: {names[:3]}", flush=True)
        except Exception:
            pass

        # 4. Flood attacker's open ports with honeypot messages
        immune_msg = self._get_immune_response("COUNTER")
        counter_msg = (
            f"\n\n===================================\n"
            f"  HONEYPOT COUNTER-RESPONSE\n"
            f"  Your IP: {ip}\n"
            f"  Your open ports: {open_ports}\n"
            f"  Attempt #{entry.get('attempt_number', '?')}\n"
            f"  You have been logged, blocked,\n"
            f"  and scanned back.\n"
            f"  {immune_msg}\n"
            f"===================================\n"
        ).encode()

        for port in open_ports[:3]:
            try:
                s = socket.socket()
                s.settimeout(2)
                s.connect((ip, port))
                s.send(counter_msg)
                s.close()
                result["actions"].append(f"Counter message sent to port {port}")
                print(f"  [COUNTER] Message sent to {ip}:{port}", flush=True)
            except Exception:
                pass

        # 5. Log everything
        counter_file = self.log_dir / f"counter_{ip.replace('.', '_')}_{int(time.time())}.json"
        counter_file.write_text(json.dumps(result, indent=2))
        print(f"  [COUNTER] Full report saved to {counter_file}", flush=True)

        # 6. Send CRITICAL alert
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent / "alerter"))
            from alerter import send_alert
            await send_alert(
                "CRITICAL",
                f"COUNTER-EXPLOIT triggered against {ip}",
                f"Attacker tried {entry.get('attempt_number', '?')} times.\n"
                f"Open ports on attacker: {open_ports}\n"
                f"Actions taken: {result['actions']}",
                source="Honeypot Counter",
            )
        except Exception:
            pass

    # ================================================================
    # FAKE POSTGRESQL
    # ================================================================

    async def start_fake_postgres(self, port=5433):
        """Fake PostgreSQL that serves realistic query results."""

        async def handle_pg(reader, writer):
            addr = writer.get_extra_info("peername")
            self._log_connection("PostgreSQL", addr)

            # Send PostgreSQL startup response
            # AuthenticationOk
            writer.write(b'R\x00\x00\x00\x08\x00\x00\x00\x00')
            # ReadyForQuery
            writer.write(b'Z\x00\x00\x00\x05I')
            await writer.drain()

            try:
                while True:
                    data = await asyncio.wait_for(reader.read(4096), timeout=30)
                    if not data:
                        break

                    query = data.decode("utf-8", errors="replace").lower()

                    # Realistic DB delay
                    await AntiDetection.realistic_delay("db")

                    # 3% chance of DB error
                    db_err = AntiDetection.db_error()
                    if db_err:
                        writer.write(b'E' + len(db_err).to_bytes(4, 'big') + db_err)
                        writer.write(b'Z\x00\x00\x00\x05I')
                        await writer.drain()
                        continue

                    # Respond to common queries with imperfect fake data
                    if "select" in query and "users" in query:
                        count = AntiDetection.vary_count()
                        users = [self.fake_data.fake_user(i) for i in range(1, count + 1)]
                        AntiDetection.add_imperfections(users)
                        response = json.dumps(users, indent=2).encode()
                    elif "select" in query and "transaction" in query:
                        txs = [self.fake_data.fake_transaction(i) for i in range(1, 6)]
                        response = json.dumps(txs, indent=2).encode()
                    elif "show" in query or "\\d" in query:
                        response = b"users\ntransactions\nsessions\napi_keys\naudit_log\nconfigs\n"
                    elif "select" in query and "config" in query:
                        response = json.dumps(self.fake_data.fake_config(), indent=2).encode()
                    else:
                        response = b"OK\n"

                    self._log_connection("PostgreSQL-Query", addr, len(response))

                    # Send as DataRow
                    writer.write(b'D' + len(response).to_bytes(4, 'big') + response)
                    # After data, send immune response
                    immune = self._get_immune_response("PostgreSQL").encode()
                    writer.write(b'N' + len(immune).to_bytes(4, 'big') + immune)
                    writer.write(b'Z\x00\x00\x00\x05I')  # ReadyForQuery
                    await writer.drain()

            except (asyncio.TimeoutError, ConnectionResetError):
                pass
            finally:
                writer.close()

        server = await asyncio.start_server(handle_pg, "0.0.0.0", port)
        print(f"  [HONEYPOT] Fake PostgreSQL on port {port}", flush=True)
        return server

    # ================================================================
    # FAKE REDIS
    # ================================================================

    async def start_fake_redis(self, port=6399):
        """Fake Redis that serves session data."""

        async def handle_redis(reader, writer):
            addr = writer.get_extra_info("peername")
            self._log_connection("Redis", addr)

            try:
                while True:
                    data = await asyncio.wait_for(reader.read(4096), timeout=30)
                    if not data:
                        break

                    cmd = data.decode("utf-8", errors="replace").strip().upper()
                    await AntiDetection.realistic_delay("redis")

                    if "KEYS" in cmd:
                        # Return fake session keys
                        sessions = [f"session:{self.fake_data._random_hex(16)}" for _ in range(20)]
                        response = "\r\n".join(f"${len(s)}\r\n{s}" for s in sessions)
                        writer.write(f"*{len(sessions)}\r\n{response}\r\n".encode())
                    elif "GET" in cmd:
                        session = self.fake_data.fake_session()
                        val = json.dumps(session)
                        writer.write(f"${len(val)}\r\n{val}\r\n".encode())
                    elif "INFO" in cmd:
                        info = "redis_version:7.0.11\r\nused_memory:4521984\r\nconnected_clients:23\r\ndb0:keys=1547,expires=892\r\n"
                        writer.write(f"${len(info)}\r\n{info}\r\n".encode())
                    elif "CONFIG" in cmd:
                        writer.write(b"+OK\r\n")
                    elif "PING" in cmd:
                        writer.write(b"+PONG\r\n")
                    elif "QUIT" in cmd:
                        immune = self._get_immune_response("Redis")
                        writer.write(f"+{immune}\r\n".encode())
                    else:
                        writer.write(b"+OK\r\n")

                    # After a few commands, send the immune response
                    if len([c for c in self.connections if c["client_ip"] == addr[0] and "Redis" in c["service"]]) >= 3:
                        immune = self._get_immune_response("Redis")
                        writer.write(f"${len(immune)}\r\n{immune}\r\n".encode())

                    self._log_connection("Redis-Command", addr)
                    await writer.drain()

            except (asyncio.TimeoutError, ConnectionResetError):
                pass
            finally:
                writer.close()

        server = await asyncio.start_server(handle_redis, "0.0.0.0", port)
        print(f"  [HONEYPOT] Fake Redis on port {port}", flush=True)
        return server

    # ================================================================
    # FAKE HTTP API
    # ================================================================

    async def start_fake_api(self, port=8888):
        """Fake REST API with realistic endpoints."""

        async def handle_http(reader, writer):
            addr = writer.get_extra_info("peername")
            self._log_connection("HTTP-API", addr)

            try:
                data = await asyncio.wait_for(reader.read(4096), timeout=10)
                request = data.decode("utf-8", errors="replace")
                await AntiDetection.realistic_delay("http")

                first_line = request.split("\n")[0] if request else ""
                method = first_line.split(" ")[0] if " " in first_line else "?"
                path = first_line.split(" ")[1] if len(first_line.split(" ")) > 1 else "/"

                # Route to handlers
                if "/api/users" in path:
                    body = json.dumps([self.fake_data.fake_user(i) for i in range(1, 21)])
                elif "/api/config" in path:
                    body = json.dumps(self.fake_data.fake_config())
                elif "/api/transactions" in path:
                    body = json.dumps([self.fake_data.fake_transaction(i) for i in range(1, 11)])
                elif "/api/sessions" in path:
                    body = json.dumps([self.fake_data.fake_session() for _ in range(15)])
                elif "/health" in path:
                    body = json.dumps({"status": "ok", "version": "2.4.1", "uptime": random.randint(100000, 9999999)})
                elif "/.env" in path:
                    body = "DB_PASSWORD=Pr0d_a8f3e2d1c4b5!\nAWS_SECRET=AKIA7f8e9d0c1b2a3\nJWT_SECRET=super_secret_key_123\n"
                elif "/admin" in path:
                    body = json.dumps({"error": "Authentication required", "login_url": "/admin/login"})
                else:
                    body = json.dumps({
                        "api": "Internal API v2.4",
                        "endpoints": ["/api/users", "/api/config", "/api/transactions",
                                      "/api/sessions", "/health", "/admin"],
                        "docs": "/api/docs",
                    })

                # Add immune response as hidden header + footer
                immune = self._get_immune_response("HTTP")

                response = (f"HTTP/1.1 200 OK\r\n"
                           f"Content-Type: application/json\r\n"
                           f"Content-Length: {len(body)}\r\n"
                           f"Server: nginx/1.24.0\r\n"
                           f"X-Request-ID: {self.fake_data._random_hex(16)}\r\n"
                           f"X-Honeypot: {immune[:80]}\r\n"
                           f"\r\n{body}")

                self._log_connection(f"HTTP-{method}-{path[:30]}", addr, len(body))
                writer.write(response.encode())
                await writer.drain()

            except (asyncio.TimeoutError, ConnectionResetError):
                pass
            finally:
                writer.close()

        server = await asyncio.start_server(handle_http, "0.0.0.0", port)
        print(f"  [HONEYPOT] Fake HTTP API on port {port}", flush=True)
        return server

    # ================================================================
    # FAKE SSH
    # ================================================================

    async def start_fake_ssh(self, port=2222):
        """Fake SSH — serves banner, logs credentials."""

        async def handle_ssh(reader, writer):
            addr = writer.get_extra_info("peername")
            self._log_connection("SSH", addr)

            # Send SSH banner with realistic delay
            await AntiDetection.realistic_delay("ssh")
            writer.write(b"SSH-2.0-OpenSSH_9.6p1 Ubuntu-3ubuntu13\r\n")
            await writer.drain()

            try:
                data = await asyncio.wait_for(reader.read(4096), timeout=15)
                if data:
                    self._log_connection("SSH-Auth-Attempt", addr)
                    # Send immune response disguised as SSH error
                    immune = self._get_immune_response("SSH")
                    writer.write(immune.encode())
                    await writer.drain()
            except (asyncio.TimeoutError, ConnectionResetError):
                pass
            finally:
                writer.close()

        server = await asyncio.start_server(handle_ssh, "0.0.0.0", port)
        print(f"  [HONEYPOT] Fake SSH on port {port}", flush=True)
        return server

    # ================================================================
    # FAKE FTP
    # ================================================================

    async def start_fake_ftp(self, port=2121):
        """Fake FTP with file listing."""

        async def handle_ftp(reader, writer):
            addr = writer.get_extra_info("peername")
            self._log_connection("FTP", addr)

            await AntiDetection.realistic_delay("ftp")
            writer.write(b"220 ProFTPD 1.3.8 Server ready.\r\n")
            await writer.drain()

            try:
                while True:
                    data = await asyncio.wait_for(reader.read(4096), timeout=30)
                    if not data:
                        break

                    cmd = data.decode("utf-8", errors="replace").strip()
                    self._log_connection(f"FTP-{cmd[:20]}", addr)

                    if cmd.upper().startswith("USER"):
                        writer.write(b"331 Password required.\r\n")
                    elif cmd.upper().startswith("PASS"):
                        writer.write(b"230 Login successful.\r\n")
                    elif cmd.upper().startswith("LIST") or cmd.upper().startswith("NLST"):
                        listing = (
                            "drwxr-xr-x  2 admin admin  4096 Mar 31 10:00 backups\r\n"
                            "-rw-r--r--  1 admin admin 15234 Mar 30 22:15 database_dump.sql\r\n"
                            "-rw-r--r--  1 admin admin  4521 Mar 29 14:30 credentials.csv\r\n"
                            "-rw-r--r--  1 admin admin  1024 Mar 28 09:00 .env.production\r\n"
                            "-rw-r--r--  1 admin admin  8192 Mar 27 16:45 api_keys.json\r\n"
                            "drwxr-xr-x  3 admin admin  4096 Mar 26 12:00 ssl_certs\r\n"
                        )
                        writer.write(f"150 Opening data connection.\r\n{listing}226 Transfer complete.\r\n".encode())
                    elif cmd.upper().startswith("QUIT"):
                        immune = self._get_immune_response("FTP")
                        writer.write(f"221 {immune}\r\n".encode())
                        break
                    elif cmd.upper().startswith("RETR"):
                        # They try to download a file — serve the immune response
                        immune = self._get_immune_response("FTP")
                        writer.write(f"150 Opening data.\r\n{immune}\r\n226 Transfer complete.\r\n".encode())
                    else:
                        writer.write(b"200 OK.\r\n")

                    await writer.drain()

            except (asyncio.TimeoutError, ConnectionResetError):
                pass
            finally:
                writer.close()

        server = await asyncio.start_server(handle_ftp, "0.0.0.0", port)
        print(f"  [HONEYPOT] Fake FTP on port {port}", flush=True)
        return server

    # ================================================================
    # ORCHESTRATOR
    # ================================================================

    async def start_all(self, duration=3600):
        """Start all honeypot services."""
        print(f"\n{'='*60}", flush=True)
        print(f"  NETWORK HONEYPOT — Fake Services Active", flush=True)
        print(f"  Duration: {duration}s", flush=True)
        print(f"  Log dir: {self.log_dir}", flush=True)
        print(f"{'='*60}\n", flush=True)

        servers = []
        services = [
            (self.start_fake_postgres, 15432, "PostgreSQL"),
            (self.start_fake_redis, 16379, "Redis"),
            (self.start_fake_api, 18888, "HTTP API"),
            (self.start_fake_ssh, 12222, "SSH"),
            (self.start_fake_ftp, 12121, "FTP"),
        ]
        for start_fn, port, name in services:
            try:
                servers.append(await start_fn(port))
            except OSError as e:
                print(f"  [HONEYPOT] {name} port {port} failed: {e}", flush=True)

        self.running = True
        print(f"\n  [HONEYPOT] All services running. Waiting for connections...\n", flush=True)

        try:
            await asyncio.sleep(duration)
        except KeyboardInterrupt:
            pass

        # Shutdown
        for s in servers:
            s.close()
            await s.wait_closed()

        self.running = False

        # Summary
        print(f"\n{'='*60}", flush=True)
        print(f"  HONEYPOT SUMMARY", flush=True)
        print(f"{'='*60}", flush=True)
        print(f"  Total connections: {len(self.connections)}", flush=True)

        if self.connections:
            by_service = {}
            by_ip = {}
            for c in self.connections:
                svc = c["service"]
                ip = c["client_ip"]
                by_service[svc] = by_service.get(svc, 0) + 1
                by_ip[ip] = by_ip.get(ip, 0) + 1

            print(f"\n  By service:", flush=True)
            for svc, count in sorted(by_service.items(), key=lambda x: -x[1]):
                print(f"    {svc:30s} {count} connections", flush=True)

            print(f"\n  By IP:", flush=True)
            for ip, count in sorted(by_ip.items(), key=lambda x: -x[1]):
                print(f"    {ip:20s} {count} connections", flush=True)
        else:
            print(f"  No connections — network appears clean.", flush=True)

        return {
            "duration": duration,
            "total_connections": len(self.connections),
            "connections": self.connections,
            "alerts": self.alerts,
        }


if __name__ == "__main__":
    import sys

    duration = 300
    notify = True

    for arg in sys.argv[1:]:
        if arg == "--no-notify":
            notify = False
        elif arg.isdigit():
            duration = int(arg)

    honeypot = HoneypotServer(notify=notify)
    print(f"  Notifications: {'ON (Telegram + Slack + Windows Toast)' if notify else 'OFF'}")
    asyncio.run(honeypot.start_all(duration=duration))
