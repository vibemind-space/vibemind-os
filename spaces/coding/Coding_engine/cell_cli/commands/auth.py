"""
Authentication commands.
"""

import json
import os
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlparse
import time

import click
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from ..config import get_config, save_config, get_credentials, save_credentials, clear_credentials

console = Console()


@click.group()
def auth():
    """Authentication commands."""
    pass


@auth.command()
@click.option("--provider", "-p", type=click.Choice(["github", "google"]),
              default="github", help="OAuth provider")
@click.pass_context
def login(ctx, provider: str):
    """
    Authenticate with Cell Colony.

    Opens browser for OAuth authentication.
    """
    api_url = ctx.obj.get("api_url", "http://localhost:8000")

    console.print(f"\n[bold]Logging in with {provider.title()}...[/bold]\n")

    # Start local callback server
    auth_result = {"token": None, "error": None}
    callback_received = {"done": False}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/callback":
                params = parse_qs(parsed.query)

                if "token" in params:
                    auth_result["token"] = params["token"][0]
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"""
                        <html><body style="font-family: sans-serif; text-align: center; padding: 50px;">
                        <h1>Authentication Successful!</h1>
                        <p>You can close this window and return to the terminal.</p>
                        </body></html>
                    """)
                elif "error" in params:
                    auth_result["error"] = params.get("error_description", params["error"])[0]
                    self.send_response(400)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.wfile.write(f"""
                        <html><body style="font-family: sans-serif; text-align: center; padding: 50px;">
                        <h1>Authentication Failed</h1>
                        <p>{auth_result['error']}</p>
                        </body></html>
                    """.encode())

                callback_received["done"] = True

        def log_message(self, format, *args):
            pass  # Suppress server logs

    # Find available port
    server = HTTPServer(("localhost", 0), CallbackHandler)
    port = server.server_address[1]
    callback_url = f"http://localhost:{port}/callback"

    # Start server in background
    server_thread = Thread(target=server.handle_request)
    server_thread.start()

    # Build auth URL
    auth_url = f"{api_url}/auth/{provider}/authorize?redirect_uri={callback_url}"

    console.print(f"Opening browser for authentication...")
    console.print(f"[dim]If browser doesn't open, visit: {auth_url}[/dim]\n")

    # Open browser
    webbrowser.open(auth_url)

    # Wait for callback
    with console.status("[bold green]Waiting for authentication..."):
        timeout = 120  # 2 minutes
        start = time.time()
        while not callback_received["done"] and (time.time() - start) < timeout:
            time.sleep(0.5)

    server_thread.join(timeout=1)

    if auth_result["error"]:
        console.print(f"[red]Authentication failed: {auth_result['error']}[/red]")
        raise SystemExit(1)

    if not auth_result["token"]:
        console.print("[red]Authentication timed out[/red]")
        raise SystemExit(1)

    # Fetch user info
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{api_url}/auth/me",
                headers={"Authorization": f"Bearer {auth_result['token']}"}
            )
            response.raise_for_status()
            user_info = response.json()
    except Exception as e:
        console.print(f"[red]Failed to fetch user info: {e}[/red]")
        raise SystemExit(1)

    # Save credentials
    save_credentials({
        "token": auth_result["token"],
        "user": user_info,
        "provider": provider,
    })

    console.print(Panel(
        f"[green]Successfully logged in as [bold]{user_info.get('name', user_info.get('email'))}[/bold][/green]\n\n"
        f"Email: {user_info.get('email')}\n"
        f"Provider: {provider.title()}",
        title="Authentication Successful",
    ))


@auth.command()
@click.pass_context
def logout(ctx):
    """Log out and clear credentials."""
    creds = get_credentials()

    if not creds:
        console.print("[yellow]Not currently logged in[/yellow]")
        return

    user_name = creds.get("user", {}).get("name", "Unknown")
    clear_credentials()

    console.print(f"[green]Logged out successfully (was: {user_name})[/green]")


@auth.command()
@click.pass_context
def status(ctx):
    """Show current authentication status."""
    creds = get_credentials()

    if not creds:
        console.print("[yellow]Not logged in[/yellow]")
        console.print("\nRun [bold]cell login[/bold] to authenticate.")
        return

    user = creds.get("user", {})
    console.print(Panel(
        f"[green]Logged in[/green]\n\n"
        f"User: [bold]{user.get('name', 'N/A')}[/bold]\n"
        f"Email: {user.get('email', 'N/A')}\n"
        f"Provider: {creds.get('provider', 'N/A').title()}\n"
        f"Tenants: {len(user.get('tenant_ids', []))}",
        title="Authentication Status",
    ))


@auth.command()
@click.pass_context
def token(ctx):
    """Print current access token (for debugging)."""
    creds = get_credentials()

    if not creds:
        console.print("[red]Not logged in[/red]")
        raise SystemExit(1)

    console.print(creds.get("token", ""))


@auth.command()
@click.argument("tenant_slug")
@click.pass_context
def switch(ctx, tenant_slug: str):
    """Switch active tenant context."""
    api_url = ctx.obj.get("api_url", "http://localhost:8000")
    creds = get_credentials()

    if not creds:
        console.print("[red]Not logged in[/red]")
        raise SystemExit(1)

    # Find tenant by slug
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{api_url}/api/v1/portal/tenants",
                headers={"Authorization": f"Bearer {creds['token']}"}
            )
            response.raise_for_status()
            tenants = response.json()
    except Exception as e:
        console.print(f"[red]Failed to fetch tenants: {e}[/red]")
        raise SystemExit(1)

    matching = [t for t in tenants if t["slug"] == tenant_slug]
    if not matching:
        console.print(f"[red]Tenant '{tenant_slug}' not found[/red]")
        console.print("\nAvailable tenants:")
        for t in tenants:
            console.print(f"  - {t['slug']} ({t['name']})")
        raise SystemExit(1)

    tenant = matching[0]

    # Update config
    config = get_config()
    config["active_tenant"] = tenant["id"]
    config["active_tenant_slug"] = tenant["slug"]
    save_config(config)

    console.print(f"[green]Switched to tenant: [bold]{tenant['name']}[/bold] ({tenant['slug']})[/green]")
