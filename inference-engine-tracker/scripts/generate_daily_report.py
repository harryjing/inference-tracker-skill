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


def format_status_label(item: dict) -> str:
    """返回中文状态标签"""
    if item['type'] == 'PR':
        if item.get('merged_at'):
            return '已合并'
        elif item['state'] == 'closed':
            return '已关闭'
        return '进行中'
    elif item['type'] == 'Issue':
        if item['state'] == 'closed':
            return '已关闭'
        return '开放中'
    return ''


def format_keywords_cn(key_points: list) -> str:
    """将英文关键词转为中文标签"""
    kw_map = {
        'kv cache': 'KV缓存', 'kvcache': 'KV缓存', 'cache': '缓存',
        'attention': '注意力', 'memory': '显存', 'batch': '批处理',
        'parallel': '并行', 'speculative': '投机解码', 'quantization': '量化',
        'moe': 'MoE', 'scheduler': '调度', 'performance': '性能',
        'optimize': '优化', 'speed': '速度', 'latency': '延迟',
        'throughput': '吞吐', 'reduce': '降低', 'improve': '改进',
        'swap': '交换', 'compress': '压缩', 'deployment': '部署',
        'benchmark': '基准测试', 'config': '配置', 'support': '支持',
    }
    cn_kws = []
    for kw in key_points[:4]:
        cn_kws.append(kw_map.get(kw.lower(), kw))
    return ' '.join(f'`{k}`' for k in cn_kws)


def generate_highlights_section(all_items: List[dict], max_items: int = 8) -> str:
    """生成"今日重点"汇总区（全中文增强版）"""
    if not all_items:
        return ""

    lines = ["## 今日重点\n"]

    for i, item in enumerate(all_items[:max_items], 1):
        status_label = format_status_label(item)
        keywords_str = format_keywords_cn(item['key_points']) if item['key_points'] else ''
        importance = score_label(item['score'])

        lines.append(
            f"{i}. **[{item['repo']} {item['type']} #{item['number']}]({item['url']})** "
            f"[{status_label}] @{item['author']} {keywords_str} 【重要性: {importance}】"
        )
        if item.get('explanation'):
            # explanation 可能包含多行（核心要点在第二行）
            for exp_line in item['explanation'].split('\n'):
                exp_line = exp_line.strip()
                if exp_line:
                    lines.append(f"   > {exp_line}")
        # 显示量化指标
        if item.get('metrics'):
            metrics_str = '、'.join(item['metrics'][:3])
            lines.append(f"   > 📊 性能数据: {metrics_str}")
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

        # 输出 Issues（按评分排序，增强中文描述）
        if relevant_issues:
            lines.append(f"### Issues ({len(relevant_issues)} 个相关，按重要性排序)")
            for issue in relevant_issues[:15]:
                state_cn = "开放" if issue['state'] == 'open' else "已关闭"
                labels_str = f" `{'` `'.join(issue['labels'])}`" if issue['labels'] else ""
                importance = score_label(issue['score'])
                author_str = f" @{issue['author']}" if issue['author'] else ""

                lines.append(
                    f"- **[{state_cn}]** [#{issue['number']}: {issue['title']}]({issue['url']})"
                    f"{labels_str}{author_str} 【重要性: {importance}】"
                )
                if issue.get('explanation'):
                    for exp_line in issue['explanation'].split('\n'):
                        exp_line = exp_line.strip()
                        if exp_line:
                            lines.append(f"  > {exp_line}")
                if issue.get('metrics'):
                    metrics_str = '、'.join(issue['metrics'][:3])
                    lines.append(f"  > 📊 性能数据: {metrics_str}")
            lines.append("")

        # 输出 PRs（按评分排序，增强中文描述）
        if relevant_prs:
            lines.append(f"### PRs ({len(relevant_prs)} 个相关，按重要性排序)")
            for pr in relevant_prs[:15]:
                status_cn = "已合并" if pr.get('merged_at') else ("已关闭" if pr['state'] == 'closed' else "进行中")
                labels_str = f" `{'` `'.join(pr['labels'])}`" if pr['labels'] else ""
                importance = score_label(pr['score'])
                author_str = f" @{pr['author']}" if pr['author'] else ""

                lines.append(
                    f"- **[{status_cn}]** [#{pr['number']}: {pr['title']}]({pr['url']})"
                    f"{labels_str}{author_str} 【重要性: {importance}】"
                )
                if pr.get('explanation'):
                    for exp_line in pr['explanation'].split('\n'):
                        exp_line = exp_line.strip()
                        if exp_line:
                            lines.append(f"  > {exp_line}")
                if pr.get('metrics'):
                    metrics_str = '、'.join(pr['metrics'][:3])
                    lines.append(f"  > 📊 性能数据: {metrics_str}")
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
        "*本报告聚焦推理加速、显存优化、量化技术、投机解码与准确率提升等核心技术方向*",
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
