"""
scanner.py — PageSpeed Insights API Scanner Module (Concurrent)

Handles all interactions with the Google PageSpeed Insights V5 API.
For each URL it runs both 'mobile' and 'desktop' strategies and extracts:
  • Category scores   (Performance, Accessibility, Best Practices, SEO)
  • Lab metrics       (FCP, LCP, CLS, TBT, Speed Index, TTI)
  • Field / CrUX data (FCP, LCP, CLS, INP, TTFB — when available)
  • Top opportunities (recommendations with estimated savings)
  • Diagnostics       (informational audits)

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

# Lab metric audit IDs → human-readable names
LAB_METRIC_IDS = {
    "first-contentful-paint": "FCP",
    "largest-contentful-paint": "LCP",
    "cumulative-layout-shift": "CLS",
    "total-blocking-time": "TBT",
    "speed-index": "Speed Index",
    "interactive": "TTI",
}

# CrUX field metric keys → human-readable names
FIELD_METRIC_KEYS = {
    "FIRST_CONTENTFUL_PAINT_MS": "FCP",
    "LARGEST_CONTENTFUL_PAINT_MS": "LCP",
    "CUMULATIVE_LAYOUT_SHIFT_SCORE": "CLS",
    "INTERACTION_TO_NEXT_PAINT": "INP",
    "EXPERIMENTAL_TIME_TO_FIRST_BYTE": "TTFB",
    "FIRST_INPUT_DELAY_MS": "FID",
}

# Maximum number of opportunities / diagnostics to extract per scan
MAX_OPPORTUNITIES = 10
MAX_DIAGNOSTICS = 5

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
        "category": CATEGORIES,
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


# ── Extraction helpers ──────────────────────────────────────────────────────


def _extract_category_scores(
    data: Dict[str, Any],
) -> Dict[str, Optional[int]]:
    """
    Extract the four Lighthouse category scores (0–100).
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


