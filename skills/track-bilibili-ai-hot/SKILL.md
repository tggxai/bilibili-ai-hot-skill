---
name: track-bilibili-ai-hot
description: Collect the current Bilibili 综合热门、全站排行榜、每周必看 lists, classify videos into mutually exclusive AI software, technology hardware/3C, and AIGC content categories, identify product/brand and explicitly disclosed client labels, deduplicate them, append a date-first Feishu report, and sample the popular list to study its update cadence. Use for B站 AI/科技数码热门日报、AI 软件监测、AI 与科技硬件、3C 数码、创客工程、机械航模、航空航天、AIGC 榜单统计、产品或甲方客户识别、热门更新规律观测、每日视频监测、复跑某天报告，或把榜单结果写入飞书文档。
---

# B站 AI 热门日报

运行确定性脚本抓取榜单、读取视频标签并过滤误命中。每支视频只归入一个主分类：“AI 软件”“科技硬件 / 3C”“AIGC 内容”，并单独标注可识别的产品、品牌和明确披露的甲方客户。B站分区只作为候选来源，不直接作为报告分类。写入时通过 `--doc` 或 `BILIBILI_AI_FEISHU_DOC` 指定目标飞书文档。

## 工作流

1. 若要写入飞书，先加载并遵守 `lark-doc` 与 `lark-shared` 技能。文档操作使用用户身份。
2. 从本技能目录运行：

   ```bash
   python3 scripts/collect_and_write.py --upsert --doc "飞书文档 URL 或 token"
   ```

3. 检查脚本返回的 JSON：
   - `status: written`：当天首次运行，已追加并回读验证。
   - `status: updated`：当天已有报告，已只刷新当天章节并保留历史日期。
   - 非零退出：报告失败阶段与简短错误，不把空榜单写入飞书。
   - 标签接口失败超过 5% 时脚本主动失败，避免把限速造成的漏数写进日报。
4. 不要自行重写脚本已经完成的统计，也不要仅凭标题二次删改候选。用户要求改变口径时，修改脚本规则并重新验证。
5. 除非用户明确要求只做调试或 dry run，否则把飞书同步作为任务的最后一个执行步骤：运行 `--upsert` 后检查返回状态，并回读当天章节。只有写入和回读都成功，任务才算完成；失败时说明原因，不得把本地抓取成功表述为任务完成。

## 统计口径

- 综合热门持续翻页到首个空页，最多 50 页；当前通常为 25 页、500 个榜单位。
- 排行榜使用全站榜单；每周必看使用最新一期。
- **AI 软件**：教程、工具、模型、智能体、软件、AI 编程、AI 游戏/应用与 AI 安全。
- **科技硬件 / 3C**：AI 眼镜、机器人与具身智能设备；手机、电脑、系统、影像影音、外设、智能穿戴与家居；以及有明确标题或标签证据的创客工程、机械航模、航空航天和科技实验。不能只因处于“科技”“数码”或“极客 DIY”分区就纳入。
- **AIGC 内容**：AI 视频、音乐、动画、短剧、配音、AI 辅助创作，以及使用 Updream、MiniMax、Seedance、Seko 等工具生成的成片。
- 三个主分类按视频内容主轴互斥：软件教程/工具归 AI 软件，设备、数码与硬科技归科技硬件 / 3C，作品展示归 AIGC 内容。
- **产品 / 客户标签**是附加维度：产品名与普通品牌露出分别标为“产品”“品牌”；只有标题、简介或标签明确披露合作、赞助、推广或联合出品时才标为“客户”。不根据推测把普通品牌提及当作甲方。
- 反诈提醒、禁用声明、“不是 AI”、作者名或被 @ 用户名里的偶然字符串不计入。
- 同一 BV 号在同一榜单只计一次；三榜总数另按 BV 号去重。

## 幂等与写入

- 文档标题固定为 `B站 AI 热门日报`；每个日期使用 `YYYY-MM-DD` 一级标题，时区固定为 `Asia/Shanghai`。
- 日期章节按日期倒序排列，最新日期紧跟日报说明，历史日期依次向下。
- 每个日期下面只使用三个二级标题：`AI 软件`、`科技硬件 / 3C`、`AIGC 内容`。三榜来源和榜位合并到表格行中，不重复创建三套章节。
- 写入前按日期一级标题查询目标文档；当天不存在则插入所有旧日期之前，已存在则只替换当天标题下的内容并确保当天在顶部。
- 写入内容包含分类摘要、产品 / 客户标签、视频链接、来源/榜位、UP 主和判定依据。
- 写入后再次查询最新抓取时间；未命中则视为失败。

## 调试

不写飞书的快速实测：

```bash
python3 scripts/collect_and_write.py --max-popular-pages 1
```

标签接口失败超过阈值且另一个受信任环境能够完整抓取时，可把该环境的 `collect()` JSON 通过标准输入交给本机写入流程：

```bash
python3 scripts/collect_and_write.py --upsert --report-input -
```

输入报告必须是当天数据，且三类去重数量与明细一致，否则脚本拒绝写入。飞书用户凭证仍只保留在执行 `--upsert` 的本机。

写入目标文档时显式传入：

```bash
python3 scripts/collect_and_write.py --upsert --doc "飞书文档 URL 或 token"
```

不要在脚本、日志或文档中写入飞书凭证或浏览器 Cookie；脚本仅使用临时匿名 B站指纹 Cookie。

## 热门更新规律采样

研究“综合热门”何时换榜时，使用固定的无 Cookie 口径抓取前 200 位，避免登录态带来的个性化排序：

```bash
python3 scripts/sample_popular.py --db data/popular_samples.sqlite3 --limit 200
python3 scripts/analyze_popular_samples.py --db data/popular_samples.sqlite3
```

采样器只写追加式 SQLite 快照，不写飞书。建议连续 14 天每半小时在 `07` 分和 `37` 分采样；日报仍保持低频，实验结束后依据 Top 20/50/100/200 的新增、退出和名次变化选择更合适的日报时间。
