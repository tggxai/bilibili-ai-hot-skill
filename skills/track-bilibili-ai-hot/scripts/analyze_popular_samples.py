#!/usr/bin/env python3
"""Analyze turnover and update timing in Bilibili popular-list samples."""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


def mean(values: list[float]) -> float:
    """Return a rounded mean or zero for an empty series."""
    return round(statistics.mean(values), 3) if values else 0.0


def load_runs(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    """Load complete runs and their ordered BV ids."""
    runs: list[dict[str, Any]] = []
    for run_id, sampled_at, item_count in connection.execute(
        "SELECT run_id, sampled_at, item_count FROM runs ORDER BY sampled_at_epoch"
    ):
        rows = connection.execute(
            "SELECT rank, bvid FROM items WHERE run_id = ? ORDER BY rank", (run_id,)
        ).fetchall()
        if len(rows) != item_count or item_count < 100:
            continue
        runs.append(
            {
                "run_id": run_id,
                "sampled_at": sampled_at,
                "timestamp": datetime.fromisoformat(sampled_at),
                "bvids": [row[1] for row in rows],
            }
        )
    return runs


def compare(previous: dict[str, Any], current: dict[str, Any], depth: int) -> dict[str, Any]:
    """Compare consecutive runs at one ranking depth."""
    old = previous["bvids"][:depth]
    new = current["bvids"][:depth]
    old_set = set(old)
    new_set = set(new)
    retained = old_set.intersection(new_set)
    old_rank = {bvid: index for index, bvid in enumerate(old, start=1)}
    new_rank = {bvid: index for index, bvid in enumerate(new, start=1)}
    shifts = [abs(old_rank[bvid] - new_rank[bvid]) for bvid in retained]
    union = old_set.union(new_set)
    return {
        "entered": len(new_set - old_set),
        "exited": len(old_set - new_set),
        "retained": len(retained),
        "jaccard": round(len(retained) / len(union), 4) if union else 1.0,
        "mean_rank_shift": mean([float(value) for value in shifts]),
        "identical_order": old == new,
    }


def analyze(db_path: Path) -> dict[str, Any]:
    """Aggregate consecutive-snapshot changes by hour and half-hour phase."""
    with sqlite3.connect(str(db_path)) as connection:
        runs = load_runs(connection)
    if len(runs) < 2:
        raise RuntimeError("at least two complete samples are required")

    comparisons: list[dict[str, Any]] = []
    by_hour: dict[int, list[float]] = defaultdict(list)
    by_phase: dict[str, list[float]] = defaultdict(list)
    for previous, current in zip(runs, runs[1:]):
        metrics = {str(depth): compare(previous, current, depth) for depth in [20, 50, 100, 200]}
        interval_minutes = (current["timestamp"] - previous["timestamp"]).total_seconds() / 60
        phase = "07分样本" if current["timestamp"].minute < 20 else "37分样本"
        comparisons.append(
            {
                "from": previous["sampled_at"],
                "to": current["sampled_at"],
                "interval_minutes": round(interval_minutes, 2),
                "metrics": metrics,
            }
        )
        by_hour[current["timestamp"].hour].append(float(metrics["200"]["entered"]))
        by_phase[phase].append(float(metrics["200"]["entered"]))

    phase_means = {phase: mean(values) for phase, values in sorted(by_phase.items())}
    hour_means = {f"{hour:02d}:00": mean(values) for hour, values in sorted(by_hour.items())}
    depth_summary = {}
    for depth in [20, 50, 100, 200]:
        key = str(depth)
        depth_summary[key] = {
            "mean_entered": mean([float(item["metrics"][key]["entered"]) for item in comparisons]),
            "mean_jaccard": mean([float(item["metrics"][key]["jaccard"]) for item in comparisons]),
            "unchanged_share": mean(
                [1.0 if item["metrics"][key]["identical_order"] else 0.0 for item in comparisons]
            ),
        }

    phase_values = list(phase_means.values())
    cadence_hint = "insufficient phase coverage"
    if len(phase_values) == 2:
        gap = abs(phase_values[0] - phase_values[1])
        baseline = max(min(phase_values), 1.0)
        cadence_hint = (
            "half-hour phases differ materially; updates may cluster near one phase"
            if gap / baseline >= 0.5
            else "half-hour phases are similar; the list likely rolls continuously"
        )

    return {
        "ok": True,
        "sample_count": len(runs),
        "comparison_count": len(comparisons),
        "start": runs[0]["sampled_at"],
        "end": runs[-1]["sampled_at"],
        "depth_summary": depth_summary,
        "mean_new_entries_top200_by_hour": hour_means,
        "mean_new_entries_top200_by_phase": phase_means,
        "cadence_hint": cadence_hint,
        "largest_top200_changes": sorted(
            comparisons,
            key=lambda item: item["metrics"]["200"]["entered"],
            reverse=True,
        )[:12],
    }


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/popular_samples.sqlite3")
    return parser.parse_args()


def main() -> int:
    """Print the analysis as JSON."""
    args = parse_args()
    try:
        print(json.dumps(analyze(Path(args.db)), ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
