#!/usr/bin/env python3
"""
Trend tracking for checkpoint latency tests.

Aggregates JSON reports from reports/checkpoint_latency_*.json into
reports/checkpoint_latency_trend.csv for long-term trend analysis.

Usage:
    python scripts/track_checkpoint_latency.py

Output:
    - Appends new rows to reports/checkpoint_latency_trend.csv
    - Skips dates already present (idempotent)
"""

import csv
import json
import os
from pathlib import Path


def load_existing_trend_csv() -> dict:
    """Load existing CSV and return dict: {date: row_dict} for fast lookup."""
    trend_file = "reports/checkpoint_latency_trend.csv"
    if not os.path.exists(trend_file):
        return {}
    
    existing_dates = {}
    try:
        with open(trend_file, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_dates[row['date']] = row
    except (OSError, json.JSONDecodeError):
        # If CSV is malformed, start fresh
        return {}
    
    return existing_dates

def process_json_reports() -> list:
    """Process all checkpoint latency JSON reports and return new rows."""
    reports_dir = Path("reports")
    if not reports_dir.exists():
        return []
    
    existing_dates = load_existing_trend_csv()
    new_rows = []
    
    # Find all checkpoint latency JSON files
    json_files = list(reports_dir.glob("checkpoint_latency_*.json"))
    
    for json_file in sorted(json_files):
        try:
            with open(json_file, 'r') as f:
                report = json.load(f)
            
            date = report.get('date')
            if not date:
                continue
            
            # Skip if date already exists in CSV
            if date in existing_dates:
                continue
            
            # Create CSV row
            row = {
                'date': date,
                'samples': str(report.get('samples', 0)),
                'p50_ms': str(report.get('p50_ms', 0.0)),
                'p95_ms': str(report.get('p95_ms', 0.0)),
                'p99_ms': str(report.get('p99_ms', 0.0)),
                'budget_ms': str(report.get('budget_ms', 0.0)),
                'wall_s': str(report.get('wall_s', 0.0)),
                'errors': str(report.get('errors', 0)),
            }
            new_rows.append(row)
            
        except (OSError, json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Could not process {json_file}: {e}")
    
    return new_rows

def update_trend_csv(new_rows: list):
    """Update the trend CSV with new rows."""
    if not new_rows:
        print("No new reports to process")
        return
    
    trend_file = "reports/checkpoint_latency_trend.csv"
    fieldnames = ['date', 'samples', 'p50_ms', 'p95_ms', 'p99_ms', 'budget_ms', 'wall_s', 'errors']
    
    # Read existing data
    existing_rows = []
    if os.path.exists(trend_file):
        try:
            with open(trend_file, 'r', newline='') as f:
                reader = csv.DictReader(f)
                existing_rows = list(reader)
        except (OSError, csv.Error):
            existing_rows = []
    
    # Combine existing + new, sort by date
    all_rows = existing_rows + new_rows
    all_rows.sort(key=lambda x: x['date'])
    
    # Write back
    with open(trend_file, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
    
    print(f"Updated {trend_file} with {len(new_rows)} new entries")
    for row in new_rows:
        print(f"  Added: {row['date']} (p99_ms={row['p99_ms']}, samples={row['samples']})")

def main():
    """Main entry point."""
    # Ensure reports directory exists
    os.makedirs("reports", exist_ok=True)
    
    # Process JSON reports
    new_rows = process_json_reports()
    
    # Update CSV
    update_trend_csv(new_rows)
    
    # Summary
    if new_rows:
        print(f"\n✅ Processed {len(new_rows)} new checkpoint latency reports")
    else:
        print("\n✅ No new checkpoint latency reports found")

if __name__ == "__main__":
    main()