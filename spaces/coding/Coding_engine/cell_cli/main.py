"""
Cell CLI main entry point.
"""

import click
from rich.console import Console

from . import __version__
from .commands import auth, cells, colony, marketplace

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="cell")
@click.option("--api-url", envvar="CELL_API_URL", default="http://localhost:8000",
              help="API server URL")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.pass_context
def cli(ctx: click.Context, api_url: str, verbose: bool):
    """
    Cell CLI - Manage your Cell Colony deployments.

    \b
    Examples:
      cell login              # Authenticate with GitHub/Google
      cell init my-api        # Initialize a new cell
      cell publish            # Publish cell to marketplace
      cell install @org/cell  # Install a cell from marketplace
      cell deploy             # Deploy to colony
      cell status             # Check colony status
    """
    ctx.ensure_object(dict)
    ctx.obj["api_url"] = api_url
    ctx.obj["verbose"] = verbose
    ctx.obj["console"] = console


# Register command groups
cli.add_command(auth.auth)
cli.add_command(cells.cells)
cli.add_command(colony.colony)
cli.add_command(marketplace.marketplace)

# Shortcuts for common commands
cli.add_command(auth.login)
cli.add_command(auth.logout)
cli.add_command(cells.init)
cli.add_command(cells.publish)
cli.add_command(marketplace.install)
cli.add_command(marketplace.search)
cli.add_command(colony.deploy)
cli.add_command(colony.status)


def main():
    """Entry point for the CLI."""
    cli(obj={})


if __name__ == "__main__":
    main()
