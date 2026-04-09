#!/usr/bin/env python3
"""
日报生成模块 v2

将分析后的 GitHub 更新数据生成为结构化的 Markdown 日报。

v2 改进：
- 新增"今日重点"跨仓库汇总（按评分排序 Top 8）
- 每条 Issue/PR 展示更丰富的信息（作者、评分、摘要描述）
- Release 提取 release notes 摘要
- 仓库内按评分降序排列
"""

import json
import re
from datetime import datetime
from typing import Dict, Any, Optional, List
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


def score_label(score: float) -> str:
    """返回评分标签"""
    if score >= 0.7:
        return '高'
    elif score >= 0.4:
        return '中'
    return '低'


def extract_release_highlights(body: str, max_items: int = 5) -> list:
    """从 release notes body 中提取关键变更点"""
    if not body:
        return []

    lines = body.split('\n')
    highlights = []

    for line in lines:
        line = line.strip()
        # 匹配 bullet point 或 numbered list
        if re.match(r'^[-*]\s+', line) or re.match(r'^\d+\.\s+', line):
            # 清理 markdown
            cleaned = re.sub(r'^[-*\d.]+\s+', '', line).strip()
            cleaned = re.sub(r'\[([^\]]*)\]\([^\)]*\)', r'\1', cleaned)  # 链接转文本
            cleaned = re.sub(r'`([^`]*)`', r'\1', cleaned)  # 去除 code
            cleaned = re.sub(r'\*\*([^*]*)\*\*', r'\1', cleaned)  # 去除 bold
            if len(cleaned) > 10 and len(cleaned) < 200:
                highlights.append(cleaned)
                if len(highlights) >= max_items:
                    break

    return highlights


def collect_all_relevant_items(updates: Dict[str, Any]) -> List[dict]:
    """跨仓库收集所有相关条目，用于生成"今日重点" """
    items = []

    for repo_name, repo_data in updates.items():
        # Issues
        for issue in repo_data.get('issues', []):
            analysis = issue.get('analysis', {})
            if not analysis.get('is_relevant'):
                continue
            items.append({
                'type': 'Issue',
                'repo': repo_name,
                'number': issue.get('number', 0),
                'title': issue.get('title', ''),
                'url': issue.get('url', ''),
                'author': issue.get('author', ''),
                'state': issue.get('state', 'open'),
                'merged_at': None,
                'score': analysis.get('relevance_score', 0),
                'impact': analysis.get('impact_level', 'low'),
                'explanation': analysis.get('chinese_explanation', ''),
                'key_points': analysis.get('key_points', []),
                'metrics': analysis.get('metrics', []),
                'labels': issue.get('labels', []),
            })

        # PRs
        for pr in repo_data.get('pulls', []):
            analysis = pr.get('analysis', {})
            if not analysis.get('is_relevant'):
                continue
            items.append({
                'type': 'PR',
                'repo': repo_name,
                'number': pr.get('number', 0),
                'title': pr.get('title', ''),
                'url': pr.get('url', ''),
                'author': pr.get('author', ''),
                'state': pr.get('state', 'open'),
                'merged_at': pr.get('merged_at'),
                'score': analysis.get('relevance_score', 0),
                'impact': analysis.get('impact_level', 'low'),
                'explanation': analysis.get('chinese_explanation', ''),
                'key_points': analysis.get('key_points', []),
                'metrics': analysis.get('metrics', []),
                'labels': pr.get('labels', []),
            })

    # 按评分降序排列
    items.sort(key=lambda x: x['score'], reverse=True)
    return items


def generate_highlights_section(all_items: List[dict], max_items: int = 8) -> str:
    """生成"今日重点"汇总区"""
    if not all_items:
        return ""

    lines = ["## 今日重点\n"]

    for i, item in enumerate(all_items[:max_items], 1):
        type_label = item['type']
        status = ''
        if item['type'] == 'PR':
            if item.get('merged_at'):
                status = ' (已合并)'
            elif item['state'] == 'closed':
                status = ' (已关闭)'
        elif item['type'] == 'Issue':
            if item['state'] == 'closed':
                status = ' (已关闭)'

        keywords_str = ''
        if item['key_points']:
            kw_display = item['key_points'][:3]
            keywords_str = ' ' + ' '.join(f'`{k}`' for k in kw_display)

        lines.append(
            f"{i}. **[{item['repo']} {type_label} #{item['number']}]({item['url']})**{status} "
            f"@{item['author']}{keywords_str} [{score_label(item['score'])}]"
        )
        if item.get('explanation'):
            lines.append(f"   > {item['explanation']}")
        lines.append("")

    return "\n".join(lines)


