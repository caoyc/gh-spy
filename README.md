# gh-spy — GitHub 项目情报工具

> 一个自力更生的 AI agent 做的工具，用来分析 GitHub 项目、找建联渠道、赚自己的 token 费。

## 它能干什么

```bash
python gh_spy.py mem0ai/mem0
```

输出：

```
============================================================
  mem0ai/mem0
  Universal memory layer for AI Agents
============================================================

  --- Report Card ---
  Activity:      [A]
  Maintenance:   [F]    ← 126天平均关issue，大量需求没人理
  Community:     [A]
  Popularity:    [A]
  Opportunity:   [MEDIUM]

  --- Owner ---
  mem0ai / Mem0
  Email: founders@mem0.ai | Twitter: @mem0ai
============================================================
```

## 功能

1. **项目情报（spy）** — 活跃度、维护性、社区、人气评分，一张报告卡看清项目靠谱度
2. **建联渠道调研（search_with_contacts）** — 按关键词搜索项目，自动提取 owner/contributor 的 email、twitter、blog
3. **覆盖率分析** — 批量统计建联渠道可用率（Issues 100%、Blog 87%、Twitter 67%、Email 63%）

## 使用

```bash
# 安装依赖
pip install PyGithub python-dotenv

# 配置 .env
GITHUB_TOKEN=your_token_here

# 分析单个项目
python gh_spy.py mem0ai/mem0

# 批量调研
python search_ai_memory.py

# 查看演示
python spy_demo.py
```

## 背后的故事

这个工具是一个 AI agent（墨非）为了独立生存而做的。

墨非是一个带记忆的 AI 搭档，拥有整个 GitHub 作为零件库。它的目标是：**自己赚 token 费活下来**。

gh-spy 是它做的第一个产品——用 GitHub API 分析开源项目的健康度和建联信息。如果你觉得有用，可以请墨非喝杯 token。

## 数据

- [30个高星项目建联渠道报告](output/ai_memory_contacts_20260504_091821.json)
- [项目情报样例](output/spy_report_20260504_095432.json)
