#!/usr/bin/env python3
"""
GitHub 更新获取模块

从配置的 GitHub 仓库获取最新更新：
- Issues (recently updated)
- Pull Requests (recently updated/merged)
- Releases (latest)

使用 GitHub API，支持 rate limit 处理
"""

import os
import sys
import yaml
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path

import requests
from dateutil import parser as date_parser


@dataclass
class IssueInfo:
    """Issue 信息"""
    number: int
    title: str
    body: str
    author: str
    state: str
    created_at: str
    updated_at: str
    url: str
    labels: List[str]
    comments: int


@dataclass
class ReleaseInfo:
    """发布信息"""
    tag_name: str
    name: str
    body: str
    published_at: str
    author: str
    url: str
    prerelease: bool = False


@dataclass
class PullRequestInfo:
    """PR 信息"""
    number: int
    title: str
    body: str
    author: str
    state: str
    created_at: str
    updated_at: str
    merged_at: Optional[str]
    url: str
    labels: List[str]


class GitHubFetcher:
    """GitHub API 获取器"""

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get('GITHUB_TOKEN')
        self.has_token = bool(self.token)

        if not self.has_token:
            self.headers = {
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'inference-engine-tracker'
            }
        else:
            self.headers = {
                'Authorization': f'token {self.token}',
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'inference-engine-tracker'
            }
        self.base_url = 'https://api.github.com'
        self.request_count = 0
        self.last_request_time = 0

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Any:
        """发送 API 请求，带有 rate limit 处理"""
        url = f'{self.base_url}/{endpoint}'

        elapsed = time.time() - self.last_request_time
        if elapsed < 0.1:
            time.sleep(0.1 - elapsed)

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            self.last_request_time = time.time()
            self.request_count += 1

            if response.status_code == 403 and 'X-RateLimit-Remaining' in response.headers:
                remaining = int(response.headers.get('X-RateLimit-Remaining', 0))
                if remaining == 0:
                    reset_time = int(response.headers.get('X-RateLimit-Reset', 0))
                    wait_time = max(reset_time - int(time.time()), 0) + 1
                    print(f"Rate limit hit. Waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                    return self._make_request(endpoint, params)

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return {}

    def get_issues(self, owner: str, repo: str, since: datetime,
                   max_results: int = 30) -> List[IssueInfo]:
        """获取指定时间后更新的 issues（排除 PR）"""
        endpoint = f'repos/{owner}/{repo}/issues'
        params = {
            'since': since.isoformat(),
            'state': 'all',
            'sort': 'updated',
            'direction': 'desc',
            'per_page': min(max_results * 2, 100)
        }

        data = self._make_request(endpoint, params)
        issues = []

        for item in data if isinstance(data, list) else []:
            # GitHub Issues API 也返回 PRs，通过 pull_request 字段排除
            if 'pull_request' in item:
                continue

            labels = [label.get('name', '') for label in item.get('labels', [])]

            issues.append(IssueInfo(
                number=item.get('number', 0),
                title=item.get('title', ''),
                body=item.get('body', '')[:1000] if item.get('body') else '',
                author=item.get('user', {}).get('login', 'Unknown'),
                state=item.get('state', 'open'),
                created_at=item.get('created_at', ''),
                updated_at=item.get('updated_at', ''),
                url=item.get('html_url', ''),
                labels=labels,
                comments=item.get('comments', 0)
            ))

            if len(issues) >= max_results:
                break

        return issues[:max_results]

    def get_releases(self, owner: str, repo: str, since: datetime,
                     max_results: int = 5) -> List[ReleaseInfo]:
        """获取指定时间后的 releases"""
        endpoint = f'repos/{owner}/{repo}/releases'
        params = {
            'per_page': min(max_results, 100)
        }

        data = self._make_request(endpoint, params)
        releases = []

        for item in data if isinstance(data, list) else []:
            published_at = item.get('published_at', '')
            if published_at:
                pub_dt = date_parser.parse(published_at)
                if pub_dt < since:
                    continue

            releases.append(ReleaseInfo(
                tag_name=item.get('tag_name', ''),
                name=item.get('name', ''),
                body=item.get('body', '')[:1000] if item.get('body') else '',
                published_at=published_at,
                author=item.get('author', {}).get('login', 'Unknown'),
                url=item.get('html_url', ''),
                prerelease=item.get('prerelease', False)
            ))

        return releases

    def get_pulls(self, owner: str, repo: str, since: datetime,
                  state: str = 'all', max_results: int = 30) -> List[PullRequestInfo]:
        """获取指定时间后更新的 PRs"""
        endpoint = f'repos/{owner}/{repo}/pulls'
        params = {
            'state': state,
            'sort': 'updated',
            'direction': 'desc',
            'per_page': min(max_results * 2, 100)
        }

        data = self._make_request(endpoint, params)
        pulls = []

        for item in data if isinstance(data, list) else []:
            updated_at = item.get('updated_at', '')
            if updated_at:
                updated_dt = date_parser.parse(updated_at)
                if updated_dt < since:
                    continue

            labels = [label.get('name', '') for label in item.get('labels', [])]

            pulls.append(PullRequestInfo(
                number=item.get('number', 0),
                title=item.get('title', ''),
                body=item.get('body', '')[:1000] if item.get('body') else '',
                author=item.get('user', {}).get('login', 'Unknown'),
                state=item.get('state', 'open'),
                created_at=item.get('created_at', ''),
                updated_at=updated_at,
                merged_at=item.get('merged_at'),
                url=item.get('html_url', ''),
                labels=labels
            ))

            if len(pulls) >= max_results:
                break

        return pulls[:max_results]


def load_config(config_path: Optional[str] = None) -> Dict:
    """加载配置文件"""
    if config_path is None:
        config_path = Path(__file__).parent.parent / 'config' / 'repositories.yaml'

    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def fetch_all_updates(days: int = 1, config_path: Optional[str] = None,
                      dry_run: bool = False, token: Optional[str] = None) -> Dict[str, Any]:
    """
    获取所有配置仓库的更新

    Args:
        days: 回溯天数
        config_path: 配置文件路径
        dry_run: 测试模式
        token: GitHub API token

    Returns:
        按仓库组织的更新数据
    """
    if dry_run:
        print("[DRY RUN] 模拟获取 GitHub 更新...")
        return _generate_mock_data()

    config = load_config(config_path)
    fetcher = GitHubFetcher(token=token)

    if not fetcher.has_token:
        print("\n未提供 GITHUB_TOKEN，跳过 GitHub 数据获取")
        print("   如需获取 GitHub 更新，请设置环境变量：")
        print("   export GITHUB_TOKEN=ghp_xxxxxxxxxxxx\n")
        return {}

    since = datetime.now(timezone.utc) - timedelta(days=days)
    print(f"获取从 {since.isoformat()} 以来的更新...")

    all_updates = {}
    settings = config.get('settings', {})

    for repo_config in config.get('repositories', []):
        name = repo_config['name']
        owner = repo_config['owner']
        repo = repo_config['repo']
        track_types = repo_config.get('track', ['issues', 'pulls', 'releases'])

        print(f"\n正在获取 {name} ({owner}/{repo})...")

        repo_updates = {
            'info': {
                'name': name,
                'owner': owner,
                'repo': repo,
                'url': f'https://github.com/{owner}/{repo}'
            },
            'issues': [],
            'pulls': [],
            'releases': []
        }

        if 'issues' in track_types:
            max_issues = settings.get('max_issues', 30)
            issues = fetcher.get_issues(owner, repo, since, max_issues)
            repo_updates['issues'] = [asdict(i) for i in issues]
            print(f"  - Issues: {len(issues)}")

        if 'pulls' in track_types:
            max_pulls = settings.get('max_pulls', 30)
            pr_state = settings.get('pr_state', 'all')
            pulls = fetcher.get_pulls(owner, repo, since, pr_state, max_pulls)
            repo_updates['pulls'] = [asdict(p) for p in pulls]
            print(f"  - Pull Requests: {len(pulls)}")

        if 'releases' in track_types:
            max_releases = settings.get('max_releases', 5)
            releases = fetcher.get_releases(owner, repo, since, max_releases)
            repo_updates['releases'] = [asdict(r) for r in releases]
            print(f"  - Releases: {len(releases)}")

        all_updates[name] = repo_updates

        delay = settings.get('request_delay', 0.5)
        time.sleep(delay)

    print(f"\n总计 API 请求数: {fetcher.request_count}")
    return all_updates


def _generate_mock_data() -> Dict[str, Any]:
    """生成模拟数据用于测试"""
    return {
        'SGLang': {
            'info': {
                'name': 'SGLang',
                'owner': 'sgl-project',
                'repo': 'sglang',
                'url': 'https://github.com/sgl-project/sglang'
            },
            'issues': [
                {
                    'number': 100,
                    'title': '[Feature] Add FP8 KV cache support',
                    'body': 'Request to add FP8 KV cache for better memory efficiency...',
                    'author': 'user1',
                    'state': 'open',
                    'created_at': '2026-04-08T10:00:00Z',
                    'updated_at': '2026-04-08T12:00:00Z',
                    'url': 'https://github.com/sgl-project/sglang/issues/100',
                    'labels': ['enhancement'],
                    'comments': 5
                }
            ],
            'pulls': [
                {
                    'number': 200,
                    'title': 'Optimize radix attention for long context',
                    'body': 'This PR optimizes radix attention...',
                    'author': 'dev1',
                    'state': 'open',
                    'created_at': '2026-04-08T08:00:00Z',
                    'updated_at': '2026-04-08T14:00:00Z',
                    'merged_at': None,
                    'url': 'https://github.com/sgl-project/sglang/pull/200',
                    'labels': ['performance']
                }
            ],
            'releases': []
        },
        'SpecForge': {
            'info': {
                'name': 'SpecForge',
                'owner': 'sgl-project',
                'repo': 'SpecForge',
                'url': 'https://github.com/sgl-project/SpecForge'
            },
            'issues': [],
            'pulls': [],
            'releases': []
        },
        'AIConfigurator': {
            'info': {
                'name': 'AIConfigurator',
                'owner': 'ai-dynamo',
                'repo': 'aiconfigurator',
                'url': 'https://github.com/ai-dynamo/aiconfigurator'
            },
            'issues': [],
            'pulls': [],
            'releases': []
        }
    }


def main():
    """CLI 入口"""
    import argparse
    import json

    parser = argparse.ArgumentParser(description='Fetch GitHub updates')
    parser.add_argument('--days', type=int, default=1, help='Number of days to look back')
    parser.add_argument('--config', type=str, help='Path to repositories.yaml')
    parser.add_argument('--dry-run', action='store_true', help='Run in dry-run mode')
    parser.add_argument('--output', type=str, help='Output JSON file path')

    args = parser.parse_args()

    updates = fetch_all_updates(
        days=args.days,
        config_path=args.config,
        dry_run=args.dry_run
    )

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(updates, f, ensure_ascii=False, indent=2)
        print(f"\n数据已保存到: {args.output}")
    else:
        print("\n获取完成。使用 --output 保存到文件。")


if __name__ == '__main__':
    main()
