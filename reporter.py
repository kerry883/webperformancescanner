"""
reporter.py — Comprehensive Performance Report Module

Produces a multi-section terminal report and CSV export:
  1. Category Scores table (individual routes)
  2. Separate Mobile & Desktop average tables
  3. Core Web Vitals (Lab Data) table
  4. Field Data (CrUX / Real-User Metrics) table
  5. Top Recommendations panel (opportunities + diagnostics)
  6. Actionable Improvement Summary panel

Uses pandas for aggregation and rich for colour-coded terminal output.
"""

from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

# The four Lighthouse categories
SCORE_COLUMNS = ["performance", "accessibility", "best-practices", "seo"]

# Lab metric labels (must match scanner.py LAB_METRIC_IDS values)
LAB_LABELS = ["FCP", "LCP", "CLS", "TBT", "Speed Index", "TTI"]

# Field metric labels (must match scanner.py FIELD_METRIC_KEYS values)
FIELD_LABELS = ["FCP", "LCP", "CLS", "INP", "TTFB", "FID"]


# ── Colour / formatting helpers ────────────────────────────────────────────


def _score_color(score: Any) -> str:
    """Return a rich colour based on Lighthouse thresholds (0–100)."""
    if score is None or (isinstance(score, float) and pd.isna(score)):
        return "dim"
    score = int(score)
    if score >= 90:
        return "green"
    if score >= 50:
        return "yellow"
    return "red"


def _format_score(score: Any) -> Text:
    """Colour-coded score text."""
    if score is None or (isinstance(score, float) and pd.isna(score)):
        return Text("N/A", style="dim")
    value = int(score)
    return Text(str(value), style=_score_color(value))


def _field_category_color(category: Optional[str]) -> str:
    """Colour for CrUX field categories (FAST / AVERAGE / SLOW)."""
    if not category:
        return "dim"
    cat = category.upper()
    if cat == "FAST":
        return "green"
    if cat == "AVERAGE":
        return "yellow"
    return "red"


def _format_field_category(category: Optional[str]) -> Text:
    """Colour-coded field category text."""
    if not category:
        return Text("N/A", style="dim")
    return Text(category, style=_field_category_color(category))


def _format_ms(value: Any) -> str:
    """Format a millisecond value as a human-readable string."""
    if value is None:
        return "N/A"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if v >= 1000:
        return f"{v / 1000:.1f} s"
    return f"{v:.0f} ms"


def _lab_score_color(score: Any) -> str:
    """Colour for lab metric scores (same thresholds, but 0–100 scale)."""
    if score is None:
        return "dim"
    score = int(score)
    if score >= 90:
        return "green"
    if score >= 50:
        return "yellow"
    return "red"


# ── Public API ──────────────────────────────────────────────────────────────


