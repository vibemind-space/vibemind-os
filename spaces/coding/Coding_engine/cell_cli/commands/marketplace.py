"""
Marketplace commands for searching and installing cells.
"""

import json
import shutil
from pathlib import Path
from typing import Optional

import click
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, DownloadColumn
from rich.table import Table

from ..config import (
    get_credentials,
    get_config,
    add_installed_cell,
    remove_installed_cell,
    get_installed_cells,
    add_recent_cell,
)

console = Console()


def get_auth_headers():
    """Get authorization headers."""
    creds = get_credentials()
    if not creds:
        console.print("[red]Not logged in. Run 'cell login' first.[/red]")
        raise SystemExit(1)
    return {"Authorization": f"Bearer {creds['token']}"}


@click.group()
def marketplace():
    """Marketplace commands for discovering and installing cells."""
    pass


@marketplace.command()
@click.argument("query", required=False)
@click.option("--category", "-c", help="Filter by category")
@click.option("--tag", "-t", multiple=True, help="Filter by tags")
@click.option("--sort", type=click.Choice(["downloads", "rating", "recent", "trending"]), default="trending")
@click.option("--verified", is_flag=True, help="Show only verified cells")
@click.option("--limit", "-l", type=int, default=20, help="Maximum results")
@click.option("--page", "-p", type=int, default=1, help="Page number")
@click.pass_context
def search(ctx, query: Optional[str], category: Optional[str], tag: tuple, sort: str, verified: bool, limit: int, page: int):
    """
    Search the cell marketplace.

    Examples:
        cell marketplace search "authentication"
        cell marketplace search --category api --tag python
        cell marketplace search --sort downloads --verified
    """
    api_url = ctx.obj.get("api_url", "http://localhost:8000")

    params = {
        "q": query or "",
        "sort_by": sort,
        "page": page,
        "page_size": limit,
    }

    if category:
        params["category"] = category
    if tag:
        params["tags"] = list(tag)
    if verified:
        params["verified_only"] = True

    console.print(f"\n[dim]Searching marketplace...[/dim]\n")

    try:
        with httpx.Client() as client:
            response = client.get(
                f"{api_url}/api/v1/marketplace/search",
                params=params,
            )
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPStatusError as e:
        console.print(f"[red]Search failed: {e.response.text}[/red]")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)

    cells = result.get("cells", [])
    total = result.get("total", 0)

    if not cells:
        console.print("[yellow]No cells found matching your query.[/yellow]")
        return

    table = Table(title=f"Marketplace Results ({total} total)")
    table.add_column("Namespace", style="cyan")
    table.add_column("Name")
    table.add_column("Version")
    table.add_column("Rating", justify="right")
    table.add_column("Downloads", justify="right")
    table.add_column("Verified")

    for cell in cells:
        rating = cell.get("average_rating", 0)
        rating_str = f"{'*' * int(rating)} ({rating:.1f})" if rating else "-"

        downloads = cell.get("download_count", 0)
        if downloads >= 1000000:
            downloads_str = f"{downloads / 1000000:.1f}M"
        elif downloads >= 1000:
            downloads_str = f"{downloads / 1000:.1f}K"
        else:
            downloads_str = str(downloads)

        verified_str = "[green]Yes[/green]" if cell.get("is_verified") else "[dim]No[/dim]"

        table.add_row(
            cell.get("namespace", ""),
            cell.get("name", ""),
            cell.get("latest_version", "-"),
            rating_str,
            downloads_str,
            verified_str,
        )

    console.print(table)

    if total > limit * page:
        console.print(f"\n[dim]Showing page {page} of {(total + limit - 1) // limit}. Use --page to see more.[/dim]")


