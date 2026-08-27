"""Regression tests for hot-list podcast opportunity selection."""

from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path
import sys
import unittest


SCRIPT = (
    Path(__file__).parents[1]
    / "skills"
    / "track-bilibili-ai-hot"
    / "scripts"
    / "collect_and_write.py"
)
SPEC = importlib.util.spec_from_file_location("collect_and_write", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def video(
    bvid: str,
    title: str,
    *,
    position: int = 1,
    description: str = "",
    duration: int = 0,
) -> object:
    """Build one normalized test video."""
    return MODULE.Video(
        position=position,
        bvid=bvid,
        title=title,
        category="知识",
        owner="测试UP",
        description=description,
        view=100,
        like=10,
        duration=duration,
        pubtime=0,
    )


class PodcastClassificationTests(unittest.TestCase):
    """Keep the calibration corpus separate from daily source selection."""

    def test_explicit_podcast_title_is_strong_evidence(self) -> None:
        candidate = video("BV1explicit", "和产品经理聊 AI【视频播客】")

        self.assertEqual(
            MODULE.classify_podcast(candidate, []),
            (True, "标题明确标注视频播客"),
        )

    def test_long_structured_conversation_is_included(self) -> None:
        candidate = video(
            "BV1structured",
            "EP12 对话 AI 创业者",
            duration=3600,
        )

        included, reason = MODULE.classify_podcast(candidate, [])

        self.assertTrue(included)
        self.assertIn("长对谈", reason)

    def test_duration_or_campaign_tag_alone_is_not_enough(self) -> None:
        candidate = video(
            "BV1campaign",
            "聊聊最近的 AI 新闻",
            duration=3600,
        )

        self.assertEqual(
            MODULE.classify_podcast(candidate, ["上B站看播客"]),
            (False, ""),
        )

    def test_opportunities_only_keep_current_hot_list_sources(self) -> None:
        current = video("BV1current", "AI 产品观察【Podcast】", position=7)
        same_video = video("BV1current", "AI 产品观察【Podcast】", position=3)
        historical_reference = video("BV1reference", "历史专区里的普通长视频", duration=3600)

        selected = MODULE.select_podcast_opportunities(
            [("综合热门", [current, historical_reference]), ("全站排行榜", [same_video])],
            {current.bvid: []},
        )

        self.assertEqual([item["bvid"] for item in selected], ["BV1current"])
        self.assertEqual(
            selected[0]["sources"],
            ["综合热门 #7", "全站排行榜 #3"],
        )
        self.assertTrue(all("专区" not in source for source in selected[0]["sources"]))

    def test_report_treats_podcast_as_overlay_not_source(self) -> None:
        report = {
            "date": "2026-08-27",
            "snapshot_at": "2026-08-27 18:00:00 CST",
            "popular": {"total_slots": 500, "related_count": 0, "items": []},
            "ranking": {"total_slots": 100, "related_count": 0, "items": []},
            "weekly": {
                "checked": True,
                "number": 342,
                "label": "第 342 期",
                "total_slots": 30,
                "related_count": 0,
                "items": [],
            },
            "podcast": {
                "candidate_count": 580,
                "related_count": 0,
                "topic_overlap_count": 0,
                "multi_source_count": 0,
                "items": [],
            },
        }

        rendered = MODULE.render_xml(report)

        self.assertIn("播客候选池：</b>本次三源去重 580 支", rendered)
        self.assertIn("<b>本次三源去重：</b>", rendered)
        self.assertNotIn("<tr><td>视频播客机会</td>", rendered)
        self.assertNotIn("官方视频播客专区", rendered)

    def test_weekly_auto_mode_only_fetches_after_friday_18(self) -> None:
        thursday_evening = datetime(2026, 8, 27, 18, 0, tzinfo=MODULE.TIMEZONE)
        friday_morning = datetime(2026, 8, 28, 10, 0, tzinfo=MODULE.TIMEZONE)
        friday_evening = datetime(2026, 8, 28, 18, 0, tzinfo=MODULE.TIMEZONE)

        self.assertFalse(MODULE.should_fetch_weekly(thursday_evening, "auto"))
        self.assertFalse(MODULE.should_fetch_weekly(friday_morning, "auto"))
        self.assertTrue(MODULE.should_fetch_weekly(friday_evening, "auto"))
        self.assertTrue(MODULE.should_fetch_weekly(thursday_evening, "fetch"))
        self.assertFalse(MODULE.should_fetch_weekly(friday_evening, "skip"))

    def test_unchecked_weekly_is_reported_as_not_checked(self) -> None:
        report = {
            "date": "2026-08-27",
            "snapshot_at": "2026-08-27 18:00:00 CST",
            "popular": {"total_slots": 500, "related_count": 0, "items": []},
            "ranking": {"total_slots": 100, "related_count": 0, "items": []},
            "weekly": {
                "checked": False,
                "number": 0,
                "label": "本次未检查",
                "total_slots": 0,
                "related_count": 0,
                "items": [],
            },
            "podcast": {
                "candidate_count": 550,
                "related_count": 0,
                "topic_overlap_count": 0,
                "multi_source_count": 0,
                "items": [],
            },
        }

        rendered = MODULE.render_xml(report)

        self.assertIn("每周必看（本次未检查）", rendered)
        self.assertIn("每周五 18:00 更新", rendered)
        self.assertIn("<b>本次两源去重：</b>", rendered)
        self.assertNotIn("每周必看第 0 期", rendered)


if __name__ == "__main__":
    unittest.main()
