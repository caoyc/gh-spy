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


def generate_landscape(fetcher, keyword, top_n, output_path=None):
    """生成领域全景报告（可发布的 markdown 文章）。"""
    g = fetcher.github
    print(f"生成「{keyword}」领域全景报告 (top {top_n}) ...\n")

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

    # 生成 markdown
    lines = []
    lines.append(f"# 「{keyword}」领域全景扫描")
    lines.append(f"")
    lines.append(f"> 由 [gh-spy](https://github.com/caoyc/gh-spy) 自动生成 · {datetime.now().strftime('%Y-%m-%d')}")
    lines.append(f">")
    lines.append(f"> gh-spy 由一个自力更生的 AI agent（墨非）构建，正在努力赚自己的 token 费。")
    lines.append(f"")
    lines.append(f"共分析 {len(reports)} 个项目，按 star 倒序排列。")
    lines.append(f"")
    lines.append(f"## 排行榜")
    lines.append(f"")
    lines.append(f"| # | 项目 | Stars | Report Card | 亮点 |")
    lines.append(f"|---|------|-------|-------------|------|")
    for i, r in enumerate(reports, 1):
        s = r['scores']
        card = f"Act:{s['activity']} Maint:{s['maintenance']} Comm:{s['community']}"
        highlight = []
        if s['maintenance'] == 'F':
            highlight.append('Issue积压')
        if s['opportunity'] == 'high':
            highlight.append('机会大')
        if r['metrics']['commits_last_30d'] > 50:
            highlight.append('高速迭代')
        lines.append(f"| {i} | [{r['basic']['name']}](https://github.com/{r['basic']['name']}) | {r['metrics']['stars']:,} | {card} | {', '.join(highlight) or '-'} |")

    lines.append(f"")
    lines.append(f"## 详细分析")
    lines.append(f"")
    for r in reports:
        lines.append(fetcher.format_spy_report(r))
        lines.append("")

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
