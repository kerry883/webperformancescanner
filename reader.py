"""
reader.py — CSV URL Reader Module

Reads URLs or route paths from a CSV file.
Supports two formats:
  - Full URLs   (e.g. https://example.com/about)  → used as-is
  - Route paths (e.g. /about)                     → base domain prepended
"""

import csv
import sys
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urlparse

from rich.console import Console

console = Console()


def _is_full_url(value: str) -> bool:
    """Return True if *value* looks like a complete URL (has a scheme)."""
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https")


def read_urls(csv_path: str = "urls.csv") -> Tuple[List[str], List[str]]:
    """
    Read entries from a single-column CSV file.

    Each row can be either:
      • A full URL  (https://…)  — collected into the *full_urls* list.
      • A route path (/about)    — collected into the *routes* list.

    The CSV must have a header row (skipped automatically).

    Args:
        csv_path: Path to the CSV file.

    Returns:
        A tuple of (full_urls, routes) where:
          - full_urls: URLs that are already fully qualified.
          - routes:    Bare paths that still need a base domain.

    Raises:
        SystemExit: If the file is missing, unreadable, or empty.
    """
    path = Path(csv_path)

    # --- Guard: file existence ---
    if not path.exists():
        console.print(
            f"[bold red]Error:[/bold red] CSV file not found: '{csv_path}'"
        )
        console.print(
            "Please create a 'urls.csv' file with one URL or route per line."
        )
        sys.exit(1)

    full_urls: List[str] = []
    routes: List[str] = []

    try:
        with open(path, newline="", encoding="utf-8") as csvfile:
            reader = csv.reader(csvfile)
            next(reader, None)  # Skip the header row

            for row_number, row in enumerate(reader, start=2):
                # Skip empty rows
                if not row or not row[0].strip():
                    continue

                entry = row[0].strip()

                if _is_full_url(entry):
                    # Already a complete URL — use as-is
                    full_urls.append(entry)
                else:
                    # Treat as a route path; ensure it starts with /
                    if not entry.startswith("/"):
                        console.print(
                            f"[yellow]Warning:[/yellow] Row {row_number} "
                            f"route '{entry}' does not start with '/'. "
                            "Prepending '/' automatically."
                        )
                        entry = "/" + entry
                    routes.append(entry)

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

    total = len(full_urls) + len(routes)
    if total == 0:
        console.print(
            f"[bold red]Error:[/bold red] No valid entries found in '{csv_path}'."
        )
        sys.exit(1)

    # Summary
    if full_urls:
        console.print(
            f"[green]✓[/green] Loaded [bold]{len(full_urls)}[/bold] full URL(s) "
            f"from '{csv_path}'."
        )
    if routes:
        console.print(
            f"[green]✓[/green] Loaded [bold]{len(routes)}[/bold] route path(s) "
            f"from '{csv_path}' (base domain will be prepended)."
        )

    return full_urls, routes


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
