"""
Colony management commands.
"""

import json
import time
from pathlib import Path
from typing import Optional

import click
import httpx
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

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
def colony():
    """Colony deployment and management commands."""
    pass


@colony.command()
@click.option("--namespace", "-n", help="K8s namespace to deploy to")
@click.option("--env", "-e", multiple=True, help="Environment variables (KEY=VALUE)")
@click.option("--replicas", "-r", type=int, default=1, help="Number of replicas")
@click.option("--wait", is_flag=True, help="Wait for deployment to complete")
@click.pass_context
def deploy(ctx, namespace: Optional[str], env: tuple, replicas: int, wait: bool):
    """
    Deploy cell to the colony.

    Uses cell.json in current directory.
    """
    api_url = ctx.obj.get("api_url", "http://localhost:8000")
    cwd = Path.cwd()
    manifest_path = cwd / CELL_MANIFEST_FILE

    if not manifest_path.exists():
        console.print(f"[red]{CELL_MANIFEST_FILE} not found. Run 'cell init' first.[/red]")
        raise SystemExit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    # Parse env vars
    env_vars = {}
    for e in env:
        if "=" in e:
            key, value = e.split("=", 1)
            env_vars[key] = value

    console.print(f"\n[bold]Deploying {manifest['namespace']}...[/bold]\n")

    headers = get_auth_headers()
    config = get_config()
    headers["X-Tenant-ID"] = config.get("active_tenant", "")

    deploy_request = {
        "namespace": manifest["namespace"],
        "version": manifest.get("version", "latest"),
        "k8s_namespace": namespace or "cell-colony",
        "replicas": replicas,
        "env_vars": env_vars,
        "resources": manifest.get("resources", {}),
        "health_check": manifest.get("healthCheck", {}),
    }

    try:
        with httpx.Client(timeout=120) as client:
            response = client.post(
                f"{api_url}/api/v1/colony/deploy",
                headers=headers,
                json=deploy_request,
            )
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Deployment failed: {e.response.text}[/red]")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)

    deployment_id = result.get("deployment_id", "unknown")
    console.print(f"[green]Deployment initiated: {deployment_id}[/green]")

    if wait:
        console.print("\nWaiting for deployment to complete...")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Deploying...", total=None)

            for _ in range(60):  # 5 minutes timeout
                time.sleep(5)
                try:
                    status_response = client.get(
                        f"{api_url}/api/v1/colony/deployments/{deployment_id}",
                        headers=headers,
                    )
                    status_response.raise_for_status()
                    status = status_response.json()

                    if status.get("status") == "healthy":
                        progress.update(task, description="[green]Healthy[/green]")
                        break
                    elif status.get("status") == "failed":
                        progress.update(task, description="[red]Failed[/red]")
                        console.print(f"\n[red]Deployment failed: {status.get('error')}[/red]")
                        raise SystemExit(1)
                    else:
                        progress.update(task, description=f"Status: {status.get('status', 'pending')}")
                except Exception:
                    pass
            else:
                console.print("\n[yellow]Deployment timed out. Check status with 'cell status'[/yellow]")
                raise SystemExit(1)

    console.print(Panel(
        f"[green]Deployment successful![/green]\n\n"
        f"Cell: [bold]{manifest['namespace']}[/bold]\n"
        f"Version: {manifest.get('version', 'latest')}\n"
        f"Namespace: {namespace or 'cell-colony'}\n"
        f"Replicas: {replicas}",
        title="Deployed",
    ))