@marketplace.command()
@click.argument("namespace")
@click.pass_context
def info(ctx, namespace: str):
    """
    Show detailed information about a cell.

    Examples:
        cell marketplace info @acme/auth-service
    """
    api_url = ctx.obj.get("api_url", "http://localhost:8000")

    try:
        with httpx.Client() as client:
            response = client.get(
                f"{api_url}/api/v1/marketplace/cells/{namespace}",
            )
            response.raise_for_status()
            cell = response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            console.print(f"[red]Cell '{namespace}' not found.[/red]")
        else:
            console.print(f"[red]Error: {e.response.text}[/red]")
        raise SystemExit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)

    add_recent_cell(namespace)

    # Build info panel
    verified_badge = "[green]Verified[/green]" if cell.get("is_verified") else ""
    featured_badge = "[yellow]Featured[/yellow]" if cell.get("is_featured") else ""
    badges = " ".join(filter(None, [verified_badge, featured_badge]))

    rating = cell.get("average_rating", 0)
    rating_str = f"{'*' * int(rating)} ({rating:.1f}/5.0 from {cell.get('review_count', 0)} reviews)"

    info_text = f"""
[bold]{cell.get('name', namespace)}[/bold] {badges}
[dim]{namespace}[/dim]

{cell.get('description', 'No description')}

[bold]Latest Version:[/bold] {cell.get('latest_version', 'N/A')}
[bold]Category:[/bold] {cell.get('category', 'Uncategorized')}
[bold]License:[/bold] {cell.get('license', 'Not specified')}
[bold]Rating:[/bold] {rating_str}
[bold]Downloads:[/bold] {cell.get('download_count', 0):,}

[bold]Tags:[/bold] {', '.join(cell.get('tags', [])) or 'None'}

[bold]Homepage:[/bold] {cell.get('homepage_url', 'N/A')}
[bold]Repository:[/bold] {cell.get('repo_url', 'N/A')}
[bold]Documentation:[/bold] {cell.get('docs_url', 'N/A')}

[bold]Author:[/bold] {cell.get('author', 'Unknown')}
[bold]Published:[/bold] {cell.get('published_at', 'N/A')}
[bold]Last Updated:[/bold] {cell.get('updated_at', 'N/A')}
"""

    console.print(Panel(info_text.strip(), title=f"Cell Info: {namespace}"))

    # Show dependencies if any
    deps = cell.get("dependencies", [])
    if deps:
        console.print("\n[bold]Dependencies:[/bold]")
        for dep in deps:
            console.print(f"  - {dep.get('namespace')} ({dep.get('version_constraint', '*')})")


