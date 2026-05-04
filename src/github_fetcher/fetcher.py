import os
import sys
from typing import List, Dict, Optional
from github import Github, Auth

# 添加 llm_client 模块路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
_llm_client_path = os.path.join(project_root, 'llm_client', 'src')
if _llm_client_path not in sys.path:
    sys.path.insert(0, _llm_client_path)

from llm_client.client import LLMClient


class GitHubFetcher:
    """GitHub 项目获取器"""

    def __init__(self, github_token: Optional[str] = None, proxy_url: Optional[str] = None,
                 openai_api_key: Optional[str] = None, openai_base_url: Optional[str] = None):
        """
        初始化

        Args:
            github_token: GitHub token（可选）
            proxy_url: 代理地址（可选，如 http://127.0.0.1:7890）
            openai_api_key: OpenAI API key
            openai_base_url: OpenAI API base url
        """
        # 设置代理
        if proxy_url:
            os.environ['HTTP_PROXY'] = proxy_url
            os.environ['HTTPS_PROXY'] = proxy_url

        # GitHub 认证
        auth = Auth.Token(github_token) if github_token else None
        self.github = Github(auth=auth)

        # LLM 客户端
        self.llm_client = None
        if openai_api_key:
            self.llm_client = LLMClient(
                api_key=openai_api_key,
                base_url=openai_base_url or "https://api.openai.com/v1",
                model="deepseek-chat"
            )

    def parse_requirement(self, requirement: str) -> Dict:
        """
        LLM 解析用户需求

        Args:
            requirement: 用户需求描述

        Returns:
            解析结果（关键词、搜索语句、筛选条件）
        """
        if not self.llm_client:
            return {
                'keywords': requirement.split(),
                'search_query': requirement,
                'filters': {}
            }

        prompt = f"""分析以下需求，提取信息：

需求：{requirement}

请以 JSON 格式返回：
{{
  "keywords": ["关键词1", "关键词2"],
  "search_query": "GitHub 搜索语句",
  "filters": {{
    "language": "python/java等（可选）",
    "license": "MIT/Apache等（可选）",
    "min_stars": 数字（可选）
  }}
}}"""

        import json
        response = self.llm_client.chat(prompt)
        return json.loads(response)

    def search_repos(self, query: str, max_results: int = 10,
                   language: Optional[str] = None, min_stars: Optional[int] = None) -> List[Dict]:
        """
        搜索 GitHub 仓库

        Args:
            query: 搜索语句
            max_results: 最大结果数
            language: 编程语言筛选
            min_stars: 最小 stars 数

        Returns:
            仓库信息列表
        """
        # 构建完整搜索语句
        full_query = query
        if language:
            full_query += f" language:{language}"
        if min_stars:
            full_query += f" stars:>{min_stars}"

        repos = []
        result = self.github.search_repositories(query=full_query, sort='stars', order='desc')

        for i, repo in enumerate(result):
            if i >= max_results:
                break
            repos.append({
                'name': repo.full_name,
                'description': repo.description or "",
                'stars': repo.stargazers_count,
                'forks': repo.forks_count,
                'language': repo.language,
                'updated_at': repo.updated_at,
                'url': repo.html_url
            })

        return repos

    def analyze_fit(self, requirement: str, repo: Dict) -> float:
        """
        LLM 分析仓库与需求的契合度

        Args:
            requirement: 用户需求
            repo: 仓库信息

        Returns:
            契合度分数 (0-1)
        """
        if not self.llm_client:
            return 0.5

        repo_info = f"""
仓库名称：{repo['name']}
描述：{repo['description']}
Stars：{repo['stars']}
语言：{repo['language']}
"""

        prompt = f"""评估以下 GitHub 仓库与用户需求的契合度。

用户需求：{requirement}

仓库信息：
{repo_info}

请评估契合度，返回 0 到 1 之间的分数，1 表示完全契合。
只需返回数字，例如：0.85"""

        try:
            response = self.llm_client.chat(prompt)
            score = float(response.strip())
            return max(0, min(1, score))
        except:
            return 0.5

    def fetch_repos(self, requirement: str, max_results: int = 10) -> List[Dict]:
        """
        完整流程：解析需求 -> 搜索 -> 分析 -> 排序

        Args:
            requirement: 用户需求
            max_results: 返回结果数

        Returns:
            排序后的推荐列表
        """
        # 1. 解析需求
        parsed = self.parse_requirement(requirement)

        # 2. 搜索仓库
        repos = self.search_repos(
            query=parsed['search_query'],
            max_results=max_results * 2,  # 多搜索一些用于分析
            language=parsed['filters'].get('language'),
            min_stars=parsed['filters'].get('min_stars')
        )

        # 3. 分析契合度
        for repo in repos:
            repo['fit_score'] = self.analyze_fit(requirement, repo)

        # 4. 排序
        repos.sort(key=lambda x: x['fit_score'], reverse=True)

        return repos[:max_results]

    def format_results(self, repos: List[Dict]) -> str:
        """格式化输出结果"""
        output = []
        for i, repo in enumerate(repos, 1):
            output.append(f"\n{i}. {repo['name']}")
            output.append(f"   契合度: {repo['fit_score']:.2f}")
            output.append(f"   Stars: {repo['stars']}")
            output.append(f"   描述: {repo['description']}")
            output.append(f"   URL: {repo['url']}")
        return "\n".join(output)

    def get_maintainer_info(self, repo_name: str, top_contributors: int = 3) -> Dict:
        """
        获取仓库维护者信息和建联渠道。

        Args:
            repo_name: 仓库名称（格式：owner/repo）
            top_contributors: 获取前 N 个贡献者

        Returns:
            {
                'repo': repo基本信息,
                'owner': 仓库拥有者信息 + 建联渠道,
                'contributors': [前N贡献者信息 + 建联渠道],
                'channels': 仓库级建联渠道（issues/discussions等）
            }
        """
        repo = self.github.get_repo(repo_name)

        # --- 仓库基本信息 ---
        repo_info = {
            'full_name': repo.full_name,
            'description': repo.description,
            'stars': repo.stargazers_count,
            'forks': repo.forks_count,
            'language': repo.language,
            'topics': repo.topics,
            'homepage': repo.homepage,
            'updated_at': repo.updated_at,
            'created_at': repo.created_at,
        }

        # --- Owner 信息 ---
        owner = repo.owner
        owner_info = self._extract_user_contact(owner)

        # --- Top Contributors ---
        contributors_info = []
        try:
            contributors = repo.get_contributors()
            count = 0
            for c in contributors:
                if count >= top_contributors:
                    break
                if c.login == owner.login:
                    continue
                contributors_info.append(self._extract_user_contact(c))
                count += 1
        except Exception:
            pass

        # --- 仓库级建联渠道 ---
        channels = {
            'issues_enabled': repo.has_issues,
            'discussions_enabled': getattr(repo, 'has_discussions', None),
            'wiki_enabled': repo.has_wiki,
            'homepage': repo.homepage,
            'open_issues_count': repo.open_issues_count,
        }

        return {
            'repo': repo_info,
            'owner': owner_info,
            'contributors': contributors_info,
            'channels': channels,
        }

    def _extract_user_contact(self, user) -> Dict:
        """从 GitHub User 对象提取联系信息。"""
        return {
            'login': user.login,
            'name': user.name,
            'email': user.email,
            'blog': user.blog if user.blog else None,
            'twitter': user.twitter_username,
            'company': user.company,
            'location': user.location,
            'bio': user.bio,
            'github_url': user.html_url,
            'public_repos': user.public_repos,
            'followers': user.followers,
        }

    def search_with_contacts(self, query: str, max_results: int = 10,
                             language: Optional[str] = None,
                             min_stars: Optional[int] = None,
                             top_contributors: int = 2) -> List[Dict]:
        """
        搜索仓库并附带建联信息。按 star 倒序。

        Args:
            query: 搜索语句
            max_results: 最大结果数
            language: 编程语言筛选
            min_stars: 最小 stars 数
            top_contributors: 每个仓库获取的贡献者数

        Returns:
            仓库列表，每个包含 repo 基本信息 + 建联信息
        """
        full_query = query
        if language:
            full_query += f" language:{language}"
        if min_stars:
            full_query += f" stars:>{min_stars}"

        results = []
        repos = self.github.search_repositories(query=full_query, sort='stars', order='desc')

        for i, repo in enumerate(repos):
            if i >= max_results:
                break
            try:
                info = self.get_maintainer_info(repo.full_name, top_contributors=top_contributors)
                results.append(info)
                print(f"  [{i+1}/{max_results}] {repo.full_name} ★{repo.stargazers_count}")
            except Exception as e:
                print(f"  [{i+1}/{max_results}] {repo.full_name} - 获取失败: {e}")
                results.append({
                    'repo': {
                        'full_name': repo.full_name,
                        'description': repo.description,
                        'stars': repo.stargazers_count,
                    },
                    'owner': {'login': repo.owner.login, 'github_url': repo.owner.html_url},
                    'contributors': [],
                    'channels': {},
                })

        return results

    def format_contact_report(self, results: List[Dict]) -> str:
        """格式化建联报告。"""
        lines = []
        for i, item in enumerate(results, 1):
            repo = item['repo']
            owner = item['owner']
            contributors = item['contributors']
            channels = item['channels']

            lines.append(f"\n{'='*70}")
            lines.append(f"{i}. {repo.get('full_name', 'N/A')}  ★{repo.get('stars', '?')}")
            lines.append(f"   {repo.get('description', 'No description')}")
            lines.append(f"   Topics: {', '.join(repo.get('topics', []))}")
            lines.append(f"   Language: {repo.get('language', 'N/A')}")
            if repo.get('homepage'):
                lines.append(f"   Homepage: {repo['homepage']}")

            # Owner 联系方式
            lines.append(f"\n   [Owner] {owner.get('login', 'N/A')}")
            if owner.get('name'):
                lines.append(f"     Name: {owner['name']}")
            if owner.get('email'):
                lines.append(f"     Email: {owner['email']}")
            if owner.get('blog'):
                lines.append(f"     Blog: {owner['blog']}")
            if owner.get('twitter'):
                lines.append(f"     Twitter: @{owner['twitter']}")
            if owner.get('company'):
                lines.append(f"     Company: {owner['company']}")
            if owner.get('location'):
                lines.append(f"     Location: {owner['location']}")
            if owner.get('bio'):
                lines.append(f"     Bio: {owner['bio'][:100]}")
            lines.append(f"     GitHub: {owner.get('github_url', 'N/A')}")
            lines.append(f"     Followers: {owner.get('followers', '?')} | Repos: {owner.get('public_repos', '?')}")

            # 贡献者
            for j, c in enumerate(contributors, 1):
                lines.append(f"\n   [Contributor {j}] {c.get('login', 'N/A')}")
                if c.get('email'):
                    lines.append(f"     Email: {c['email']}")
                if c.get('blog'):
                    lines.append(f"     Blog: {c['blog']}")
                if c.get('twitter'):
                    lines.append(f"     Twitter: @{c['twitter']}")

            # 仓库级渠道
            lines.append(f"\n   [仓库渠道]")
            ch_parts = []
            if channels.get('issues_enabled'):
                ch_parts.append(f"Issues({channels.get('open_issues_count', '?')} open)")
            if channels.get('discussions_enabled'):
                ch_parts.append("Discussions")
            if channels.get('wiki_enabled'):
                ch_parts.append("Wiki")
            if channels.get('homepage'):
                ch_parts.append("Homepage")
            lines.append(f"     {' | '.join(ch_parts) if ch_parts else '无特殊渠道'}")

        return "\n".join(lines)

    def download_repo(self, repo_name: str, output_dir: str = None) -> str:
        """
        下载 GitHub 仓库

        Args:
            repo_name: 仓库名称（格式：owner/repo）
            output_dir: 输出目录，默认为 github 目录

        Returns:
            下载路径
        """
        import subprocess

        if output_dir is None:
            # 默认下载到项目根目录下的 github 目录
            project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
            output_dir = os.path.join(project_root, 'github')

        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)

        # 构建克隆 URL（使用 HTTPS）
        clone_url = f"https://github.com/{repo_name}.git"
        target_path = os.path.join(output_dir, repo_name.replace('/', '_'))

        print(f"正在下载 {repo_name}...")
        print(f"目标路径: {target_path}")

        # 检查是否已存在
        if os.path.exists(target_path):
            print(f"仓库已存在于 {target_path}")
            return target_path

        # 执行 git clone
        try:
            subprocess.run(['git', 'clone', clone_url, target_path], check=True, capture_output=True)
            print(f"下载完成: {target_path}")
            return target_path
        except subprocess.CalledProcessError as e:
            print(f"下载失败: {e.stderr.decode('utf-8', errors='ignore')}")
            raise
        except FileNotFoundError:
            print("错误: 未找到 git 命令，请先安装 Git")
            raise


    def spy(self, repo_name: str) -> Dict:
        """
        项目情报分析：健康度、活跃度、社区、机会识别。

        Args:
            repo_name: 仓库名（owner/repo）

        Returns:
            情报报告字典
        """
        from datetime import datetime, timezone, timedelta

        repo = self.github.get_repo(repo_name)
        now = datetime.now(timezone.utc)

        # --- 基础指标 ---
        created = repo.created_at
        age_days = (now - created).days
        stars = repo.stargazers_count
        forks = repo.forks_count
        watchers = repo.subscribers_count
        open_issues = repo.open_issues_count
        size_kb = repo.size

        # --- 活跃度：最近30天提交数 ---
        recent_commits = 0
        try:
            since = now - timedelta(days=30)
            for c in repo.get_commits(since=since):
                recent_commits += 1
        except Exception:
            pass

        # --- Issue 响应速度：最近5个closed issue ---
        issue_close_days = []
        try:
            closed = repo.get_issues(state='closed', sort='updated', direction='desc')
            count = 0
            for iss in closed:
                if count >= 5:
                    break
                if iss.pull_request:
                    continue
                delta = (iss.closed_at - iss.created_at).total_seconds() / 86400
                issue_close_days.append(round(delta, 1))
                count += 1
        except Exception:
            pass

        avg_close_days = round(sum(issue_close_days) / len(issue_close_days), 1) if issue_close_days else None

        # --- 贡献者分布 ---
        contributor_count = 0
        try:
            for c in repo.get_contributors():
                contributor_count += 1
        except Exception:
            pass

        # --- Release 频率 ---
        release_count = 0
        last_release = None
        try:
            for r in repo.get_releases():
                release_count += 1
                if last_release is None:
                    last_release = r.published_at
                if release_count >= 10:
                    break
        except Exception:
            pass

        # --- 评分 ---
        # 活跃度：最近30天提交数
        if recent_commits > 50: activity_score = 'A'
        elif recent_commits > 20: activity_score = 'B'
        elif recent_commits > 5: activity_score = 'C'
        elif recent_commits > 0: activity_score = 'D'
        else: activity_score = 'F'

        # 维护性：Issue 响应速度
        if avg_close_days is None: maintenance_score = '?'
        elif avg_close_days < 3: maintenance_score = 'A'
        elif avg_close_days < 7: maintenance_score = 'B'
        elif avg_close_days < 14: maintenance_score = 'C'
        elif avg_close_days < 30: maintenance_score = 'D'
        else: maintenance_score = 'F'

        # 社区：贡献者数量
        if contributor_count > 100: community_score = 'A'
        elif contributor_count > 30: community_score = 'B'
        elif contributor_count > 10: community_score = 'C'
        elif contributor_count > 3: community_score = 'D'
        else: community_score = 'F'

        # 人气
        if stars > 10000: popularity_score = 'A'
        elif stars > 3000: popularity_score = 'B'
        elif stars > 500: popularity_score = 'C'
        elif stars > 100: popularity_score = 'D'
        else: popularity_score = 'F'

        # 机会识别：open issues 多 + 贡献者少 = 机会大
        opportunity = 'high' if open_issues > 50 and contributor_count < 20 else \
                      'medium' if open_issues > 20 else 'low'

        return {
            'basic': {
                'name': repo.full_name,
                'description': repo.description,
                'language': repo.language,
                'topics': repo.topics,
                'license': repo.license.spdx_id if repo.license else None,
                'homepage': repo.homepage,
                'created_at': created.strftime('%Y-%m-%d'),
                'age_days': age_days,
                'size_mb': round(size_kb / 1024, 1),
            },
            'metrics': {
                'stars': stars,
                'forks': forks,
                'watchers': watchers,
                'open_issues': open_issues,
                'contributors': contributor_count,
                'releases': release_count,
                'commits_last_30d': recent_commits,
                'avg_issue_close_days': avg_close_days,
                'last_release': last_release.strftime('%Y-%m-%d') if last_release else None,
            },
            'scores': {
                'activity': activity_score,
                'maintenance': maintenance_score,
                'community': community_score,
                'popularity': popularity_score,
                'opportunity': opportunity,
            },
            'owner': self._extract_user_contact(repo.owner),
        }

    def format_spy_report(self, report: Dict) -> str:
        """格式化情报报告。"""
        b = report['basic']
        m = report['metrics']
        s = report['scores']
        o = report['owner']

        lines = []
        lines.append(f"{'='*60}")
        lines.append(f"  {b['name']}")
        lines.append(f"  {b.get('description', 'No description')}")
        lines.append(f"{'='*60}")
        lines.append(f"")
        lines.append(f"  Language:  {b.get('language', 'N/A')}")
        lines.append(f"  License:   {b.get('license', 'N/A')}")
        lines.append(f"  Topics:    {', '.join(b.get('topics', [])[:8])}")
        lines.append(f"  Age:       {b['age_days']} days (since {b['created_at']})")
        lines.append(f"  Size:      {b.get('size_mb', '?')} MB")
        if b.get('homepage'):
            lines.append(f"  Homepage:  {b['homepage']}")
        lines.append(f"")
        lines.append(f"  --- Metrics ---")
        lines.append(f"  Stars:           {m['stars']:>8,}")
        lines.append(f"  Forks:           {m['forks']:>8,}")
        lines.append(f"  Watchers:        {m['watchers']:>8,}")
        lines.append(f"  Open Issues:     {m['open_issues']:>8,}")
        lines.append(f"  Contributors:    {m['contributors']:>8,}")
        lines.append(f"  Releases:        {m['releases']:>8,}")
        lines.append(f"  Commits (30d):   {m['commits_last_30d']:>8,}")
        lines.append(f"  Avg Issue Close: {str(m['avg_issue_close_days']) + ' days' if m['avg_issue_close_days'] else 'N/A':>8}")
        lines.append(f"  Last Release:    {str(m.get('last_release') or 'N/A'):>8}")
        lines.append(f"")
        lines.append(f"  --- Report Card ---")
        lines.append(f"  Activity:      [{s['activity']}]")
        lines.append(f"  Maintenance:   [{s['maintenance']}]")
        lines.append(f"  Community:     [{s['community']}]")
        lines.append(f"  Popularity:    [{s['popularity']}]")
        lines.append(f"  Opportunity:   [{s['opportunity'].upper()}]")
        lines.append(f"")
        lines.append(f"  --- Owner ---")
        lines.append(f"  {o.get('login', '?')} / {o.get('name', '?')}")
        contacts = []
        if o.get('email'): contacts.append(f"Email: {o['email']}")
        if o.get('twitter'): contacts.append(f"Twitter: @{o['twitter']}")
        if o.get('blog'): contacts.append(f"Blog: {o['blog']}")
        if o.get('location'): contacts.append(f"Location: {o['location']}")
        lines.append(f"  {' | '.join(contacts) if contacts else 'GitHub only'}")
        lines.append(f"{'='*60}")
        return "\n".join(lines)


if __name__ == '__main__':
    # 测试
    fetcher = GitHubFetcher()
    results = fetcher.fetch_repos("需要处理 CSV 文件的 Python 库", max_results=3)
    print(fetcher.format_results(results))
