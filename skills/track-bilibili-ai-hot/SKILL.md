---
name: track-bilibili-ai-hot
description: Collect the current Bilibili 综合热门、全站排行榜 and 每周必看, classify videos into mutually exclusive AI software, technology hardware/3C, and AIGC content categories, identify podcast-form opportunities within those hot lists as a separate overlapping track, identify product/brand and explicitly disclosed client labels, deduplicate them, append a date-first Feishu report, and sample the popular list to study its update cadence. Use for B站 AI/科技数码热门日报、热门榜中的播客或视频播客机会监测、AI 软件监测、AI 与科技硬件、3C 数码、创客工程、机械航模、航空航天、AIGC 榜单统计、产品或甲方客户识别、热门更新规律观测、每日视频监测、复跑某天报告，或把榜单结果写入飞书文档。
---

# B站 AI 热门日报

运行确定性脚本抓取综合热门、全站排行榜和最新每周必看，读取视频标签并过滤误命中。每支主题相关视频只归入一个主分类：“AI 软件”“科技硬件 / 3C”“AIGC 内容”；“视频播客机会”只在这三个热门榜单的当前候选中识别，是可与三个主分类重叠的内容形态。B站分区只作为候选来源，不直接作为报告分类。写入时通过 `--doc` 或 `BILIBILI_AI_FEISHU_DOC` 指定目标飞书文档。

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
   - 标签接口失败超过 5% 时，脚本主动失败，避免把限速造成的漏数写进日报。
4. 不要自行重写脚本已经完成的统计，也不要仅凭标题二次删改候选。用户要求改变口径时，修改脚本规则并重新验证。
5. 除非用户明确要求只做调试或 dry run，否则把飞书同步作为任务的最后一个执行步骤：运行 `--upsert` 后检查返回状态，并回读当天章节。只有写入和回读都成功，任务才算完成；失败时说明原因，不得把本地抓取成功表述为任务完成。

## 统计口径

- 综合热门持续翻页到首个空页，最多 50 页；当前通常为 25 页、500 个榜单位。
- 排行榜使用全站榜单；每周必看使用最新一期。
- **视频播客机会**不是第四个数据源或主题分类。它只扫描当天综合热门、全站排行榜和每周必看中的视频，并把符合播客形态的条目标为可重叠机会；不得固定加入官方专区视频，也不得把专区位置当成热度。
- 用户提供的官方专区前 30 页表格是离线校准样本，只用于提炼“值得纳入”的格式信号，不在日常运行中抓取、引用或充当白名单。强证据是标题或独立标签明确写有“视频播客/播客/Podcast”；无显式标签时，必须同时满足至少 20 分钟、对话/访谈信号，以及期数或主播/嘉宾结构。时长、UP 主历史和“上B站看播客”等活动标签都不能单独作为结论。
- **AI 软件**：教程、工具、模型、智能体、软件、AI 编程、AI 游戏/应用与 AI 安全。
- **科技硬件 / 3C**：AI 眼镜、机器人与具身智能设备；手机、电脑、系统、影像影音、外设、智能穿戴与家居；以及有明确标题或标签证据的创客工程、机械航模、航空航天和科技实验。不能只因处于“科技”“数码”或“极客 DIY”分区就纳入。
- **AIGC 内容**：AI 视频、音乐、动画、短剧、配音、AI 辅助创作，以及使用 Updream、MiniMax、Seedance、Seko 等工具生成的成片。
- 三个主分类按视频内容主轴互斥：软件教程/工具归 AI 软件，设备、数码与硬科技归科技硬件 / 3C，作品展示归 AIGC 内容。
- **产品 / 客户标签**是附加维度：产品名与普通品牌露出分别标为“产品”“品牌”；只有标题、简介或标签明确披露合作、赞助、推广或联合出品时才标为“客户”。不根据推测把普通品牌提及当作甲方。
- 反诈提醒、禁用声明、“不是 AI”、作者名或被 @ 用户名里的偶然字符串不计入。
- 同一 BV 号在同一来源只计一次；三个榜单按 BV 号合并，播客轨道与三个主题的交集不重复增加主题去重数。

## 幂等与写入

- 文档标题固定为 `B站 AI 热门日报`；每个日期使用 `YYYY-MM-DD` 一级标题，时区固定为 `Asia/Shanghai`。
- 日期章节按日期倒序排列，最新日期紧跟日报说明，历史日期依次向下。
- 每个日期下面使用四个二级标题：`AI 软件`、`科技硬件 / 3C`、`AIGC 内容`、`视频播客机会`。前三个主题互斥，第四个为可重叠的内容形态；各来源和位置合并到表格行中。
- 写入前按日期一级标题查询目标文档；当天不存在则插入所有旧日期之前，已存在则只替换当天标题下的内容并确保当天在顶部。
- 写入内容包含分类摘要、产品 / 客户标签、视频链接、来源/位置、UP 主和判定依据；播客表额外包含主题、播放量与机会依据。
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

输入报告必须是当天数据，且三个主题、播客候选池、机会数、多榜交叉数和明细一致；播客来源只能是综合热门、全站排行榜或每周必看，否则脚本拒绝写入。飞书用户凭证仍只保留在执行 `--upsert` 的本机。

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
