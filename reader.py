"""
reader.py — CSV URL Reader Module

Reads route paths from a CSV file and combines them with a base domain
to produce fully-qualified URLs ready for scanning.
"""

import csv
import sys
from pathlib import Path
from typing import List

from rich.console import Console

console = Console()


def read_routes(csv_path: str = "urls.csv") -> List[str]:
    """
    Read route paths from a single-column CSV file.

    The CSV file is expected to have a header row (ignored) and one route
    per subsequent row, e.g.:
        route
        /
        /about
        /pricing

    Args:
        csv_path: Path to the CSV file containing route paths.

    Returns:
        A list of route path strings (e.g. ["/", "/about", "/pricing"]).

    Raises:
        SystemExit: If the file is not found or cannot be read.
    """
    path = Path(csv_path)

    # --- Guard: file existence ---
    if not path.exists():
        console.print(
            f"[bold red]Error:[/bold red] CSV file not found: '{csv_path}'"
        )
        console.print(
            "Please create a 'urls.csv' file with one route per line."
        )
        sys.exit(1)

    routes: List[str] = []

    try:
        with open(path, newline="", encoding="utf-8") as csvfile:
            reader = csv.reader(csvfile)
            next(reader, None)  # Skip the header row

            for row_number, row in enumerate(reader, start=2):
                # Skip empty rows
                if not row or not row[0].strip():
                    continue

                route = row[0].strip()

                # Basic validation: routes should start with /
                if not route.startswith("/"):
                    console.print(
                        f"[yellow]Warning:[/yellow] Row {row_number} "
                        f"route '{route}' does not start with '/'. "
                        "Prepending '/' automatically."
                    )
                    route = "/" + route

                routes.append(route)

    except csv.Error as exc:
        console.print(
            f"[bold red]Error:[/bold red] Failed to parse '{csv_path}': {exc}"
        )
        sys.exit(1)
    except OSError as exc:
        console.print(
            f"[bold red]Error:[/bold red] Could not read '{csv_path}': {exc}"
        )
        sys.exit(1)

    if not routes:
        console.print(
            f"[bold red]Error:[/bold red] No valid routes found in '{csv_path}'."
        )
        sys.exit(1)

    console.print(
        f"[green]✓[/green] Loaded [bold]{len(routes)}[/bold] route(s) "
        f"from '{csv_path}'."
    )
    return routes


def build_full_urls(base_url: str, routes: List[str]) -> List[str]:
    """
    Combine a base domain with route paths to produce full URLs.

    Args:
        base_url: The base domain (e.g. "https://example.com").
        routes:   A list of route paths (e.g. ["/", "/about"]).

    Returns:
        A list of fully-qualified URLs.
    """
    # Strip trailing slash from base to avoid double slashes
    base = base_url.rstrip("/")
    full_urls = [f"{base}{route}" for route in routes]
    return full_urls
