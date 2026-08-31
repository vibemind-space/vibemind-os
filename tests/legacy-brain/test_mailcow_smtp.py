import smtplib
import ssl
from email.mime.text import MIMEText
from email.utils import formataddr

USER = "user@example.com"
PASS = "Felix1234,1234"

# Unsicherer SSL-Context (Self-Signed Cert akzeptieren)
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

attempts = [
    ("localhost", 465, "SSL"),
    ("localhost", 587, "STARTTLS"),
    ("localhost", 25, "PLAIN"),
]

for host, port, mode in attempts:
    print(f"\n--- {host}:{port} ({mode}) ---")
    try:
        if mode == "SSL":
            smtp = smtplib.SMTP_SSL(host, port, timeout=10, context=ctx)
        else:
            smtp = smtplib.SMTP(host, port, timeout=10)
            smtp.ehlo()
            if mode == "STARTTLS":
                smtp.starttls(context=ctx)
                smtp.ehlo()

        smtp.login(USER, PASS)
        print("  LOGIN OK!")

        msg = MIMEText("Test von deinem lokalen Mailcow!", "plain", "utf-8")
        msg["From"] = formataddr(("VibeMind Team", USER))
        msg["To"] = "test@example.com"
        msg["Subject"] = f"Mailcow Local Test ({host}:{port})"

        smtp.sendmail(USER, ["test@example.com"], msg.as_string())
        print("  GESENDET!")
        smtp.quit()
        break
    except Exception as e:
        print(f"  FEHLER: {e}")