def generate_github_section(updates: Dict[str, Any]) -> str:
    """生成 GitHub 更新部分（按仓库分组，每个仓库内按评分排序）"""
    if not updates:
        return "## GitHub 项目更新\n\n今日暂无更新。\n"

    lines = []

    for repo_name, repo_data in updates.items():
        info = repo_data.get('info', {})
        lines.append(f"## [{repo_name}]({info.get('url', '')})\n")

        relevant_issues = []
        relevant_prs = []
        releases = []

        # 收集相关 Issues
        for issue in repo_data.get('issues', []):
            analysis = issue.get('analysis', {})
            if not analysis.get('is_relevant'):
                continue
            relevant_issues.append({
                'number': issue.get('number', 0),
                'title': issue.get('title', ''),
                'url': issue.get('url', ''),
                'state': issue.get('state', 'open'),
                'author': issue.get('author', ''),
                'labels': issue.get('labels', []),
                'comments': issue.get('comments', 0),
                'score': analysis.get('relevance_score', 0),
                'impact': analysis.get('impact_level', 'low'),
                'explanation': analysis.get('chinese_explanation', ''),
                'key_points': analysis.get('key_points', []),
                'metrics': analysis.get('metrics', []),
            })

        # 收集相关 PRs
        for pr in repo_data.get('pulls', []):
            analysis = pr.get('analysis', {})
            if not analysis.get('is_relevant'):
                continue
            relevant_prs.append({
                'number': pr.get('number', 0),
                'title': pr.get('title', ''),
                'url': pr.get('url', ''),
                'state': pr.get('state', 'open'),
                'author': pr.get('author', ''),
                'merged_at': pr.get('merged_at'),
                'labels': pr.get('labels', []),
                'score': analysis.get('relevance_score', 0),
                'impact': analysis.get('impact_level', 'low'),
                'explanation': analysis.get('chinese_explanation', ''),
                'key_points': analysis.get('key_points', []),
                'metrics': analysis.get('metrics', []),
            })

        # 收集 Releases
        for release in repo_data.get('releases', []):
            releases.append({
                'tag': release.get('tag_name', ''),
                'name': release.get('name', ''),
                'url': release.get('url', ''),
                'body': release.get('body', ''),
                'published_at': release.get('published_at', ''),
                'author': release.get('author', ''),
            })

        # 按评分降序排列
        relevant_issues.sort(key=lambda x: x['score'], reverse=True)
        relevant_prs.sort(key=lambda x: x['score'], reverse=True)

        # 输出 Releases（增强版）
        if releases:
            lines.append("### 版本发布")
            for r in releases:
                pub_date = format_date(r['published_at'])
                lines.append(f"- **[{r['tag']}]({r['url']})** {r['name']} (发布于 {pub_date})")
                highlights = extract_release_highlights(r.get('body', ''))
                if highlights:
                    lines.append(f"  > 主要变更:")
                    for h in highlights:
                        lines.append(f"  > - {h}")
                elif r.get('body'):
                    # 没有 bullet point 时，取 body 前 150 字符
                    snippet = r['body'][:150].replace('\n', ' ').strip()
                    if snippet:
                        lines.append(f"  > {snippet}...")
            lines.append("")

        # 输出 Issues（按评分排序）
        if relevant_issues:
            lines.append(f"### Issues ({len(relevant_issues)} 个相关，按重要性排序)")
            for issue in relevant_issues[:15]:
                state_icon = "O" if issue['state'] == 'open' else "C"
                labels_str = f" `{'` `'.join(issue['labels'])}`" if issue['labels'] else ""
                score_str = f" [{score_label(issue['score'])}]"
                author_str = f" @{issue['author']}" if issue['author'] else ""

                lines.append(
                    f"- **[{state_icon}]** [#{issue['number']}: {issue['title']}]({issue['url']})"
                    f"{labels_str}{author_str}{score_str}"
                )
                if issue.get('explanation'):
                    lines.append(f"  > {issue['explanation']}")
            lines.append("")

        # 输出 PRs（按评分排序）
        if relevant_prs:
            lines.append(f"### PRs ({len(relevant_prs)} 个相关，按重要性排序)")
            for pr in relevant_prs[:15]:
                status = "merged" if pr.get('merged_at') else pr['state']
                labels_str = f" `{'` `'.join(pr['labels'])}`" if pr['labels'] else ""
                score_str = f" [{score_label(pr['score'])}]"
                author_str = f" @{pr['author']}" if pr['author'] else ""

                lines.append(
                    f"- **[{status}]** [#{pr['number']}: {pr['title']}]({pr['url']})"
                    f"{labels_str}{author_str}{score_str}"
                )
                if pr.get('explanation'):
                    lines.append(f"  > {pr['explanation']}")
            lines.append("")

        if not any([relevant_issues, relevant_prs, releases]):
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
    # 收集所有相关条目（用于今日重点）
    all_items = collect_all_relevant_items(github_updates)

    # 生成各部分
    highlights_section = generate_highlights_section(all_items)
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
        highlights_section,
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
