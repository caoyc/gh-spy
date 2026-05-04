"""gh-spy — GitHub 项目情报工具。

用法:
    python gh_spy.py mem0ai/mem0
    python gh_spy.py mem0ai/mem0 --contacts
    python gh_spy.py --search "AI memory" --top 5
"""
import os
import sys
import json
import argparse
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from dotenv import load_dotenv
from github_fetcher import GitHubFetcher


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description='gh-spy — GitHub 项目情报工具')
    parser.add_argument('repo', nargs='?', help='目标仓库 (owner/repo)')
    parser.add_argument('--contacts', action='store_true', help='输出建联渠道信息')
    parser.add_argument('--search', type=str, help='搜索关键词')
    parser.add_argument('--top', type=int, default=10, help='搜索结果数 (默认10)')
    parser.add_argument('--json', type=str, help='JSON 输出路径')
    args = parser.parse_args()

    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        print("请在 .env 中配置 GITHUB_TOKEN")
        sys.exit(1)

    fetcher = GitHubFetcher(github_token=github_token, proxy_url=os.getenv('PROXY_URL'))

    if args.repo:
        # 单项目分析
        print(f"分析 {args.repo} ...\n")
        report = fetcher.spy(args.repo)
        print(fetcher.format_spy_report(report))

        if args.contacts:
            print("\n获取建联信息 ...\n")
            contacts = fetcher.get_maintainer_info(args.repo, top_contributors=3)
            print(fetcher.format_contact_report([contacts]))

        if args.json:
            with open(args.json, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2, default=str)
            print(f"\nJSON: {args.json}")

    elif args.search:
        # 搜索模式
        print(f"搜索: {args.search} (top {args.top})\n")
        results = fetcher.search_with_contacts(
            query=args.search,
            max_results=args.top,
            top_contributors=2,
        )
        print(fetcher.format_contact_report(results))

        if args.json:
            with open(args.json, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2, default=str)
            print(f"\nJSON: {args.json}")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
