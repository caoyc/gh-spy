"""gh-spy 实战演示：用零件库拼出的产品。"""
import os, sys, json
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
from github_fetcher import GitHubFetcher

load_dotenv()
fetcher = GitHubFetcher(github_token=os.getenv('GITHUB_TOKEN'))

# 目标：国内+国际各挑几个项目，出情报
targets = [
    "hiyouga/LlamaFactory",     # 中国AI大项目，994个open issues
    "mem0ai/mem0",              # AI记忆赛道头部
    "Dataojitori/nocturne_memory",  # 小但精准的AI记忆项目
]

print("gh-spy — GitHub 项目情报工具")
print(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

reports = []
for target in targets:
    print(f"  正在分析 {target}...")
    try:
        report = fetcher.spy(target)
        reports.append(report)
        print(fetcher.format_spy_report(report))
    except Exception as e:
        print(f"  分析失败: {e}\n")

# 保存 JSON
output_dir = os.path.join(os.path.dirname(__file__), 'output')
os.makedirs(output_dir, exist_ok=True)
ts = datetime.now().strftime('%Y%m%d_%H%M%S')
json_path = os.path.join(output_dir, f'spy_report_{ts}.json')
with open(json_path, 'w', encoding='utf-8') as f:
    json.dump(reports, f, ensure_ascii=False, indent=2, default=str)
print(f"\nJSON: {json_path}")
