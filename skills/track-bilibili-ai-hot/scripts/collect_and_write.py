#!/usr/bin/env python3
"""Collect Bilibili AI-related popular videos and append a Feishu report."""

from __future__ import annotations

import argparse
import concurrent.futures
import html
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


DEFAULT_DOC = os.environ.get("BILIBILI_AI_FEISHU_DOC", "")
TIMEZONE = timezone(timedelta(hours=8), name="CST")
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 Chrome/138 Safari/537.36"
)
API = "https://api.bilibili.com"
VIDEO_URL = "https://www.bilibili.com/video/{bvid}/"

AI_TERM = re.compile(
    r"(?<![A-Za-z0-9])AI(?![A-Za-z0-9])|AIGC|人工智能|大模型|智能体|"
    r"ChatGPT|GPT(?:-[0-9.]+)?|Claude|Gemini|DeepSeek|LLM|GLM(?:-[0-9.]+)?|"
    r"生成式|AI生成|AI绘画|AI动画|AI视频|AI游戏|AI短剧|AI音乐|AI影像|"
    r"AI剧情|AI整活|AI伴侣|AI伙伴|AI安全|AI演绎|AI配音|AI辅助|物理AI",
    re.IGNORECASE,
)
GENERATION_TERM = re.compile(
    r"AIGC|生成式|AI生成|AI绘画|AI动画|AI视频|AI短剧|AI音乐|AI影像|"
    r"AI剧情|AI整活|AI演绎|AI配音|AI辅助|AI电影|AI故事|"
    r"AI全民制作人|SpecialForAAIFF|"
    r"updream|MiniMax(?:\s*H?\d(?:\.\d)?)?|Seedance(?:\s*\d(?:\.\d)?)?|"
    r"Seedream(?:\s*\d(?:\.\d)?)?|可灵(?:\s*\d(?:\.\d)?)?|"
    r"(?:全程.{0,12}|#)Seko(?:AI)?",
    re.IGNORECASE,
)
TECH_TERM = re.compile(
    r"人工智能|大模型|智能体|Agent|ChatGPT|GPT(?:-[0-9.]+)?|Claude|Gemini|"
    r"DeepSeek|LLM|GLM(?:-[0-9.]+)?|AI伴侣|AI伙伴|AI安全|AI眼镜|"
    r"AI工具|AI教程|AI编程|AI应用|物理AI|人形机器人",
    re.IGNORECASE,
)
TECH_CONTEXT = re.compile(
    r"教程|工具|应用|实测|网站|开源|插件|编程|代码|软件|产品|项目|游戏|"
    r"模型|智能体|Agent|机器人|眼镜|安全|漏洞|渗透|游戏开发|自制游戏|"
    r"BilibiliToy|数字生命|监督学习|番茄钟|技术|实验|部署|API",
    re.IGNORECASE,
)
CREATIVE_CATEGORY = re.compile(
    r"影视|动画|音乐|鬼畜|手书|短片|绘画|设计|小剧场|娱乐|综合|日常|MV|AMV",
    re.IGNORECASE,
)
NEGATIVE_ONLY = re.compile(
    r"请勿相信.{0,80}(?:人工智能|AI).{0,20}生成|"
    r"禁止.{0,20}(?:融?AI|人工智能)|"
    r"(?:不是|并非|没有|不含|非)\s*AI|人肉.{0,20}没有\s*AI|"
    r"近期.{0,30}(?:AI|人工智能).{0,20}作品",
    re.IGNORECASE,
)


class CollectionError(RuntimeError):
    """Raised when a required Bilibili or Feishu operation fails."""


@dataclass(frozen=True)
class Video:
    """Normalized video metadata from one Bilibili list."""

    position: int
    bvid: str
    title: str
    category: str
    owner: str
    description: str
    view: int
    like: int


