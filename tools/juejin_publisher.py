"""掘金文章发布工具 — gh-spy 分发工具链

用法:
    python juejin_publisher.py report.md --dry-run     # 预览，不实际发布
    python juejin_publisher.py report.md --publish      # 创建草稿并发布
    python juejin_publisher.py report.md --draft        # 只创建草稿，不发布

认证方式:
    需要掘金 cookie 中的 sessionid。
    获取方法：浏览器登录掘金 → F12 → Application → Cookies → sessionid
    配置到 .env 文件的 JUEJIN_SESSION_ID 字段。

API 参考:
    - 创建草稿: POST https://api.juejin.cn/content_api/v1/article_draft/create
    - 更新草稿: POST https://api.juejin.cn/content_api/v1/article_draft/update
    - 发布文章: POST https://api.juejin.cn/content_api/v1/article/publish
"""
import os
import sys
import json
import argparse
import re

import requests
from dotenv import load_dotenv

JUEJIN_API = "https://api.juejin.cn"

# 掘金分类 ID（常用）
CATEGORIES = {
    "后端": "6809637767543259144",
    "前端": "6809635626879549454",
    "Android": "6809635626879549453",
    "iOS": "6809635626879549452",
    "人工智能": "6809637773959178254",
    "开发工具": "6809637771511070734",
    "代码人生": "6809637773959178253",
    "阅读": "6809637773959178255",
}

# 掘金标签 ID（常用）
TAGS = {
    "AI": "6809640445233070098",
    "开源": "6809640445233070094",
    "GitHub": "6809640445233070093",
    "Python": "6809640445233070104",
    "TypeScript": "6809640445233070099",
    "Go": "6809640445233070105",
    "大模型": "6809640445233070110",
    "RAG": "6809640445233070111",
    "Agent": "6809640445233070112",
    "LLM": "6809640445233070113",
}


def parse_frontmatter(md_content):
    """从 markdown 中提取标题、摘要等元数据。"""
    # 标题：取第一个 # 开头的行
    title_match = re.search(r'^#\s+(.+)', md_content, re.MULTILINE)
    title = title_match.group(1).strip() if title_match else "Untitled"

    # 清理标题中的特殊字符
    title = re.sub(r'[#*`\[\]]', '', title).strip()
    if len(title) > 64:
        title = title[:61] + "..."

    # 摘要：取标题后第一个非空、非 > 开头的段落
    lines = md_content.split('\n')
    brief_lines = []
    past_title = False
    for line in lines:
        if line.startswith('#') and not past_title:
            past_title = True
            continue
        if past_title and line.strip() and not line.startswith('>') and not line.startswith('#') and not line.startswith('|') and not line.startswith('-') and not line.startswith('---'):
            brief_lines.append(line.strip())
            if len(''.join(brief_lines)) > 80:
                break

    brief = ''.join(brief_lines)
    if len(brief) < 50:
        brief = brief + " — gh-spy 自动生成的领域全景分析报告。"
    brief = brief[:100]  # 掘金要求 50-100 字

    return title, brief


def guess_category_and_tags(title, content):
    """根据内容猜测分类和标签。"""
    text = (title + " " + content).lower()

    # 分类
    category = CATEGORIES["人工智能"]  # 默认 AI
    if any(kw in text for kw in ["前端", "css", "html", "react", "vue"]):
        category = CATEGORIES["前端"]
    elif any(kw in text for kw in ["工具", "cli", "devops"]):
        category = CATEGORIES["开发工具"]
    elif any(kw in text for kw in ["java", "spring"]) and "ai" not in text:
        category = CATEGORIES["后端"]
    # AI 相关关键词优先级最高
    if any(kw in text for kw in ["ai", "llm", "rag", "agent", "mcp", "embedding", "向量", "模型", "记忆"]):
        category = CATEGORIES["人工智能"]

    # 标签
    tag_ids = []
    for tag_name, tag_id in TAGS.items():
        if tag_name.lower() in text:
            tag_ids.append(tag_id)
    if not tag_ids:
        tag_ids = [TAGS["AI"]]

    return category, tag_ids[:3]  # 最多3个标签


class JuejinPublisher:
    def __init__(self, session_id):
        self.session_id = session_id
        self.headers = {
            "Content-Type": "application/json",
            "Cookie": f"sessionid={session_id}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }

    def create_draft(self, title, brief, content, category_id, tag_ids):
        """创建草稿。"""
        payload = {
            "title": title,
            "brief_content": brief,
            "edit_type": 10,  # Markdown 模式
            "mark_content": content,
            "category_id": category_id,
            "tag_ids": tag_ids,
        }
        resp = requests.post(
            f"{JUEJIN_API}/content_api/v1/article_draft/create",
            headers=self.headers,
            json=payload,
        )
        data = resp.json()
        if data.get("err_no") != 0:
            raise Exception(f"创建草稿失败: {data}")
        draft_id = data["data"]["id"]
        return draft_id

    def publish(self, draft_id):
        """发布草稿。"""
        payload = {
            "draft_id": str(draft_id),
            "sync_to_org": False,
        }
        resp = requests.post(
            f"{JUEJIN_API}/content_api/v1/article/publish",
            headers=self.headers,
            json=payload,
        )
        data = resp.json()
        if data.get("err_no") != 0:
            raise Exception(f"发布失败: {data}")
        article_id = data["data"]["article_id"]
        return article_id


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="掘金文章发布工具")
    parser.add_argument("file", help="Markdown 报告文件路径")
    parser.add_argument("--dry-run", action="store_true", help="预览，不实际发布")
    parser.add_argument("--draft", action="store_true", help="只创建草稿，不发布")
    parser.add_argument("--publish", action="store_true", help="创建草稿并发布")
    parser.add_argument("--title", type=str, help="覆盖标题")
    parser.add_argument("--category", type=str, choices=CATEGORIES.keys(), help="分类")
    parser.add_argument("--tags", type=str, nargs="+", choices=TAGS.keys(), help="标签")
    args = parser.parse_args()

    # 读取文件
    with open(args.file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 提取元数据
    title, brief = parse_frontmatter(content)
    if args.title:
        title = args.title

    category_id, tag_ids = guess_category_and_tags(title, content)
    if args.category:
        category_id = CATEGORIES[args.category]
    if args.tags:
        tag_ids = [TAGS[t] for t in args.tags]

    print(f"标题: {title}")
    print(f"摘要: {brief}")
    print(f"分类 ID: {category_id}")
    print(f"标签 IDs: {tag_ids}")
    print(f"内容长度: {len(content)} 字符")
    print()

    if args.dry_run:
        print("[DRY RUN] 以上为发布参数预览，未实际发布。")
        return

    # 获取认证
    session_id = os.getenv("JUEJIN_SESSION_ID")
    if not session_id:
        print("请在 .env 中配置 JUEJIN_SESSION_ID")
        print("获取方法：浏览器登录掘金 → F12 → Application → Cookies → sessionid")
        sys.exit(1)

    publisher = JuejinPublisher(session_id)

    # 创建草稿
    print("创建草稿...")
    draft_id = publisher.create_draft(title, brief, content, category_id, tag_ids)
    print(f"草稿 ID: {draft_id}")
    print(f"草稿链接: https://juejin.cn/editor/draft/{draft_id}")

    if args.publish:
        print("发布文章...")
        article_id = publisher.publish(draft_id)
        print(f"文章 ID: {article_id}")
        print(f"文章链接: https://juejin.cn/post/{article_id}")
    else:
        print(f"\n草稿已创建，未发布。使用 --publish 参数发布，或在掘金编辑器中手动发布。")


if __name__ == "__main__":
    main()