@colony.command()
@click.option("--namespace", "-n", help="Filter by K8s namespace")
@click.option("--watch", "-w", is_flag=True, help="Watch for changes")
@click.pass_context
def status(ctx, namespace: Optional[str], watch: bool):
    """
    Show colony status.

    Lists all deployed cells and their health.
    """
    api_url = ctx.obj.get("api_url", "http://localhost:8000")
    headers = get_auth_headers()
    config = get_config()
    headers["X-Tenant-ID"] = config.get("active_tenant", "")

    def get_status():
        try:
            with httpx.Client() as client:
                params = {}
                if namespace:
                    params["namespace"] = namespace

                response = client.get(
                    f"{api_url}/api/v1/colony/status",
                    headers=headers,
                    params=params,
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            return {"error": str(e)}

    def render_status(data):
        if "error" in data:
            return Panel(f"[red]Error: {data['error']}[/red]", title="Colony Status")

        # Summary
        summary = data.get("summary", {})
        cells = data.get("cells", [])

        table = Table(title="Colony Status")
        table.add_column("Cell", style="cyan")
        table.add_column("Version")
        table.add_column("Status")
        table.add_column("Replicas")
        table.add_column("CPU")
        table.add_column("Memory")
        table.add_column("Age")

        status_colors = {
            "healthy": "green",
            "degraded": "yellow",
            "failed": "red",
            "pending": "blue",
            "deploying": "blue",
        }

        for cell in cells:
            status_val = cell.get("status", "unknown")
            status_color = status_colors.get(status_val, "white")

            table.add_row(
                cell.get("name", "unknown"),
                cell.get("version", "-"),
                f"[{status_color}]{status_val}[/{status_color}]",
                f"{cell.get('ready_replicas', 0)}/{cell.get('replicas', 1)}",
                cell.get("cpu_usage", "-"),
                cell.get("memory_usage", "-"),
                cell.get("age", "-"),
            )

        # Add summary panel
        summary_text = (
            f"Total Cells: {summary.get('total', len(cells))}\n"
            f"Healthy: [green]{summary.get('healthy', 0)}[/green]\n"
            f"Degraded: [yellow]{summary.get('degraded', 0)}[/yellow]\n"
            f"Failed: [red]{summary.get('failed', 0)}[/red]"
        )

        return Panel(
            f"{summary_text}\n\n" + str(table) if cells else summary_text,
            title=f"Colony Status - {namespace or 'all namespaces'}",
        )

    if watch:
        with Live(console=console, refresh_per_second=0.5) as live:
            while True:
                data = get_status()
                live.update(render_status(data))
                time.sleep(5)
    else:
        data = get_status()
        console.print(render_status(data))


@colony.command()
@click.argument("cell_name")
@click.option("--follow", "-f", is_flag=True, help="Follow log output")
@click.option("--tail", "-t", type=int, default=100, help="Number of lines to show")
@click.option("--since", "-s", help="Show logs since (e.g., 5m, 1h)")
@click.pass_context
def logs(ctx, cell_name: str, follow: bool, tail: int, since: Optional[str]):
    """
    View logs for a deployed cell.
    """
    api_url = ctx.obj.get("api_url", "http://localhost:8000")
    headers = get_auth_headers()
    config = get_config()
    headers["X-Tenant-ID"] = config.get("active_tenant", "")

    params = {
        "tail": tail,
        "follow": follow,
    }
    if since:
        params["since"] = since

    try:
        if follow:
            # Stream logs
            with httpx.Client(timeout=None) as client:
                with client.stream(
                    "GET",
                    f"{api_url}/api/v1/colony/cells/{cell_name}/logs",
                    headers=headers,
                    params=params,
                ) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        console.print(line)
        else:
            with httpx.Client() as client:
                response = client.get(
                    f"{api_url}/api/v1/colony/cells/{cell_name}/logs",
                    headers=headers,
                    params=params,
                )
                response.raise_for_status()
                logs_data = response.json()

                for log in logs_data.get("logs", []):
                    timestamp = log.get("timestamp", "")
                    message = log.get("message", "")
                    level = log.get("level", "info")

                    level_colors = {
                        "error": "red",
                        "warn": "yellow",
                        "info": "white",
                        "debug": "dim",
                    }
                    color = level_colors.get(level, "white")

                    console.print(f"[dim]{timestamp}[/dim] [{color}]{message}[/{color}]")

    except httpx.HTTPStatusError as e:
        console.print(f"[red]Error: {e.response.text}[/red]")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)


@colony.command()
@click.argument("cell_name")
@click.option("--force", "-f", is_flag=True, help="Force termination")
@click.pass_context
def terminate(ctx, cell_name: str, force: bool):
    """
    Terminate a deployed cell.
    """
    api_url = ctx.obj.get("api_url", "http://localhost:8000")
    headers = get_auth_headers()
    config = get_config()
    headers["X-Tenant-ID"] = config.get("active_tenant", "")

    if not force:
        from rich.prompt import Confirm
        if not Confirm.ask(f"[yellow]Terminate cell '{cell_name}'?[/yellow]"):
            console.print("Aborted.")
            return

    try:
        with httpx.Client() as client:
            response = client.delete(
                f"{api_url}/api/v1/colony/cells/{cell_name}",
                headers=headers,
                params={"force": force},
            )
            response.raise_for_status()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)

    console.print(f"[green]Cell '{cell_name}' terminated[/green]")


@colony.command()
@click.argument("cell_name")
@click.option("--replicas", "-r", type=int, help="Number of replicas")
@click.pass_context
def scale(ctx, cell_name: str, replicas: int):
    """
    Scale a deployed cell.
    """
    api_url = ctx.obj.get("api_url", "http://localhost:8000")
    headers = get_auth_headers()
    config = get_config()
    headers["X-Tenant-ID"] = config.get("active_tenant", "")

    try:
        with httpx.Client() as client:
            response = client.patch(
                f"{api_url}/api/v1/colony/cells/{cell_name}/scale",
                headers=headers,
                json={"replicas": replicas},
            )
            response.raise_for_status()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)

    console.print(f"[green]Scaled '{cell_name}' to {replicas} replicas[/green]")


@colony.command()
@click.argument("cell_name")
@click.argument("version", required=False)
@click.option("--rollback", is_flag=True, help="Rollback to previous version")
@click.pass_context
def upgrade(ctx, cell_name: str, version: Optional[str], rollback: bool):
    """
    Upgrade or rollback a deployed cell.
    """
    api_url = ctx.obj.get("api_url", "http://localhost:8000")
    headers = get_auth_headers()
    config = get_config()
    headers["X-Tenant-ID"] = config.get("active_tenant", "")

    action = "rollback" if rollback else "upgrade"

    try:
        with httpx.Client() as client:
            response = client.post(
                f"{api_url}/api/v1/colony/cells/{cell_name}/{action}",
                headers=headers,
                json={"version": version} if version else {},
            )
            response.raise_for_status()
            result = response.json()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)

    if rollback:
        console.print(f"[green]Rolled back '{cell_name}' to {result.get('version', 'previous version')}[/green]")
    else:
        console.print(f"[green]Upgraded '{cell_name}' to {version or 'latest'}[/green]")
