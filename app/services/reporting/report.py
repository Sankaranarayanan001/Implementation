
"""Generate concise analytical HTML report and cleaned Excel."""
from __future__ import annotations

import html
from pathlib import Path
from collections import Counter

import pandas as pd

E = html.escape


def _card(label, value, note=""):
    return f"""
    <div class="card">
        <div class="card-label">{E(str(label))}</div>
        <div class="card-value">{E(str(value))}</div>
        <div class="card-note">{E(str(note))}</div>
    </div>
    """


def _item(label, value):
    return f"""
    <div class="item">
        <span>{E(str(label))}</span>
        <strong>{E(str(value))}</strong>
    </div>
    """


def build_html(ds, st: dict) -> str:
    insp = st.get("inspection", {})
    prof = st.get("profile", {})
    cons = st.get("consolidated", {})
    post = st.get("post_validation", {})

    issues = cons.get("issues", [])
    cleaning_log = st.get("cleaning_log", [])
    comparison = post.get("comparison", [])

    rows_before = post.get("rows_before", 0)
    rows_after = post.get("rows_after", 0)
    issues_before = post.get("issues_before", len(issues))
    issues_after = post.get("issues_after", 0)
    columns = insp.get("column_count", len(prof.get("columns", [])))

    verified = sum(1 for i in cleaning_log if i.get("status") in ("verified", "applied"))
    needs_review = sum(1 for i in cleaning_log if i.get("status") in ("needs_review", "not_verified", "failed"))
    skipped = sum(1 for i in cleaning_log if i.get("status") in ("skipped", "flagged", "no_change"))

    resolved = max(0, issues_before - issues_after)

    # Issue distribution
    issue_types = Counter(
        item.get("issue_type", "Other") for item in issues
    )
    severities = Counter(
        str(item.get("severity", "Unknown")).title()
        for item in issues
    )

    # Compact issue summaries
    issue_html = "".join(
        _item(name.replace("_", " ").title(), count)
        for name, count in issue_types.most_common()
    ) or "<p>No issues detected.</p>"

    severity_html = "".join(
        _item(name, count)
        for name, count in severities.most_common()
    ) or "<p>No severity information available.</p>"

    # Most affected columns
    column_counts = Counter(
        item.get("column") or "Dataset"
        for item in issues
    )

    column_html = "".join(
        _item(name, count)
        for name, count in column_counts.most_common(5)
    ) or "<p>No affected columns.</p>"

    # Profiling highlights
    profile_columns = prof.get("columns", [])

    missing_columns = sorted(
        [
            item for item in profile_columns
            if float(item.get("missing_pct") or 0) > 0
        ],
        key=lambda item: float(item.get("missing_pct") or 0),
        reverse=True
    )[:5]

    missing_html = "".join(
        _item(
            item.get("name", "Unknown"),
            f"{item.get('missing_pct', 0)}% missing"
        )
        for item in missing_columns
    ) or "<p>No missing values identified in the profile.</p>"

    # Cleaning actions
    action_counts = Counter(
        str(i.get("action", "Action")).replace("_", " ").title() for i in cleaning_log
    )
    cleaning_html = "".join(
        _item(name, f"{n} column(s)") for name, n in action_counts.most_common()
    ) or "<p>No cleaning actions recorded.</p>"

    # Before/after comparison
    comparison_html = "".join(
        _item(
            item.get("column") or "Dataset",
            f"{item.get('before', '-')} → {item.get('after', '-')}"
        )
        for item in comparison[:6]
    ) or "<p>No additional column comparisons available.</p>"

    # Final assessment
    if issues_before:
        improvement = round(
            (resolved / issues_before) * 100, 1
        )
    else:
        improvement = 100.0

    if issues_after == 0:
        assessment = "No remaining detected issues."
    elif issues_after < issues_before:
        assessment = "Data quality improved, but some issues remain."
    else:
        assessment = "Further data quality improvements are required."

    css = """
    * {
        box-sizing: border-box;
    }

    body {
        font-family: Arial, sans-serif;
        background: #f5f7fb;
        color: #263244;
        margin: 0;
        padding: 32px;
        line-height: 1.5;
    }

    .container {
        max-width: 1050px;
        margin: auto;
    }

    header {
        margin-bottom: 28px;
    }

    h1 {
        margin: 0 0 8px;
        font-size: 28px;
        color: #172033;
    }

    .subtitle {
        color: #64748b;
        font-size: 14px;
    }

    h2 {
        font-size: 18px;
        margin: 28px 0 12px;
        color: #172033;
    }

    .metrics {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 14px;
    }

    .card, .section {
        background: white;
        border: 1px solid #e5eaf1;
        border-radius: 10px;
        padding: 18px;
    }

    .card-label {
        color: #64748b;
        font-size: 13px;
    }

    .card-value {
        color: #172033;
        font-size: 27px;
        font-weight: 700;
        margin-top: 8px;
    }

    .card-note {
        color: #64748b;
        font-size: 12px;
        margin-top: 4px;
    }

    .grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 16px;
    }

    .item {
        display: flex;
        justify-content: space-between;
        gap: 12px;
        padding: 9px 0;
        border-bottom: 1px solid #edf0f4;
        font-size: 13px;
    }

    .item:last-child {
        border-bottom: none;
    }

    .item span {
        color: #526174;
        overflow-wrap: anywhere;
    }

    .item strong {
        color: #172033;
        text-align: right;
    }

    .assessment {
        background: #eef4ff;
        border-left: 4px solid #4779ce;
        padding: 16px;
        border-radius: 6px;
        margin-top: 16px;
    }

    .assessment strong {
        display: block;
        margin-bottom: 5px;
        color: #1e3a66;
    }

    .assessment p {
        margin: 0;
        color: #475569;
        font-size: 14px;
    }

    footer {
        margin-top: 30px;
        padding-top: 15px;
        border-top: 1px solid #e2e8f0;
        color: #94a3b8;
        font-size: 12px;
    }

    @media (max-width: 700px) {
        body {
            padding: 16px;
        }

        .metrics {
            grid-template-columns: repeat(2, 1fr);
        }

        .grid {
            grid-template-columns: 1fr;
        }
    }
    """

    parts = f"""
    <div class="container">

        <header>
            <h1>Data Quality Analysis Report</h1>
            <div class="subtitle">
                File: {E(ds.filename)} |
                Category: {E(ds.category)} |
                Purpose: {E(ds.purpose)}
            </div>
        </header>

        <h2>Overview</h2>

        <div class="metrics">
            {_card("Total Rows", rows_before, "Original dataset")}
            {_card("Total Columns", columns, "Dataset fields")}
            {_card("Issues Detected", issues_before, "Before cleaning")}
            {_card("Issues Remaining", issues_after, "After cleaning")}
        </div>

        <h2>Data Quality Findings</h2>

        <div class="grid">
            <div class="section">
                <h3>Issue Distribution</h3>
                {issue_html}
            </div>

            <div class="section">
                <h3>Severity Distribution</h3>
                {severity_html}
            </div>

            <div class="section">
                <h3>Most Affected Columns</h3>
                {column_html}
            </div>

            <div class="section">
                <h3>Missing Value Highlights</h3>
                {missing_html}
            </div>
        </div>

        <h2>Cleaning Summary</h2>

        <div class="metrics">
            {_card("Verified Actions", verified, "Successfully validated")}
            {_card("Needs Review", needs_review, "Could not be fully verified")}
            {_card("Skipped Actions", skipped, "No modification performed")}
            {_card("Issues Resolved", resolved, f"{improvement}% improvement")}
        </div>

        <h2>Applied Cleaning Actions</h2>

        <div class="section">
            {cleaning_html}
        </div>

        <h2>Before and After Comparison</h2>

        <div class="grid">
            <div class="section">
                <h3>Dataset Changes</h3>
                {_item("Rows Before", rows_before)}
                {_item("Rows After", rows_after)}
                {_item("Issues Before", issues_before)}
                {_item("Issues After", issues_after)}
            </div>

            <div class="section">
                <h3>Column Comparison</h3>
                {comparison_html}
            </div>
        </div>

        <div class="assessment">
            <strong>Final Assessment</strong>
            <p>{E(assessment)}</p>
        </div>

        <footer>
            Generated by Data Quality Inspector
        </footer>

    </div>
    """

    return (
        "<!doctype html><html><head>"
        "<meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Data Quality Analysis Report</title>"
        f"<style>{css}</style>"
        f"</head><body>{parts}</body></html>"
    )


def write_excel(path: Path, cleaned: pd.DataFrame, st: dict) -> None:
    post = st.get("post_validation", {})

    with pd.ExcelWriter(path, engine="openpyxl",
                        datetime_format="dd-mm-yyyy", date_format="dd-mm-yyyy") as writer:
        cleaned.to_excel(
            writer,
            sheet_name="Cleaned_Data",
            index=False
        )

        pd.DataFrame(
            st.get("cleaning_log", [])
        ).to_excel(
            writer,
            sheet_name="Cleaning_Log",
            index=False
        )

        pd.DataFrame(
            post.get("comparison", [])
        ).to_excel(
            writer,
            sheet_name="Before_After",
            index=False
        )

        pd.DataFrame([
            {
                key: issue.get(key)
                for key in (
                    "id",
                    "severity",
                    "column",
                    "issue_type",
                    "affected_rows"
                )
            }
            for issue in st.get("consolidated", {}).get("issues", [])
        ]).to_excel(
            writer,
            sheet_name="Issues_Found",
            index=False
        )