@marketplace.command()
@click.argument("namespace")
@click.option("--version", "-v", help="Specific version to install")
@click.option("--path", "-p", type=click.Path(), help="Installation path")
@click.option("--no-deps", is_flag=True, help="Skip dependency installation")
@click.option("--force", "-f", is_flag=True, help="Force reinstall")
@click.pass_context
def install(ctx, namespace: str, version: Optional[str], path: Optional[str], no_deps: bool, force: bool):
    """
    Install a cell from the marketplace.

    Examples:
        cell marketplace install @acme/auth-service
        cell marketplace install @acme/auth-service --version 1.2.0
        cell marketplace install @acme/auth-service --path ./services/auth
    """
    api_url = ctx.obj.get("api_url", "http://localhost:8000")
    headers = get_auth_headers()
    config = get_config()
    headers["X-Tenant-ID"] = config.get("active_tenant", "")

    # Check if already installed
    installed = get_installed_cells()
    if namespace in installed and not force:
        existing = installed[namespace]
        console.print(f"[yellow]Cell '{namespace}' is already installed (v{existing['version']}).[/yellow]")
        console.print("[dim]Use --force to reinstall.[/dim]")
        raise SystemExit(1)

    install_path = Path(path) if path else Path.cwd() / "cells" / namespace.replace("/", "_").replace("@", "")

    console.print(f"\n[bold]Installing {namespace}...[/bold]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        DownloadColumn(),
        console=console,
    ) as progress:
        # Fetch cell info
        task = progress.add_task("Fetching cell info...", total=None)

        try:
            with httpx.Client() as client:
                # Get cell info
                cell_response = client.get(
                    f"{api_url}/api/v1/marketplace/cells/{namespace}",
                )
                cell_response.raise_for_status()
                cell = cell_response.json()

                target_version = version or cell.get("latest_version")
                if not target_version:
                    console.print("[red]No version available for this cell.[/red]")
                    raise SystemExit(1)

                progress.update(task, description=f"Installing v{target_version}...")

                # Get version details
                version_response = client.get(
                    f"{api_url}/api/v1/marketplace/cells/{namespace}/versions/{target_version}",
                )
                version_response.raise_for_status()
                version_info = version_response.json()

                # Check dependencies
                if not no_deps:
                    deps = version_info.get("dependencies", [])
                    for dep in deps:
                        dep_namespace = dep.get("namespace")
                        if dep_namespace not in installed:
                            progress.update(task, description=f"Installing dependency: {dep_namespace}...")
                            # Recursively install dependency
                            ctx.invoke(
                                install,
                                namespace=dep_namespace,
                                version=dep.get("version_constraint"),
                                no_deps=False,
                                force=False,
                            )

                # Download artifact
                progress.update(task, description="Downloading artifact...", total=100)

                download_url = version_info.get("artifact_url")
                if not download_url:
                    # Generate download URL
                    download_url = f"{api_url}/api/v1/marketplace/cells/{namespace}/versions/{target_version}/download"

                # Track download
                client.post(
                    f"{api_url}/api/v1/marketplace/cells/{namespace}/versions/{target_version}/download",
                    headers=headers,
                )

                # Create install directory
                install_path.mkdir(parents=True, exist_ok=True)

                # Download and extract
                with client.stream("GET", download_url, headers=headers) as r:
                    r.raise_for_status()
                    total_size = int(r.headers.get("content-length", 0))

                    if total_size:
                        progress.update(task, total=total_size)

                    artifact_path = install_path / "artifact.tar.gz"
                    downloaded = 0

                    with open(artifact_path, "wb") as f:
                        for chunk in r.iter_bytes(chunk_size=8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            progress.update(task, completed=downloaded)

                # Extract artifact
                progress.update(task, description="Extracting...", total=None)

                import tarfile
                with tarfile.open(artifact_path, "r:gz") as tar:
                    tar.extractall(install_path)

                artifact_path.unlink()

                # Save cell manifest
                manifest = {
                    "namespace": namespace,
                    "name": cell.get("name"),
                    "version": target_version,
                    "installed_from": "marketplace",
                    "dependencies": version_info.get("dependencies", []),
                }

                with open(install_path / "cell.json", "w") as f:
                    json.dump(manifest, f, indent=2)

                # Track installation
                add_installed_cell(namespace, target_version, str(install_path))

                progress.update(task, description="[green]Installed![/green]")

        except httpx.HTTPStatusError as e:
            console.print(f"[red]Installation failed: {e.response.text}[/red]")
            raise SystemExit(1)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            raise SystemExit(1)

    console.print(Panel(
        f"[green]Successfully installed![/green]\n\n"
        f"Cell: [bold]{namespace}[/bold]\n"
        f"Version: {target_version}\n"
        f"Location: {install_path}",
        title="Installation Complete",
    ))


@marketplace.command()
@click.argument("namespace")
@click.option("--keep-files", is_flag=True, help="Keep cell files after uninstall")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.pass_context
def uninstall(ctx, namespace: str, keep_files: bool, force: bool):
    """
    Uninstall a cell.

    Examples:
        cell marketplace uninstall @acme/auth-service
    """
    installed = get_installed_cells()

    if namespace not in installed:
        console.print(f"[yellow]Cell '{namespace}' is not installed.[/yellow]")
        raise SystemExit(1)

    cell_info = installed[namespace]
    cell_path = Path(cell_info["path"])

    if not force:
        from rich.prompt import Confirm
        if not Confirm.ask(f"[yellow]Uninstall '{namespace}'?[/yellow]"):
            console.print("Aborted.")
            return

    # Remove from tracking
    remove_installed_cell(namespace)

    # Remove files if requested
    if not keep_files and cell_path.exists():
        try:
            shutil.rmtree(cell_path)
            console.print(f"[green]Removed cell files from {cell_path}[/green]")
        except Exception as e:
            console.print(f"[yellow]Could not remove files: {e}[/yellow]")

    console.print(f"[green]Uninstalled '{namespace}'[/green]")


@marketplace.command("list")
@click.option("--outdated", is_flag=True, help="Show only outdated cells")
@click.pass_context
def list_installed(ctx, outdated: bool):
    """
    List installed cells.

    Examples:
        cell marketplace list
        cell marketplace list --outdated
    """
    api_url = ctx.obj.get("api_url", "http://localhost:8000")
    installed = get_installed_cells()

    if not installed:
        console.print("[yellow]No cells installed.[/yellow]")
        console.print("[dim]Install cells with: cell marketplace install <namespace>[/dim]")
        return

    table = Table(title="Installed Cells")
    table.add_column("Namespace", style="cyan")
    table.add_column("Version")
    table.add_column("Latest")
    table.add_column("Path")
    table.add_column("Installed")

    for namespace, info in installed.items():
        latest = "-"

        # Check for updates
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(
                    f"{api_url}/api/v1/marketplace/cells/{namespace}",
                )
                if response.status_code == 200:
                    cell = response.json()
                    latest = cell.get("latest_version", "-")
        except Exception:
            pass

        current = info.get("version", "-")
        is_outdated = latest != "-" and current != latest

        if outdated and not is_outdated:
            continue

        version_str = f"[yellow]{current}[/yellow]" if is_outdated else current
        latest_str = f"[green]{latest}[/green]" if is_outdated else latest

        table.add_row(
            namespace,
            version_str,
            latest_str,
            info.get("path", "-"),
            info.get("installed_at", "-")[:10] if info.get("installed_at") else "-",
        )

    console.print(table)

    if outdated:
        console.print("\n[dim]Update cells with: cell marketplace update <namespace>[/dim]")


@marketplace.command()
@click.argument("namespace", required=False)
@click.option("--all", "-a", "update_all", is_flag=True, help="Update all cells")
@click.pass_context
def update(ctx, namespace: Optional[str], update_all: bool):
    """
    Update installed cells to latest version.

    Examples:
        cell marketplace update @acme/auth-service
        cell marketplace update --all
    """
    api_url = ctx.obj.get("api_url", "http://localhost:8000")
    installed = get_installed_cells()

    if not namespace and not update_all:
        console.print("[red]Specify a cell namespace or use --all to update all cells.[/red]")
        raise SystemExit(1)

    cells_to_update = [namespace] if namespace else list(installed.keys())

    for ns in cells_to_update:
        if ns not in installed:
            console.print(f"[yellow]Cell '{ns}' is not installed, skipping.[/yellow]")
            continue

        current_version = installed[ns].get("version", "0.0.0")

        # Check latest version
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{api_url}/api/v1/marketplace/cells/{ns}",
                )
                response.raise_for_status()
                cell = response.json()
                latest = cell.get("latest_version")

                if latest and latest != current_version:
                    console.print(f"\n[bold]Updating {ns}: {current_version} -> {latest}[/bold]")
                    ctx.invoke(
                        install,
                        namespace=ns,
                        version=latest,
                        path=installed[ns].get("path"),
                        force=True,
                    )
                else:
                    console.print(f"[dim]{ns} is up to date ({current_version})[/dim]")

        except Exception as e:
            console.print(f"[red]Failed to update {ns}: {e}[/red]")