def _extract_lab_metrics(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract Core Web Vitals and other lab metrics from Lighthouse audits.

    Returns a dict like:
        {"lab_FCP": "1.8 s", "lab_FCP_ms": 1800, "lab_LCP": "2.5 s", ...}
    """
    audits = data.get("lighthouseResult", {}).get("audits", {})
    metrics: Dict[str, Any] = {}

    for audit_id, label in LAB_METRIC_IDS.items():
        audit = audits.get(audit_id, {})
        # displayValue is the human-readable string ("1.8 s", "0.12")
        metrics[f"lab_{label}"] = audit.get("displayValue")
        # numericValue is the raw number (ms or unitless for CLS)
        metrics[f"lab_{label}_value"] = audit.get("numericValue")
        # score 0–1 for colour coding
        score = audit.get("score")
        metrics[f"lab_{label}_score"] = (
            int(score * 100) if score is not None else None
        )

    return metrics


def _extract_field_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract Chrome User Experience Report (CrUX) field data from the
    ``loadingExperience`` section of the API response.

    Returns a dict like:
        {"field_overall": "SLOW", "field_FCP": "1,200 ms",
         "field_FCP_category": "FAST", "field_FCP_percentile": 1200, ...}
    """
    loading_exp = data.get("loadingExperience", {})
    field: Dict[str, Any] = {}

    # Overall field category (FAST / AVERAGE / SLOW / NONE)
    field["field_overall"] = loading_exp.get("overall_category")

    # Origin-level flag
    field["field_origin_fallback"] = loading_exp.get(
        "origin_fallback", False
    )

    metrics = loading_exp.get("metrics", {})

    for api_key_name, label in FIELD_METRIC_KEYS.items():
        metric = metrics.get(api_key_name, {})
        if metric:
            field[f"field_{label}_category"] = metric.get("category")
            field[f"field_{label}_percentile"] = metric.get("percentile")

            # Build distributions (GOOD / NEEDS_IMPROVEMENT / POOR %)
            distributions = metric.get("distributions", [])
            if distributions and len(distributions) == 3:
                field[f"field_{label}_good"] = round(
                    distributions[0].get("proportion", 0) * 100, 1
                )
                field[f"field_{label}_needs_improvement"] = round(
                    distributions[1].get("proportion", 0) * 100, 1
                )
                field[f"field_{label}_poor"] = round(
                    distributions[2].get("proportion", 0) * 100, 1
                )
        else:
            field[f"field_{label}_category"] = None
            field[f"field_{label}_percentile"] = None

    return field


def _extract_opportunities(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract the top Lighthouse opportunities (performance suggestions
    with estimated savings).

    Returns a list of dicts sorted by potential savings (descending):
        [{"id": "...", "title": "...", "savings_ms": 1200,
          "savings_display": "1.2 s", "description": "..."}, ...]
    """
    audits = data.get("lighthouseResult", {}).get("audits", {})
    perf_cat = (
        data.get("lighthouseResult", {})
        .get("categories", {})
        .get("performance", {})
    )
    audit_refs = perf_cat.get("auditRefs", [])

    # Collect opportunity-type audits that have overallSavingsMs
    opportunities: List[Dict[str, Any]] = []
    for ref in audit_refs:
        if ref.get("group") != "opportunity":
            continue
        audit_id = ref.get("id", "")
        audit = audits.get(audit_id, {})
        # Skip audits that already pass (score == 1)
        if audit.get("score") == 1:
            continue

        savings_ms = (
            audit.get("details", {}).get("overallSavingsMs")
            or audit.get("numericValue")
        )

        opportunities.append(
            {
                "id": audit_id,
                "title": audit.get("title", audit_id),
                "description": audit.get("description", ""),
                "savings_ms": savings_ms if savings_ms else 0,
                "display_value": audit.get("displayValue", ""),
                "score": audit.get("score"),
            }
        )

    # Sort by biggest savings first, take top N
    opportunities.sort(key=lambda o: o.get("savings_ms", 0), reverse=True)
    return opportunities[:MAX_OPPORTUNITIES]


def _extract_diagnostics(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract top Lighthouse diagnostics (informational audits that
    highlight issues but don't have a direct savings estimate).

    Returns a list of dicts:
        [{"id": "...", "title": "...", "display_value": "...",
          "description": "..."}, ...]
    """
    audits = data.get("lighthouseResult", {}).get("audits", {})
    perf_cat = (
        data.get("lighthouseResult", {})
        .get("categories", {})
        .get("performance", {})
    )
    audit_refs = perf_cat.get("auditRefs", [])

    diagnostics: List[Dict[str, Any]] = []
    for ref in audit_refs:
        if ref.get("group") != "diagnostics":
            continue
        audit_id = ref.get("id", "")
        audit = audits.get(audit_id, {})
        if audit.get("score") == 1:
            continue

        diagnostics.append(
            {
                "id": audit_id,
                "title": audit.get("title", audit_id),
                "description": audit.get("description", ""),
                "display_value": audit.get("displayValue", ""),
                "score": audit.get("score"),
            }
        )

    return diagnostics[:MAX_DIAGNOSTICS]


# ── Scan functions ──────────────────────────────────────────────────────────


def _scan_single(
    url: str, strategy: str, api_key: str
) -> Dict[str, Any]:
    """
    Scan a single URL + strategy combination and extract full data.

    This is the unit of work submitted to the thread pool.
    """
    data = _fetch_pagespeed(url, strategy, api_key)

    if data is None:
        return {
            "url": url,
            "strategy": strategy,
            "performance": None,
            "accessibility": None,
            "best-practices": None,
            "seo": None,
            "lab_metrics": {},
            "field_data": {},
            "opportunities": [],
            "diagnostics": [],
        }

    scores = _extract_category_scores(data)
    lab = _extract_lab_metrics(data)
    field = _extract_field_data(data)
    opps = _extract_opportunities(data)
    diags = _extract_diagnostics(data)

    return {
        "url": url,
        "strategy": strategy,
        **scores,
        "lab_metrics": lab,
        "field_data": field,
        "opportunities": opps,
        "diagnostics": diags,
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
                     (default 10).

    Returns:
        A list of result dicts with scores, lab metrics, field data,
        opportunities, and diagnostics.
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

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_job = {
                executor.submit(_scan_single, url, strategy, api_key): (
                    url,
                    strategy,
                )
                for url, strategy in jobs
            }

            for future in as_completed(future_to_job):
                url, strategy = future_to_job[future]
                try:
                    result = future.result()
                except Exception as exc:
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
                        "lab_metrics": {},
                        "field_data": {},
                        "opportunities": [],
                        "diagnostics": [],
                    }

                with _results_lock:
                    results.append(result)

                progress.update(
                    task,
                    description=(
                        f"[green]✓[/green] [cyan]{strategy.upper():>7}"
                        f"[/cyan] {url}"
                    ),
                )
                progress.advance(task)

    # Sort results by original URL order, then strategy
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
        1 for r in results if r["performance"] is not None
    )
    console.print(
        f"[green]✓[/green] Completed: "
        f"[bold]{success_count}[/bold]/{total_requests} "
        f"successful API calls."
    )

    return results
