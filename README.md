# Web Performance Scanner

A modular Python CLI tool that batch-scans website URLs using the **Google PageSpeed Insights API** and produces a **comprehensive, multi-section performance report** with lab metrics, field data (CrUX), recommendations, and actionable improvement suggestions.

---

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
  - [API Key](#api-key)
  - [Environment Variables](#environment-variables)
- [URL Input](#url-input)
  - [CSV File Format](#csv-file-format)
- [Usage](#usage)
  - [Basic Run](#basic-run)
  - [CLI Arguments](#cli-arguments)
  - [Examples](#examples)
- [Reliability & Rate Limiting](#reliability--rate-limiting)
  - [Retry with Exponential Back-off](#retry-with-exponential-back-off)
  - [Token-Bucket Rate Limiter](#token-bucket-rate-limiter)
  - [URL Validation & Sanitisation](#url-validation--sanitisation)
- [Output](#output)
  - [Report Sections](#report-sections)
  - [CSV Export](#csv-export)
  - [Score Colour Coding](#score-colour-coding)
- [Module Reference](#module-reference)
  - [main.py](#mainpy)
  - [reader.py](#readerpy)
  - [scanner.py](#scannerpy)
  - [reporter.py](#reporterpy)
- [Performance & Concurrency](#performance--concurrency)
- [Error Handling](#error-handling)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)
- [License](#license)

---

## Features

### Scanning

- **Batch scanning** — Analyse hundreds of URLs in a single run.
- **Concurrent API calls** — Uses a thread pool (`ThreadPoolExecutor`) so every URL gets its own "channel"; scans that previously took ~2 hours now finish in ~10–15 minutes.
- **Dual strategy** — Every URL is tested for both **mobile** and **desktop**.
- **CSV-driven batch input** — Specify a CSV file with `--csv` containing the URLs or routes to scan.
- **Flexible URL format** — CSV may contain full URLs (`https://…`) *or* bare route paths (`/about`) combined with a configurable base domain.
- **Automatic deduplication** — Duplicate URLs are removed before scanning.

### Reliability

- **Retry with exponential back-off** — Failed API calls (400/429/5xx) are retried up to 3 times with increasing delays (4s → 8s → 16s).
- **Token-bucket rate limiter** — Caps requests per second across all threads (default: 5 req/s) to prevent API burst throttling.
- **URL validation & sanitisation** — Pre-scan checks filter out malformed URLs, resolve shortlink redirects, and encode unsafe characters.
- **Detailed error logging** — Full API error response bodies are parsed and displayed, not just the HTTP status code.

### Data Extraction

- **Four Lighthouse categories** — Performance, Accessibility, Best Practices, and SEO scores (0–100).
- **Lab metrics** — First Contentful Paint (FCP), Largest Contentful Paint (LCP), Cumulative Layout Shift (CLS), Total Blocking Time (TBT), Speed Index, and Time to Interactive (TTI) with display values, raw values, and individual scores.
- **Field / CrUX data** — Real-user metrics from the Chrome User Experience Report: FCP, LCP, CLS, INP, TTFB, and FID with percentile values, category ratings (FAST/AVERAGE/SLOW), and distribution percentages.
- **Opportunities** — Top 10 recommendations with estimated time savings (ms) per URL.
- **Diagnostics** — Top 5 informational audit findings per URL.

### Reporting

- **6-section terminal report** — Comprehensive colour-coded output powered by [Rich](https://github.com/Textualize/rich).
- **Separate mobile & desktop averages** — Average scores calculated independently for each strategy, plus overall averages, with performance ratings (Excellent/Good/Needs Improvement/Poor).
- **Lab metrics table** — Core Web Vitals displayed with display values, raw values, and colour-coded scores per URL.
- **Field data table** — CrUX real-user metrics with percentile values, categories, and distribution breakdowns (Good/Needs Improvement/Poor %).
- **Recommendations panel** — Aggregated opportunities ranked by frequency and average savings; most common diagnostics listed.
- **Actionable improvement summary** — Auto-generated priority areas, worst-performing routes, category-specific suggestions, lab-metric suggestions, and mobile-vs-desktop gap analysis.
- **CSV export** — Full results with flattened lab metrics, field data, top opportunity, and 3 average rows (mobile/desktop/overall).
- **Secure configuration** — API key loaded from a `.env` file via `python-dotenv`.
- **Graceful error handling** — File-not-found, HTTP errors, timeouts, and malformed API responses are all caught and reported cleanly.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                            main.py                                   │
│                  CLI entry point & orchestrator                       │
│     Loads .env → Parses args → Coordinates modules below             │
└──────┬──────────────────┬──────────────────────┬─────────────────────┘
       │                  │                      │
       ▼                  ▼                      ▼
 ┌───────────┐   ┌───────────────┐       ┌──────────────┐
 │ reader.py │   │  scanner.py   │       │ reporter.py  │
 │           │   │               │       │              │
 │ CSV       │   │ PageSpeed API │       │ 6-section    │
 │ parsing   │   │ (concurrent   │       │ terminal     │
 │ & URL     │   │  threads)     │       │ report:      │
 │ building  │   │               │       │  • Scores    │
 │           │   │ Extracts:     │       │  • Averages  │
 │           │   │  • Scores     │       │  • Lab data  │
 │           │   │  • Lab data   │       │  • Field data│
 │           │   │  • Field data │       │  • Recs      │
 │           │   │  • Opps       │       │  • Summary   │
 │           │   │  • Diagnostics│       │ + CSV export │
 └───────────┘   └───────────────┘       └──────────────┘
```

**Data flow:**

1. `reader.py` reads `urls.csv` and separates full URLs from route paths.
2. Route paths are combined with the base domain to produce full URLs.
3. `scanner.py` dispatches all URL × strategy combinations to a thread pool and collects:
   - 4 Lighthouse category scores
   - 6 lab metrics (FCP, LCP, CLS, TBT, Speed Index, TTI)
   - CrUX field data (FCP, LCP, CLS, INP, TTFB, FID)
   - Top 10 opportunities with estimated savings
   - Top 5 diagnostics
4. `reporter.py` builds a DataFrame, computes separate mobile/desktop/overall averages, prints a 6-section colour-coded report, and exports everything to CSV.

---

## Prerequisites

- **Python 3.10+** (tested with Python 3.13)
- A **Google PageSpeed Insights API key** — free to obtain from the [Google Cloud Console](https://developers.google.com/speed/docs/insights/v5/get-started)

---

## Installation

### 1. Clone the repository

```bash
git clone <repository-url>
cd webperformancescanner
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

### 3. Activate the virtual environment

**Windows (PowerShell):**
```powershell
.\venv\Scripts\Activate.ps1
```

**Windows (cmd):**
```cmd
.\venv\Scripts\activate.bat
```

**Linux / macOS:**
```bash
source venv/bin/activate
```

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

**Dependencies:**

| Package        | Purpose                                 |
|----------------|-----------------------------------------|
| `requests`     | HTTP client for PageSpeed Insights API  |
| `pandas`       | Data aggregation & averaging            |
| `python-dotenv`| Load API key from `.env` file           |
| `rich`         | Colour-coded terminal tables & progress |

> `csv`, `argparse`, `threading`, `concurrent.futures` are Python standard library modules — no installation required.

---

## Configuration

### API Key

1. Visit the [Google PageSpeed Insights – Get Started](https://developers.google.com/speed/docs/insights/v5/get-started) page.
2. Create or select a Google Cloud project and enable the **PageSpeed Insights API**.
3. Generate an API key from the **Credentials** panel.
4. Paste the key into your `.env` file (see below).

### Environment Variables

Create a `.env` file in the project root (already git-ignored):

```dotenv
# Required — your Google API key
API_KEY=AIzaSy__your_key_here__

# Optional — default base domain for route paths
BASE_URL=https://example.com

# Optional — delay between API requests (seconds, default: 2)
REQUEST_DELAY=2
```

| Variable        | Required | Default              | Description                                      |
|-----------------|----------|----------------------|--------------------------------------------------|
| `API_KEY`       | **Yes**  | —                    | Google PageSpeed Insights API key                |
| `BASE_URL`      | No*      | `https://example.com`| Base domain prepended to route paths             |
| `REQUEST_DELAY` | No       | `2`                  | Delay between sequential requests (legacy param) |

> \* `BASE_URL` is only required if your URLs include bare route paths (e.g. `/about`). If using full URLs, it is not needed.

---

## URL Input

The scanner reads URLs from a **CSV file** specified with the required `--csv` argument. The file must have a **header row** and one entry per line.

```bash
python main.py --csv my_routes.csv
```

### CSV File Format

**Option A — Full URLs (recommended for multi-domain scans):**

```csv
URL
https://example.com/
https://example.com/about
https://example.com/pricing
https://another-site.com/
```

**Option B — Route paths (combined with `BASE_URL`):**

```csv
route
/
/about
/pricing
/contact
```

**Option C — Mixed (both formats in one file):**

```csv
URL
https://other-domain.com/page
/about
/pricing
```

Full URLs are used as-is; route paths have the base domain prepended.

---

## Usage

### Basic Run

```bash
python main.py --csv urls.csv
```

### CLI Arguments

| Argument         | Type   | Default       | Description                                                          |
|------------------|--------|---------------|----------------------------------------------------------------------|
| `--csv`          | string | **(required)**| Path to a CSV file with URLs/routes to scan in batch.                |
| `--base-url`     | string | `.env` value  | Base domain to prepend to route paths                                |
| `--delay`        | float  | `2.0`         | Legacy delay parameter (kept for compatibility)                      |
| `--output`       | string | `results.csv` | Path for the exported results file                                   |
| `--workers`      | int    | `10`          | Number of concurrent threads ("channels") for parallel scans         |
| `--rate-limit`   | float  | `5.0`         | Maximum API requests per second across all workers                   |
| `--no-validate`  | flag   | off           | Skip URL validation and shortlink resolution                         |

### Examples

```bash
# Scan from a CSV file with defaults
python main.py --csv urls.csv

# Use a custom CSV and 20 parallel workers
python main.py --csv my_routes.csv --workers 20

# Export results to a custom file
python main.py --csv urls.csv --output report_feb2026.csv

# Conservative mode (fewer workers + lower rate limit)
python main.py --csv urls.csv --workers 5 --rate-limit 2

# Skip URL validation (if you're sure all URLs are clean)
python main.py --csv urls.csv --no-validate

# Full example with all options
python main.py --csv routes.csv --base-url https://mysite.com --workers 15 --rate-limit 4 --output scan.csv
```

---

## Reliability & Rate Limiting

### Retry with Exponential Back-off

Every API call is retried up to **3 times** on failure. Retryable HTTP status codes: `400`, `429`, `500`, `502`, `503`.

| Attempt | Delay before retry |
|---------|-------------------|
| 1st     | 4 seconds          |
| 2nd     | 8 seconds          |
| 3rd     | Final failure      |

The actual Google API error message is extracted from the response body and displayed:

```
⟳ Retry 1/3 for https://example.com/checkout (mobile):
  HTTP 400 — Bad Request | LIGHTHOUSE_ERROR | ERRORED_DOCUMENT_REQUEST — waiting 4s
```

### Token-Bucket Rate Limiter

A shared rate limiter ensures no more than `--rate-limit` requests per second are sent across all worker threads. This prevents burst-triggered `400` errors that occur when too many requests hit the API simultaneously.

| Rate limit | Behaviour                                           |
|------------|-----------------------------------------------------|
| `5` (default) | Good balance of speed and reliability             |
| `2–3`      | Conservative — use if you still see 400 errors       |
| `8–10`     | Aggressive — may trigger throttling on free tier     |

### URL Validation & Sanitisation

Before scanning, all URLs pass through a validation pipeline (disable with `--no-validate`):

1. **Format check** — Ensures valid scheme (`http`/`https`) and hostname.
2. **Shortlink detection** — URLs from `bit.ly`, `goo.gl`, `t.co`, etc. are automatically resolved to their final destination via HTTP redirect.
3. **Character encoding** — Non-ASCII and unsafe characters in URL paths are percent-encoded.
4. **Fragment stripping** — URL fragments (`#section`) are removed (API ignores them).
5. **Invalid URL skipping** — Malformed URLs are skipped with a warning instead of wasting API calls.

---

## Output

### Report Sections

The scanner produces a **6-section terminal report** using the Rich library. Each section is displayed as a colour-coded table or panel.

#### Section 1 — Category Scores

Individual Lighthouse scores for each URL × strategy:

```
┌──────────────────────────────────┬──────────┬─────────────┬───────────────┬────────────────┬─────┐
│ URL                              │ Strategy │ Performance │ Accessibility │ Best Practices │ SEO │
├──────────────────────────────────┼──────────┼─────────────┼───────────────┼────────────────┼─────┤
│ https://example.com/             │ Mobile   │     45      │      92       │       87       │  91 │
│ https://example.com/             │ Desktop  │     78      │      92       │       87       │  91 │
│ https://example.com/about        │ Mobile   │     62      │      95       │       91       │  89 │
│ https://example.com/about        │ Desktop  │     91      │      95       │       91       │  89 │
└──────────────────────────────────┴──────────┴─────────────┴───────────────┴────────────────┴─────┘
```

#### Section 2 — Strategy Averages

Three separate tables showing average scores for **Mobile**, **Desktop**, and **Overall**, with performance ratings:

```
📱 MOBILE Averages                          🖥️ DESKTOP Averages
┌─────────────┬───────┬────────┐            ┌─────────────┬───────┬────────┐
│ Category    │ Score │ Rating │            │ Category    │ Score │ Rating │
├─────────────┼───────┼────────┤            ├─────────────┼───────┼────────┤
│ Performance │ 53.5  │ Needs… │            │ Performance │ 84.5  │ Good   │
│ Accessib.   │ 93.5  │ Excel. │            │ Accessib.   │ 93.5  │ Excel. │
│ Best Pract. │ 89.0  │ Good   │            │ Best Pract. │ 89.0  │ Good   │
│ SEO         │ 90.0  │ Excel. │            │ SEO         │ 90.0  │ Excel. │
└─────────────┴───────┴────────┘            └─────────────┴───────┴────────┘

🌐 OVERALL Averages
┌─────────────┬───────┬────────┐
│ Category    │ Score │ Rating │
├─────────────┼───────┼────────┤
│ Performance │ 69.0  │ Needs… │
│ ...         │ ...   │ ...    │
└─────────────┴───────┴────────┘
```

Ratings: **Excellent** (≥ 90), **Good** (≥ 75), **Needs Improvement** (≥ 50), **Poor** (< 50).

#### Section 3 — Lab Metrics (Core Web Vitals)

Detailed lab data for each URL showing display values, raw values, and individual scores:

| URL | Strategy | FCP (display) | FCP (raw) | FCP (score) | LCP | CLS | TBT | SI | TTI |
|-----|----------|---------------|-----------|-------------|-----|-----|-----|----|-----|

#### Section 4 — Field Data (CrUX)

Real-user metrics from the Chrome User Experience Report (when available):

| URL | Strategy | FCP (p75) | FCP (cat) | FCP (good/avg/poor %) | LCP | CLS | INP | TTFB | FID |
|-----|----------|-----------|-----------|------------------------|-----|-----|-----|------|-----|

> **Note:** Field data is only available for URLs with enough real-user traffic in the CrUX dataset.

#### Section 5 — Recommendations

Aggregated opportunities and diagnostics across all scanned URLs:

- **Top Opportunities** — Ranked by frequency (how many URLs share the same recommendation) and average estimated savings in milliseconds.
- **Common Diagnostics** — Most frequently appearing informational audit findings.

#### Section 6 — Actionable Improvement Summary

Auto-generated panel with:

- **Priority areas** — Categories scoring below 75 that need attention.
- **Worst-performing routes** — Bottom 5 URLs by Performance score.
- **Category-specific suggestions** — Tailored tips for Performance, Accessibility, Best Practices, and SEO based on actual scores.
- **Lab-metric suggestions** — Specific advice based on FCP, LCP, CLS, TBT, and TTI values.
- **Mobile vs Desktop gap analysis** — Shows score differences and calls out mobile-specific issues when the gap is > 10 points.

### CSV Export

The `results.csv` file contains all individual results with flattened lab metrics, field data, and top opportunity, plus **3 average rows** (mobile, desktop, overall):

```csv
url,strategy,performance,accessibility,best-practices,seo,lab_FCP_display,lab_FCP_raw,lab_FCP_score,lab_LCP_display,...,field_FCP_p75,field_FCP_category,...,top_opportunity,top_opp_savings_ms
https://example.com/,mobile,45,92,87,91,2.5 s,2500,45,4.1 s,...,1800,AVERAGE,...,Reduce unused CSS,850
...
AVERAGE,Mobile,53.5,93.5,89.0,90.0,...
AVERAGE,Desktop,84.5,93.5,89.0,90.0,...
AVERAGE,Overall,69.0,93.5,89.0,90.0,...
```

### Score Colour Coding

| Colour     | Score Range | Meaning          |
|------------|-------------|------------------|
| 🟢 Green   | 90 – 100    | Good             |
| 🟡 Yellow  | 50 – 89     | Needs improvement|
| 🔴 Red     | 0 – 49      | Poor             |
| ⚫ Dim/Grey | N/A         | Scan failed      |

These thresholds match [Google's official Lighthouse scoring](https://developer.chrome.com/docs/lighthouse/performance/performance-scoring/).

Field data categories use the same colour scheme: **FAST** (green), **AVERAGE** (yellow), **SLOW** (red).

Lab metric scores use extended thresholds: ≥ 90 (green), ≥ 50 (yellow), ≥ 25 (orange), < 25 (red).

---

## Module Reference

### main.py

**Role:** CLI entry point and orchestrator.

| Function        | Description                                        |
|-----------------|----------------------------------------------------|
| `_load_env()`   | Loads variables from `.env` via `python-dotenv`    |
| `_parse_args()` | Parses CLI arguments with `argparse` (`--csv` is required) |
| `main()`        | Orchestrates the full pipeline: read → scan → report |

**Pipeline steps:**
1. Load `.env` and parse CLI arguments
2. Validate `API_KEY` (abort if missing)
3. Resolve `BASE_URL` (from CLI or `.env`)
4. Read URLs from CSV via `reader.read_urls()`
5. Build full URLs from route paths via `reader.build_full_urls()`
6. Deduplicate URLs
7. Scan all URLs concurrently via `scanner.scan_urls()` (returns enriched result dicts with scores, lab, field, opportunities, diagnostics)
8. Build DataFrame via `reporter.build_dataframe()`
9. Compute strategy averages via `reporter.compute_averages_by_strategy()` (mobile / desktop / overall)
10. Display 6-section report via `reporter.print_full_report()`
11. Export flattened CSV with 3 average rows via `reporter.export_csv()`

---

### reader.py

**Role:** CSV parsing and URL construction.

| Function                         | Description                                                 |
|----------------------------------|-------------------------------------------------------------|
| `_is_full_url(value)`            | Returns `True` if the value has an `http(s)://` scheme      |
| `read_urls(csv_path)`            | Reads CSV and separates full URLs from route paths          |
| `build_full_urls(base_url, routes)` | Prepends a base domain to a list of route paths          |

**Input format:** Single-column CSV with a header row. Each row is either a full URL or a bare route path.

**Error handling:**
- File not found → prints error, exits with code 1
- CSV parse error → prints error, exits with code 1
- Empty file → prints error, exits with code 1
- Route path missing leading `/` → auto-prepended with a warning

---

### scanner.py

**Role:** Google PageSpeed Insights API interaction with concurrent execution, retry logic, rate limiting, URL validation, and comprehensive data extraction.

| Function                                          | Description                                                                  |
|---------------------------------------------------|------------------------------------------------------------------------------|
| `_RateLimiter(rate)`                              | Thread-safe token-bucket rate limiter class                                  |
| `_is_shortlink(url)`                              | Detects URLs from known shortlink domains (bit.ly, goo.gl, etc.)             |
| `_resolve_redirect(url)`                          | Follows HTTP redirects to find the final destination URL                     |
| `_sanitise_url(url)`                              | Validates and encodes a URL; returns `None` if invalid                       |
| `validate_urls(urls, resolve_redirects)`           | Pre-scan pipeline: validate, resolve shortlinks, sanitise; returns (valid, skipped) |
| `_fetch_pagespeed(url, strategy, key, limiter)`   | Single API request with retry + exponential back-off                         |
| `_extract_api_error(response)`                    | Parses the API error response body for human-readable messages               |
| `_extract_category_scores(data)`                  | Extracts 4 category scores (0–100) from API response                         |
| `_extract_lab_metrics(data)`                      | Extracts 6 lab metrics (FCP, LCP, CLS, TBT, SI, TTI) with display/raw/score |
| `_extract_field_data(data)`                       | Extracts CrUX field data (FCP, LCP, CLS, INP, TTFB, FID) with distributions |
| `_extract_opportunities(data)`                    | Extracts top 10 opportunities sorted by estimated savings                    |
| `_extract_diagnostics(data)`                      | Extracts top 5 informational diagnostics                                     |
| `_scan_single(url, strategy, key, limiter)`       | Unit of work for one URL + strategy (submitted to thread pool)               |
| `scan_urls(urls, key, delay, max_workers, rate_limit)` | Dispatches all jobs concurrently with rate limiting                      |

**API details:**
- Endpoint: `https://www.googleapis.com/pagespeedonline/v5/runPagespeed`
- Strategies: `mobile`, `desktop`
- Categories: `performance`, `accessibility`, `best-practices`, `seo`
- Timeout: 120 seconds per request
- Retries: 3 attempts with exponential back-off (4s → 8s → 16s)
- Retryable status codes: 400, 429, 500, 502, 503

**Data extracted per scan:**

| Data Type          | Fields                                                        |
|--------------------|---------------------------------------------------------------|
| Category scores    | Performance, Accessibility, Best Practices, SEO (0–100)       |
| Lab metrics        | FCP, LCP, CLS, TBT, Speed Index, TTI (display + raw + score) |
| Field / CrUX data  | FCP, LCP, CLS, INP, TTFB, FID (p75 + category + distribution)|
| Opportunities      | Up to 10 per scan, with title + savings_ms                    |
| Diagnostics        | Up to 5 per scan, with title + display value                  |

**Concurrency model:**
- Uses `concurrent.futures.ThreadPoolExecutor` with configurable `max_workers`
- All URL × strategy pairs are submitted simultaneously
- Token-bucket rate limiter is shared across all threads
- Results are collected via `as_completed()` for real-time progress updates
- Thread-safe result collection via `threading.Lock`
- Results are sorted back into original URL order after collection

---

### reporter.py

**Role:** Comprehensive multi-section report, data aggregation, and CSV export.

| Function                                  | Description                                                              |
|-------------------------------------------|--------------------------------------------------------------------------|
| `_score_color(score)`                     | Returns a Rich colour name based on Lighthouse score thresholds          |
| `_format_score(score)`                    | Returns a coloured `rich.Text` object for scores                         |
| `_field_category_color(category)`         | Returns colour for field data categories (FAST/AVERAGE/SLOW)             |
| `_format_field_category(category)`        | Returns coloured text for field categories                               |
| `_format_ms(value)`                       | Formats millisecond values for display                                   |
| `_lab_score_color(score)`                 | Returns colour for lab scores (extended 4-tier thresholds)               |
| `build_dataframe(results)`                | Converts result dicts to a `pandas.DataFrame`                            |
| `compute_averages_by_strategy(df)`        | Computes separate mobile / desktop / overall average scores              |
| `print_scores_table(df)`                  | **Section 1** — Individual category scores per URL                       |
| `print_averages_tables(averages)`         | **Section 2** — Mobile / Desktop / Overall average tables with ratings   |
| `print_lab_metrics_table(df)`             | **Section 3** — Core Web Vitals lab data per URL                         |
| `print_field_data_table(df)`              | **Section 4** — CrUX real-user metrics with distributions                |
| `print_recommendations(df)`               | **Section 5** — Aggregated opportunities + diagnostics                   |
| `print_summary(df, averages)`             | **Section 6** — Auto-generated actionable improvement summary            |
| `_get_suggestions(category, score)`       | Returns category-specific improvement tips                               |
| `_add_lab_suggestions(suggestions, df)`   | Adds lab-metric-specific suggestions based on actual values              |
| `export_csv(df, averages, output_path)`   | Writes flattened CSV with 3 average rows                                 |
| `print_full_report(df, averages)`         | Master function that calls all 6 sections in sequence                    |

---

## Performance & Concurrency

The scanner uses a **thread pool** to run API calls in parallel, dramatically reducing wall-clock time.

| Scenario             | URLs | API Calls | Sequential Time | 10 Workers  | 20 Workers |
|----------------------|------|-----------|-----------------|-------------|------------|
| Small site           | 10   | 20        | ~7 min          | ~2 min      | ~1 min     |
| Medium site          | 50   | 100       | ~35 min         | ~5 min      | ~3 min     |
| Large site (yours)   | 189  | 378       | ~2+ hours       | ~10–15 min  | ~5–8 min   |

**How it works:**

1. Each URL × strategy pair becomes a "job".
2. Jobs are submitted to a `ThreadPoolExecutor` with `max_workers` threads.
3. A shared **token-bucket rate limiter** ensures no more than `--rate-limit` requests/second.
4. Up to `max_workers` API calls run simultaneously — each on its own “channel”.
5. Failed calls are **retried** up to 3 times with exponential back-off.
6. As each job completes, the progress bar updates in real time.
7. Once all jobs finish, results are sorted and passed to the reporter.

**Tuning `--workers` and `--rate-limit`:**

| Workers | Rate Limit | Trade-off                                                    |
|---------|------------|--------------------------------------------------------------|
| `5`     | `2`        | Very conservative — near-zero failures, slower overall       |
| `10`    | `5`        | Default — good balance of speed and API courtesy              |
| `15`    | `5`        | Faster, relying on rate limiter to smooth bursts              |
| `20`    | `8`        | Aggressive — may trigger throttling on free-tier API keys    |

> **Tip:** If you see `HTTP 400` or `HTTP 429` in the output, reduce rate limit: `--rate-limit 2 --workers 5`

---

## Error Handling

The tool handles errors gracefully at every stage:

| Error                      | Behaviour                                                        |
|----------------------------|------------------------------------------------------------------|
| Missing `.env` / API key   | Prints clear message, exits with code 1                          |
| Missing CSV file           | Prints file-not-found message, exits with code 1                 |
| No URLs in CSV             | Prints "no entries found" message, exits with code 1              |
| Empty CSV / no valid rows  | Prints "no entries found" message, exits with code 1             |
| Invalid / malformed URL    | Skipped during validation with a warning                         |
| Shortlink URL              | Automatically resolved via redirect before scanning              |
| HTTP 400 from API          | Retried up to 3 times; full error body logged                    |
| HTTP 429 (rate limit)      | Retried with exponential back-off (4s → 8s)                     |
| HTTP 5xx (server error)    | Retried up to 3 times; records `N/A` scores if all fail          |
| Connection error           | Retried; logs the error, records `N/A` scores                    |
| Request timeout (>120s)    | Retried; logs the error, records `N/A` scores                    |
| Malformed API response     | Missing categories are recorded as `None` / `N/A`               |
| Unexpected thread exception| Caught, logged, recorded as `N/A`, scan continues                |

The scanner **never crashes mid-run** — failed URLs are recorded with `N/A` scores so you can identify and re-scan them.

---

## Troubleshooting

### "No valid API_KEY found"
Ensure your `.env` file exists in the project root and contains `API_KEY=your_actual_key` (not the placeholder).

### "CSV file not found"
Use `--csv path/to/file.csv` to specify the correct path to your CSV file.

### HTTP 429 — Too Many Requests
The Google API has rate limits. Reduce both workers and rate limit:
```bash
python main.py --csv urls.csv --workers 5 --rate-limit 2
```

### HTTP 400 — Bad Request
Common causes:
- **Burst throttling** — too many simultaneous requests. Reduce `--rate-limit`.
- **Malformed URL** — check your input for typos or special characters.
- **Auth-required page** — Lighthouse can’t scan pages behind a login wall.
- **Shortlink** — use `validate_urls` (enabled by default) to auto-resolve redirects.

The tool now shows the **actual API error message** (e.g., `LIGHTHOUSE_ERROR`) instead of just “400 — Bad Request”.

### All scores show N/A
- Verify your API key is valid and has the PageSpeed Insights API enabled.
- Check your internet connection.
- Try scanning a single known-good URL to isolate the issue.

### Script runs but no output file
Ensure you have write permissions in the current directory. Check the `--output` path.

---

## Project Structure

```
webperformancescanner/
├── .env                 # API key & config (git-ignored)
├── .gitignore           # Ignores venv, .env, results, __pycache__
├── main.py              # CLI entry point & orchestrator
├── reader.py            # CSV parsing & URL construction
├── scanner.py           # PageSpeed API + data extraction (concurrent)
├── reporter.py          # 6-section report, averages, recommendations, CSV
├── urls.csv             # Example input: URLs or route paths (optional)
├── results.csv          # Output: flattened scan results (git-ignored)
├── requirements.txt     # Python dependencies
├── README.md            # This documentation
└── venv/                # Virtual environment (git-ignored)
```

---

## License

This project is proprietary to Oracom. All rights reserved.
