"""
reporter.py — Results Aggregation & Output Module

Uses pandas to aggregate scan results and rich to display a color-coded
terminal table.  Also exports the full dataset to a CSV file.
"""

from typing import Any, Dict, List

import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()

# The four Lighthouse categories (must match keys from scanner.py)
SCORE_COLUMNS = ["performance", "accessibility", "best-practices", "seo"]


# ── Colour helpers ──────────────────────────────────────────────────────────


def _score_color(score: Any) -> str:
    """
    Return a rich colour name based on score thresholds.

    - Green  : score >= 90  (good)
    - Yellow : 50 <= score < 90  (needs improvement)
    - Red    : score < 50  (poor)
    - Dim    : score is None / unavailable
    """
    if score is None or pd.isna(score):
        return "dim"
    score = int(score)
    if score >= 90:
        return "green"
    if score >= 50:
        return "yellow"
    return "red"


def _format_score(score: Any) -> Text:
    """Return a rich Text object with the score coloured appropriately."""
    if score is None or pd.isna(score):
        return Text("N/A", style="dim")
    value = int(score)
    return Text(str(value), style=_score_color(value))


# ── Public API ──────────────────────────────────────────────────────────────


def build_dataframe(results: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Convert the raw list of result dicts into a pandas DataFrame.

    Args:
        results: List of dicts returned by scanner.scan_urls().

    Returns:
        A DataFrame with columns: url, strategy, performance,
        accessibility, best-practices, seo.
    """
    df = pd.DataFrame(results)
    return df


def compute_averages(df: pd.DataFrame) -> pd.Series:
    """
    Compute the mean score for each category across all results.

    Args:
        df: The full results DataFrame.

    Returns:
        A pandas Series with the average for each score column,
        rounded to one decimal place.
    """
    averages = df[SCORE_COLUMNS].mean(numeric_only=True).round(1)
    return averages


def print_results_table(df: pd.DataFrame, averages: pd.Series) -> None:
    """
    Print a rich-formatted table showing individual route scores
    and a summary averages row.

    Scores are colour-coded:
        Green  (>= 90)  |  Yellow (50-89)  |  Red (< 50)

    Args:
        df:       The full results DataFrame.
        averages: Series of average scores per category.
    """
    console.print()
    console.rule("[bold cyan]PageSpeed Insights Results[/bold cyan]")
    console.print()

    # ── Build the table ─────────────────────────────────────────────────
    table = Table(
        title="Individual Route Scores",
        show_lines=True,
        header_style="bold magenta",
        border_style="bright_black",
        title_style="bold white",
    )

    table.add_column("URL", style="cyan", min_width=30)
    table.add_column("Strategy", justify="center", style="bold")
    table.add_column("Performance", justify="center")
    table.add_column("Accessibility", justify="center")
    table.add_column("Best Practices", justify="center")
    table.add_column("SEO", justify="center")

    # ── Individual rows ─────────────────────────────────────────────────
    for _, row in df.iterrows():
        table.add_row(
            str(row["url"]),
            row["strategy"].capitalize(),
            _format_score(row.get("performance")),
            _format_score(row.get("accessibility")),
            _format_score(row.get("best-practices")),
            _format_score(row.get("seo")),
        )

    # ── Averages row ────────────────────────────────────────────────────
    table.add_section()
    table.add_row(
        Text("AVERAGE", style="bold white"),
        Text("ALL", style="bold white"),
        _format_score(averages.get("performance")),
        _format_score(averages.get("accessibility")),
        _format_score(averages.get("best-practices")),
        _format_score(averages.get("seo")),
        style="bold",
    )

    console.print(table)
    console.print()


def export_csv(
    df: pd.DataFrame,
    averages: pd.Series,
    output_path: str = "results.csv",
) -> None:
    """
    Export the results DataFrame and averages to a CSV file.

    The averages are appended as a final row with url='AVERAGE'
    and strategy='ALL'.

    Args:
        df:          The full results DataFrame.
        averages:    Series of average scores per category.
        output_path: Destination CSV file path (default: results.csv).
    """
    # Create an averages row and append it
    avg_row = {"url": "AVERAGE", "strategy": "ALL"}
    avg_row.update(averages.to_dict())
    avg_df = pd.DataFrame([avg_row])

    export_df = pd.concat([df, avg_df], ignore_index=True)
    export_df.to_csv(output_path, index=False)

    console.print(
        f"[green]✓[/green] Results exported to "
        f"[bold]'{output_path}'[/bold]."
    )