@marketplace.command()
@click.pass_context
def trending(ctx):
    """
    Show trending cells.
    """
    api_url = ctx.obj.get("api_url", "http://localhost:8000")

    try:
        with httpx.Client() as client:
            response = client.get(
                f"{api_url}/api/v1/marketplace/trending",
            )
            response.raise_for_status()
            result = response.json()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)

    cells = result.get("cells", [])

    if not cells:
        console.print("[yellow]No trending cells found.[/yellow]")
        return

    console.print("\n[bold]Trending Cells[/bold]\n")

    for i, cell in enumerate(cells[:10], 1):
        verified = " [green]Verified[/green]" if cell.get("is_verified") else ""
        rating = cell.get("average_rating", 0)
        stars = "*" * int(rating) if rating else ""

        console.print(f"{i}. [cyan]{cell.get('namespace')}[/cyan]{verified}")
        console.print(f"   {cell.get('description', '')[:60]}...")
        console.print(f"   [dim]Downloads: {cell.get('download_count', 0):,} | Rating: {stars} ({rating:.1f})[/dim]\n")


@marketplace.command()
@click.pass_context
def categories(ctx):
    """
    List available categories.
    """
    api_url = ctx.obj.get("api_url", "http://localhost:8000")

    try:
        with httpx.Client() as client:
            response = client.get(
                f"{api_url}/api/v1/marketplace/categories",
            )
            response.raise_for_status()
            result = response.json()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise SystemExit(1)

    categories = result.get("categories", [])

    table = Table(title="Categories")
    table.add_column("Category", style="cyan")
    table.add_column("Cells", justify="right")
    table.add_column("Description")

    for cat in categories:
        table.add_row(
            cat.get("name", ""),
            str(cat.get("cell_count", 0)),
            cat.get("description", ""),
        )

    console.print(table)
