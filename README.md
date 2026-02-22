# Web Performance Scanner

A modular Python CLI tool that batch-scans website routes using the **Google PageSpeed Insights API** and produces colour-coded performance reports with averaged metrics.

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
  - [Terminal Table](#terminal-table)
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

- **Batch scanning** — Analyse hundreds of URLs in a single run.
- **Concurrent API calls** — Uses a thread pool (`ThreadPoolExecutor`) so every URL gets its own "channel"; scans that previously took ~2 hours now finish in ~10–15 minutes.
- **Dual strategy** — Every URL is tested for both **mobile** and **desktop**.
- **Four Lighthouse categories** — Performance, Accessibility, Best Practices, and SEO.
- **Flexible input** — The CSV file accepts full URLs (`https://…`) *or* bare route paths (`/about`) that are combined with a configurable base domain.
- **Automatic deduplication** — Duplicate URLs are removed before scanning.
- **Colour-coded terminal output** — Powered by [Rich](https://github.com/Textualize/rich); scores are green (≥ 90), yellow (50–89), or red (< 50).
- **Averages row** — Overall averages are computed with [pandas](https://pandas.pydata.org/) and displayed at the bottom of the table.
- **CSV export** — Full results (individual + averages) are written to `results.csv`.
- **Secure configuration** — API key loaded from a `.env` file via `python-dotenv`.
- **Graceful error handling** — File-not-found, HTTP errors, timeouts, and malformed API responses are all caught and reported cleanly.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                       main.py                           │
│              CLI entry point & orchestrator              │
│  Loads .env → Parses args → Coordinates modules below   │
└────────┬──────────────┬──────────────────┬──────────────┘
         │              │                  │
         ▼              ▼                  ▼
   ┌──────────┐  ┌─────────────┐   ┌─────────────┐
   │ reader.py│  │ scanner.py  │   │ reporter.py │
   │          │  │             │   │             │
   │ CSV      │  │ PageSpeed   │   │ pandas      │
   │ parsing  │  │ API calls   │   │ aggregation │
   │ & URL    │  │ (concurrent │   │ + Rich      │
   │ building │  │  threads)   │   │ table +     │
   │          │  │             │   │ CSV export  │
   └──────────┘  └─────────────┘   └─────────────┘
```

**Data flow:**

1. `reader.py` reads `urls.csv` and separates full URLs from route paths.
2. Route paths are combined with the base domain to produce full URLs.
3. `scanner.py` dispatches all URL × strategy combinations to a thread pool and collects Lighthouse scores.
4. `reporter.py` aggregates the results, prints a colour-coded table, and exports to CSV.

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

### Terminal Table

The scanner prints a colour-coded table using the Rich library:

```
┌──────────────────────────────────┬──────────┬─────────────┬───────────────┬────────────────┬─────┐
│ URL                              │ Strategy │ Performance │ Accessibility │ Best Practices │ SEO │
├──────────────────────────────────┼──────────┼─────────────┼───────────────┼────────────────┼─────┤
│ https://example.com/             │ Mobile   │     45      │      92       │       87       │  91 │
│ https://example.com/             │ Desktop  │     78      │      92       │       87       │  91 │
│ https://example.com/about        │ Mobile   │     62      │      95       │       91       │  89 │
│ https://example.com/about        │ Desktop  │     91      │      95       │       91       │  89 │
├──────────────────────────────────┼──────────┼─────────────┼───────────────┼────────────────┼─────┤
│ AVERAGE                          │   ALL    │    69.0     │     93.5      │      89.0      │90.0 │
└──────────────────────────────────┴──────────┴─────────────┴───────────────┴────────────────┴─────┘
```

### CSV Export

The `results.csv` file contains all individual results plus an `AVERAGE` row:

```csv
url,strategy,performance,accessibility,best-practices,seo
https://example.com/,mobile,45,92,87,91
https://example.com/,desktop,78,92,87,91
https://example.com/about,mobile,62,95,91,89
https://example.com/about,desktop,91,95,91,89
AVERAGE,ALL,69.0,93.5,89.0,90.0
```

### Score Colour Coding

| Colour     | Score Range | Meaning          |
|------------|-------------|------------------|
| 🟢 Green   | 90 – 100    | Good             |
| 🟡 Yellow  | 50 – 89     | Needs improvement|
| 🔴 Red     | 0 – 49      | Poor             |
| ⚫ Dim/Grey | N/A         | Scan failed      |

These thresholds match [Google's official Lighthouse scoring](https://developer.chrome.com/docs/lighthouse/performance/performance-scoring/).

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
7. Scan all URLs concurrently via `scanner.scan_urls()`
8. Aggregate and display via `reporter.*`
9. Export to CSV

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

**Role:** Google PageSpeed Insights API interaction with concurrent execution.

| Function                              | Description                                              |
|---------------------------------------|----------------------------------------------------------|
| `_fetch_pagespeed(url, strategy, key)`| Single API request; returns JSON or `None` on failure    |
| `_extract_scores(data)`              | Extracts 4 category scores (0–100) from API response     |
| `_scan_single(url, strategy, key)`   | Unit of work for one URL + strategy (submitted to thread pool) |
| `scan_urls(urls, key, delay, max_workers)` | Dispatches all jobs concurrently and collects results |

**API details:**
- Endpoint: `https://www.googleapis.com/pagespeedonline/v5/runPagespeed`
- Strategies: `mobile`, `desktop`
- Categories: `performance`, `accessibility`, `best-practices`, `seo`
- Timeout: 120 seconds per request

**Concurrency model:**
- Uses `concurrent.futures.ThreadPoolExecutor` with configurable `max_workers`
- All URL × strategy pairs are submitted simultaneously
- Results are collected via `as_completed()` for real-time progress updates
- Thread-safe result collection via `threading.Lock`
- Results are sorted back into original URL order after collection

---

### reporter.py

**Role:** Data aggregation, terminal display, and CSV export.

| Function                              | Description                                            |
|---------------------------------------|--------------------------------------------------------|
| `_score_color(score)`                 | Returns a Rich colour name based on score thresholds   |
| `_format_score(score)`                | Returns a coloured `rich.Text` object                  |
| `build_dataframe(results)`            | Converts result dicts to a `pandas.DataFrame`          |
| `compute_averages(df)`               | Calculates mean score per category (rounded to 1 d.p.) |
| `print_results_table(df, averages)`   | Prints the colour-coded Rich table to the terminal     |
| `export_csv(df, averages, path)`      | Writes results + averages row to a CSV file            |

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
├── scanner.py           # PageSpeed API calls (concurrent)
├── reporter.py          # pandas aggregation, Rich table, CSV export
├── urls.csv             # Input: URLs or route paths to scan
├── results.csv          # Output: scan results (git-ignored)
├── requirements.txt     # Python dependencies
├── README.md            # This documentation
└── venv/                # Virtual environment (git-ignored)
```

---

## License

This project is proprietary to Oracom. All rights reserved.