class BilibiliClient:
    """Small authenticated-anonymous client for Bilibili public list APIs."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cookie = ""
        self.refresh_cookie()

    def refresh_cookie(self) -> None:
        """Refresh the anonymous fingerprint cookie used by guarded endpoints."""
        payload = self._request_json("/x/frontend/finger/spi", use_cookie=False)
        data = payload.get("data") or {}
        b3 = data.get("b_3")
        b4 = data.get("b_4")
        if not b3 or not b4:
            raise CollectionError("Bilibili fingerprint API returned no identifiers")
        with self._lock:
            self._cookie = f"buvid3={b3}; buvid4={b4}; b_nut={int(time.time())}"

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET a Bilibili JSON endpoint and retry transient or risk-control failures."""
        query = urllib.parse.urlencode(params or {})
        full_path = f"{path}?{query}" if query else path
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                payload = self._request_json(full_path, use_cookie=True)
                if payload.get("code") == 0:
                    return payload
                if payload.get("code") == -352 and attempt < 3:
                    self.refresh_cookie()
                    time.sleep(0.25 * (attempt + 1))
                    continue
                raise CollectionError(
                    f"Bilibili API {path} failed: code={payload.get('code')} "
                    f"message={payload.get('message')}"
                )
            except (CollectionError, OSError, ValueError) as exc:
                last_error = exc
                if attempt == 3:
                    break
                time.sleep(0.35 * (attempt + 1))
        raise CollectionError(f"Bilibili request failed for {path}: {last_error}")

    def _request_json(self, path: str, *, use_cookie: bool) -> dict[str, Any]:
        url = path if path.startswith("https://") else f"{API}{path}"
        headers = {"User-Agent": UA, "Referer": "https://www.bilibili.com/"}
        if use_cookie:
            with self._lock:
                headers["Cookie"] = self._cookie
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise CollectionError(f"HTTP {exc.code} for {url}") from exc
        return json.loads(raw.decode("utf-8"))


def normalize_video(item: dict[str, Any], position: int) -> Video:
    """Convert a Bilibili list item into the fields used by the report."""
    stat = item.get("stat") or {}
    owner = item.get("owner") or {}
    return Video(
        position=position,
        bvid=str(item.get("bvid") or ""),
        title=str(item.get("title") or ""),
        category=str(item.get("tname") or ""),
        owner=str(owner.get("name") or ""),
        description=str(item.get("desc") or ""),
        view=int(stat.get("view") or 0),
        like=int(stat.get("like") or 0),
    )


def dedupe(videos: list[Video]) -> list[Video]:
    """Keep the first occurrence of each BV id while preserving order."""
    seen: set[str] = set()
    result: list[Video] = []
    for video in videos:
        if not video.bvid or video.bvid in seen:
            continue
        seen.add(video.bvid)
        result.append(video)
    return result


def fetch_popular(client: BilibiliClient, max_pages: int) -> tuple[list[Video], int]:
    """Fetch 综合热门 until the first empty page."""
    videos: list[Video] = []
    slots = 0
    for page in range(1, max_pages + 1):
        payload = client.get("/x/web-interface/popular", {"pn": page, "ps": 20})
        items = (payload.get("data") or {}).get("list") or []
        if not items:
            break
        for offset, item in enumerate(items, start=1):
            videos.append(normalize_video(item, (page - 1) * 20 + offset))
        slots += len(items)
    if not videos:
        raise CollectionError("综合热门 returned an empty list")
    return dedupe(videos), slots


def fetch_ranking(client: BilibiliClient) -> tuple[list[Video], int]:
    """Fetch the current all-site ranking."""
    payload = client.get("/x/web-interface/ranking/v2", {"rid": 0, "type": "all"})
    items = (payload.get("data") or {}).get("list") or []
    if not items:
        raise CollectionError("全站排行榜 returned an empty list")
    videos = [normalize_video(item, index) for index, item in enumerate(items, start=1)]
    return dedupe(videos), len(items)


def fetch_weekly(client: BilibiliClient) -> tuple[list[Video], int, str, int]:
    """Fetch the latest 每周必看 series and its videos."""
    listing = client.get("/x/web-interface/popular/series/list")
    series = ((listing.get("data") or {}).get("list") or [])
    if not series:
        raise CollectionError("每周必看 series list was empty")
    latest = series[0]
    number = int(latest.get("number") or 0)
    payload = client.get("/x/web-interface/popular/series/one", {"number": number})
    data = payload.get("data") or {}
    items = data.get("list") or []
    if not items:
        raise CollectionError(f"每周必看第 {number} 期 returned an empty list")
    label = str((data.get("config") or {}).get("label") or latest.get("name") or f"第 {number} 期")
    videos = [normalize_video(item, index) for index, item in enumerate(items, start=1)]
    return dedupe(videos), len(items), label, number