def build_dataframe(results: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Convert raw result dicts into a pandas DataFrame.

    Nested dicts (lab_metrics, field_data) are kept as columns for
    programmatic access; the flat score columns are used for aggregation.
    """
    df = pd.DataFrame(results)
    return df


def compute_averages_by_strategy(
    df: pd.DataFrame,
) -> Dict[str, pd.Series]:
    """
    Compute mean scores per category, grouped by strategy.

    Returns:
        {"mobile": Series, "desktop": Series, "all": Series}
    """
    averages: Dict[str, pd.Series] = {}
    for strategy in ["mobile", "desktop"]:
        subset = df[df["strategy"] == strategy]
        if not subset.empty:
            averages[strategy] = (
                subset[SCORE_COLUMNS].mean(numeric_only=True).round(1)
            )
        else:
            averages[strategy] = pd.Series(
                {c: None for c in SCORE_COLUMNS}
            )
    averages["all"] = df[SCORE_COLUMNS].mean(numeric_only=True).round(1)
    return averages


# ── Section 1: Category Scores Table ───────────────────────────────────────


def print_scores_table(df: pd.DataFrame) -> None:
    """Print individual route scores (no averages — those come separately)."""
    console.print()
    console.rule("[bold cyan]1 · Lighthouse Category Scores[/bold cyan]")
    console.print()

    table = Table(
        show_lines=True,
        header_style="bold magenta",
        border_style="bright_black",
    )
    table.add_column("#", justify="right", style="dim", width=4)
    table.add_column("URL", style="cyan", min_width=30)
    table.add_column("Strategy", justify="center", style="bold")
    table.add_column("Perf", justify="center")
    table.add_column("A11y", justify="center")
    table.add_column("BP", justify="center")
    table.add_column("SEO", justify="center")

    for idx, (_, row) in enumerate(df.iterrows(), start=1):
        table.add_row(
            str(idx),
            str(row["url"]),
            row["strategy"].capitalize(),
            _format_score(row.get("performance")),
            _format_score(row.get("accessibility")),
            _format_score(row.get("best-practices")),
            _format_score(row.get("seo")),
        )

    console.print(table)


# ── Section 2: Separate Mobile & Desktop Averages ─────────────────────────


def print_averages_tables(
    averages: Dict[str, pd.Series],
    df: pd.DataFrame,
) -> None:
    """Print side-by-side average tables for mobile and desktop."""
    console.print()
    console.rule(
        "[bold cyan]2 · Average Scores by Strategy[/bold cyan]"
    )
    console.print()

    for strategy in ["mobile", "desktop"]:
        avg = averages.get(strategy)
        if avg is None:
            continue

        count = len(df[df["strategy"] == strategy])
        label = strategy.upper()

        table = Table(
            title=f"{label} Averages  ({count} routes)",
            show_lines=True,
            header_style="bold magenta",
            border_style="bright_black",
            title_style="bold white",
            min_width=50,
        )
        table.add_column("Category", style="bold")
        table.add_column("Average Score", justify="center")
        table.add_column("Rating", justify="center")

        for col in SCORE_COLUMNS:
            val = avg.get(col)
            rating = _get_rating_text(val)
            table.add_row(
                col.replace("-", " ").title(),
                _format_score(val),
                rating,
            )

        console.print(table)
        console.print()

    # Overall
    overall = averages.get("all")
    if overall is not None:
        table = Table(
            title="OVERALL Averages (Mobile + Desktop combined)",
            show_lines=True,
            header_style="bold magenta",
            border_style="cyan",
            title_style="bold cyan",
            min_width=50,
        )
        table.add_column("Category", style="bold")
        table.add_column("Average Score", justify="center")
        table.add_column("Rating", justify="center")

        for col in SCORE_COLUMNS:
            val = overall.get(col)
            rating = _get_rating_text(val)
            table.add_row(
                col.replace("-", " ").title(),
                _format_score(val),
                rating,
            )
        console.print(table)
        console.print()


def _get_rating_text(score: Any) -> Text:
    """Return a human-readable rating label with colour."""
    if score is None or (isinstance(score, float) and pd.isna(score)):
        return Text("N/A", style="dim")
    s = float(score)
    if s >= 90:
        return Text("Good", style="bold green")
    if s >= 50:
        return Text("Needs Improvement", style="bold yellow")
    return Text("Poor", style="bold red")


# ── Section 3: Core Web Vitals (Lab Data) ─────────────────────────────────


def print_lab_metrics_table(df: pd.DataFrame) -> None:
    """Print a table of Core Web Vitals lab metrics per route."""
    console.print()
    console.rule("[bold cyan]3 · Core Web Vitals (Lab Data)[/bold cyan]")
    console.print()

    table = Table(
        show_lines=True,
        header_style="bold magenta",
        border_style="bright_black",
    )
    table.add_column("URL", style="cyan", min_width=25, max_width=40)
    table.add_column("Strategy", justify="center", style="bold")
    for label in LAB_LABELS:
        table.add_column(label, justify="center")

    for _, row in df.iterrows():
        lab = row.get("lab_metrics", {})
        if not lab:
            lab = {}

        cells = []
        for label in LAB_LABELS:
            display = lab.get(f"lab_{label}")
            score = lab.get(f"lab_{label}_score")
            if display:
                color = _lab_score_color(score)
                cells.append(Text(str(display), style=color))
            else:
                cells.append(Text("N/A", style="dim"))

        table.add_row(
            str(row["url"]),
            row["strategy"].capitalize(),
            *cells,
        )

    console.print(table)
    console.print()


# ── Section 4: Field Data (CrUX) ──────────────────────────────────────────


def print_field_data_table(df: pd.DataFrame) -> None:
    """Print real-user / CrUX field data when available."""
    console.print()
    console.rule(
        "[bold cyan]4 · Field Data (Chrome User Experience Report)[/bold cyan]"
    )
    console.print()

    # Check if any field data is available
    has_field = any(
        row.get("field_data", {}).get("field_overall") is not None
        for _, row in df.iterrows()
    )

    if not has_field:
        console.print(
            "[dim]No field (CrUX) data available for the scanned URLs. "
            "Field data requires sufficient real-user traffic recorded "
            "by Chrome.[/dim]"
        )
        console.print()
        return

    table = Table(
        show_lines=True,
        header_style="bold magenta",
        border_style="bright_black",
    )
    table.add_column("URL", style="cyan", min_width=25, max_width=40)
    table.add_column("Strategy", justify="center", style="bold")
    table.add_column("Overall", justify="center")
    for label in FIELD_LABELS:
        table.add_column(label, justify="center")

    for _, row in df.iterrows():
        field = row.get("field_data", {})
        if not field:
            field = {}

        overall = field.get("field_overall")

        cells = []
        for label in FIELD_LABELS:
            cat = field.get(f"field_{label}_category")
            p = field.get(f"field_{label}_percentile")
            if cat and p is not None:
                display = _format_ms(p) if label != "CLS" else str(p)
                cells.append(
                    Text(
                        f"{display} ({cat})",
                        style=_field_category_color(cat),
                    )
                )
            else:
                cells.append(Text("N/A", style="dim"))

        table.add_row(
            str(row["url"]),
            row["strategy"].capitalize(),
            _format_field_category(overall),
            *cells,
        )

    console.print(table)
    console.print()


# ── Section 5: Top Recommendations ────────────────────────────────────────


def print_recommendations(df: pd.DataFrame) -> None:
    """
    Aggregate and print the most common Lighthouse opportunities and
    diagnostics across all scanned routes.
    """
    console.print()
    console.rule(
        "[bold cyan]5 · Top Recommendations from Google PageSpeed"
        "[/bold cyan]"
    )
    console.print()

    # ── Opportunities ───────────────────────────────────────────────────
    opp_counter: Counter = Counter()
    opp_details: Dict[str, Dict[str, Any]] = {}
    opp_savings: Dict[str, List[float]] = {}

    for _, row in df.iterrows():
        for opp in row.get("opportunities", []):
            title = opp.get("title", "Unknown")
            opp_counter[title] += 1
            if title not in opp_details:
                opp_details[title] = opp
            savings = opp.get("savings_ms", 0)
            opp_savings.setdefault(title, []).append(savings)

    if opp_counter:
        table = Table(
            title="Opportunities (Performance Improvements)",
            show_lines=True,
            header_style="bold magenta",
            border_style="bright_black",
            title_style="bold white",
        )
        table.add_column("#", justify="right", style="dim", width=3)
        table.add_column("Recommendation", style="bold", min_width=30)
        table.add_column("Affected Routes", justify="center")
        table.add_column("Avg Savings", justify="center")

        for idx, (title, count) in enumerate(
            opp_counter.most_common(15), start=1
        ):
            avg_sav = sum(opp_savings[title]) / len(opp_savings[title])
            savings_str = _format_ms(avg_sav) if avg_sav > 0 else "—"
            table.add_row(
                str(idx),
                title,
                str(count),
                Text(savings_str, style="yellow"),
            )

        console.print(table)
        console.print()
    else:
        console.print("[green]No failing opportunities — great job![/green]")
        console.print()

    # ── Diagnostics ─────────────────────────────────────────────────────
    diag_counter: Counter = Counter()
    diag_details: Dict[str, Dict[str, Any]] = {}

    for _, row in df.iterrows():
        for diag in row.get("diagnostics", []):
            title = diag.get("title", "Unknown")
            diag_counter[title] += 1
            if title not in diag_details:
                diag_details[title] = diag

    if diag_counter:
        table = Table(
            title="Diagnostics (Informational Issues)",
            show_lines=True,
            header_style="bold magenta",
            border_style="bright_black",
            title_style="bold white",
        )
        table.add_column("#", justify="right", style="dim", width=3)
        table.add_column("Diagnostic", style="bold", min_width=30)
        table.add_column("Affected Routes", justify="center")

        for idx, (title, count) in enumerate(
            diag_counter.most_common(10), start=1
        ):
            table.add_row(str(idx), title, str(count))

        console.print(table)
        console.print()


# ── Section 6: Actionable Summary & Suggestions ───────────────────────────


def print_summary(
    df: pd.DataFrame,
    averages: Dict[str, pd.Series],
) -> None:
    """
    Generate an actionable improvement summary based on the scan results.
    Identifies the weakest areas and provides targeted recommendations.
    """
    console.print()
    console.rule(
        "[bold cyan]6 · Performance Improvement Summary[/bold cyan]"
    )
    console.print()

    lines: List[str] = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_routes = len(df["url"].unique())
    total_scans = len(df)

    lines.append(
        f"[bold]Scan completed:[/bold] {timestamp}\n"
        f"[bold]Routes scanned:[/bold] {total_routes}  |  "
        f"[bold]Total tests:[/bold] {total_scans}"
    )
    lines.append("")

    # ── Per-strategy analysis ───────────────────────────────────────────
    for strategy in ["mobile", "desktop"]:
        avg = averages.get(strategy)
        if avg is None:
            continue
        label = strategy.upper()
        lines.append(f"[bold underline]{label}[/bold underline]")

        for col in SCORE_COLUMNS:
            val = avg.get(col)
            if val is None or pd.isna(val):
                continue
            v = float(val)
            name = col.replace("-", " ").title()
            if v >= 90:
                lines.append(f"  [green]✓[/green] {name}: {v:.1f} — Good")
            elif v >= 50:
                lines.append(
                    f"  [yellow]▲[/yellow] {name}: {v:.1f} — "
                    "Needs Improvement"
                )
            else:
                lines.append(
                    f"  [red]✗[/red] {name}: {v:.1f} — Poor"
                )
        lines.append("")

    # ── Identify worst categories ───────────────────────────────────────
    all_avg = averages.get("all", pd.Series())
    weak_areas = [
        (col, float(all_avg.get(col, 100)))
        for col in SCORE_COLUMNS
        if all_avg.get(col) is not None and float(all_avg.get(col)) < 90
    ]
    weak_areas.sort(key=lambda x: x[1])

    if weak_areas:
        lines.append("[bold underline]PRIORITY IMPROVEMENT AREAS[/bold underline]")
        lines.append("")

        for col, val in weak_areas:
            name = col.replace("-", " ").title()
            suggestions = _get_suggestions(col, val, df)
            lines.append(
                f"  [bold]{name}[/bold] (avg {val:.1f}):"
            )
            for s in suggestions:
                lines.append(f"    → {s}")
            lines.append("")
    else:
        lines.append(
            "[bold green]All categories score 90+! "
            "Your web application is performing well.[/bold green]"
        )

    # ── Worst performing routes ─────────────────────────────────────────
    if "performance" in df.columns:
        perf_col = df[["url", "strategy", "performance"]].dropna(
            subset=["performance"]
        )
        if not perf_col.empty:
            worst = perf_col.nsmallest(5, "performance")
            if not worst.empty and float(worst.iloc[0]["performance"]) < 50:
                lines.append(
                    "[bold underline]WORST PERFORMING ROUTES[/bold underline]"
                )
                lines.append("")
                for _, row in worst.iterrows():
                    lines.append(
                        f"  [red]•[/red] {row['url']} "
                        f"({row['strategy']}) — "
                        f"Performance: {int(row['performance'])}"
                    )
                lines.append("")

    # ── Mobile vs Desktop gap ───────────────────────────────────────────
    m_avg = averages.get("mobile", pd.Series())
    d_avg = averages.get("desktop", pd.Series())
    m_perf = m_avg.get("performance")
    d_perf = d_avg.get("performance")
    if m_perf is not None and d_perf is not None:
        gap = float(d_perf) - float(m_perf)
        if gap > 15:
            lines.append(
                "[bold underline]MOBILE vs DESKTOP GAP[/bold underline]"
            )
            lines.append("")
            lines.append(
                f"  Desktop performance ({d_perf:.1f}) is "
                f"[bold]{gap:.0f} points higher[/bold] than mobile "
                f"({m_perf:.1f})."
            )
            lines.append(
                "  → Prioritise mobile optimisation: reduce JS payload, "
                "optimise images for smaller screens, and test on "
                "throttled connections."
            )
            lines.append("")

    console.print(
        Panel(
            "\n".join(lines),
            title="[bold white]Improvement Summary[/bold white]",
            border_style="cyan",
            padding=(1, 2),
        )
    )
    console.print()


def _get_suggestions(
    category: str, avg_score: float, df: pd.DataFrame
) -> List[str]:
    """
    Return targeted suggestions based on which category is weak.
    """
    suggestions: List[str] = []

    if category == "performance":
        if avg_score < 50:
            suggestions.append(
                "Critical: Performance is in the red zone. "
                "Focus on reducing JavaScript bundle size and "
                "eliminating render-blocking resources."
            )
        suggestions.extend([
            "Optimise and compress images (use WebP/AVIF formats).",
            "Minify CSS, JavaScript, and HTML.",
            "Enable text compression (Gzip/Brotli) on the server.",
            "Implement lazy loading for below-the-fold images and iframes.",
            "Reduce server response time (TTFB) — consider a CDN.",
            "Defer or async non-critical JavaScript.",
            "Preconnect to required origins and preload key resources.",
        ])
        # Check lab data for specific issues
        _add_lab_suggestions(df, suggestions)

    elif category == "accessibility":
        suggestions.extend([
            "Add alt text to all images.",
            "Ensure sufficient colour contrast ratios (WCAG AA).",
            "Use semantic HTML elements (<nav>, <main>, <header>, etc.).",
            "Ensure all interactive elements are keyboard accessible.",
            "Add ARIA labels to icon-only buttons and links.",
            "Ensure form inputs have associated <label> elements.",
        ])

    elif category == "best-practices":
        suggestions.extend([
            "Serve all assets over HTTPS (no mixed content).",
            "Use HTTP/2 or HTTP/3 for asset delivery.",
            "Avoid deprecated APIs and browser features.",
            "Ensure correct image aspect ratios to prevent layout shifts.",
            "Add a Content Security Policy (CSP) header.",
            "Keep JavaScript libraries up to date to patch vulnerabilities.",
        ])

    elif category == "seo":
        suggestions.extend([
            "Ensure every page has a unique <title> and <meta description>.",
            "Use a mobile-friendly responsive design.",
            "Ensure all pages return valid HTTP status codes.",
            "Add structured data (Schema.org JSON-LD) where applicable.",
            "Create and submit an XML sitemap.",
            "Ensure links have descriptive anchor text.",
        ])

    return suggestions


def _add_lab_suggestions(
    df: pd.DataFrame, suggestions: List[str]
) -> None:
    """Add specific suggestions based on lab metric scores."""
    for _, row in df.iterrows():
        lab = row.get("lab_metrics", {})
        if not lab:
            continue

        lcp_score = lab.get("lab_LCP_score")
        cls_score = lab.get("lab_CLS_score")
        tbt_score = lab.get("lab_TBT_score")

        if lcp_score is not None and lcp_score < 50:
            sug = (
                "LCP is poor — optimise the largest element "
                "(hero image, heading font, or large text block)."
            )
            if sug not in suggestions:
                suggestions.append(sug)

        if cls_score is not None and cls_score < 50:
            sug = (
                "CLS is poor — set explicit width/height on images "
                "and embeds, avoid injecting content above the fold."
            )
            if sug not in suggestions:
                suggestions.append(sug)

        if tbt_score is not None and tbt_score < 50:
            sug = (
                "TBT is poor — break up long JavaScript tasks, "
                "use code splitting, and defer heavy computations."
            )
            if sug not in suggestions:
                suggestions.append(sug)

        # Only need one row to check trends
        break


# ── CSV Export ──────────────────────────────────────────────────────────────


def export_csv(
    df: pd.DataFrame,
    averages: Dict[str, pd.Series],
    output_path: str = "results.csv",
) -> None:
    """
    Export all results to a CSV file.

    Includes:
      - Individual route scores + lab metrics (flattened)
      - Separate AVERAGE rows for Mobile, Desktop, and Overall
      - Top opportunities per route (as a semicolon-delimited string)
    """
    # Flatten lab metrics and field data into columns
    rows: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        flat: Dict[str, Any] = {
            "url": row["url"],
            "strategy": row["strategy"],
        }

        # Category scores
        for col in SCORE_COLUMNS:
            flat[col] = row.get(col)

        # Lab metrics
        lab = row.get("lab_metrics", {})
        if lab:
            for label in LAB_LABELS:
                flat[f"lab_{label}"] = lab.get(f"lab_{label}")
                flat[f"lab_{label}_score"] = lab.get(f"lab_{label}_score")

        # Field data
        field = row.get("field_data", {})
        if field:
            flat["field_overall"] = field.get("field_overall")
            for label in FIELD_LABELS:
                flat[f"field_{label}_category"] = field.get(
                    f"field_{label}_category"
                )
                flat[f"field_{label}_percentile"] = field.get(
                    f"field_{label}_percentile"
                )

        # Top opportunities (semicolon-separated titles)
        opps = row.get("opportunities", [])
        if opps:
            flat["top_opportunities"] = "; ".join(
                o.get("title", "") for o in opps[:5]
            )
        else:
            flat["top_opportunities"] = ""

        rows.append(flat)

    # Add average rows
    for strategy_key, label in [
        ("mobile", "AVERAGE_MOBILE"),
        ("desktop", "AVERAGE_DESKTOP"),
        ("all", "AVERAGE_OVERALL"),
    ]:
        avg = averages.get(strategy_key)
        if avg is not None:
            avg_row: Dict[str, Any] = {
                "url": label,
                "strategy": strategy_key if strategy_key != "all" else "all",
            }
            avg_row.update(avg.to_dict())
            rows.append(avg_row)

    export_df = pd.DataFrame(rows)
    export_df.to_csv(output_path, index=False)

    console.print(
        f"[green]✓[/green] Full results exported to "
        f"[bold]'{output_path}'[/bold]."
    )


# ── Master report function ─────────────────────────────────────────────────


def print_full_report(
    df: pd.DataFrame,
    averages: Dict[str, pd.Series],
) -> None:
    """
    Print the complete multi-section performance report.

    Sections:
        1. Lighthouse Category Scores (all routes)
        2. Separate Mobile & Desktop Averages
        3. Core Web Vitals (Lab Data)
        4. Field Data (CrUX)
        5. Top Recommendations
        6. Actionable Improvement Summary
    """
    console.print()
    console.print(
        Panel(
            "[bold cyan]Web Performance Scanner — Comprehensive Report[/bold cyan]",
            border_style="cyan",
        )
    )

    # Section 1: Individual scores
    print_scores_table(df)

    # Section 2: Strategy averages
    print_averages_tables(averages, df)

    # Section 3: Lab metrics
    print_lab_metrics_table(df)

    # Section 4: Field data
    print_field_data_table(df)

    # Section 5: Recommendations
    print_recommendations(df)

    # Section 6: Summary
    print_summary(df, averages)
