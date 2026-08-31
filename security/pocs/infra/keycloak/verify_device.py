"""
Device & Application Verification Client for Keycloak.

Demonstrates three flows:
1. Device Authorization Grant  — for phones/IoT devices without browser
2. Client Credentials           — for machine-to-machine app verification
3. Token Introspection          — verify any token is legitimate
"""

import time
import requests

KEYCLOAK_URL = "http://localhost:8080"
REALM = "device-verification"
TOKEN_URL = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token"
DEVICE_AUTH_URL = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/auth/device"
INTROSPECT_URL = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token/introspect"


# ---------------------------------------------------------------------------
# 1) Device Authorization Grant — Handy-Verifizierung
# ---------------------------------------------------------------------------
def device_flow_verify(client_id: str = "device-cli"):
    """
    OAuth2 Device Authorization Grant.
    Der User bekommt einen Code, gibt ihn am Handy/Browser ein,
    und das Geraet erhaelt danach ein Access Token.
    """
    print("\n=== Device Authorization Grant ===")

    # Step 1: Request device code
    resp = requests.post(DEVICE_AUTH_URL, data={"client_id": client_id})
    resp.raise_for_status()
    data = resp.json()

    device_code = data["device_code"]
    user_code = data["user_code"]
    verification_uri = data["verification_uri_complete"]
    interval = data.get("interval", 5)
    expires_in = data.get("expires_in", 600)

    print(f"  User Code:        {user_code}")
    print(f"  Verification URL: {verification_uri}")
    print(f"  Expires in:       {expires_in}s")
    print(f"\n  --> Oeffne die URL im Browser und gib den Code ein.\n")

    # Step 2: Poll for token
    deadline = time.time() + expires_in
    while time.time() < deadline:
        time.sleep(interval)
        token_resp = requests.post(TOKEN_URL, data={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": client_id,
            "device_code": device_code,
        })

        if token_resp.status_code == 200:
            tokens = token_resp.json()
            print("  Device verifiziert!")
            print(f"  Access Token:  {tokens['access_token'][:50]}...")
            print(f"  Token Type:    {tokens['token_type']}")
            print(f"  Expires in:    {tokens['expires_in']}s")
            return tokens

        error = token_resp.json().get("error", "")
        if error == "authorization_pending":
            print("  ...warte auf User-Eingabe...")
        elif error == "slow_down":
            interval += 1
        else:
            print(f"  Fehler: {token_resp.json()}")
            return None

    print("  Timeout — Device nicht verifiziert.")
    return None


# ---------------------------------------------------------------------------
# 2) Client Credentials — App-Verifizierung (Machine-to-Machine)
# ---------------------------------------------------------------------------
def verify_application(client_id: str, client_secret: str):
    """
    OAuth2 Client Credentials Grant.
    Verifiziert, dass eine Applikation legitim ist.
    """
    print("\n=== Application Verification (Client Credentials) ===")

    resp = requests.post(TOKEN_URL, data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    })

    if resp.status_code == 200:
        tokens = resp.json()
        print(f"  App '{client_id}' verifiziert!")
        print(f"  Access Token:  {tokens['access_token'][:50]}...")
        print(f"  Expires in:    {tokens['expires_in']}s")
        return tokens
    else:
        print(f"  App-Verifizierung fehlgeschlagen: {resp.json()}")
        return None


# ---------------------------------------------------------------------------
# 3) Token Introspection — Token pruefen
# ---------------------------------------------------------------------------
def introspect_token(token: str, client_id: str, client_secret: str):
    """
    Prueft ob ein Token gueltig ist.
    Nutze das um eingehende Requests zu verifizieren.
    """
    print("\n=== Token Introspection ===")

    resp = requests.post(INTROSPECT_URL, data={
        "token": token,
        "client_id": client_id,
        "client_secret": client_secret,
    })

    if resp.status_code == 200:
        info = resp.json()
        active = info.get("active", False)
        print(f"  Token aktiv:   {active}")
        if active:
            print(f"  Client:        {info.get('client_id', 'N/A')}")
            print(f"  Scope:         {info.get('scope', 'N/A')}")
            print(f"  Token Type:    {info.get('token_type', 'N/A')}")
        return info
    else:
        print(f"  Introspection fehlgeschlagen: {resp.text}")
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Keycloak Device & App Verification Demo")
    print("=" * 50)

    # 1) App verifizieren (Backend-Service)
    app_tokens = verify_application(
        client_id="backend-service",
        client_secret="CHANGE_ME_backend_secret",
    )

    # 2) Token pruefen
    if app_tokens:
        introspect_token(
            token=app_tokens["access_token"],
            client_id="backend-service",
            client_secret="CHANGE_ME_backend_secret",
        )

    # 3) Device Flow starten (interaktiv)
    print("\n" + "=" * 50)
    answer = input("Device Flow starten? (j/n): ")
    if answer.lower() == "j":
        device_flow_verify()