def fetch_tags(client: BilibiliClient, bvid: str) -> list[str]:
    """Fetch Bilibili tags for one video."""
    payload = client.get("/x/web-interface/view/detail/tag", {"bvid": bvid})
    return [str(tag.get("tag_name") or "") for tag in (payload.get("data") or []) if tag.get("tag_name")]


def classify(video: Video, tags: list[str]) -> tuple[str | None, str]:
    """Separate AI technology applications from AIGC-generated content."""
    text = f"{video.title} {video.description}"
    all_text = f"{text} {video.category} {' '.join(tags)}"
    tag_hits = [tag for tag in tags if AI_TERM.search(tag) or GENERATION_TERM.search(tag)]
    generation_hits = [tag for tag in tags if GENERATION_TERM.search(tag)]
    technology_hits = [tag for tag in tags if TECH_TERM.search(tag)]
    title_or_desc_ai = bool(AI_TERM.search(text))
    generation_text = bool(GENERATION_TERM.search(text))
    technology_text = bool(TECH_TERM.search(text))
    technology_context = bool(TECH_CONTEXT.search(all_text))

    if not tag_hits and not title_or_desc_ai and not generation_text and not technology_text:
        return None, ""
    if not generation_hits and not technology_hits and NEGATIVE_ONLY.search(text):
        return None, ""

    technology_score = 0
    if technology_hits or technology_text:
        technology_score += 3
    if title_or_desc_ai and technology_context:
        technology_score += 2
    elif tag_hits and technology_context:
        technology_score += 1

    generation_score = 0
    if generation_hits or generation_text:
        generation_score += 3
    if title_or_desc_ai and CREATIVE_CATEGORY.search(video.category):
        generation_score += 1
    elif tag_hits and CREATIVE_CATEGORY.search(video.category):
        generation_score += 1

    if technology_score == 0 and generation_score == 0:
        return None, ""

    direction = "AI科技应用" if technology_score > generation_score else "AIGC生成内容"
    reasons: list[str] = []
    if direction == "AI科技应用":
        reasons.append("教程/工具/产品或技术应用")
    else:
        reasons.append("AI生成或辅助创作")
    evidence = technology_hits if direction == "AI科技应用" else generation_hits
    if evidence:
        reasons.append("标签：" + "、".join(evidence[:3]))
    elif title_or_desc_ai or generation_text or technology_text:
        reasons.append("标题或简介明确披露")
    return direction, "；".join(reasons)


