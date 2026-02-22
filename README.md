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
  - [URL Input File](#url-input-file)
- [Usage](#usage)
  - [Basic Run](#basic-run)
  - [CLI Arguments](#cli-arguments)
  - [Examples](#examples)
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
- **Flexible input** — The CSV file accepts full URLs (`https://…`) *or* bare route paths (`/about`) that are combined with a configurable base domain.
- **Automatic deduplication** — Duplicate URLs are removed before scanning.

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

> \* `BASE_URL` is only required if your `urls.csv` contains bare route paths (e.g. `/about`). If the CSV has full URLs, it is not needed.

### URL Input File

Create a file called `urls.csv` in the project root. It must have a **header row** and one entry per line.

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
python main.py
```

This uses the `API_KEY` and `BASE_URL` from `.env`, reads from `urls.csv`, runs 10 concurrent workers, and exports to `results.csv`.

### CLI Arguments

| Argument       | Type   | Default       | Description                                                  |
|----------------|--------|---------------|--------------------------------------------------------------|
| `--base-url`   | string | `.env` value  | Base domain to prepend to route paths                        |
| `--csv`        | string | `urls.csv`    | Path to the input CSV file                                   |
| `--delay`      | float  | `2.0`         | Legacy delay parameter (kept for compatibility)              |
| `--output`     | string | `results.csv` | Path for the exported results file                           |
| `--workers`    | int    | `10`          | Number of concurrent threads ("channels") for parallel scans |

### Examples

```bash
# Scan with defaults (10 workers, urls.csv, results.csv)
python main.py

# Override base URL from the command line
python main.py --base-url https://mysite.com

# Use a different input file and 20 parallel workers
python main.py --csv my_routes.csv --workers 20

# Export results to a custom file
python main.py --output report_feb2026.csv

# Conservative mode (fewer workers to avoid rate limits)
python main.py --workers 5

# Full example with all options
python main.py --base-url https://mysite.com --csv routes.csv --workers 15 --output scan.csv
```

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
| `_parse_args()` | Parses CLI arguments with `argparse`               |
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

**Role:** Google PageSpeed Insights API interaction with concurrent execution and comprehensive data extraction.

| Function                                   | Description                                                                  |
|--------------------------------------------|------------------------------------------------------------------------------|
| `_fetch_pagespeed(url, strategy, key)`     | Single API request; returns full JSON or `None` on failure                   |
| `_extract_category_scores(data)`           | Extracts 4 category scores (0–100) from API response                         |
| `_extract_lab_metrics(data)`               | Extracts 6 lab metrics (FCP, LCP, CLS, TBT, SI, TTI) with display/raw/score |
| `_extract_field_data(data)`                | Extracts CrUX field data (FCP, LCP, CLS, INP, TTFB, FID) with distributions |
| `_extract_opportunities(data)`             | Extracts top 10 opportunities sorted by estimated savings                    |
| `_extract_diagnostics(data)`               | Extracts top 5 informational diagnostics                                     |
| `_scan_single(url, strategy, key)`         | Unit of work for one URL + strategy (submitted to thread pool)               |
| `scan_urls(urls, key, delay, max_workers)` | Dispatches all jobs concurrently and collects results                         |

**API details:**
- Endpoint: `https://www.googleapis.com/pagespeedonline/v5/runPagespeed`
- Strategies: `mobile`, `desktop`
- Categories: `performance`, `accessibility`, `best-practices`, `seo`
- Timeout: 120 seconds per request

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
3. Up to `max_workers` API calls run simultaneously — each on its own "channel".
4. As each job completes, the progress bar updates in real time.
5. Once all jobs finish, results are sorted and passed to the reporter.

**Tuning `--workers`:**

| Workers | Trade-off                                                    |
|---------|--------------------------------------------------------------|
| `5`     | Conservative — unlikely to hit rate limits, slower overall   |
| `10`    | Default — good balance of speed and API courtesy             |
| `15–20` | Aggressive — faster, but may trigger `429 Too Many Requests` |
| `25+`   | Not recommended unless you have a high API quota             |

> **Tip:** If you see `HTTP Error 429` in the output, reduce workers: `--workers 5`

---

## Error Handling

The tool handles errors gracefully at every stage:

| Error                      | Behaviour                                                  |
|----------------------------|------------------------------------------------------------|
| Missing `.env` / API key   | Prints clear message, exits with code 1                    |
| Missing `urls.csv`         | Prints file-not-found message, exits with code 1           |
| Empty CSV / no valid rows  | Prints "no entries found" message, exits with code 1       |
| HTTP 4xx / 5xx from API    | Logs the error, records `N/A` scores, continues scanning   |
| Connection error           | Logs the error, records `N/A` scores, continues scanning   |
| Request timeout (>120s)    | Logs the error, records `N/A` scores, continues scanning   |
| Malformed API response     | Missing categories are recorded as `None` / `N/A`         |
| Unexpected thread exception| Caught, logged, recorded as `N/A`, scan continues          |

The scanner **never crashes mid-run** — failed URLs are recorded with `N/A` scores so you can identify and re-scan them.

---

## Troubleshooting

### "No valid API_KEY found"
Ensure your `.env` file exists in the project root and contains `API_KEY=your_actual_key` (not the placeholder).

### "CSV file not found"
The default input path is `urls.csv` in the current working directory. Use `--csv path/to/file.csv` to specify a different location.

### HTTP 429 — Too Many Requests
The Google API has rate limits. Reduce the number of concurrent workers:
```bash
python main.py --workers 5
```

### HTTP 400 — Bad Request
Usually means a URL is malformed. Check your `urls.csv` for typos or invalid URLs.

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
├── urls.csv             # Input: URLs or route paths to scan
├── results.csv          # Output: flattened scan results (git-ignored)
├── requirements.txt     # Python dependencies
├── README.md            # This documentation
└── venv/                # Virtual environment (git-ignored)
```

---

## License

This project is proprietary to Oracom. All rights reserved.
