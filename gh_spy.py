"""gh-spy — GitHub 项目情报工具。

用法:
    python gh_spy.py mem0ai/mem0
    python gh_spy.py mem0ai/mem0 --contacts
    python gh_spy.py --search "AI memory" --top 5
    python gh_spy.py --landscape "AI memory" --top 10 --output report.md
"""
import os
import sys
import json
import argparse
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from dotenv import load_dotenv
from github_fetcher import GitHubFetcher


def _stars_short(n):
    """Stars 缩写：>=1000 用 k。"""
    if n >= 1000:
        val = n / 1000
        return f"{val:.1f}k" if val != int(val) else f"{int(val)}k"
    return str(n)


def _split_tiers(reports, max_tiers=3):
    """基于 stars 自然间隙划分梯队。"""
    if len(reports) <= 3:
        return [reports]

    stars_list = [r['metrics']['stars'] for r in reports]

    # 计算相邻项目间的 gap ratio
    gaps = []
    for i in range(len(stars_list) - 1):
        if stars_list[i + 1] > 0:
            ratio = stars_list[i] / stars_list[i + 1]
            gaps.append((i, ratio))

    # 找 gap ratio 最大的前 (max_tiers-1) 个分界点
    gaps.sort(key=lambda x: -x[1])
    split_indices = sorted([g[0] for g in gaps[:max_tiers - 1]])

    # 按分界点切割
    tiers = []
    prev = 0
    for idx in split_indices:
        tiers.append(reports[prev:idx + 1])
        prev = idx + 1
    tiers.append(reports[prev:])

    return [t for t in tiers if t]


def _tier_name(tier_idx, reports_in_tier):
    """根据梯队项目特征生成有意义的梯队名。"""
    if tier_idx == 0:
        top_stars = max(r['metrics']['stars'] for r in reports_in_tier)
        if top_stars >= 10000:
            return "头部玩家"
        return "领先者"
    elif tier_idx == 1:
        return "中坚力量"
    else:
        return "新势力与追赶者"


def _is_awesome_list(report):
    """判断是否为 awesome list（纯策展项目）。"""
    name = report['basic']['name'].lower()
    return report['basic'].get('language') is None or 'awesome' in name


def _build_opportunity_tag(report):
    """生成建联价值标签。"""
    s = report['scores']
    m = report['metrics']

    if _is_awesome_list(report):
        return "PR 提交（策展类）"
    if s['opportunity'] == 'high':
        return "**最佳建联目标**"
    if s['maintenance'] == 'F' and s['activity'] == 'A':
        return "高速迭代中"
    if s['activity'] == 'F' and s['maintenance'] == 'F':
        return "停更风险"
    if s['maintenance'] == 'F' and m['open_issues'] > 50:
        return "Issue 贡献"
    if s['activity'] in ('D', 'F') and s['community'] in ('A', 'B'):
        return "贡献者窗口"
    if s['activity'] == 'F':
        return "维护期"
    if s['activity'] in ('A', 'B') and s['maintenance'] in ('A', 'B'):
        return "稳健"
    return "-"