def enrich(
    client: BilibiliClient,
    groups: list[list[Video]],
) -> tuple[dict[str, list[str]], list[str]]:
    """Fetch tags once for every BV id across all lists."""
    bvids = list(dict.fromkeys(video.bvid for group in groups for video in group))
    tags: dict[str, list[str]] = {}
    errors: list[str] = []

    def one(bvid: str) -> tuple[str, list[str], str | None]:
        try:
            return bvid, fetch_tags(client, bvid), None
        except Exception as exc:  # Keep title/description classification available.
            return bvid, [], str(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        for bvid, values, error in executor.map(one, bvids):
            tags[bvid] = values
            if error:
                errors.append(f"{bvid}: {error}")
    return tags, errors


def select(videos: list[Video], tags: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Select AI-related videos and serialize report fields."""
    selected: list[dict[str, Any]] = []
    for video in videos:
        direction, reason = classify(video, tags.get(video.bvid, []))
        if direction is None:
            continue
        selected.append(
            {
                "position": video.position,
                "bvid": video.bvid,
                "title": video.title,
                "category": video.category,
                "owner": video.owner,
                "view": video.view,
                "like": video.like,
                "direction": direction,
                "reason": reason,
                "url": VIDEO_URL.format(bvid=video.bvid),
            }
        )
    return selected


def pct(count: int, total: int) -> str:
    """Format one-decimal percentages for summary tables."""
    return f"{(100 * count / total):.1f}%" if total else "—"


def x(value: Any) -> str:
    """Escape text for Feishu's XML subset."""
    return html.escape(str(value), quote=True)


def count_direction(group: dict[str, Any], direction: str) -> int:
    """Count one direction inside a source list."""
    return sum(1 for item in group["items"] if item["direction"] == direction)


def merge_direction(report: dict[str, Any], direction: str) -> list[dict[str, Any]]:
    """Merge source appearances by BV id for one report direction."""
    merged: dict[str, dict[str, Any]] = {}
    sources = [
        ("综合热门", report["popular"]["items"]),
        ("排行榜", report["ranking"]["items"]),
        (f"每周必看第{report['weekly']['number']}期", report["weekly"]["items"]),
    ]
    for source, items in sources:
        for item in items:
            if item["direction"] != direction:
                continue
            if item["bvid"] not in merged:
                merged[item["bvid"]] = {**item, "sources": []}
            merged[item["bvid"]]["sources"].append(f"{source} #{item['position']}")
    return list(merged.values())


def render_rows(items: list[dict[str, Any]]) -> str:
    """Render the rows shared by the two direction tables."""
    return "".join(
        "<tr>"
        f"<td>{x('；'.join(item['sources']))}</td>"
        f"<td><a href=\"{x(item['url'])}\">{x(item['title'])}</a></td>"
        f"<td>{x(item['owner'])}</td>"
        f"<td>{x(item['reason'])}</td>"
        "</tr>"
        for item in items
    )


def render_table(items: list[dict[str, Any]]) -> str:
    """Render a compact linked-video table, or a plain empty-state paragraph."""
    if not items:
        return "<p>本日未命中。</p>"
    return (
        "<table><colgroup><col width=\"165\"/><col width=\"300\"/>"
        "<col width=\"120\"/><col width=\"210\"/></colgroup>"
        "<thead><tr><th background-color=\"light-gray\">来源 / 榜位</th>"
        "<th background-color=\"light-gray\">视频</th>"
        "<th background-color=\"light-gray\">UP 主</th>"
        "<th background-color=\"light-gray\">判定依据</th></tr></thead>"
        f"<tbody>{render_rows(items)}</tbody></table>"
    )


def render_xml(report: dict[str, Any], *, leading_rule: bool = True) -> str:
    """Render one date-first section with only two second-level headings."""
    popular = report["popular"]
    ranking = report["ranking"]
    weekly = report["weekly"]
    technology = merge_direction(report, "AI科技应用")
    aigc = merge_direction(report, "AIGC生成内容")
    prefix = "<hr/>" if leading_rule else ""
    return "".join(
        [
            prefix,
            f"<h1>{x(report['date'])}</h1>",
            f"<p><b>抓取时间：</b>{x(report['snapshot_at'])}　"
            f"<b>每周必看：</b>{x(weekly['label'])}</p>",
            "<table><colgroup><col width=\"150\"/><col width=\"90\"/>"
            "<col width=\"120\"/><col width=\"120\"/><col width=\"90\"/></colgroup>"
            "<thead><tr><th background-color=\"light-gray\">榜单</th>"
            "<th background-color=\"light-gray\">规模</th>"
            "<th background-color=\"light-blue\">AI 科技应用</th>"
            "<th background-color=\"light-gray\">AIGC 生成内容</th>"
            "<th background-color=\"light-gray\">合计</th></tr></thead><tbody>",
            f"<tr><td>综合热门</td><td>{popular['total_slots']}</td>"
            f"<td>{count_direction(popular, 'AI科技应用')}</td>"
            f"<td>{count_direction(popular, 'AIGC生成内容')}</td><td>{popular['ai_count']}</td></tr>",
            f"<tr><td>全站排行榜</td><td>{ranking['total_slots']}</td>"
            f"<td>{count_direction(ranking, 'AI科技应用')}</td>"
            f"<td>{count_direction(ranking, 'AIGC生成内容')}</td><td>{ranking['ai_count']}</td></tr>",
            f"<tr><td>每周必看第 {weekly['number']} 期</td><td>{weekly['total_slots']}</td>"
            f"<td>{count_direction(weekly, 'AI科技应用')}</td>"
            f"<td>{count_direction(weekly, 'AIGC生成内容')}</td><td>{weekly['ai_count']}</td></tr>",
            "</tbody></table>",
            f"<p><b>三榜去重：</b>AI 科技应用 {len(technology)} 支，AIGC 生成内容 {len(aigc)} 支。"
            "团队重点关注前者；综合热门按匿名新访客会话抓取，排序可能个性化。</p>",
            f"<h2>AI 科技应用（重点）：{len(technology)} 支</h2>",
            render_table(technology),
            f"<h2>AIGC 生成内容：{len(aigc)} 支</h2>",
            render_table(aigc),
            "<p><b>口径：</b>教程、工具、模型、智能体、软件、AI 编程、产品和物理 AI 归入 AI 科技应用；"
            "AI 视频、音乐、动画、短剧、配音和生成工具成片归入 AIGC 生成内容。"
            "反诈提醒、禁用声明和“不是 AI”等偶然命中排除。</p>",
        ]
    )


def render_document(report: dict[str, Any]) -> str:
    """Render a complete tracker document for the initial structure migration."""
    return "".join(
        [
            "<title>B站 AI 热门日报</title>",
            "<p>每日记录综合热门、全站排行榜和每周必看中的 AI 科技应用与 AIGC 生成内容。"
            "AI 科技应用是团队重点关注方向。</p>",
            render_xml(report, leading_rule=False),
        ]
    )


def run_lark(
    args: list[str],
    *,
    stdin: str | None = None,
    require_ok: bool = True,
) -> dict[str, Any]:
    """Run lark-cli with stable JSON output and validate its success envelope."""
    env = os.environ.copy()
    env["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
    env["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
    process = subprocess.run(
        ["lark-cli", *args],
        input=stdin,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    stream = process.stdout if process.returncode == 0 else process.stderr
    try:
        payload = json.loads(stream)
    except json.JSONDecodeError as exc:
        raise CollectionError(f"lark-cli returned non-JSON output: {stream[:300]}") from exc
    if process.returncode != 0 or (require_ok and payload.get("ok") is not True):
        error = payload.get("error") or {}
        raise CollectionError(f"lark-cli failed: {error.get('message') or stream[:300]}")
    return payload


def verify_lark_user() -> None:
    """Fail before document work when the Feishu user identity is unavailable."""
    status = run_lark(["auth", "status", "--json", "--verify"], require_ok=False)
    user = ((status.get("identities") or {}).get("user") or {})
    if not status.get("verified") or user.get("status") != "ready":
        raise CollectionError("Feishu user identity is not ready or verified")


def write_report(doc: str, date: str, xml: str) -> str:
    """Append one idempotent report section and verify it by keyword lookup."""
    verify_lark_user()
    existing = run_lark(
        [
            "docs",
            "+fetch",
            "--as",
            "user",
            "--doc",
            doc,
            "--scope",
            "keyword",
            "--keyword",
            date,
            "--detail",
            "simple",
        ]
    )
    content = (((existing.get("data") or {}).get("document") or {}).get("content") or "")
    if date in content:
        return "already_exists"

    run_lark(
        ["docs", "+update", "--as", "user", "--doc", doc, "--command", "append", "--content", "-"],
        stdin=xml,
    )
    verified = run_lark(
        [
            "docs",
            "+fetch",
            "--as",
            "user",
            "--doc",
            doc,
            "--scope",
            "keyword",
            "--keyword",
            date,
            "--detail",
            "simple",
        ]
    )
    check = (((verified.get("data") or {}).get("document") or {}).get("content") or "")
    if date not in check:
        raise CollectionError("Feishu append returned success but the daily marker was not found")
    return "written"


def overwrite_report(doc: str, date: str, xml: str) -> str:
    """Replace the tracker once when migrating it to the date-first structure."""
    verify_lark_user()
    run_lark(
        ["docs", "+update", "--as", "user", "--doc", doc, "--command", "overwrite", "--content", "-"],
        stdin=xml,
    )
    verified = run_lark(
        [
            "docs",
            "+fetch",
            "--as",
            "user",
            "--doc",
            doc,
            "--scope",
            "keyword",
            "--keyword",
            date,
            "--detail",
            "simple",
        ]
    )
    content = (((verified.get("data") or {}).get("document") or {}).get("content") or "")
    if date not in content:
        raise CollectionError("Feishu overwrite returned success but the date heading was not found")
    return "overwritten"


def collect(max_popular_pages: int) -> dict[str, Any]:
    """Collect, tag, classify, and aggregate all three Bilibili lists."""
    client = BilibiliClient()
    popular, popular_slots = fetch_popular(client, max_popular_pages)
    ranking, ranking_slots = fetch_ranking(client)
    weekly, weekly_slots, weekly_label, weekly_number = fetch_weekly(client)
    tags, tag_errors = enrich(client, [popular, ranking, weekly])
    tag_total = len({video.bvid for group in [popular, ranking, weekly] for video in group})
    if len(tag_errors) > max(5, int(tag_total * 0.05)):
        raise CollectionError(
            f"Bilibili tag lookup failed for {len(tag_errors)}/{tag_total} videos; refusing to write an undercount"
        )
    popular_ai = select(popular, tags)
    ranking_ai = select(ranking, tags)
    weekly_ai = select(weekly, tags)
    unique_ai = {item["bvid"] for item in popular_ai + ranking_ai + weekly_ai}
    unique_technology = {
        item["bvid"]
        for item in popular_ai + ranking_ai + weekly_ai
        if item["direction"] == "AI科技应用"
    }
    unique_aigc = {
        item["bvid"]
        for item in popular_ai + ranking_ai + weekly_ai
        if item["direction"] == "AIGC生成内容"
    }
    now = datetime.now(TIMEZONE)
    return {
        "date": now.strftime("%Y-%m-%d"),
        "snapshot_at": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "popular": {
            "total_slots": popular_slots,
            "unique_videos": len(popular),
            "ai_count": len(popular_ai),
            "items": popular_ai,
        },
        "ranking": {
            "total_slots": ranking_slots,
            "unique_videos": len(ranking),
            "ai_count": len(ranking_ai),
            "items": ranking_ai,
        },
        "weekly": {
            "number": weekly_number,
            "label": weekly_label,
            "total_slots": weekly_slots,
            "unique_videos": len(weekly),
            "ai_count": len(weekly_ai),
            "items": weekly_ai,
        },
        "unique_ai_count": len(unique_ai),
        "unique_technology_count": len(unique_technology),
        "unique_aigc_count": len(unique_aigc),
        "tag_errors": tag_errors,
    }


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--doc",
        default=DEFAULT_DOC,
        help="Feishu document URL or token (or set BILIBILI_AI_FEISHU_DOC)",
    )
    parser.add_argument("--write", action="store_true", help="Append the report to Feishu")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace the document with the generic tracker title and today's date section",
    )
    parser.add_argument(
        "--max-popular-pages",
        type=int,
        default=50,
        help="Safety cap for 综合热门 pagination (default: 50)",
    )
    return parser.parse_args()


def main() -> int:
    """Run collection and optionally perform the idempotent Feishu append."""
    args = parse_args()
    try:
        if args.write and args.overwrite:
            raise CollectionError("Choose only one of --write or --overwrite")
        if (args.write or args.overwrite) and not args.doc:
            raise CollectionError(
                "Feishu document is required; pass --doc or set BILIBILI_AI_FEISHU_DOC"
            )
        report = collect(args.max_popular_pages)
        xml = render_xml(report)
        status = "dry_run"
        if args.overwrite:
            xml = render_document(report)
            status = overwrite_report(args.doc, report["date"], xml)
        elif args.write:
            status = write_report(args.doc, report["date"], xml)
        output = {
            "ok": True,
            "status": status,
            "document_url": args.doc,
            "date": report["date"],
            "snapshot_at": report["snapshot_at"],
            "popular": {
                "total": report["popular"]["total_slots"],
                "ai_count": report["popular"]["ai_count"],
                "technology_count": count_direction(report["popular"], "AI科技应用"),
                "aigc_count": count_direction(report["popular"], "AIGC生成内容"),
            },
            "ranking": {
                "total": report["ranking"]["total_slots"],
                "ai_count": report["ranking"]["ai_count"],
                "technology_count": count_direction(report["ranking"], "AI科技应用"),
                "aigc_count": count_direction(report["ranking"], "AIGC生成内容"),
            },
            "weekly": {
                "number": report["weekly"]["number"],
                "total": report["weekly"]["total_slots"],
                "ai_count": report["weekly"]["ai_count"],
                "technology_count": count_direction(report["weekly"], "AI科技应用"),
                "aigc_count": count_direction(report["weekly"], "AIGC生成内容"),
            },
            "unique_ai_count": report["unique_ai_count"],
            "unique_technology_count": report["unique_technology_count"],
            "unique_aigc_count": report["unique_aigc_count"],
            "tag_error_count": len(report["tag_errors"]),
            "xml_bytes": len(xml.encode("utf-8")),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
