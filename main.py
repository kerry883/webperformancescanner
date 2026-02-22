"""
main.py — CLI Entry Point & Orchestrator

Ties together the reader, scanner, and reporter modules to run a
full PageSpeed Insights scan from the command line.

Usage:
    python main.py                          # uses BASE_URL from .env
    python main.py --base-url https://example.com
    python main.py --csv routes.csv --delay 3
"""

import argparse
import os
import sys

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from reader import build_full_urls, read_urls
from reporter import (
    build_dataframe,
    compute_averages_by_strategy,
    export_csv,
    print_full_report,
)
from scanner import scan_urls

console = Console()


def _load_env() -> None:
    """Load environment variables from the .env file."""
    load_dotenv()


def _parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        Namespace with base_url, csv, delay, and output attributes.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Scan website routes with the Google PageSpeed Insights API "
            "and report average performance metrics."
        ),
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help=(
            "Base domain to prepend to routes "
            "(e.g. https://example.com). "
            "Defaults to BASE_URL in .env."
        ),
    )
    parser.add_argument(
        "--csv",
        type=str,
        default="urls.csv",
        help="Path to the CSV file containing routes (default: urls.csv).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=None,
        help=(
            "Seconds to wait between API requests (default: 2). "
            "Overrides REQUEST_DELAY in .env."
        ),
    )
    parser.add_argument(
        "--output",
        type=str,
        default="results.csv",
        help="Path for the exported results CSV (default: results.csv).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help=(
            "Number of concurrent threads / 'channels' for parallel "
            "API calls (default: 10). Increase for more speed, "
            "decrease if you hit rate-limit errors."
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Main orchestration function."""

    # ── 1. Load environment & CLI args ──────────────────────────────────
    _load_env()
    args = _parse_args()

    console.print(
        Panel(
            "[bold cyan]Web Performance Scanner[/bold cyan]\n"
            "Google PageSpeed Insights — Batch Route Analyser",
            border_style="cyan",
        )
    )

    # ── 2. Resolve API key ──────────────────────────────────────────────
    api_key = os.getenv("API_KEY")
    if not api_key or api_key == "your_api_key_here":
        console.print(
            "[bold red]Error:[/bold red] No valid API_KEY found.\n"
            "Set your Google PageSpeed Insights API key in the "
            "[bold].env[/bold] file."
        )
        sys.exit(1)

    # ── 3. Resolve base URL (may be optional if CSV has full URLs) ────
    base_url = args.base_url or os.getenv("BASE_URL")

    # ── 4. Resolve request delay ────────────────────────────────────────
    if args.delay is not None:
        delay = args.delay
    else:
        try:
            delay = float(os.getenv("REQUEST_DELAY", "2"))
        except ValueError:
            delay = 2.0

    # ── 5. Read URLs / routes from CSV ──────────────────────────────────
    csv_full_urls, routes = read_urls(args.csv)

    # Build full URLs from route paths (needs a base domain)
    if routes:
        if not base_url or base_url == "https://example.com":
            console.print(
                "[bold red]Error:[/bold red] CSV contains route paths that "
                "need a base URL, but none is configured.\n"
                "Pass [bold]--base-url[/bold] or set BASE_URL in .env."
            )
            sys.exit(1)
        csv_full_urls.extend(build_full_urls(base_url, routes))

    # Deduplicate while preserving order
    seen = set()
    full_urls = []
    for url in csv_full_urls:
        if url not in seen:
            seen.add(url)
            full_urls.append(url)

    if base_url and base_url != "https://example.com":
        console.print(f"[bold]Base URL:[/bold]  {base_url}")
    console.print(f"[bold]URLs:[/bold]      {len(full_urls)} unique target(s)")
    console.print(f"[bold]Workers:[/bold]   {args.workers} concurrent threads")
    console.print(f"[bold]Output:[/bold]    {args.output}")

    # ── 6. Scan URLs via API (concurrent) ───────────────────────────────
    results = scan_urls(
        full_urls, api_key, delay=delay, max_workers=args.workers
    )

    if not results:
        console.print(
            "[bold red]Error:[/bold red] No results were returned. "
            "Check your API key and network connection."
        )
        sys.exit(1)

    # ── 7. Aggregate & display comprehensive report ──────────────────
    df = build_dataframe(results)
    averages = compute_averages_by_strategy(df)
    print_full_report(df, averages)

    # ── 8. Export CSV ───────────────────────────────────────────────────
    export_csv(df, averages, output_path=args.output)

    console.print()
    console.print("[bold green]Done![/bold green] 🎉")


if __name__ == "__main__":
    main()
