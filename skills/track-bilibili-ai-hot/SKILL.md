---
name: track-bilibili-ai-hot
description: Collect the current Bilibili 综合热门、全站排行榜、每周必看 lists, separate AI technology applications such as tutorials and tools from AIGC-generated content, deduplicate the videos, and append a date-first report to Feishu. Use for B站 AI 热门日报、AI 科技应用监测、AIGC 榜单统计、每日 AI 视频监测、复跑某天报告，或把榜单结果写入飞书文档。
---

# B站 AI 热门日报

运行确定性脚本抓取榜单、读取视频标签、过滤误命中，并把结果拆成“AI 科技应用”和“AIGC 生成内容”。团队重点关注教程、工具、模型、产品与真实应用。写入时通过 `--doc` 或 `BILIBILI_AI_FEISHU_DOC` 指定目标飞书文档。

## 工作流

1. 若要写入飞书，先加载并遵守 `lark-doc` 与 `lark-shared` 技能。文档操作使用用户身份。
2. 从本技能目录运行：

   ```bash
   python3 scripts/collect_and_write.py --write --doc "飞书文档 URL 或 token"
   ```

3. 检查脚本返回的 JSON：
   - `status: written`：已追加并回读验证；报告数量和 `document_url`。
   - `status: already_exists`：当天报告已存在；不要再次写入，报告已有文档链接。
   - 非零退出：报告失败阶段与简短错误，不把空榜单写入飞书。
   - 标签接口失败超过 5% 时脚本主动失败，避免把限速造成的漏数写进日报。
4. 不要自行重写脚本已经完成的统计，也不要仅凭标题二次删改候选。用户要求改变口径时，修改脚本规则并重新验证。

## 统计口径

- 综合热门持续翻页到首个空页，最多 50 页；当前通常为 25 页、500 个榜单位。
- 排行榜使用全站榜单；每周必看使用最新一期。
- **AI 科技应用（重点）**：教程、工具、模型、智能体、软件、AI 编程、产品、AI 游戏/应用、AI 安全、AI 眼镜和物理 AI 机器人。
- **AIGC 生成内容**：AI 视频、音乐、动画、短剧、配音、AI 辅助创作，以及使用 Updream、MiniMax、Seedance、Seko 等工具生成的成片。
- 同时命中两类时，以视频主轴判断：教程、工具和产品优先归入 AI 科技应用；作品展示优先归入 AIGC 生成内容。
- 反诈提醒、禁用声明、“不是 AI”、作者名或被 @ 用户名里的偶然字符串不计入。
- 同一 BV 号在同一榜单只计一次；三榜总数另按 BV 号去重。

## 幂等与写入

- 文档标题固定为 `B站 AI 热门日报`；每个日期使用 `YYYY-MM-DD` 一级标题，时区固定为 `Asia/Shanghai`。
- 每个日期下面只使用两个二级标题：`AI 科技应用（重点）`、`AIGC 生成内容`。三榜来源和榜位合并到表格行中，不重复创建三套章节。
- 写入前用日期查询目标文档；命中即返回 `already_exists`。
- 写入内容包含分类摘要、视频链接、来源/榜位、UP 主和判定依据。
- 写入后再次查询当天日期；未命中则视为失败。

## 调试

不写飞书的快速实测：

```bash
python3 scripts/collect_and_write.py --max-popular-pages 1
```

写入目标文档时显式传入：

```bash
python3 scripts/collect_and_write.py --write --doc "飞书文档 URL 或 token"
```

不要在脚本、日志或文档中写入飞书凭证或浏览器 Cookie；脚本仅使用临时匿名 B站指纹 Cookie。
