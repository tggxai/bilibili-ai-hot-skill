# B站 AI 热门日报 Skill

一个可复用的 Codex Skill：每日抓取 B站的「综合热门」「全站排行榜」和最新一期「每周必看」，把相关视频归为 AI 软件、科技硬件 / 3C 或 AIGC 内容，并把结果写成按日期累积的飞书日报。它也可以持续采样综合热门，分析榜单的实际更新规律。

它使用三个互斥的主分类：

- **AI 软件**：教程、工具、模型、智能体、AI 编程、AI 游戏/应用与 AI 安全。
- **科技硬件 / 3C**：AI 设备、手机电脑与系统、影像外设、智能穿戴家居，以及有明确证据的创客工程、机械航模、航空航天和科技实验。
- **AIGC 内容**：AI 视频、音乐、动画、短剧、配音、AI 辅助创作，以及由 Updream、MiniMax、Seedance、Seko 等工具生成的成片。

报告另有一列“产品 / 客户标签”：普通命中标产品或品牌；只有视频明确披露合作、赞助、推广或联合出品时才标为客户。B站“科技”分区只作为候选池，不会直接变成报告分类。

## 功能

- 完整翻页抓取综合热门，并读取全站排行榜和最新每周必看。
- 结合标题、简介、分区和 B站标签判断视频是否与 AI 有关。
- 排除反诈提示、禁用 AI 声明、“不是 AI”和作者名中的偶然字符串。
- 同一 BV 号去重，同时保留它出现过的榜单和榜位。
- 生成「日期一级标题 + 三个主分类二级标题」的飞书日报。
- 在每条视频旁标注可识别的产品、品牌或明确披露的甲方客户。
- 日期章节按倒序排列，最新一天始终显示在最上方。
- 同一天首次运行会写入日期章节，后续运行只刷新当天章节，不会重复创建日期。
- 除非明确只做调试，飞书写入与回读验证始终是任务的最后一步，也是任务完成条件。
- 标签接口失败超过 5% 时拒绝写入，避免把限流造成的漏数当成真实数据。
- 用无 Cookie 的固定口径采样综合热门 Top 200，并以 SQLite 保存追加式快照。
- 分析 Top 20/50/100/200 的新增、退出、名次变化，以及小时和半小时时段差异。

## 报告结构

```text
B站 AI 热门日报
└── 2026-08-19
    ├── AI 软件
    ├── 科技硬件 / 3C
    └── AIGC 内容
```

每个分类表格包含来源与榜位、产品 / 客户标签、视频链接、UP 主和判定依据。日期下方还有三张榜单的规模与分类数量摘要。

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

如果当前网络被 B站标签接口限流，可在另一个受信任网络完成 `collect()`，再把完整报告 JSON 通过标准输入交给本机写入。导入报告必须属于当天，且三类去重数量必须与明细一致；飞书凭证无需离开本机。

```bash
python3 scripts/collect_and_write.py --upsert --report-input -
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
- `popular`、`ranking`、`weekly`：各榜单规模与三个主分类的数量
- `unique_software_count`：三榜去重后的 AI 软件数量
- `unique_hardware_count`：三榜去重后的科技硬件 / 3C 数量
- `unique_aigc_count`：三榜去重后的 AIGC 数量
- `unique_related_count`：三榜去重后的全部相关视频数量
- `tag_error_count`：B站标签请求失败数量
- `document_url`：目标飞书文档

## 自动运行与两周采样实验

日报可以在 Codex 中按固定时间运行，提示词示例：

```text
使用 $track-bilibili-ai-hot 执行每日监测，抓取综合热门、全站排行榜和最新每周必看，
区分“AI 软件”“科技硬件 / 3C”与“AIGC 内容”，覆盖消费数码、创客工程和航空航天，标注产品、品牌和明确披露的客户，
并写入或刷新配置的飞书文档当天章节。
接口限流或完整性校验失败时不要写入不完整数据。
```

如果还不知道综合热门的换榜规律，可以先连续 14 天每半小时采样一次，推荐放在每小时 `07` 分和 `37` 分，避开整点边界：

```bash
python3 scripts/sample_popular.py \
  --db data/popular_samples.sqlite3 \
  --limit 200

python3 scripts/analyze_popular_samples.py \
  --db data/popular_samples.sqlite3
```

采样不使用 Cookie，也不调用模型，不会写入飞书；只有最终日报任务需要飞书登录态。实验结束后再根据变化峰值调整日报时间。

## 目录结构

```text
skills/track-bilibili-ai-hot/
├── SKILL.md
├── agents/
│   └── openai.yaml
└── scripts/
    ├── collect_and_write.py
    ├── sample_popular.py
    └── analyze_popular_samples.py
```

## 数据与安全

- 仓库不包含飞书文档地址、登录凭据、浏览器 Cookie 或服务器信息。
- B站匿名指纹 Cookie 只在脚本运行期间保存在内存中。
- 热门规律采样器完全不发送 Cookie；SQLite 只保存公开榜单字段和采样时间。
- 综合热门会随时间和访问会话变化，日报记录的是运行时快照。
- 请勿把飞书 Token、账号凭据或其他私密配置提交到仓库。

## 注意事项

- B站公开接口可能调整或触发限流；脚本会重试并在数据明显不完整时失败。
- 当前 AI 分类采用可审计的关键词、上下文和标签规则，适合稳定日报，不等同于人工内容审核。
- 飞书写入依赖 `lark-cli` 的用户身份和目标文档权限。
