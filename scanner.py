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

Reliability features:
  • Retry with exponential back-off (3 attempts for 400/429/5xx)
  • Per-second rate limiter (token-bucket) to avoid API burst throttling
  • URL validation & sanitisation before sending
  • Full error-body logging for easier debugging
"""

import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlparse, urlunparse

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

# ── Retry & rate-limit configuration ───────────────────────────────────────

MAX_RETRIES = 3            # Total attempts per API call (1 original + 2 retries)
RETRY_BASE_DELAY = 4.0     # Seconds — doubled each retry (4 → 8 → 16)
RETRYABLE_STATUS_CODES = {400, 429, 500, 502, 503}

# Default requests per second across all threads (token-bucket)
DEFAULT_RATE_LIMIT = 5     # 5 req/s is safe for free-tier PSI API


# ── Token-bucket rate limiter ───────────────────────────────────────────────

class _RateLimiter:
    """Thread-safe token-bucket rate limiter."""

    def __init__(self, rate: float):
        """
        Args:
            rate: Maximum requests per second.
        """
        self._rate = rate
        self._lock = threading.Lock()
        self._tokens = rate
        self._last_refill = time.monotonic()

    def acquire(self) -> None:
        """Block until a token is available."""
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_refill
                self._tokens = min(
                    self._rate, self._tokens + elapsed * self._rate
                )
                self._last_refill = now

                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return

            # No token — wait a short interval and retry
            time.sleep(1.0 / self._rate)

# Thread-safe lock for appending results
_results_lock = threading.Lock()


# ── URL validation & sanitisation ───────────────────────────────────────────

# Domains known to be URL shorteners / redirect services
_SHORTLINK_DOMAINS = {
    "bit.ly", "goo.gl", "t.co", "tinyurl.com", "ow.ly",
    "buff.ly", "is.gd", "v.gd", "rebrand.ly", "cutt.ly",
    "shorturl.at", "tiny.cc", "lnkd.in",
}


def _is_shortlink(url: str) -> bool:
    """Return True if the URL belongs to a known shortlink domain."""
    try:
        host = urlparse(url).hostname or ""
        # Also catch sub-domains like "1.envato.market"
        return (
            host in _SHORTLINK_DOMAINS
            or any(host.endswith(f".{d}") for d in _SHORTLINK_DOMAINS)
        )
    except Exception:
        return False


def _resolve_redirect(url: str, timeout: int = 10) -> str:
    """
    Follow redirects and return the final destination URL.

    Falls back to the original URL on any error.
    """
    try:
        resp = requests.head(
            url, allow_redirects=True, timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        final = resp.url
        if final and final != url:
            console.print(
                f"  [cyan]↳ Resolved[/cyan] {url} → {final}"
            )
        return final
    except Exception:
        return url


def _sanitise_url(url: str) -> Optional[str]:
    """
    Validate and sanitise a URL before sending it to the PSI API.

    Returns the cleaned URL, or None if the URL is invalid.
    """
    url = url.strip()
    if not url:
        return None

    # Must have a scheme
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return None

    if not parsed.hostname:
        return None

    # Encode non-ASCII / unsafe chars in the path
    safe_path = quote(parsed.path, safe="/:@!$&'()*+,;=-._~")

    # Rebuild with encoded path
    sanitised = urlunparse((
        parsed.scheme,
        parsed.netloc,
        safe_path,
        parsed.params,
        parsed.query,
        "",  # drop fragment — API ignores it
    ))

    return sanitised


def validate_urls(
    urls: List[str],
    resolve_redirects: bool = True,
) -> Tuple[List[str], List[Dict[str, str]]]:
    """
    Validate and sanitise a list of URLs before scanning.

    Performs:
      1. Basic format validation (scheme, host)
      2. Shortlink detection & redirect resolution
      3. URL encoding / sanitisation

    Args:
        urls:              Raw URL list from the CSV.
        resolve_redirects: Whether to follow shortlink redirects.

    Returns:
        (valid_urls, skipped) — skipped contains {url, reason} dicts.
    """
    valid: List[str] = []
    skipped: List[Dict[str, str]] = []

    console.print()
    console.rule("[bold cyan]Validating URLs[/bold cyan]")

    for url in urls:
        # 1. Basic sanitisation
        clean = _sanitise_url(url)
        if clean is None:
            skipped.append({"url": url, "reason": "Invalid URL format"})
            console.print(
                f"  [yellow]⚠ Skipped[/yellow] {url} — invalid format"
            )
            continue

        # 2. Shortlink resolution
        if _is_shortlink(clean) and resolve_redirects:
            resolved = _resolve_redirect(clean)
            resolved_clean = _sanitise_url(resolved)
            if resolved_clean is None:
                skipped.append({
                    "url": url,
                    "reason": f"Redirect resolved to invalid URL: {resolved}",
                })
                console.print(
                    f"  [yellow]⚠ Skipped[/yellow] {url} — "
                    f"redirect led to invalid URL"
                )
                continue
            clean = resolved_clean

        valid.append(clean)

    if skipped:
        console.print(
            f"\n  [yellow]⚠[/yellow] {len(skipped)} URL(s) skipped "
            f"(see above). {len(valid)} URL(s) will be scanned."
        )
    else:
        console.print(
            f"  [green]✓[/green] All {len(valid)} URL(s) passed validation."
        )

    return valid, skipped


def _fetch_pagespeed(
    url: str,
    strategy: str,
    api_key: str,
    rate_limiter: Optional[_RateLimiter] = None,
) -> Optional[Dict[str, Any]]:
    """
    Make a single PageSpeed Insights API request **with retries**.

    Retries on 400/429/5xx with exponential back-off.  On each
    failure the full error body is logged for diagnosis.

    Args:
        url:          The fully-qualified URL to analyse.
        strategy:     Either 'mobile' or 'desktop'.
        api_key:      Google API key.
        rate_limiter: Optional token-bucket rate limiter.

    Returns:
        The JSON response dict on success, or None on failure.
    """
    params = {
        "url": url,
        "key": api_key,
        "strategy": strategy,
        "category": CATEGORIES,
    }

    last_error_msg = ""
    for attempt in range(1, MAX_RETRIES + 1):
        # Respect rate limit before every request
        if rate_limiter:
            rate_limiter.acquire()

        try:
            response = requests.get(API_ENDPOINT, params=params, timeout=120)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code
            # Extract the real error message from the API response body
            error_detail = _extract_api_error(exc.response)
            last_error_msg = (
                f"HTTP {status} — {exc.response.reason}"
                f"{f' | {error_detail}' if error_detail else ''}"
            )

            if status in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                wait = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                console.print(
                    f"  [yellow]⟳ Retry {attempt}/{MAX_RETRIES}[/yellow] "
                    f"for {url} ({strategy}): {last_error_msg} "
                    f"— waiting {wait:.0f}s"
                )
                time.sleep(wait)
                continue

            # Final attempt failed or non-retryable status
            console.print(
                f"  [red]✗ Failed[/red] {url} ({strategy}): {last_error_msg}"
            )

        except requests.exceptions.ConnectionError:
            last_error_msg = "Connection error — could not reach the API"
            if attempt < MAX_RETRIES:
                wait = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                console.print(
                    f"  [yellow]⟳ Retry {attempt}/{MAX_RETRIES}[/yellow] "
                    f"for {url} ({strategy}): {last_error_msg} "
                    f"— waiting {wait:.0f}s"
                )
                time.sleep(wait)
                continue
            console.print(
                f"  [red]✗ Failed[/red] {url} ({strategy}): {last_error_msg}"
            )

        except requests.exceptions.Timeout:
            last_error_msg = "Request timed out (>120s)"
            if attempt < MAX_RETRIES:
                wait = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                console.print(
                    f"  [yellow]⟳ Retry {attempt}/{MAX_RETRIES}[/yellow] "
                    f"for {url} ({strategy}): {last_error_msg} "
                    f"— waiting {wait:.0f}s"
                )
                time.sleep(wait)
                continue
            console.print(
                f"  [red]✗ Failed[/red] {url} ({strategy}): {last_error_msg}"
            )

        except requests.exceptions.RequestException as exc:
            console.print(
                f"  [red]✗ Failed[/red] {url} ({strategy}): {exc}"
            )

        return None

    return None


def _extract_api_error(response: requests.Response) -> str:
    """
    Extract the human-readable error message from a PSI API error
    response body.  Returns an empty string if parsing fails.
    """
    try:
        body = response.json()
        error = body.get("error", {})
        # Google API errors have a "message" field
        message = error.get("message", "")
        # Sometimes there are nested "errors" with "reason"
        reasons = [
            e.get("reason", "")
            for e in error.get("errors", [])
            if e.get("reason")
        ]
        parts = [message] + reasons
        return " | ".join(p for p in parts if p)
    except Exception:
        # Fall back to raw text (truncated)
        try:
            return response.text[:200]
        except Exception:
            return ""


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
    url: str,
    strategy: str,
    api_key: str,
    rate_limiter: Optional[_RateLimiter] = None,
) -> Dict[str, Any]:
    """
    Scan a single URL + strategy combination and extract full data.

    This is the unit of work submitted to the thread pool.
    """
    data = _fetch_pagespeed(url, strategy, api_key, rate_limiter)

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
    rate_limit: float = DEFAULT_RATE_LIMIT,
) -> List[Dict[str, Any]]:
    """
    Scan a list of URLs with the PageSpeed Insights API **concurrently**.

    Each URL is tested for both 'mobile' and 'desktop' strategies.
    All API calls are dispatched across a thread pool so they run in
    parallel — like each URL having its own channel.

    A token-bucket rate limiter ensures no more than *rate_limit*
    requests are sent per second, regardless of the number of workers.
    Failed requests are retried with exponential back-off.

    Args:
        urls:        List of fully-qualified URLs to scan.
        api_key:     Google API key.
        delay:       Kept for interface compatibility (ignored in
                     concurrent mode — parallelism handles throughput).
        max_workers: Number of concurrent threads / "channels"
                     (default 10).
        rate_limit:  Maximum API requests per second (default 5).

    Returns:
        A list of result dicts with scores, lab metrics, field data,
        opportunities, and diagnostics.
    """
    results: List[Dict[str, Any]] = []
    total_requests = len(urls) * len(STRATEGIES)

    # Create rate limiter shared across all threads
    limiter = _RateLimiter(rate_limit)

    console.print()
    console.rule("[bold cyan]Scanning URLs (Concurrent)[/bold cyan]")
    console.print(
        f"URLs: [bold]{len(urls)}[/bold]  |  "
        f"Strategies: [bold]{', '.join(STRATEGIES)}[/bold]  |  "
        f"Total API calls: [bold]{total_requests}[/bold]  |  "
        f"Workers: [bold]{max_workers}[/bold]  |  "
        f"Rate limit: [bold]{rate_limit:.0f}[/bold] req/s  |  "
        f"Max retries: [bold]{MAX_RETRIES}[/bold]"
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
                executor.submit(
                    _scan_single, url, strategy, api_key, limiter
                ): (url, strategy)
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
