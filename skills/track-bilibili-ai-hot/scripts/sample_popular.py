#!/usr/bin/env python3
"""Store a stable, no-cookie Bilibili popular-list snapshot in SQLite."""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


API = "https://api.bilibili.com/x/web-interface/popular"
TIMEZONE = timezone(timedelta(hours=8), name="CST")
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
)


def request_page(page: int, page_size: int) -> list[dict[str, Any]]:
    """Fetch one public popular page without a personalization cookie."""
    query = urllib.parse.urlencode({"pn": page, "ps": page_size})
    request = urllib.request.Request(
        f"{API}?{query}",
        headers={
            "User-Agent": UA,
            "Referer": "https://www.bilibili.com/v/popular/all/",
            "Accept": "application/json, text/plain, */*",
        },
    )
    last_error = ""
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("code") == 0:
                return ((payload.get("data") or {}).get("list") or [])
            last_error = f"code={payload.get('code')} message={payload.get('message')}"
        except (urllib.error.URLError, ValueError) as exc:
            last_error = str(exc)
        if attempt < 3:
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"popular page {page} failed: {last_error}")


def collect(limit: int, delay: float) -> list[dict[str, Any]]:
    """Collect the first N positions while keeping API traffic conservative."""
    page_size = 20
    videos: list[dict[str, Any]] = []
    seen: set[str] = set()
    page = 1
    while len(videos) < limit:
        items = request_page(page, page_size)
        if not items:
            break
        for item in items:
            bvid = str(item.get("bvid") or "")
            if not bvid or bvid in seen:
                continue
            seen.add(bvid)
            stat = item.get("stat") or {}
            owner = item.get("owner") or {}
            videos.append(
                {
                    "rank": len(videos) + 1,
                    "bvid": bvid,
                    "title": str(item.get("title") or ""),
                    "category": str(item.get("tname") or ""),
                    "owner": str(owner.get("name") or ""),
                    "view": int(stat.get("view") or 0),
                    "likes": int(stat.get("like") or 0),
                    "pubdate": int(item.get("pubdate") or 0),
                }
            )
            if len(videos) >= limit:
                break
        page += 1
        if len(videos) < limit:
            time.sleep(delay)
    if len(videos) < limit:
        raise RuntimeError(f"popular snapshot was incomplete: {len(videos)}/{limit}")
    return videos


def initialize(connection: sqlite3.Connection) -> None:
    """Create the append-only sampling schema."""
    connection.executescript(
        """
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS runs (
            run_id INTEGER PRIMARY KEY AUTOINCREMENT,
            sampled_at TEXT NOT NULL,
            sampled_at_epoch INTEGER NOT NULL,
            item_count INTEGER NOT NULL,
            elapsed_ms INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS items (
            run_id INTEGER NOT NULL,
            rank INTEGER NOT NULL,
            bvid TEXT NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            owner TEXT NOT NULL,
            view_count INTEGER NOT NULL,
            like_count INTEGER NOT NULL,
            pubdate INTEGER NOT NULL,
            PRIMARY KEY (run_id, rank),
            FOREIGN KEY (run_id) REFERENCES runs(run_id)
        );
        CREATE INDEX IF NOT EXISTS idx_items_bvid ON items(bvid);
        """
    )


def store(db_path: Path, videos: list[dict[str, Any]], elapsed_ms: int) -> tuple[int, str]:
    """Commit one complete snapshot atomically."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(TIMEZONE)
    sampled_at = now.isoformat(timespec="seconds")
    with sqlite3.connect(str(db_path)) as connection:
        initialize(connection)
        cursor = connection.execute(
            "INSERT INTO runs(sampled_at, sampled_at_epoch, item_count, elapsed_ms) VALUES (?, ?, ?, ?)",
            (sampled_at, int(now.timestamp()), len(videos), elapsed_ms),
        )
        run_id = int(cursor.lastrowid)
        connection.executemany(
            """
            INSERT INTO items(
                run_id, rank, bvid, title, category, owner,
                view_count, like_count, pubdate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    run_id,
                    video["rank"],
                    video["bvid"],
                    video["title"],
                    video["category"],
                    video["owner"],
                    video["view"],
                    video["likes"],
                    video["pubdate"],
                )
                for video in videos
            ],
        )
    return run_id, sampled_at


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/popular_samples.sqlite3")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--delay", type=float, default=0.6)
    return parser.parse_args()


def main() -> int:
    """Collect and store one snapshot."""
    args = parse_args()
    started = time.monotonic()
    try:
        videos = collect(args.limit, args.delay)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        run_id, sampled_at = store(Path(args.db), videos, elapsed_ms)
        print(
            json.dumps(
                {
                    "ok": True,
                    "run_id": run_id,
                    "sampled_at": sampled_at,
                    "item_count": len(videos),
                    "elapsed_ms": elapsed_ms,
                    "cookie_mode": "none",
                },
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