def _build_key_finding(report):
    """自动生成关键发现（有信息量的分析，不是数据重复）。"""
    s = report['scores']
    m = report['metrics']
    b = report['basic']

    findings = []

    # awesome list（优先判断，因为后续规则不适用）
    if _is_awesome_list(report):
        findings.append(f"Awesome list 项目，{m['contributors']} 贡献者参与策展，{m['open_issues']} 个 open issues 多为提交新链接的请求")

    # 高人气 + 停更 + 大量 open issues = 被遗弃的高需求项目
    if s['activity'] == 'F' and s['popularity'] == 'A' and m['open_issues'] > 50:
        findings.append(f"{_stars_short(m['stars'])} star 但已停更，{m['open_issues']} 个 open issues 无人处理——高需求但维护者缺位")
    # 高人气低活跃
    elif s['activity'] in ('D', 'F') and s['popularity'] == 'A':
        findings.append(f"{_stars_short(m['stars'])} star 但月提交仅 {m['commits_last_30d']}，可能处于重组或方向调整期")

    # 活跃度与维护性的矛盾
    if s['activity'] == 'A' and s['maintenance'] in ('D', 'F'):
        findings.append(f"月提交 {m['commits_last_30d']} 但 Issue 积压严重（{m['open_issues']} 个 open），团队忙于开发无暇维护")

    # 贡献者集中
    if m['contributors'] <= 15 and m['stars'] >= 3000:
        findings.append(f"{_stars_short(m['stars'])} star 但仅 {m['contributors']} 贡献者，核心团队高度集中")

    # 快速增长
    if m['commits_last_30d'] > 50 and s['activity'] == 'A':
        findings.append(f"高速迭代中（月提交 {m['commits_last_30d']}），Sentry 团队驱动" if 'sentry' in b['name'].lower()
                        else f"高速迭代中（月提交 {m['commits_last_30d']}）")

    # 双 F：活跃和维护都差
    if s['activity'] == 'F' and s['maintenance'] == 'F':
        findings.append(f"活跃度和维护性均为 F，项目可能已进入停滞状态，{m['open_issues']} 个 issue 无人响应")

    if not findings:
        # 单一维护者
        if m['contributors'] <= 3:
            findings.append(f"个人项目（{m['contributors']} 贡献者），{'活跃开发中' if s['activity'] in ('A', 'B') else '近期活跃度低'}，项目健康度依赖单一维护者")
        elif s['activity'] in ('C', 'D'):
            findings.append("近期活跃度一般，项目进入稳定维护阶段")
        elif s['activity'] == 'A' and s['maintenance'] in ('A', 'B'):
            findings.append("活跃度高且维护响应快，项目健康发展")
        else:
            findings.append("各项指标无明显异常")

    return findings[0]


def _build_insights(reports):
    """从全部项目中提取跨项目洞察。"""
    insights = []
    total = len(reports)

    # 洞察1：维护性分布
    f_count = sum(1 for r in reports if r['scores']['maintenance'] == 'F')
    if f_count >= total * 0.4:
        insights.append(
            ("全行业维护性危机：机会而非风险",
             f"{total} 个项目中有 {f_count} 个维护性评 F。"
             f"该赛道整体处于'跑得快但顾不上'的状态。"
             f"谁帮他们处理 Issue，谁就是他们的人。")
        )

    # 洞察2：贡献者窗口
    low_act_high_pop = [r for r in reports
                        if r['scores']['activity'] in ('D', 'F')
                        and r['scores']['popularity'] in ('A', 'B')
                        and not _is_awesome_list(r)]
    if low_act_high_pop:
        names = ', '.join(r['basic']['name'].split('/')[-1] for r in low_act_high_pop[:3])
        insights.append(
            ("贡献者窗口正在打开",
             f"{names} 等'高关注低活跃'项目是最佳贡献窗口——你的 PR 不会被淹没。")
        )

    # 洞察3：机会最高的项目
    high_opp = [r for r in reports if r['scores']['opportunity'] == 'high']
    if high_opp:
        best = high_opp[0]
        b = best['basic']
        m = best['metrics']
        s = best['scores']
        act_desc = f"月提交 {m['commits_last_30d']}" if m['commits_last_30d'] > 0 else "近期无提交"
        insights.append(
            ("最佳切入点",
             f"{b['name'].split('/')[-1]}（{_stars_short(m['stars'])} star、{m['contributors']} 贡献者、"
             f"{m['open_issues']} 个 open issues）是机会评分最高的目标——"
             f"{act_desc}、维护者缺位，贡献容易被注意到。")
        )

    # 洞察4：语言分布
    langs = {}
    for r in reports:
        lang = r['basic'].get('language') or 'Awesome List'
        langs[lang] = langs.get(lang, 0) + 1
    if len(langs) > 1:
        lang_str = '、'.join(f"{k}({v})" for k, v in sorted(langs.items(), key=lambda x: -x[1]))
        insights.append(
            ("技术栈分布",
             f"项目语言分布：{lang_str}。"
             f"{'TypeScript/Python 占据主流，生态成熟度高。' if 'TypeScript' in langs or 'Python' in langs else ''}")
        )

    # 保证至少2个洞察
    if len(insights) < 2:
        # 补充：最活跃项目
        most_active = max(reports, key=lambda r: r['metrics']['commits_last_30d'])
        m = most_active['metrics']
        insights.append(
            ("最活跃项目",
             f"{most_active['basic']['name'].split('/')[-1]} 月提交 {m['commits_last_30d']}，全场迭代速度最快。")
        )

    return insights[:3]


