"""
Cell management commands.
"""

import json
import os
from pathlib import Path
from typing import Optional

import click
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.syntax import Syntax

from ..config import get_credentials, get_config, CELL_MANIFEST_FILE

console = Console()


def get_auth_headers():
    """Get authorization headers."""
    creds = get_credentials()
    if not creds:
        console.print("[red]Not logged in. Run 'cell login' first.[/red]")
        raise SystemExit(1)
    return {"Authorization": f"Bearer {creds['token']}"}


@click.group()
def cells():
    """Cell management commands."""
    pass


@cells.command()
@click.argument("name", required=False)
@click.option("--namespace", "-n", help="Cell namespace (e.g., @myorg/my-cell)")
@click.option("--description", "-d", help="Cell description")
@click.option("--category", "-c", type=click.Choice([
    "api", "frontend", "backend", "database", "auth",
    "storage", "messaging", "analytics", "ai_ml", "utility", "other"
]), default="other", help="Cell category")
@click.pass_context
def init(ctx, name: Optional[str], namespace: Optional[str], description: Optional[str], category: str):
    """
    Initialize a new cell in the current directory.

    Creates a cell.json manifest file.
    """
    cwd = Path.cwd()
    manifest_path = cwd / CELL_MANIFEST_FILE

    if manifest_path.exists():
        if not Confirm.ask(f"[yellow]{CELL_MANIFEST_FILE} already exists. Overwrite?[/yellow]"):
            console.print("Aborted.")
            return

    # Interactive prompts if not provided
    if not name:
        default_name = cwd.name.lower().replace(" ", "-").replace("_", "-")
        name = Prompt.ask("Cell name", default=default_name)

    if not namespace:
        config = get_config()
        tenant_slug = config.get("active_tenant_slug", "my-org")
        default_ns = f"@{tenant_slug}/{name}"
        namespace = Prompt.ask("Namespace", default=default_ns)

    if not description:
        description = Prompt.ask("Description", default=f"A {category} cell")

    # Create manifest
    manifest = {
        "name": name,
        "namespace": namespace,
        "version": "0.1.0",
        "description": description,
        "category": category,
        "tags": [],
        "license": "MIT",
        "author": {},
        "repository": "",
        "main": "src/index.ts",
        "scripts": {
            "build": "npm run build",
            "test": "npm test",
            "start": "npm start",
        },
        "dependencies": {},
        "config": {
            "schema": {},
            "defaults": {},
        },
        "resources": {
            "cpu": "100m",
            "memory": "128Mi",
        },
        "healthCheck": {
            "path": "/health",
            "port": 8080,
        },
    }

    # Write manifest
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    console.print(Panel(
        f"[green]Cell initialized successfully![/green]\n\n"
        f"Name: [bold]{name}[/bold]\n"
        f"Namespace: {namespace}\n"
        f"Category: {category}\n\n"
        f"Created: {CELL_MANIFEST_FILE}",
        title="Cell Initialized",
    ))

    console.print("\nNext steps:")
    console.print("  1. Edit [bold]cell.json[/bold] to configure your cell")
    console.print("  2. Run [bold]cell publish[/bold] to publish to marketplace")
    console.print("  3. Run [bold]cell deploy[/bold] to deploy to colony")


