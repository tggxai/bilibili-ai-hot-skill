# B站 AI 热门日报 Skill

一个可复用的 Codex Skill：每日抓取 B站的「综合热门」「全站排行榜」和最新一期「每周必看」，识别其中的 AI 相关视频，并把结果写成按日期累积的飞书日报。

它会把内容明确分成两条线：

- **AI 科技应用（重点）**：教程、工具、模型、智能体、AI 编程、产品、AI 游戏/应用、AI 安全、AI 眼镜、物理 AI 与机器人。
- **AIGC 生成内容**：AI 视频、音乐、动画、短剧、配音、AI 辅助创作，以及由 Updream、MiniMax、Seedance、Seko 等工具生成的成片。

## 功能

- 完整翻页抓取综合热门，并读取全站排行榜和最新每周必看。
- 结合标题、简介、分区和 B站标签判断视频是否与 AI 有关。
- 排除反诈提示、禁用 AI 声明、“不是 AI”和作者名中的偶然字符串。
- 同一 BV 号去重，同时保留它出现过的榜单和榜位。
- 生成「日期一级标题 + 两个分类二级标题」的飞书日报。
- 同一天首次运行会追加日期章节，后续运行只刷新当天章节，不会重复创建日期。
- 标签接口失败超过 5% 时拒绝写入，避免把限流造成的漏数当成真实数据。

## 报告结构

```text
B站 AI 热门日报
└── 2026-08-19
    ├── AI 科技应用（重点）
    └── AIGC 生成内容
```

每个分类表格包含来源与榜位、视频链接、UP 主和判定依据。日期下方还有三张榜单的规模与分类数量摘要。

## 环境要求

- Python 3.7 或更高版本
- 可访问 B站公开接口的网络环境
- 写入飞书时需要安装 `lark-cli`，并登录一个对目标文档有编辑权限的飞书用户身份
- Codex（用于安装和触发 Skill；脚本也可以单独运行）

飞书登录示例：

```bash
lark-cli auth login --domain docs
lark-cli auth status --verify
```

## 安装 Skill

```bash
git clone https://github.com/tggxai/bilibili-ai-hot-skill.git
mkdir -p ~/.codex/skills
cp -R bilibili-ai-hot-skill/skills/track-bilibili-ai-hot ~/.codex/skills/
```

安装后可以这样调用：

```text
使用 $track-bilibili-ai-hot 抓取今天的 B站 AI 热门，并写入飞书日报。
```

## 使用方法

进入 Skill 目录：

```bash
cd ~/.codex/skills/track-bilibili-ai-hot
```

先进行不写飞书的快速测试：

```bash
python3 scripts/collect_and_write.py --max-popular-pages 1
```

执行完整抓取，但不写入文档：

```bash
python3 scripts/collect_and_write.py
```

写入指定飞书文档：

```bash
python3 scripts/collect_and_write.py \
  --upsert \
  --doc "https://example.feishu.cn/docx/你的文档Token"
```

也可以通过环境变量设置默认文档：

```bash
export BILIBILI_AI_FEISHU_DOC="https://example.feishu.cn/docx/你的文档Token"
python3 scripts/collect_and_write.py --upsert
```

首次把已有文档迁移成日报结构时，可使用 `--overwrite`。这个参数会覆盖整篇目标文档，请只在明确需要时使用：

```bash
python3 scripts/collect_and_write.py --overwrite --doc "飞书文档 URL 或 token"
```

## 返回结果

脚本把结果以 JSON 输出到终端，主要字段包括：

- `status`：`dry_run`、`written`、`updated`、`already_exists` 或 `overwritten`
- `popular`、`ranking`、`weekly`：各榜单规模与两类 AI 视频数量
- `unique_technology_count`：三榜去重后的 AI 科技应用数量
- `unique_aigc_count`：三榜去重后的 AIGC 数量
- `tag_error_count`：B站标签请求失败数量
- `document_url`：目标飞书文档

## 每日自动运行

可以在 Codex 中创建一个每天 18:30 运行的自动任务，提示词示例：

```text
使用 $track-bilibili-ai-hot 执行每日监测，抓取综合热门、全站排行榜和最新每周必看，
区分“AI 科技应用（重点）”与“AIGC 生成内容”，并写入或刷新配置的飞书文档当天章节。
接口限流或完整性校验失败时不要写入不完整数据。
```

## 目录结构

```text
skills/track-bilibili-ai-hot/
├── SKILL.md
├── agents/
│   └── openai.yaml
└── scripts/
    └── collect_and_write.py
```

## 数据与安全

- 仓库不包含飞书文档地址、登录凭据、浏览器 Cookie 或服务器信息。
- B站匿名指纹 Cookie 只在脚本运行期间保存在内存中。
- 综合热门会随时间和访问会话变化，日报记录的是运行时快照。
- 请勿把飞书 Token、账号凭据或其他私密配置提交到仓库。

## 注意事项

- B站公开接口可能调整或触发限流；脚本会重试并在数据明显不完整时失败。
- 当前 AI 分类采用可审计的关键词、上下文和标签规则，适合稳定日报，不等同于人工内容审核。
- 飞书写入依赖 `lark-cli` 的用户身份和目标文档权限。