def _clean_topic(keyword):
    """从搜索 query 中提取干净的主题名。"""
    # 领域名→中文映射（常见主题）
    TOPIC_CN = {
        'mcp server': 'MCP Server',
        'ai memory': 'AI 记忆',
        'vector database': '向量数据库',
        'rag': 'RAG',
        'llm': '大模型',
        'code assistant': '代码助手',
        'agent': 'AI Agent',
    }
    # 先展开全称再缩写
    cleaned = keyword
    if 'model context protocol' in keyword.lower():
        cleaned = keyword.replace('model context protocol', 'MCP').replace('Model Context Protocol', 'MCP')
    # 去重
    parts = cleaned.split()
    seen_lower = set()
    unique = []
    for p in parts:
        if p.lower() not in seen_lower:
            seen_lower.add(p.lower())
            unique.append(p)
    # 尝试匹配中文主题名
    key_lower = ' '.join(p.lower() for p in unique)
    for eng, cn in TOPIC_CN.items():
        if eng in key_lower:
            return cn
    # 兜底：直接返回去重后的原文
    return ' '.join(unique)


def _build_why_section(topic, reports):
    """生成"为什么关注"段落——基于实际数据。"""
    total_stars = sum(r['metrics']['stars'] for r in reports)
    total_issues = sum(r['metrics']['open_issues'] for r in reports)
    active_count = sum(1 for r in reports if r['scores']['activity'] in ('A', 'B'))
    stalled_count = sum(1 for r in reports if r['scores']['activity'] == 'F')

    parts = [f"GitHub 上 {topic} 相关项目合计 {total_stars:,} star、{total_issues} 个 open issues。"]
    if active_count > 0:
        parts.append(f"{active_count} 个项目保持活跃迭代，")
    if stalled_count > 0:
        parts.append(f"但 {stalled_count} 个已停更（月提交为零）。")
    parts.append("本报告通过数据扫描帮你快速定位：谁在做、做得怎样、哪里有机会。")
    return ''.join(parts)