@cells.command()
@click.option("--version", "-v", help="Version to publish (default: from cell.json)")
@click.option("--tag", "-t", multiple=True, help="Add tags")
@click.option("--prerelease", is_flag=True, help="Mark as prerelease")
@click.option("--dry-run", is_flag=True, help="Validate without publishing")
@click.pass_context
def publish(ctx, version: Optional[str], tag: tuple, prerelease: bool, dry_run: bool):
    """
    Publish cell to the marketplace.

    Uploads the cell manifest and artifacts.
    """
    api_url = ctx.obj.get("api_url", "http://localhost:8000")
    cwd = Path.cwd()
    manifest_path = cwd / CELL_MANIFEST_FILE

    if not manifest_path.exists():
        console.print(f"[red]{CELL_MANIFEST_FILE} not found. Run 'cell init' first.[/red]")
        raise SystemExit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    # Use provided version or from manifest
    pub_version = version or manifest.get("version", "0.1.0")

    console.print(f"\n[bold]Publishing {manifest['namespace']}@{pub_version}...[/bold]\n")

    # Validate
    errors = []
    if not manifest.get("name"):
        errors.append("Missing 'name'")
    if not manifest.get("namespace"):
        errors.append("Missing 'namespace'")
    if not manifest.get("description"):
        errors.append("Missing 'description'")

    if errors:
        console.print("[red]Validation errors:[/red]")
        for err in errors:
            console.print(f"  - {err}")
        raise SystemExit(1)

    if dry_run:
        console.print("[green]Validation passed (dry run)[/green]")
        console.print("\nManifest:")
        console.print(Syntax(json.dumps(manifest, indent=2), "json"))
        return

    # Create/update cell in registry
    headers = get_auth_headers()
    headers["X-Tenant-ID"] = get_config().get("active_tenant", "")

    try:
        with httpx.Client(timeout=60) as client:
            # Check if cell exists
            check_response = client.get(
                f"{api_url}/api/v1/portal/cells/namespace/{manifest['namespace']}",
                headers=headers,
            )

            if check_response.status_code == 404:
                # Create new cell
                console.print("Creating new cell...")
                create_response = client.post(
                    f"{api_url}/api/v1/portal/cells",
                    headers=headers,
                    json={
                        "name": manifest["name"],
                        "namespace": manifest["namespace"],
                        "display_name": manifest.get("display_name", manifest["name"]),
                        "description": manifest["description"],
                        "category": manifest.get("category", "other"),
                        "tags": list(tag) + manifest.get("tags", []),
                        "license": manifest.get("license"),
                        "repository_url": manifest.get("repository"),
                    }
                )
                create_response.raise_for_status()
                cell = create_response.json()
                cell_id = cell["id"]
                console.print(f"[green]Created cell: {cell['namespace']}[/green]")
            else:
                check_response.raise_for_status()
                cell = check_response.json()
                cell_id = cell["id"]
                console.print(f"[blue]Updating existing cell: {cell['namespace']}[/blue]")

            # Create version
            console.print(f"Publishing version {pub_version}...")
            version_response = client.post(
                f"{api_url}/api/v1/portal/cells/{cell_id}/versions",
                headers=headers,
                json={
                    "version": pub_version,
                    "changelog": f"Release {pub_version}",
                    "is_prerelease": prerelease,
                }
            )
            version_response.raise_for_status()

            # Publish cell
            publish_response = client.post(
                f"{api_url}/api/v1/portal/cells/{cell_id}/publish",
                headers=headers,
            )
            # Ignore if already published
            if publish_response.status_code != 400:
                publish_response.raise_for_status()

    except httpx.HTTPStatusError as e:
        console.print(f"[red]Failed to publish: {e.response.text}[/red]")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)

    console.print(Panel(
        f"[green]Successfully published![/green]\n\n"
        f"Cell: [bold]{manifest['namespace']}[/bold]\n"
        f"Version: {pub_version}\n"
        f"Prerelease: {'Yes' if prerelease else 'No'}",
        title="Published",
    ))


@cells.command()
@click.option("--major", is_flag=True, help="Bump major version")
@click.option("--minor", is_flag=True, help="Bump minor version")
@click.option("--patch", is_flag=True, help="Bump patch version (default)")
@click.option("--prerelease", "-pre", help="Add prerelease tag (e.g., alpha, beta, rc.1)")
@click.pass_context
def version(ctx, major: bool, minor: bool, patch: bool, prerelease: Optional[str]):
    """
    Bump cell version in cell.json.
    """
    manifest_path = Path.cwd() / CELL_MANIFEST_FILE

    if not manifest_path.exists():
        console.print(f"[red]{CELL_MANIFEST_FILE} not found[/red]")
        raise SystemExit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    current = manifest.get("version", "0.0.0")

    # Parse version
    parts = current.split("-")[0].split(".")
    if len(parts) != 3:
        console.print(f"[red]Invalid version format: {current}[/red]")
        raise SystemExit(1)

    maj, min_, pat = int(parts[0]), int(parts[1]), int(parts[2])

    # Bump
    if major:
        maj += 1
        min_ = 0
        pat = 0
    elif minor:
        min_ += 1
        pat = 0
    else:  # patch (default)
        pat += 1

    new_version = f"{maj}.{min_}.{pat}"
    if prerelease:
        new_version += f"-{prerelease}"

    manifest["version"] = new_version

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    console.print(f"[green]Version bumped: {current} → {new_version}[/green]")


@cells.command()
@click.pass_context
def list(ctx):
    """List cells in current tenant."""
    api_url = ctx.obj.get("api_url", "http://localhost:8000")
    headers = get_auth_headers()
    headers["X-Tenant-ID"] = get_config().get("active_tenant", "")

    try:
        with httpx.Client() as client:
            response = client.get(
                f"{api_url}/api/v1/portal/cells",
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)

    if not data.get("items"):
        console.print("[yellow]No cells found[/yellow]")
        return

    table = Table(title="Your Cells")
    table.add_column("Namespace", style="cyan")
    table.add_column("Version")
    table.add_column("Category")
    table.add_column("Published")
    table.add_column("Downloads", justify="right")

    for cell in data["items"]:
        table.add_row(
            cell["namespace"],
            cell.get("latest_version") or "-",
            cell["category"],
            "✓" if cell["is_published"] else "✗",
            str(cell.get("download_count", 0)),
        )

    console.print(table)


@cells.command()
@click.argument("cell_id")
@click.option("--message", "-m", required=True, help="Deprecation message")
@click.pass_context
def deprecate(ctx, cell_id: str, message: str):
    """Mark a cell as deprecated."""
    api_url = ctx.obj.get("api_url", "http://localhost:8000")
    headers = get_auth_headers()
    headers["X-Tenant-ID"] = get_config().get("active_tenant", "")

    try:
        with httpx.Client() as client:
            response = client.post(
                f"{api_url}/api/v1/portal/cells/{cell_id}/deprecate",
                headers=headers,
                params={"message": message},
            )
            response.raise_for_status()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)

    console.print(f"[green]Cell marked as deprecated[/green]")
