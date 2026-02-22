"""
scanner.py — PageSpeed Insights API Scanner Module (Concurrent)

Handles all interactions with the Google PageSpeed Insights V5 API.
For each URL it runs both 'mobile' and 'desktop' strategies and extracts
scores for Performance, Accessibility, Best Practices, and SEO.

Uses concurrent.futures.ThreadPoolExecutor so that many API calls run
in parallel ("each URL on its own channel"), dramatically reducing the
total wall-clock time from hours to minutes.
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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

# Thread-safe lock for appending results
_results_lock = threading.Lock()


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


def _scan_single(
    url: str, strategy: str, api_key: str
) -> Dict[str, Any]:
    """
    Scan a single URL + strategy combination.

    This is the unit of work submitted to the thread pool.

    Args:
        url:      Fully-qualified URL.
        strategy: 'mobile' or 'desktop'.
        api_key:  Google API key.

    Returns:
        A result dict with url, strategy, and the four category scores.
    """
    data = _fetch_pagespeed(url, strategy, api_key)

    if data is not None:
        scores = _extract_scores(data)
        return {"url": url, "strategy": strategy, **scores}

    # Record the attempt with None scores so we know it failed
    return {
        "url": url,
        "strategy": strategy,
        "performance": None,
        "accessibility": None,
        "best-practices": None,
        "seo": None,
    }


def scan_urls(
    urls: List[str],
    api_key: str,
    delay: float = 2.0,
    max_workers: int = 10,
) -> List[Dict[str, Any]]:
    """
    Scan a list of URLs with the PageSpeed Insights API **concurrently**.

    Each URL is tested for both 'mobile' and 'desktop' strategies.
    All API calls are dispatched across a thread pool so they run in
    parallel — like each URL having its own channel.

    Args:
        urls:        List of fully-qualified URLs to scan.
        api_key:     Google API key.
        delay:       Kept for interface compatibility (ignored in
                     concurrent mode — parallelism handles throughput).
        max_workers: Number of concurrent threads / "channels"
                     (default 10). Increase for more speed, decrease
                     if you hit API rate-limit errors.

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
    console.rule("[bold cyan]Scanning URLs (Concurrent)[/bold cyan]")
    console.print(
        f"URLs: [bold]{len(urls)}[/bold]  |  "
        f"Strategies: [bold]{', '.join(STRATEGIES)}[/bold]  |  "
        f"Total API calls: [bold]{total_requests}[/bold]  |  "
        f"Workers: [bold]{max_workers}[/bold]"
    )
    console.print()

    # Build the list of (url, strategy) jobs
    jobs = [
        (url, strategy)
        for url in urls
        for strategy in STRATEGIES
    ]

    # Rich progress bar for visual feedback
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            "[cyan]Scanning in parallel…[/cyan]", total=total_requests
        )

        # Submit all jobs to the thread pool
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_job = {
                executor.submit(_scan_single, url, strategy, api_key): (
                    url,
                    strategy,
                )
                for url, strategy in jobs
            }

            # Collect results as they complete
            for future in as_completed(future_to_job):
                url, strategy = future_to_job[future]
                try:
                    result = future.result()
                except Exception as exc:
                    # Catch any unexpected exception from the thread
                    console.print(
                        f"  [red]Unexpected error[/red] for {url} "
                        f"({strategy}): {exc}"
                    )
                    result = {
                        "url": url,
                        "strategy": strategy,
                        "performance": None,
                        "accessibility": None,
                        "best-practices": None,
                        "seo": None,
                    }

                with _results_lock:
                    results.append(result)

                # Update progress bar with the latest completed job
                progress.update(
                    task,
                    description=(
                        f"[green]✓[/green] [cyan]{strategy.upper():>7}"
                        f"[/cyan] {url}"
                    ),
                )
                progress.advance(task)

    # Sort results by original URL order, then strategy, for clean output
    url_order = {url: idx for idx, url in enumerate(urls)}
    strategy_order = {s: idx for idx, s in enumerate(STRATEGIES)}
    results.sort(
        key=lambda r: (
            url_order.get(r["url"], len(urls)),
            strategy_order.get(r["strategy"], len(STRATEGIES)),
        )
    )

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