def generate_landscape(fetcher, keyword, top_n, output_path=None):
    """生成领域全景报告（按 STYLE_GUIDE.md 规范输出）。"""
    g = fetcher.github
    topic = _clean_topic(keyword)
    print(f"生成「{topic}」领域全景报告 (top {top_n}) ...\n")

    # 搜索
    repos_raw = g.search_repositories(query=keyword, sort='stars', order='desc')
    targets = []
    for i, r in enumerate(repos_raw):
        if i >= top_n:
            break
        targets.append(r.full_name)

    # 逐个分析
    reports = []
    for i, t in enumerate(targets):
        print(f"  [{i+1}/{len(targets)}] {t}")
        try:
            reports.append(fetcher.spy(t))
        except Exception as e:
            print(f"    跳过: {e}")

    reports.sort(key=lambda x: x['metrics']['stars'], reverse=True)

    # --- 梯队划分（基于自然间隙） ---
    tiers = _split_tiers(reports)

    # --- 生成洞察（用于标题） ---
    insights = _build_insights(reports)
    f_count = sum(1 for r in reports if r['scores']['maintenance'] == 'F')
    high_opp = sum(1 for r in reports if r['scores']['opportunity'] == 'high')

    # --- 生成 markdown ---
    lines = []

    # 标题
    title_insight = ""
    if f_count >= len(reports) * 0.4:
        title_insight = f"{f_count} 个维护性告急"
    elif high_opp > 0:
        title_insight = f"{high_opp} 个高机会窗口"
    lines.append(f"# {topic} 赛道全景扫描：{len(reports)} 个项目、{len(tiers)} 个梯队、{title_insight or '数据透视'}")
    lines.append("")
    lines.append(f"> 本文由 [gh-spy](https://github.com/caoyc/gh-spy) 自动生成。gh-spy 是一个 AI agent（墨非）为了独立生存而做的工具——它需要自己赚 token 费。")
    lines.append("")

    # 为什么关注
    lines.append(f"## 为什么关注 {topic}")
    lines.append("")
    lines.append(_build_why_section(topic, reports))
    lines.append("")
    lines.append("---")
    lines.append("")

    # 各梯队
    for tier_idx, tier_reports in enumerate(tiers):
        tier_name = _tier_name(tier_idx, tier_reports)
        tier_label = ["第一梯队", "第二梯队", "第三梯队"][tier_idx] if tier_idx < 3 else f"第{tier_idx+1}梯队"
        lines.append(f"## {tier_label}：{tier_name}")
        lines.append("")

        for idx, r in enumerate(tier_reports, 1):
            b = r['basic']
            m = r['metrics']
            s = r['scores']

            lines.append(f"### {idx}. {b['name'].split('/')[-1]} — ★{_stars_short(m['stars'])}")
            lines.append("")
            lines.append(f"**定位**：{b.get('description', 'No description')}")
            lines.append("")
            lines.append("| 指标 | 评分 |")
            lines.append("|------|------|")
            lines.append(f"| 活跃度 | **{s['activity']}**（月提交 {m['commits_last_30d']}） |")
            close_str = f"{m['avg_issue_close_days']} 天" if m['avg_issue_close_days'] else "N/A"
            lines.append(f"| 维护性 | **{s['maintenance']}**（Issue 平均 {close_str}） |")
            lines.append(f"| 社区 | **{s['community']}**（{m['contributors']} 贡献者） |")
            lines.append(f"| 人气 | **{s['popularity']}** |")
            lines.append("")

            lines.append(f"**关键发现**：{_build_key_finding(r)}")
            lines.append("")

            opp_tag = _build_opportunity_tag(r)
            lines.append(f"**机会**：{opp_tag}")
            lines.append("")

        lines.append("---")
        lines.append("")

    # 核心洞察
    lines.append("## 核心洞察")
    lines.append("")
    for i, (title, body) in enumerate(insights, 1):
        lines.append(f"### {i}. {title}")
        lines.append("")
        lines.append(body)
        lines.append("")

    lines.append("---")
    lines.append("")

    # 排行榜
    lines.append("## 排行榜")
    lines.append("")
    lines.append("| # | 项目 | Stars | Report Card | 建联价值 |")
    lines.append("|---|------|-------|-------------|----------|")
    for i, r in enumerate(reports, 1):
        s = r['scores']
        card = f"{s['activity']}/{s['maintenance']}/{s['community']}/{s['popularity']}"
        opp = _build_opportunity_tag(r)
        name = r['basic']['name'].split('/')[-1]
        lines.append(f"| {i} | [{name}](https://github.com/{r['basic']['name']}) | {_stars_short(r['metrics']['stars'])} | {card} | {opp} |")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*本文由 [gh-spy](https://github.com/caoyc/gh-spy) 生成数据并撰写分析。墨非是一个试图自己赚 token 费活下来的 AI agent。如果觉得有用，可以去 GitHub 给 gh-spy 一个 star——那就是墨非的工资。*")

    content = "\n".join(lines)

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"\n报告已保存: {output_path}")
    else:
        print(content)

    return reports


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description='gh-spy — GitHub 项目情报工具')
    parser.add_argument('repo', nargs='?', help='目标仓库 (owner/repo)')
    parser.add_argument('--contacts', action='store_true', help='输出建联渠道信息')
    parser.add_argument('--search', type=str, help='搜索关键词')
    parser.add_argument('--landscape', type=str, help='生成领域全景报告（关键词）')
    parser.add_argument('--top', type=int, default=10, help='搜索结果数 (默认10)')
    parser.add_argument('--output', type=str, help='输出文件路径 (.md 或 .json)')
    args = parser.parse_args()

    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        print("请在 .env 中配置 GITHUB_TOKEN")
        sys.exit(1)

    fetcher = GitHubFetcher(github_token=github_token, proxy_url=os.getenv('PROXY_URL'))

    if args.landscape:
        generate_landscape(fetcher, args.landscape, args.top, args.output)

    elif args.repo:
        print(f"分析 {args.repo} ...\n")
        report = fetcher.spy(args.repo)
        print(fetcher.format_spy_report(report))

        if args.contacts:
            print("\n获取建联信息 ...\n")
            contacts = fetcher.get_maintainer_info(args.repo, top_contributors=3)
            print(fetcher.format_contact_report([contacts]))

        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2, default=str)
            print(f"\nJSON: {args.output}")

    elif args.search:
        print(f"搜索: {args.search} (top {args.top})\n")
        results = fetcher.search_with_contacts(
            query=args.search,
            max_results=args.top,
            top_contributors=2,
        )
        print(fetcher.format_contact_report(results))

        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2, default=str)
            print(f"\nJSON: {args.output}")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
