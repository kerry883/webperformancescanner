"""
scanner.py — PageSpeed Insights API Scanner Module

Handles all interactions with the Google PageSpeed Insights V5 API.
For each URL it runs both 'mobile' and 'desktop' strategies and extracts
scores for Performance, Accessibility, Best Practices, and SEO.
"""

import time
from typing import Any, Dict, List, Optional

import requests
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

console = Console()

# Google PageSpeed Insights API endpoint
API_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

# Categories to extract from the API response
CATEGORIES = ["performance", "accessibility", "best-practices", "seo"]

# Strategies to test for each URL
STRATEGIES = ["mobile", "desktop"]


def _fetch_pagespeed(
    url: str, strategy: str, api_key: str
) -> Optional[Dict[str, Any]]:
    """
    Make a single PageSpeed Insights API request.

    Args:
        url:      The fully-qualified URL to analyse.
        strategy: Either 'mobile' or 'desktop'.
        api_key:  Google API key.

    Returns:
        The JSON response dict on success, or None on failure.
    """
    params = {
        "url": url,
        "key": api_key,
        "strategy": strategy,
        "category": CATEGORIES,  # requests encodes list params correctly
    }

    try:
        response = requests.get(API_ENDPOINT, params=params, timeout=120)
        response.raise_for_status()
        return response.json()

    except requests.exceptions.HTTPError as exc:
        console.print(
            f"  [red]HTTP Error[/red] for {url} ({strategy}): "
            f"{exc.response.status_code} — {exc.response.reason}"
        )
    except requests.exceptions.ConnectionError:
        console.print(
            f"  [red]Connection Error[/red] for {url} ({strategy}): "
            "Could not reach the API."
        )
    except requests.exceptions.Timeout:
        console.print(
            f"  [red]Timeout[/red] for {url} ({strategy}): "
            "The API request timed out."
        )
    except requests.exceptions.RequestException as exc:
        console.print(
            f"  [red]Request Error[/red] for {url} ({strategy}): {exc}"
        )

    return None


def _extract_scores(data: Dict[str, Any]) -> Dict[str, Optional[int]]:
    """
    Extract category scores from a PageSpeed Insights API response.

    Scores are returned as floats 0–1 by the API; we convert to 0–100.

    Args:
        data: The full JSON response from the API.

    Returns:
        A dict mapping category names to integer scores (or None if missing).
    """
    scores: Dict[str, Optional[int]] = {}
    categories = data.get("lighthouseResult", {}).get("categories", {})

    for cat in CATEGORIES:
        cat_data = categories.get(cat)
        if cat_data and cat_data.get("score") is not None:
            scores[cat] = int(cat_data["score"] * 100)
        else:
            scores[cat] = None

    return scores


def scan_urls(
    urls: List[str],
    api_key: str,
    delay: float = 2.0,
) -> List[Dict[str, Any]]:
    """
    Scan a list of URLs with the PageSpeed Insights API.

    Each URL is tested for both 'mobile' and 'desktop' strategies.
    A configurable delay is inserted between consecutive API calls
    to respect rate limits.

    Args:
        urls:    List of fully-qualified URLs to scan.
        api_key: Google API key.
        delay:   Seconds to wait between API requests (default 2).

    Returns:
        A list of result dicts, each containing:
            - url (str)
            - strategy (str)
            - performance (int | None)
            - accessibility (int | None)
            - best-practices (int | None)
            - seo (int | None)
    """
    results: List[Dict[str, Any]] = []
    total_requests = len(urls) * len(STRATEGIES)

    console.print()
    console.rule("[bold cyan]Scanning URLs[/bold cyan]")
    console.print(
        f"URLs: [bold]{len(urls)}[/bold]  |  "
        f"Strategies: [bold]{', '.join(STRATEGIES)}[/bold]  |  "
        f"Total API calls: [bold]{total_requests}[/bold]"
    )
    console.print()

    # Rich progress bar for visual feedback
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Scanning...", total=total_requests)

        for url in urls:
            for strategy in STRATEGIES:
                progress.update(
                    task,
                    description=f"[cyan]{strategy.upper():>7}[/cyan] {url}",
                )

                data = _fetch_pagespeed(url, strategy, api_key)

                if data is not None:
                    scores = _extract_scores(data)
                    result = {
                        "url": url,
                        "strategy": strategy,
                        **scores,
                    }
                    results.append(result)
                else:
                    # Record the attempt with None scores so we know it failed
                    result = {
                        "url": url,
                        "strategy": strategy,
                        "performance": None,
                        "accessibility": None,
                        "best-practices": None,
                        "seo": None,
                    }
                    results.append(result)

                progress.advance(task)

                # Rate-limit delay (skip after the very last request)
                if not (
                    url == urls[-1]
                    and strategy == STRATEGIES[-1]
                ):
                    time.sleep(delay)

    console.print()
    success_count = sum(
        1
        for r in results
        if r["performance"] is not None
    )
    console.print(
        f"[green]✓[/green] Completed: "
        f"[bold]{success_count}[/bold]/{total_requests} "
        f"successful API calls."
    )

    return results
