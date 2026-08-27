#!/usr/bin/env python3
"""Collect Bilibili AI/tech and hot-list podcast opportunities into Feishu."""

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
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


DEFAULT_DOC = os.environ.get("BILIBILI_AI_FEISHU_DOC", "")
TIMEZONE = timezone(timedelta(hours=8), name="CST")
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
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
AI_APPLICATION_STRONG_TERM = re.compile(
    r"教程|工具|网站|开源|插件|编程|代码|软件|模型|智能体|Agent|机器人|眼镜|安全|漏洞|"
    r"部署|API|系统|平台|算法|算力|训练|推理|实测|产品功能|技术实现",
    re.IGNORECASE,
)
FINANCE_DISCUSSION_TERM = re.compile(
    r"投资|基金|行情|赛道|估值|股票|资本|财富|交易|抄底|逃顶",
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
THREE_C_PATTERNS = [
    (
        "手机通信",
        re.compile(
            r"手机|平板|iPhone|iPad|Android|安卓|鸿蒙|HarmonyOS|Pixel|Galaxy|"
            r"澎湃OS|HyperOS|折叠屏|路由器|Wi-?Fi|基带|骁龙|天玑|红米|荣耀|"
            r"OPPO|vivo|iQOO|一加|真我|魅族",
            re.IGNORECASE,
        ),
    ),
    (
        "电脑硬件",
        re.compile(
            r"电脑|笔记本|台式机|装机|显卡|GPU|CPU|处理器|主板|内存|硬盘|SSD|"
            r"NAS|MacBook|MateBook|Mac\s*mini|Mac\s*Studio|AI\s*PC|芯片|英伟达|NVIDIA|"
            r"AMD|Intel|英特尔|显示器",
            re.IGNORECASE,
        ),
    ),
    (
        "影像影音",
        re.compile(
            r"相机|镜头|摄像机|无人机|GoPro|大疆|DJI|麦克风|耳机|音箱|音响|"
            r"HiFi|电视|投影仪",
            re.IGNORECASE,
        ),
    ),
    (
        "外设游戏硬件",
        re.compile(
            r"键盘|鼠标|外设|游戏机|掌机|Switch|PlayStation|PS5|Xbox|手柄|"
            r"散热器|充电器|充电宝|拓展坞|扩展坞",
            re.IGNORECASE,
        ),
    ),
    (
        "智能穿戴家居",
        re.compile(
            r"智能手表|智能手环|智能穿戴|智能家居|米家|HomeKit|扫地机器人|"
            r"智能门锁|空气净化器|电子书|Kindle|AR眼镜|VR眼镜|Vision\s*Pro",
            re.IGNORECASE,
        ),
    ),
    (
        "AI设备与机器人",
        re.compile(
            r"AI眼镜|智能眼镜|人形机器人|机器人|机器狗|机械臂|具身智能|宇树|Unitree|"
            r"自动驾驶|无人驾驶",
            re.IGNORECASE,
        ),
    ),
]
THREE_C_CATEGORY_HINTS = {"数码", "极客DIY"}
THREE_C_WEAK_TERM = re.compile(
    r"手机|平板|电脑|荣耀|镜头|麦克风|耳机|音箱|音响|电视|投影仪",
    re.IGNORECASE,
)
THREE_C_STRONG_TERM = re.compile(
    r"iPhone|iPad|Android|安卓|鸿蒙|HarmonyOS|澎湃OS|HyperOS|Pixel|Galaxy|折叠屏|路由器|Wi-?Fi|"
    r"MacBook|MateBook|Mac\s*mini|Mac\s*Studio|AI\s*PC|显卡|GPU|CPU|处理器|主板|内存|硬盘|SSD|NAS|"
    r"相机|摄像机|无人机|GoPro|大疆|DJI|HiFi|游戏机|掌机|Switch|PlayStation|PS5|Xbox|"
    r"智能手表|智能手环|智能穿戴|智能家居|HomeKit|扫地机器人|智能门锁|空气净化器|"
    r"Kindle|AR眼镜|VR眼镜|Vision\s*Pro",
    re.IGNORECASE,
)
THREE_C_PRODUCT_CONTEXT = re.compile(
    r"评测|测评|开箱|参数|配置|性能|体验|发布|新品|选购|推荐|对比|实测|上手|"
    r"拆解|维修|内存|屏幕|续航|价格|价位|系统|芯片|影像|拍照|充电|散热|装机",
    re.IGNORECASE,
)
THREE_C_COMPUTER_OVERRIDE = re.compile(
    r"电脑|笔记本|台式机|装机|MacBook|MateBook|Mac\s*mini|Mac\s*Studio|AI\s*PC|"
    r"显卡|主板|硬盘|SSD|NAS|显示器",
    re.IGNORECASE,
)
THREE_C_SOFTWARE_CONTEXT = re.compile(r"手机游戏|手游|端游|网游", re.IGNORECASE)
GAME_CATEGORY_TERM = re.compile(r"游戏|电子竞技", re.IGNORECASE)
EXTENDED_TECH_CATEGORY_HINTS = {"极客DIY", "科工机械"}
EXTENDED_TECH_PATTERNS = [
    (
        "创客工程",
        re.compile(
            r"遥控车|航模|机翼|机械|工程|DIY|手工|模拟器|机器人|改造|自制|造了?一台",
            re.IGNORECASE,
        ),
    ),
    (
        "航空航天",
        re.compile(
            r"火箭|卫星|航天|航空|发射|着陆|回收|运载|朱雀|蓝箭航天|飞船|空间站",
            re.IGNORECASE,
        ),
    ),
]
ENTITY_PATTERNS = [
    ("ChatGPT", "产品", re.compile(r"ChatGPT|GPT-[0-9.]+", re.IGNORECASE)),
    ("OpenAI", "品牌", re.compile(r"OpenAI", re.IGNORECASE)),
    ("OKX Agent Trade Kit", "产品", re.compile(r"OKX\s*Agent\s*Trade\s*Kit", re.IGNORECASE)),
    ("OKX", "品牌", re.compile(r"(?<![A-Za-z])OKX(?![A-Za-z])", re.IGNORECASE)),
    ("Claude", "产品", re.compile(r"Claude", re.IGNORECASE)),
    ("Anthropic", "品牌", re.compile(r"Anthropic", re.IGNORECASE)),
    ("Gemini", "产品", re.compile(r"Gemini", re.IGNORECASE)),
    ("Google", "品牌", re.compile(r"Google|谷歌", re.IGNORECASE)),
    ("DeepSeek", "品牌", re.compile(r"DeepSeek", re.IGNORECASE)),
    ("Kimi", "产品", re.compile(r"Kimi", re.IGNORECASE)),
    ("月之暗面", "品牌", re.compile(r"月之暗面", re.IGNORECASE)),
    ("豆包", "产品", re.compile(r"豆包", re.IGNORECASE)),
    ("通义千问", "产品", re.compile(r"通义千问|Qwen", re.IGNORECASE)),
    ("文心一言", "产品", re.compile(r"文心一言|ERNIE", re.IGNORECASE)),
    ("腾讯元宝", "产品", re.compile(r"腾讯元宝", re.IGNORECASE)),
    ("腾讯混元", "产品", re.compile(r"腾讯混元|Hunyuan", re.IGNORECASE)),
    ("可灵", "产品", re.compile(r"可灵|Kling", re.IGNORECASE)),
    ("即梦 / Seedance", "产品", re.compile(r"即梦|Seedance|Seedream", re.IGNORECASE)),
    ("MiniMax", "品牌", re.compile(r"MiniMax", re.IGNORECASE)),
    ("海螺 AI", "产品", re.compile(r"海螺\s*AI", re.IGNORECASE)),
    ("Seko", "产品", re.compile(r"(?<![A-Za-z])Seko(?:AI)?(?![A-Za-z])", re.IGNORECASE)),
    ("Updream", "产品", re.compile(r"Updream", re.IGNORECASE)),
    ("Runway", "产品", re.compile(r"Runway", re.IGNORECASE)),
    ("Midjourney", "产品", re.compile(r"Midjourney", re.IGNORECASE)),
    ("Stable Diffusion", "产品", re.compile(r"Stable\s*Diffusion|\bSDXL\b", re.IGNORECASE)),
    ("ComfyUI", "产品", re.compile(r"ComfyUI", re.IGNORECASE)),
    ("Dify", "产品", re.compile(r"(?<![A-Za-z])Dify(?![A-Za-z])", re.IGNORECASE)),
    ("扣子 / Coze", "产品", re.compile(r"扣子|(?<![A-Za-z])Coze(?![A-Za-z])", re.IGNORECASE)),
    ("Cursor", "产品", re.compile(r"(?<![A-Za-z])Cursor(?![A-Za-z])", re.IGNORECASE)),
    ("GitHub Copilot", "产品", re.compile(r"GitHub\s*Copilot", re.IGNORECASE)),
    ("Manus", "产品", re.compile(r"(?<![A-Za-z])Manus(?![A-Za-z])", re.IGNORECASE)),
    ("Grok", "产品", re.compile(r"(?<![A-Za-z])Grok(?![A-Za-z])", re.IGNORECASE)),
    ("xAI", "品牌", re.compile(r"(?<![A-Za-z])xAI(?![A-Za-z])", re.IGNORECASE)),
    ("Llama", "产品", re.compile(r"Llama", re.IGNORECASE)),
    ("Meta AI", "品牌", re.compile(r"Meta\s*AI", re.IGNORECASE)),
    ("Apple", "品牌", re.compile(r"Apple|苹果", re.IGNORECASE)),
    ("iPhone", "产品", re.compile(r"iPhone", re.IGNORECASE)),
    ("iPad", "产品", re.compile(r"iPad", re.IGNORECASE)),
    ("MacBook", "产品", re.compile(r"MacBook", re.IGNORECASE)),
    ("Vision Pro", "产品", re.compile(r"Vision\s*Pro", re.IGNORECASE)),
    ("华为", "品牌", re.compile(r"华为", re.IGNORECASE)),
    ("鸿蒙 / HarmonyOS", "产品", re.compile(r"鸿蒙|HarmonyOS", re.IGNORECASE)),
    ("澎湃 OS / HyperOS", "产品", re.compile(r"澎湃\s*OS|Hyper\s*OS", re.IGNORECASE)),
    ("MateBook", "产品", re.compile(r"MateBook", re.IGNORECASE)),
    ("小米 / 红米", "品牌", re.compile(r"小米|红米|Redmi", re.IGNORECASE)),
    ("iQOO", "品牌", re.compile(r"iQOO", re.IGNORECASE)),
    ("iQOO Neo", "产品", re.compile(r"iQOO\s*Neo\s*\d+", re.IGNORECASE)),
    ("荣耀", "品牌", re.compile(r"荣耀", re.IGNORECASE)),
    ("OPPO", "品牌", re.compile(r"OPPO", re.IGNORECASE)),
    ("vivo", "品牌", re.compile(r"vivo", re.IGNORECASE)),
    ("一加", "品牌", re.compile(r"一加|OnePlus", re.IGNORECASE)),
    ("三星", "品牌", re.compile(r"三星|Samsung", re.IGNORECASE)),
    ("Galaxy", "产品", re.compile(r"Galaxy", re.IGNORECASE)),
    ("Google Pixel", "产品", re.compile(r"Google\s*Pixel|\bPixel\b", re.IGNORECASE)),
    ("NVIDIA", "品牌", re.compile(r"NVIDIA|英伟达", re.IGNORECASE)),
    ("RTX / GeForce", "产品", re.compile(r"GeForce|\bRTX\s*\d+", re.IGNORECASE)),
    ("AMD", "品牌", re.compile(r"(?<![A-Za-z])AMD(?![A-Za-z])", re.IGNORECASE)),
    ("Ryzen / Radeon", "产品", re.compile(r"Ryzen|Radeon", re.IGNORECASE)),
    ("Intel", "品牌", re.compile(r"Intel|英特尔", re.IGNORECASE)),
    ("大疆 / DJI", "品牌", re.compile(r"大疆|DJI", re.IGNORECASE)),
    ("索尼", "品牌", re.compile(r"索尼|Sony", re.IGNORECASE)),
    ("佳能", "品牌", re.compile(r"佳能|Canon", re.IGNORECASE)),
    ("尼康", "品牌", re.compile(r"尼康|Nikon", re.IGNORECASE)),
    ("GoPro", "品牌", re.compile(r"GoPro", re.IGNORECASE)),
    ("Nintendo", "品牌", re.compile(r"Nintendo|任天堂", re.IGNORECASE)),
    ("Switch", "产品", re.compile(r"Switch", re.IGNORECASE)),
    ("PlayStation / PS5", "产品", re.compile(r"PlayStation|PS5", re.IGNORECASE)),
    ("Xbox", "产品", re.compile(r"Xbox", re.IGNORECASE)),
    ("Steam Deck", "产品", re.compile(r"Steam\s*Deck", re.IGNORECASE)),
    ("Meta Quest", "产品", re.compile(r"Meta\s*Quest", re.IGNORECASE)),
    ("宇树 / Unitree", "品牌", re.compile(r"宇树|Unitree", re.IGNORECASE)),
    ("蓝箭航天", "品牌", re.compile(r"蓝箭航天", re.IGNORECASE)),
    ("朱雀三号", "产品", re.compile(r"朱雀三号", re.IGNORECASE)),
]
AI_ENTITY_NAMES = {
    "ChatGPT",
    "OpenAI",
    "OKX Agent Trade Kit",
    "OKX",
    "Claude",
    "Anthropic",
    "Gemini",
    "Google",
    "DeepSeek",
    "Kimi",
    "月之暗面",
    "豆包",
    "通义千问",
    "文心一言",
    "腾讯元宝",
    "腾讯混元",
    "可灵",
    "即梦 / Seedance",
    "MiniMax",
    "海螺 AI",
    "Seko",
    "Updream",
    "Runway",
    "Midjourney",
    "Stable Diffusion",
    "ComfyUI",
    "Dify",
    "扣子 / Coze",
    "Cursor",
    "GitHub Copilot",
    "Manus",
    "Grok",
    "xAI",
    "Llama",
    "Meta AI",
}
AI_HARDWARE_TERM = re.compile(
    r"AI眼镜|智能眼镜|人形机器人|机器人|机器狗|机械臂|具身智能|宇树|Unitree|"
    r"自动驾驶|无人驾驶",
    re.IGNORECASE,
)
CLIENT_CONTEXT = re.compile(
    r"本期视频由|本视频由|感谢.{0,12}(?:支持|赞助)|鸣谢|合作品牌|品牌合作|商务合作|"
    r"赞助商|联合出品|推广合作",
    re.IGNORECASE,
)
PODCAST_EXPLICIT_TERM = re.compile(r"视频播客|播客|Podcast", re.IGNORECASE)
PODCAST_STRONG_TAG = re.compile(r"^(?:视频播客|播客|Podcast)$", re.IGNORECASE)
PODCAST_CONVERSATION_TERM = re.compile(
    r"对话|对谈|访谈|专访|圆桌|聊天|漫谈|慢谈|谈话|夜谈|会客厅|聊天室|Conversation|Interview",
    re.IGNORECASE,
)
PODCAST_EPISODE_TERM = re.compile(
    r"(?:^|[^A-Za-z])(?:EP(?:ISODE)?|VOL|NO)[.\s#_-]*\d+|第\s*\d+\s*[期集]|\d+\s*期",
    re.IGNORECASE,
)
PODCAST_ROLE_TERM = re.compile(r"本期(?:节目|主播|嘉宾)|主持人|主播[:：]|嘉宾[:：]", re.IGNORECASE)


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
    duration: int
    pubtime: int


class BilibiliClient:
    """Small authenticated-anonymous client for Bilibili public list APIs."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cookie = ""
        self.refresh_cookie()

    def refresh_cookie(self) -> None:
        """Refresh the anonymous fingerprint cookie used by guarded endpoints."""
        payload = self._request_json(
            "https://api.bilibili.com/x/frontend/finger/spi",
            use_cookie=False,
        )
        data = payload.get("data") or {}
        buvid3 = str(data.get("b_3") or "")
        buvid4 = str(data.get("b_4") or "")
        if payload.get("code") != 0 or not buvid3 or not buvid4:
            raise CollectionError("Bilibili fingerprint endpoint returned incomplete cookies")
        with self._lock:
            self._cookie = f"buvid3={buvid3}; buvid4={buvid4}"

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
        headers = {
            "User-Agent": UA,
            "Referer": "https://www.bilibili.com/v/popular/all/",
            "Accept": "application/json, text/plain, */*",
        }
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
        duration=int(item.get("duration") or 0),
        pubtime=int(item.get("pubdate") or item.get("ctime") or 0),
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
    try:
        payload = client.get("/x/tag/archive/tags", {"bvid": bvid})
    except CollectionError:
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
    if (
        FINANCE_DISCUSSION_TERM.search(text)
        and not AI_APPLICATION_STRONG_TERM.search(text)
        and not generation_text
    ):
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


def classify_three_c(video: Video, tags: list[str]) -> tuple[str | None, str]:
    """Identify concrete digital, hardware, maker, and hard-tech subjects."""
    evidence_sources = [("标题", video.title)]
    if video.category in THREE_C_CATEGORY_HINTS and tags:
        evidence_sources.append(("标签", " ".join(tags)))
    for source, evidence_text in evidence_sources:
        computer_match = THREE_C_COMPUTER_OVERRIDE.search(evidence_text)
        if computer_match and (
            THREE_C_STRONG_TERM.search(evidence_text)
            or video.category in THREE_C_CATEGORY_HINTS
            or (source == "标题" and THREE_C_PRODUCT_CONTEXT.search(video.title))
        ):
            reasons = ["科技硬件品类：电脑硬件", f"{source}命中：{computer_match.group(0)}"]
            if video.category in THREE_C_CATEGORY_HINTS:
                reasons.append(f"B站{video.category}分区")
            return "电脑硬件", "；".join(reasons)
        for product_group, pattern in THREE_C_PATTERNS:
            match = pattern.search(evidence_text)
            if not match:
                continue
            if source == "标签" and not THREE_C_STRONG_TERM.search(evidence_text):
                continue
            if (
                product_group == "手机通信"
                and (
                    THREE_C_SOFTWARE_CONTEXT.search(video.title)
                    or GAME_CATEGORY_TERM.search(video.category)
                )
                and not THREE_C_STRONG_TERM.search(video.title)
            ):
                continue
            if (
                source == "标题"
                and video.category not in THREE_C_CATEGORY_HINTS
                and THREE_C_WEAK_TERM.fullmatch(match.group(0))
                and not THREE_C_STRONG_TERM.search(video.title)
                and not THREE_C_PRODUCT_CONTEXT.search(video.title)
            ):
                continue
            reasons = [f"科技硬件品类：{product_group}", f"{source}命中：{match.group(0)}"]
            if video.category in THREE_C_CATEGORY_HINTS:
                reasons.append(f"B站{video.category}分区")
            return product_group, "；".join(reasons)
    if video.category in EXTENDED_TECH_CATEGORY_HINTS:
        evidence = f"{video.title} {' '.join(tags)}"
        for product_group, pattern in EXTENDED_TECH_PATTERNS:
            match = pattern.search(evidence)
            if match:
                return product_group, "；".join(
                    [
                        f"科技硬件品类：{product_group}",
                        f"标题/标签命中：{match.group(0)}",
                        f"B站{video.category}分区",
                    ]
                )
    return None, ""


def classify_podcast(video: Video, tags: list[str]) -> tuple[bool, str]:
    """Identify podcast-form videos using rules calibrated from the reference corpus."""
    if PODCAST_EXPLICIT_TERM.search(video.title):
        return True, "标题明确标注视频播客"
    if any(PODCAST_STRONG_TAG.fullmatch(tag.strip()) for tag in tags):
        return True, "独立标签明确标注视频播客"
    conversation_text = f"{video.title} {video.description}"
    structured_conversation = (
        video.duration >= 20 * 60
        and PODCAST_CONVERSATION_TERM.search(conversation_text)
        and (
            PODCAST_EPISODE_TERM.search(video.title)
            or PODCAST_ROLE_TERM.search(video.description)
        )
    )
    if structured_conversation:
        return True, "长对谈且有期数、主播或嘉宾结构"
    return False, ""


def extract_product_client_tags(
    video: Video,
    tags: list[str],
    business_category: str | None,
) -> list[str]:
    """Extract named products or explicitly disclosed client brands."""
    secondary_evidence = f"{video.description} {' '.join(tags)}"
    evidence = f"{video.title} {secondary_evidence}"
    labels: list[str] = []
    for name, entity_type, pattern in ENTITY_PATTERNS:
        title_match = pattern.search(video.title)
        secondary_match = pattern.search(secondary_evidence)
        match = title_match or secondary_match
        if not match:
            continue
        if (
            name == "Apple"
            and match.group(0) == "苹果"
            and business_category != "科技硬件/3C"
            and not re.search(
                r"苹果.{0,12}(?:公司|发布|手机|电脑|系统|芯片|产品|设备|AI|智能)|"
                r"(?:iPhone|iPad|Mac|Vision\s*Pro).{0,12}苹果",
                evidence,
                re.IGNORECASE,
            )
        ):
            continue
        if (
            not title_match
            and business_category != "科技硬件/3C"
            and name not in AI_ENTITY_NAMES
            and not (entity_type == "品牌" and CLIENT_CONTEXT.search(secondary_evidence))
        ):
            continue
        full_match = pattern.search(evidence)
        assert full_match is not None
        context = evidence[
            max(0, full_match.start() - 60) : min(len(evidence), full_match.end() + 40)
        ]
        kind = "客户" if entity_type == "品牌" and CLIENT_CONTEXT.search(context) else entity_type
        label = f"{kind}：{name}"
        if label not in labels:
            labels.append(label)
    return labels[:4]


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
    """Assign one primary business category and auditable entity labels."""
    selected: list[dict[str, Any]] = []
    for video in videos:
        video_tags = tags.get(video.bvid, [])
        direction, ai_reason = classify(video, video_tags)
        three_c_category, three_c_reason = classify_three_c(video, video_tags)
        if direction == "AI科技应用" and not three_c_category:
            ai_hardware_match = AI_HARDWARE_TERM.search(
                f"{video.title} {video.description} {' '.join(video_tags)}"
            )
            if ai_hardware_match:
                three_c_category = "AI设备与机器人"
                three_c_reason = f"AI硬件线索：{ai_hardware_match.group(0)}"
        if direction == "AIGC生成内容":
            business_category = "AIGC内容"
        elif three_c_category:
            business_category = "科技硬件/3C"
        elif direction == "AI科技应用":
            business_category = "AI软件"
        else:
            continue
        reasons = [reason for reason in [ai_reason, three_c_reason] if reason]
        entity_labels = extract_product_client_tags(video, video_tags, business_category)
        if not entity_labels and three_c_category:
            entity_labels.append(f"品类：{three_c_category}")
        selected.append(
            {
                "position": video.position,
                "bvid": video.bvid,
                "title": video.title,
                "category": video.category,
                "owner": video.owner,
                "view": video.view,
                "like": video.like,
                "business_category": business_category,
                "entity_labels": entity_labels,
                "three_c_category": three_c_category,
                "reason": "；".join(reasons),
                "url": VIDEO_URL.format(bvid=video.bvid),
            }
        )
    return selected


def select_podcast_opportunities(
    source_videos: list[tuple[str, list[Video]]],
    tags: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Select podcast-form videos only from the current three hot-list sources."""
    candidates = dedupe([video for _, videos in source_videos for video in videos])
    topic_items = {
        item["bvid"]: item
        for item in select(candidates, tags)
    }
    opportunities: dict[str, dict[str, Any]] = {}

    def add(video: Video, source: str, podcast_reason: str) -> None:
        item = opportunities.get(video.bvid)
        if item is None:
            topic = topic_items.get(video.bvid)
            if topic:
                item = {**topic}
            else:
                item = {
                    "position": video.position,
                    "bvid": video.bvid,
                    "title": video.title,
                    "category": video.category,
                    "owner": video.owner,
                    "view": video.view,
                    "like": video.like,
                    "business_category": None,
                    "entity_labels": extract_product_client_tags(video, tags.get(video.bvid, []), None),
                    "three_c_category": None,
                    "reason": "",
                    "url": VIDEO_URL.format(bvid=video.bvid),
                }
            item["sources"] = []
            item["podcast_reasons"] = []
            opportunities[video.bvid] = item
        if source not in item["sources"]:
            item["sources"].append(source)
        if podcast_reason not in item["podcast_reasons"]:
            item["podcast_reasons"].append(podcast_reason)

    for source_name, videos in source_videos:
        for video in videos:
            is_podcast, reason = classify_podcast(video, tags.get(video.bvid, []))
            if is_podcast:
                add(video, f"{source_name} #{video.position}", reason)

    return list(opportunities.values())


def pct(count: int, total: int) -> str:
    """Format one-decimal percentages for summary tables."""
    return f"{(100 * count / total):.1f}%" if total else "—"


def x(value: Any) -> str:
    """Escape text for Feishu's XML subset."""
    return html.escape(str(value), quote=True)


def count_category(group: dict[str, Any], category: str) -> int:
    """Count one mutually exclusive business category inside a source list."""
    return sum(1 for item in group["items"] if item["business_category"] == category)


def merge_category(report: dict[str, Any], category: str) -> list[dict[str, Any]]:
    """Merge source appearances by BV id for one business category."""
    merged: dict[str, dict[str, Any]] = {}
    sources = [
        ("综合热门", report["popular"]["items"]),
        ("排行榜", report["ranking"]["items"]),
        (f"每周必看第{report['weekly']['number']}期", report["weekly"]["items"]),
    ]
    for source, items in sources:
        for item in items:
            if item["business_category"] != category:
                continue
            if item["bvid"] not in merged:
                merged[item["bvid"]] = {**item, "sources": []}
            label = f"{source} #{item['position']}"
            if label not in merged[item["bvid"]]["sources"]:
                merged[item["bvid"]]["sources"].append(label)
    return list(merged.values())


def render_rows(items: list[dict[str, Any]]) -> str:
    """Render the rows shared by the three category tables."""
    return "".join(
        "<tr>"
        f"<td>{x('；'.join(item['sources']))}</td>"
        f"<td>{x('；'.join(item['entity_labels']) or '—')}</td>"
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
        "<table><colgroup><col width=\"150\"/><col width=\"150\"/><col width=\"280\"/>"
        "<col width=\"110\"/><col width=\"220\"/></colgroup>"
        "<thead><tr><th background-color=\"light-gray\">来源 / 榜位</th>"
        "<th background-color=\"light-blue\">产品 / 客户标签</th>"
        "<th background-color=\"light-gray\">视频</th>"
        "<th background-color=\"light-gray\">UP 主</th>"
        "<th background-color=\"light-gray\">判定依据</th></tr></thead>"
        f"<tbody>{render_rows(items)}</tbody></table>"
    )


def render_podcast_table(items: list[dict[str, Any]]) -> str:
    """Render the independent video-podcast opportunity track."""
    if not items:
        return "<p>本日未命中。</p>"
    rows = "".join(
        "<tr>"
        f"<td>{x('；'.join(item['sources']))}</td>"
        f"<td>{x(item.get('business_category') or '泛主题')}</td>"
        f"<td>{x('；'.join(item['entity_labels']) or '—')}</td>"
        f"<td><a href=\"{x(item['url'])}\">{x(item['title'])}</a></td>"
        f"<td>{x(item['owner'])}</td>"
        f"<td>{x(format(item['view'], ','))}</td>"
        f"<td>{x('；'.join(item['podcast_reasons']))}</td>"
        "</tr>"
        for item in items
    )
    return (
        "<table><colgroup><col width=\"165\"/><col width=\"85\"/><col width=\"145\"/>"
        "<col width=\"260\"/><col width=\"105\"/><col width=\"85\"/><col width=\"205\"/></colgroup>"
        "<thead><tr><th background-color=\"light-gray\">来源 / 位置</th>"
        "<th background-color=\"light-blue\">主题</th>"
        "<th background-color=\"light-blue\">产品 / 客户标签</th>"
        "<th background-color=\"light-gray\">视频</th>"
        "<th background-color=\"light-gray\">UP 主</th>"
        "<th background-color=\"light-gray\">播放</th>"
        "<th background-color=\"light-gray\">机会依据</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def render_xml(
    report: dict[str, Any],
    *,
    leading_rule: bool = True,
    include_heading: bool = True,
) -> str:
    """Render one date-first section with three topics and one podcast opportunity track."""
    popular = report["popular"]
    ranking = report["ranking"]
    weekly = report["weekly"]
    podcast = report["podcast"]
    software = merge_category(report, "AI软件")
    hardware = merge_category(report, "科技硬件/3C")
    aigc = merge_category(report, "AIGC内容")
    prefix = "<hr/>" if leading_rule else ""
    heading = f"<h1>{x(report['date'])}</h1>" if include_heading else ""
    return "".join(
        [
            prefix,
            heading,
            f"<p><b>抓取时间：</b>{x(report['snapshot_at'])}　"
            f"<b>每周必看：</b>{x(weekly['label'])}　"
            f"<b>播客候选池：</b>三榜去重 {podcast['candidate_count']} 支</p>",
            "<table><colgroup><col width=\"145\"/><col width=\"75\"/>"
            "<col width=\"105\"/><col width=\"90\"/><col width=\"105\"/><col width=\"90\"/></colgroup>"
            "<thead><tr><th background-color=\"light-gray\">来源</th>"
            "<th background-color=\"light-gray\">规模</th>"
            "<th background-color=\"light-blue\">AI 软件</th>"
            "<th background-color=\"light-blue\">科技硬件 / 3C</th>"
            "<th background-color=\"light-gray\">AIGC 内容</th>"
            "<th background-color=\"light-gray\">相关视频</th></tr></thead><tbody>",
            f"<tr><td>综合热门</td><td>{popular['total_slots']}</td>"
            f"<td>{count_category(popular, 'AI软件')}</td>"
            f"<td>{count_category(popular, '科技硬件/3C')}</td>"
            f"<td>{count_category(popular, 'AIGC内容')}</td><td>{popular['related_count']}</td></tr>",
            f"<tr><td>全站排行榜</td><td>{ranking['total_slots']}</td>"
            f"<td>{count_category(ranking, 'AI软件')}</td>"
            f"<td>{count_category(ranking, '科技硬件/3C')}</td>"
            f"<td>{count_category(ranking, 'AIGC内容')}</td><td>{ranking['related_count']}</td></tr>",
            f"<tr><td>每周必看第 {weekly['number']} 期</td><td>{weekly['total_slots']}</td>"
            f"<td>{count_category(weekly, 'AI软件')}</td>"
            f"<td>{count_category(weekly, '科技硬件/3C')}</td>"
            f"<td>{count_category(weekly, 'AIGC内容')}</td><td>{weekly['related_count']}</td></tr>",
            "</tbody></table>",
            f"<p><b>三榜去重：</b>AI 软件 {len(software)} 支，科技硬件 / 3C {len(hardware)} 支，"
            f"AIGC 内容 {len(aigc)} 支；视频播客机会 {podcast['related_count']} 支，其中与三个主题重叠 "
            f"{podcast['topic_overlap_count']} 支、同时出现在多个榜单 {podcast['multi_source_count']} 支。"
            "三个主题互斥，播客是从三榜候选中识别的可重叠内容形态；科技分区只用于召回。</p>",
            f"<h2>AI 软件（{len(software)} 支）</h2>",
            render_table(software),
            f"<h2>科技硬件 / 3C（{len(hardware)} 支）</h2>",
            render_table(hardware),
            f"<h2>AIGC 内容（{len(aigc)} 支）</h2>",
            render_table(aigc),
            f"<h2>视频播客机会（{podcast['related_count']} 支）</h2>",
            render_podcast_table(podcast["items"]),
            "<p><b>口径：</b>模型、智能体、工具、教程、软件和 AI 编程归入 AI 软件；"
            "AI 设备、机器人、消费数码、创客工程、机械航模和航空航天归入科技硬件 / 3C；"
            "AI 视频、音乐、动画、短剧、配音和生成工具成片归入 AIGC 内容。"
            "“客户”标签仅用于标题、简介或标签明确披露合作、赞助或联合出品的品牌；其他命中只标产品/品牌。"
            "反诈提醒、禁用声明和“不是 AI”等偶然命中排除。"
            "视频播客机会只从当天综合热门、排行榜和每周必看中识别：标题或独立标签明确标注播客，"
            "或至少 20 分钟且同时具备对谈与期数、主播/嘉宾结构时纳入；时长和活动标签都不能单独作为结论。"
            "历史官方专区样本仅用于校准规则，不作为日报数据源，也不会固定写入专区视频。</p>",
        ]
    )


def render_document(report: dict[str, Any]) -> str:
    """Render a complete tracker document for the initial structure migration."""
    return "".join(
        [
            "<title>B站 AI 热门日报</title>",
            "<p>每日记录综合热门、全站排行榜和每周必看中的 AI 软件、"
            "科技硬件 / 3C 与 AIGC 内容，并标注可识别的产品、品牌和明确披露的客户。"
            "视频播客机会只从这三个榜单中识别，是可与三个主题重叠的内容形态；科技分区仅作为候选池。</p>",
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
    status = run_lark(["auth", "status", "--verify"], require_ok=False)
    user = ((status.get("identities") or {}).get("user") or {})
    if not status.get("verified") or user.get("status") != "ready":
        raise CollectionError("Feishu user identity is not ready or verified")


def write_report(doc: str, date: str, snapshot_at: str, xml: str) -> str:
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
    verify_report_section(doc, date, snapshot_at)
    return "written"


def find_date_heading_id(content: str, date: str) -> str | None:
    """Find the exact top-level date heading in an outline fragment."""
    for heading_date, heading_id in date_heading_ids(content):
        if heading_date == date:
            return heading_id
    return None


def date_heading_ids(content: str) -> list[tuple[str, str]]:
    """Return date heading ids in their current document order."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise CollectionError(f"Feishu outline returned invalid XML: {exc}") from exc
    headings: list[tuple[str, str]] = []
    for node in root.iter("h1"):
        label = "".join(node.itertext()).strip()
        block_id = node.attrib.get("id")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", label) and block_id:
            headings.append((label, block_id))
    return headings


def report_anchor_id(doc: str, document_id: str) -> str:
    """Find the intro block after which newest-first date sections belong."""
    result = run_lark(
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
            "每日记录综合热门",
            "--detail",
            "with-ids",
            "--doc-format",
            "xml",
        ]
    )
    content = (((result.get("data") or {}).get("document") or {}).get("content") or "")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise CollectionError(f"Feishu intro lookup returned invalid XML: {exc}") from exc
    for node in root:
        if node.attrib.get("id"):
            return str(node.attrib["id"])
        if node.attrib.get("top-block-id"):
            return str(node.attrib["top-block-id"])
    return document_id


def section_body_ids(content: str, date: str) -> list[str]:
    """Return direct top-level block ids below one date heading."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise CollectionError(f"Feishu section returned invalid XML: {exc}") from exc
    if root.tag != "fragment":
        raise CollectionError("Feishu section response did not contain a fragment")
    children = list(root)
    if not children or children[0].tag != "h1":
        raise CollectionError("Feishu date section did not start with an H1 heading")
    if "".join(children[0].itertext()).strip() != date:
        raise CollectionError("Feishu date section heading did not match the requested date")
    ids = [node.attrib.get("id") for node in children[1:]]
    if any(not block_id for block_id in ids):
        raise CollectionError("Feishu date section contained a top-level block without an id")
    return [str(block_id) for block_id in ids]


def verify_report_section(doc: str, date: str, snapshot_at: str) -> None:
    """Verify newest-first placement, the four H2 sections, and podcast table columns."""
    outline = run_lark(
        [
            "docs",
            "+fetch",
            "--as",
            "user",
            "--doc",
            doc,
            "--scope",
            "outline",
            "--max-depth",
            "1",
            "--detail",
            "with-ids",
            "--doc-format",
            "xml",
        ]
    )
    outline_content = (
        ((outline.get("data") or {}).get("document") or {}).get("content") or ""
    )
    headings = date_heading_ids(outline_content)
    if not headings or headings[0][0] != date:
        raise CollectionError("Feishu readback did not place today's date first")
    heading_id = find_date_heading_id(outline_content, date)
    if not heading_id:
        raise CollectionError("Feishu readback could not find today's date heading")
    section = run_lark(
        [
            "docs",
            "+fetch",
            "--as",
            "user",
            "--doc",
            doc,
            "--scope",
            "section",
            "--start-block-id",
            heading_id,
            "--detail",
            "simple",
            "--doc-format",
            "xml",
        ]
    )
    content = (((section.get("data") or {}).get("document") or {}).get("content") or "")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise CollectionError(f"Feishu report readback returned invalid XML: {exc}") from exc
    h2_labels = [
        re.sub(r"（\d+ 支）$", "", "".join(node.itertext()).strip())
        for node in root.iter("h2")
    ]
    expected_h2 = ["AI 软件", "科技硬件 / 3C", "AIGC 内容", "视频播客机会"]
    if h2_labels != expected_h2:
        raise CollectionError(f"Feishu readback had unexpected H2 sections: {h2_labels}")
    section_text = "".join(root.itertext())
    required_markers = [
        snapshot_at,
        "产品 / 客户标签",
        "主题",
        "播放",
        "机会依据",
    ]
    missing = [marker for marker in required_markers if marker not in section_text]
    if missing:
        raise CollectionError(f"Feishu readback missed report markers: {missing}")


def upsert_report(doc: str, report: dict[str, Any]) -> str:
    """Append a new date or refresh only the existing date section."""
    verify_lark_user()
    date = report["date"]
    outline = run_lark(
        [
            "docs",
            "+fetch",
            "--as",
            "user",
            "--doc",
            doc,
            "--scope",
            "outline",
            "--max-depth",
            "1",
            "--detail",
            "with-ids",
            "--doc-format",
            "xml",
        ]
    )
    outline_document = ((outline.get("data") or {}).get("document") or {})
    outline_content = outline_document.get("content") or ""
    document_id = str(outline_document.get("document_id") or "")
    headings = date_heading_ids(outline_content)
    heading_id = find_date_heading_id(outline_content, date)
    if not heading_id:
        if not headings:
            return write_report(doc, date, report["snapshot_at"], render_xml(report))
        anchor_id = report_anchor_id(doc, document_id)
        run_lark(
            [
                "docs",
                "+update",
                "--as",
                "user",
                "--doc",
                doc,
                "--command",
                "block_insert_after",
                "--block-id",
                anchor_id,
                "--content",
                "-",
            ],
            stdin=render_xml(report, leading_rule=False),
        )
        verify_report_section(doc, date, report["snapshot_at"])
        return "written"

    section = run_lark(
        [
            "docs",
            "+fetch",
            "--as",
            "user",
            "--doc",
            doc,
            "--scope",
            "section",
            "--start-block-id",
            heading_id,
            "--detail",
            "full",
            "--doc-format",
            "xml",
        ]
    )
    section_content = (((section.get("data") or {}).get("document") or {}).get("content") or "")
    old_body_ids = section_body_ids(section_content, date)
    if headings and heading_id != headings[0][1]:
        anchor_id = report_anchor_id(doc, document_id)
        run_lark(
            [
                "docs",
                "+update",
                "--as",
                "user",
                "--doc",
                doc,
                "--command",
                "block_move_after",
                "--block-id",
                anchor_id,
                "--src-block-ids",
                ",".join([heading_id, *old_body_ids]),
            ]
        )
    body = render_xml(report, leading_rule=False, include_heading=False)
    run_lark(
        [
            "docs",
            "+update",
            "--as",
            "user",
            "--doc",
            doc,
            "--command",
            "block_insert_after",
            "--block-id",
            heading_id,
            "--content",
            "-",
        ],
        stdin=body,
    )
    if old_body_ids:
        run_lark(
            [
                "docs",
                "+update",
                "--as",
                "user",
                "--doc",
                doc,
                "--command",
                "block_delete",
                "--block-id",
                ",".join(old_body_ids),
            ]
        )

    verify_report_section(doc, date, report["snapshot_at"])
    return "updated"


def overwrite_report(doc: str, date: str, snapshot_at: str, xml: str) -> str:
    """Replace the tracker once when migrating it to the date-first structure."""
    verify_lark_user()
    run_lark(
        ["docs", "+update", "--as", "user", "--doc", doc, "--command", "overwrite", "--content", "-"],
        stdin=xml,
    )
    verify_report_section(doc, date, snapshot_at)
    return "overwritten"


def collect(max_popular_pages: int) -> dict[str, Any]:
    """Collect, tag, classify, and aggregate three lists plus podcast opportunities."""
    client = BilibiliClient()
    weekly, weekly_slots, weekly_label, weekly_number = fetch_weekly(client)
    popular, popular_slots = fetch_popular(client, max_popular_pages)
    ranking, ranking_slots = fetch_ranking(client)
    source_videos = [
        ("综合热门", popular),
        ("全站排行榜", ranking),
        (f"每周必看第{weekly_number}期", weekly),
    ]
    podcast_candidates = dedupe([video for _, videos in source_videos for video in videos])
    tags, tag_errors = enrich(client, [popular, ranking, weekly])
    tag_total = len(
        {
            video.bvid
            for group in [popular, ranking, weekly]
            for video in group
        }
    )
    if len(tag_errors) > max(5, int(tag_total * 0.05)):
        raise CollectionError(
            f"Bilibili tag lookup failed for {len(tag_errors)}/{tag_total} videos; refusing to write an undercount"
        )
    popular_selected = select(popular, tags)
    ranking_selected = select(ranking, tags)
    weekly_selected = select(weekly, tags)
    podcast_selected = select_podcast_opportunities(source_videos, tags)
    all_selected = popular_selected + ranking_selected + weekly_selected + podcast_selected
    unique_related = {item["bvid"] for item in all_selected}
    unique_software = {
        item["bvid"] for item in all_selected if item["business_category"] == "AI软件"
    }
    unique_hardware = {
        item["bvid"] for item in all_selected if item["business_category"] == "科技硬件/3C"
    }
    unique_aigc = {
        item["bvid"] for item in all_selected if item["business_category"] == "AIGC内容"
    }
    now = datetime.now(TIMEZONE)
    return {
        "date": now.strftime("%Y-%m-%d"),
        "snapshot_at": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "popular": {
            "total_slots": popular_slots,
            "unique_videos": len(popular),
            "related_count": len(popular_selected),
            "items": popular_selected,
        },
        "ranking": {
            "total_slots": ranking_slots,
            "unique_videos": len(ranking),
            "related_count": len(ranking_selected),
            "items": ranking_selected,
        },
        "weekly": {
            "number": weekly_number,
            "label": weekly_label,
            "total_slots": weekly_slots,
            "unique_videos": len(weekly),
            "related_count": len(weekly_selected),
            "items": weekly_selected,
        },
        "podcast": {
            "candidate_count": len(podcast_candidates),
            "related_count": len(podcast_selected),
            "topic_overlap_count": sum(
                1 for item in podcast_selected if item.get("business_category")
            ),
            "multi_source_count": sum(
                1 for item in podcast_selected if len(item["sources"]) > 1
            ),
            "items": podcast_selected,
        },
        "unique_related_count": len(unique_related),
        "unique_software_count": len(unique_software),
        "unique_hardware_count": len(unique_hardware),
        "unique_aigc_count": len(unique_aigc),
        "tag_errors": tag_errors,
    }


def load_report(path: str) -> dict[str, Any]:
    """Load and validate a complete report collected in another network environment."""
    if path == "-":
        payload = json.load(sys.stdin)
    else:
        with open(path, "r", encoding="utf-8") as stream:
            payload = json.load(stream)
    if not isinstance(payload, dict):
        raise CollectionError("Imported report must be a JSON object")
    today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    if payload.get("date") != today:
        raise CollectionError(f"Imported report date must be today ({today})")
    snapshot_at = payload.get("snapshot_at")
    if not isinstance(snapshot_at, str) or not snapshot_at.startswith(today):
        raise CollectionError("Imported report has an invalid snapshot timestamp")
    categories = {"AI软件", "科技硬件/3C", "AIGC内容"}
    all_items: list[dict[str, Any]] = []
    for source in ["popular", "ranking", "weekly", "podcast"]:
        group = payload.get(source)
        if not isinstance(group, dict) or not isinstance(group.get("items"), list):
            raise CollectionError(f"Imported report is missing {source} items")
        if source != "podcast" and (
            not isinstance(group.get("total_slots"), int) or group["total_slots"] <= 0
        ):
            raise CollectionError(f"Imported report has an invalid {source} list size")
        for item in group["items"]:
            if not isinstance(item, dict):
                raise CollectionError(f"Imported report has an invalid {source} item")
            valid_category = item.get("business_category") in categories
            if source == "podcast" and item.get("business_category") is None:
                valid_category = True
            if not valid_category:
                raise CollectionError(f"Imported report has an invalid {source} category")
            if not item.get("bvid") or not item.get("url"):
                raise CollectionError(f"Imported report has an incomplete {source} item")
            if source == "podcast" and (
                not isinstance(item.get("sources"), list)
                or not item["sources"]
                or not isinstance(item.get("podcast_reasons"), list)
                or not item["podcast_reasons"]
            ):
                raise CollectionError("Imported report has incomplete podcast evidence")
            if source == "podcast" and any(
                not re.fullmatch(
                    r"(?:综合热门|全站排行榜|每周必看第\d+期) #\d+",
                    label,
                )
                for label in item["sources"]
            ):
                raise CollectionError("Imported podcast item came from outside the three hot lists")
        all_items.extend(group["items"])
    podcast = payload["podcast"]
    if (
        not isinstance(podcast.get("candidate_count"), int)
        or podcast["candidate_count"] <= 0
        or podcast["candidate_count"] < len(podcast["items"])
    ):
        raise CollectionError("Imported report has an invalid podcast candidate count")
    if podcast.get("related_count") != len(podcast["items"]):
        raise CollectionError("Imported report failed the podcast opportunity count check")
    podcast_overlap = sum(
        1 for item in podcast["items"] if item.get("business_category") in categories
    )
    if podcast.get("topic_overlap_count") != podcast_overlap:
        raise CollectionError("Imported report failed the podcast topic-overlap check")
    podcast_multi_source = sum(
        1 for item in podcast["items"] if len(item["sources"]) > 1
    )
    if podcast.get("multi_source_count") != podcast_multi_source:
        raise CollectionError("Imported report failed the podcast multi-source count check")
    unique_by_category = {
        category: {
            item["bvid"] for item in all_items if item["business_category"] == category
        }
        for category in categories
    }
    expected_counts = {
        "unique_software_count": len(unique_by_category["AI软件"]),
        "unique_hardware_count": len(unique_by_category["科技硬件/3C"]),
        "unique_aigc_count": len(unique_by_category["AIGC内容"]),
        "unique_related_count": len({item["bvid"] for item in all_items}),
    }
    for field, expected in expected_counts.items():
        if payload.get(field) != expected:
            raise CollectionError(f"Imported report failed the {field} integrity check")
    return payload


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
        "--upsert",
        action="store_true",
        help="Append a new date or refresh the existing date section in Feishu",
    )
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
    parser.add_argument(
        "--report-input",
        help="Use a complete report JSON from another collector; pass - to read stdin",
    )
    return parser.parse_args()


def main() -> int:
    """Run collection and optionally perform the idempotent Feishu append."""
    args = parse_args()
    try:
        if sum(bool(value) for value in [args.write, args.upsert, args.overwrite]) > 1:
            raise CollectionError("Choose only one of --write, --upsert, or --overwrite")
        if (args.write or args.upsert or args.overwrite) and not args.doc:
            raise CollectionError(
                "Feishu document is required; pass --doc or set BILIBILI_AI_FEISHU_DOC"
            )
        report = (
            load_report(args.report_input)
            if args.report_input
            else collect(args.max_popular_pages)
        )
        xml = render_xml(report)
        status = "dry_run"
        if args.overwrite:
            xml = render_document(report)
            status = overwrite_report(args.doc, report["date"], report["snapshot_at"], xml)
        elif args.upsert:
            status = upsert_report(args.doc, report)
        elif args.write:
            status = write_report(args.doc, report["date"], report["snapshot_at"], xml)
        output = {
            "ok": True,
            "status": status,
            "document_url": args.doc,
            "date": report["date"],
            "snapshot_at": report["snapshot_at"],
            "popular": {
                "total": report["popular"]["total_slots"],
                "related_count": report["popular"]["related_count"],
                "software_count": count_category(report["popular"], "AI软件"),
                "hardware_count": count_category(report["popular"], "科技硬件/3C"),
                "aigc_count": count_category(report["popular"], "AIGC内容"),
            },
            "ranking": {
                "total": report["ranking"]["total_slots"],
                "related_count": report["ranking"]["related_count"],
                "software_count": count_category(report["ranking"], "AI软件"),
                "hardware_count": count_category(report["ranking"], "科技硬件/3C"),
                "aigc_count": count_category(report["ranking"], "AIGC内容"),
            },
            "weekly": {
                "number": report["weekly"]["number"],
                "total": report["weekly"]["total_slots"],
                "related_count": report["weekly"]["related_count"],
                "software_count": count_category(report["weekly"], "AI软件"),
                "hardware_count": count_category(report["weekly"], "科技硬件/3C"),
                "aigc_count": count_category(report["weekly"], "AIGC内容"),
            },
            "podcast": {
                "candidate_count": report["podcast"]["candidate_count"],
                "opportunity_count": report["podcast"]["related_count"],
                "topic_overlap_count": report["podcast"]["topic_overlap_count"],
                "multi_source_count": report["podcast"]["multi_source_count"],
                "software_count": count_category(report["podcast"], "AI软件"),
                "hardware_count": count_category(report["podcast"], "科技硬件/3C"),
                "aigc_count": count_category(report["podcast"], "AIGC内容"),
            },
            "unique_related_count": report["unique_related_count"],
            "unique_software_count": report["unique_software_count"],
            "unique_hardware_count": report["unique_hardware_count"],
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
