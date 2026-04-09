#!/usr/bin/env python3
"""
日报生成模块

将分析后的 GitHub 更新数据生成为结构化的 Markdown 日报。

日报包含：
- GitHub Issues（按重要性分类）
- GitHub PRs（按重要性分类）
- Releases
- 统计数据概览
"""

import json
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path


def format_date(date_str: str) -> str:
    """格式化日期字符串"""
    if not date_str:
        return "未知"
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M')
    except Exception:
        return date_str[:10] if date_str else "未知"


def truncate_text(text: str, max_length: int = 200) -> str:
    """截断文本"""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def generate_github_section(updates: Dict[str, Any]) -> str:
    """生成 GitHub 更新部分"""
    if not updates:
        return "## GitHub 项目更新\n\n今日暂无更新。\n"

    lines = []

    for repo_name, repo_data in updates.items():
        info = repo_data.get('info', {})
        lines.append(f"## [{repo_name}]({info.get('url', '')})\n")

        # 收集所有相关更新
        important_issues = []
        other_issues = []
        important_prs = []
        feature_prs = []
        other_prs = []
        releases = []

        # 分析 Issues
        for issue in repo_data.get('issues', []):
            analysis = issue.get('analysis', {})
            entry = {
                'number': issue.get('number', 0),
                'title': issue.get('title', ''),
                'url': issue.get('url', ''),
                'state': issue.get('state', 'open'),
                'author': issue.get('author', ''),
                'labels': issue.get('labels', []),
                'comments': issue.get('comments', 0),
                'impact': analysis.get('impact_level', 'low'),
                'chinese_explanation': analysis.get('chinese_explanation', ''),
                'is_relevant': analysis.get('is_relevant', False),
            }

            if not entry['is_relevant']:
                continue

            if analysis.get('impact_level') == 'high':
                important_issues.append(entry)
            else:
                other_issues.append(entry)

        # 分析 PRs
        for pr in repo_data.get('pulls', []):
            analysis = pr.get('analysis', {})
            entry = {
                'number': pr.get('number', 0),
                'title': pr.get('title', ''),
                'url': pr.get('url', ''),
                'state': pr.get('state', 'open'),
                'author': pr.get('author', ''),
                'merged_at': pr.get('merged_at'),
                'labels': pr.get('labels', []),
                'impact': analysis.get('impact_level', 'low'),
                'chinese_explanation': analysis.get('chinese_explanation', ''),
                'is_relevant': analysis.get('is_relevant', False),
            }

            if not entry['is_relevant']:
                continue

            if analysis.get('impact_level') == 'high':
                important_prs.append(entry)
            elif analysis.get('impact_level') == 'medium':
                feature_prs.append(entry)
            else:
                other_prs.append(entry)

        # 分析 Releases
        for release in repo_data.get('releases', []):
            analysis = release.get('analysis', {})
            releases.append({
                'tag': release.get('tag_name', ''),
                'name': release.get('name', ''),
                'url': release.get('url', ''),
                'published_at': release.get('published_at', ''),
                'chinese_explanation': analysis.get('chinese_explanation', ''),
            })

        # 输出 Releases
        if releases:
            lines.append("### 版本发布")
            for r in releases:
                lines.append(f"- **[{r['tag']}]({r['url']})** {r['name']}")
                if r.get('chinese_explanation'):
                    lines.append(f"  > {r['chinese_explanation']}")
            lines.append("")

        # 输出重要 Issues
        if important_issues:
            lines.append("### 重要 Issues")
            for issue in important_issues[:10]:
                state_icon = "O" if issue['state'] == 'open' else "C"
                labels_str = f" `{'` `'.join(issue['labels'])}`" if issue['labels'] else ""
                lines.append(f"- **[{state_icon}]** [#{issue['number']}: {issue['title']}]({issue['url']}){labels_str}")
                if issue.get('chinese_explanation'):
                    lines.append(f"  > {issue['chinese_explanation']}")
            lines.append("")

        # 输出其他相关 Issues
        if other_issues:
            lines.append("### 其他相关 Issues")
            for issue in other_issues[:5]:
                state_icon = "O" if issue['state'] == 'open' else "C"
                lines.append(f"- [{state_icon}] [#{issue['number']}: {issue['title']}]({issue['url']})")
                if issue.get('chinese_explanation'):
                    lines.append(f"  > {issue['chinese_explanation']}")
            lines.append("")

        # 输出重要 PRs
        if important_prs:
            lines.append("### 重要 PRs")
            for pr in important_prs[:10]:
                status = "merged" if pr.get('merged_at') else pr['state']
                lines.append(f"- **[{status}]** [#{pr['number']}: {pr['title']}]({pr['url']})")
                if pr.get('chinese_explanation'):
                    lines.append(f"  > {pr['chinese_explanation']}")
            lines.append("")

        # 输出其他 PRs
        if feature_prs or other_prs:
            lines.append("### 其他相关 PRs")
            for pr in (feature_prs + other_prs)[:5]:
                status = "merged" if pr.get('merged_at') else pr['state']
                lines.append(f"- [{status}] [#{pr['number']}: {pr['title']}]({pr['url']})")
                if pr.get('chinese_explanation'):
                    lines.append(f"  > {pr['chinese_explanation']}")
            lines.append("")

        if not any([important_issues, other_issues, important_prs, feature_prs, other_prs, releases]):
            lines.append("暂无与推理加速/准确率相关的更新。\n")

    return "\n".join(lines)


def generate_daily_report(
    date: str,
    github_updates: Dict[str, Any],
    output_dir: Optional[str] = None
) -> str:
    """
    生成日报

    Args:
        date: 日期字符串 (YYYY-MM-DD)
        github_updates: GitHub 更新数据
        output_dir: 输出目录

    Returns:
        生成的 Markdown 内容
    """
    github_section = generate_github_section(github_updates)

    # 统计
    total_issues = 0
    total_prs = 0
    total_releases = 0
    relevant_repos = 0

    for repo_data in github_updates.values():
        issues = [i for i in repo_data.get('issues', []) if i.get('analysis', {}).get('is_relevant')]
        prs = [p for p in repo_data.get('pulls', []) if p.get('analysis', {}).get('is_relevant')]
        rels = repo_data.get('releases', [])

        total_issues += len(issues)
        total_prs += len(prs)
        total_releases += len(rels)

        if issues or prs or rels:
            relevant_repos += 1

    lines = [
        f"# GitHub 项目进展日报 - {date}",
        "",
        f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"> 相关 Issues: {total_issues} 个 | 相关 PRs: {total_prs} 个 | Releases: {total_releases} 个",
        f"> 有更新的项目: {relevant_repos} 个",
        "",
        "---",
        "",
        github_section,
        "",
        "---",
        "",
        "*报告关注推理加速和准确率提升相关的技术更新*",
        ""
    ]

    content = "\n".join(lines)

    if output_dir:
        output_path = Path(output_dir) / 'daily' / f'{date}.md'
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"日报已保存到: {output_path}")

    return content


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Generate daily report')
    parser.add_argument('--date', type=str, default=datetime.now().strftime('%Y-%m-%d'))
    parser.add_argument('--github-input', type=str, required=True)
    parser.add_argument('--output-dir', type=str, default='./reports')

    args = parser.parse_args()

    with open(args.github_input, 'r', encoding='utf-8') as f:
        github_updates = json.load(f)

    content = generate_daily_report(
        date=args.date,
        github_updates=github_updates,
        output_dir=args.output_dir
    )

    print(f"\n日报生成完成! 总长度: {len(content)} 字符")


if __name__ == '__main__':
    main()
