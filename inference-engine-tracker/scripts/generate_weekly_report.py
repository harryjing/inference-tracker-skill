#!/usr/bin/env python3
"""
周报生成模块

汇总本周的日报数据，生成综合分析报告。
"""

import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path


def collect_daily_reports(daily_dir: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """收集指定日期范围内的日报"""
    reports = []
    daily_path = Path(daily_dir)

    if not daily_path.exists():
        return []

    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')

    current = start
    while current <= end:
        date_str = current.strftime('%Y-%m-%d')
        report_file = daily_path / f'{date_str}.md'

        if report_file.exists():
            with open(report_file, 'r', encoding='utf-8') as f:
                content = f.read()

            issue_match = re.search(r'相关 Issues: (\d+) 个', content)
            pr_match = re.search(r'相关 PRs: (\d+) 个', content)
            release_match = re.search(r'Releases: (\d+) 个', content)
            repo_match = re.search(r'有更新的项目: (\d+) 个', content)

            reports.append({
                'date': date_str,
                'content': content,
                'issue_count': int(issue_match.group(1)) if issue_match else 0,
                'pr_count': int(pr_match.group(1)) if pr_match else 0,
                'release_count': int(release_match.group(1)) if release_match else 0,
                'repo_count': int(repo_match.group(1)) if repo_match else 0,
            })

        current += timedelta(days=1)

    return reports


def extract_github_updates_from_reports(reports: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """从日报中提取 GitHub 更新信息"""
    updates = {}

    for report in reports:
        content = report['content']
        date = report['date']

        repo_pattern = r'## \[(.+?)\]\(.+?\)\n'
        matches = list(re.finditer(repo_pattern, content))

        for i, match in enumerate(matches):
            repo_name = match.group(1)
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            repo_content = content[start:end]

            if repo_name not in updates:
                updates[repo_name] = []

            # 提取重要 Issues
            issues_pattern = r'### 重要 Issues\n(.+?)(?=\n###|\n---|\Z)'
            issues_match = re.search(issues_pattern, repo_content, re.DOTALL)
            if issues_match:
                updates[repo_name].append({
                    'date': date,
                    'type': 'important_issues',
                    'content': issues_match.group(1).strip()
                })

            # 提取重要 PRs
            prs_pattern = r'### 重要 PRs\n(.+?)(?=\n###|\n---|\Z)'
            prs_match = re.search(prs_pattern, repo_content, re.DOTALL)
            if prs_match:
                updates[repo_name].append({
                    'date': date,
                    'type': 'important_prs',
                    'content': prs_match.group(1).strip()
                })

            # 提取版本发布
            release_pattern = r'### 版本发布\n(.+?)(?=\n###|\n---|\Z)'
            release_match = re.search(release_pattern, repo_content, re.DOTALL)
            if release_match:
                updates[repo_name].append({
                    'date': date,
                    'type': 'releases',
                    'content': release_match.group(1).strip()
                })

    return updates


def generate_weekly_report(
    start_date: str,
    end_date: str,
    daily_dir: str,
    output_dir: Optional[str] = None
) -> str:
    """生成周报"""
    reports = collect_daily_reports(daily_dir, start_date, end_date)

    if not reports:
        print(f"警告: 未找到 {start_date} 到 {end_date} 的日报")
        return ""

    print(f"收集到 {len(reports)} 天的日报")

    total_issues = sum(r['issue_count'] for r in reports)
    total_prs = sum(r['pr_count'] for r in reports)
    total_releases = sum(r['release_count'] for r in reports)

    github_updates = extract_github_updates_from_reports(reports)

    lines = [
        f"# GitHub 项目进展周报 - {start_date} 至 {end_date}",
        "",
        f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "---",
        "",
        "## 本周数据概览",
        "",
        f"- **统计周期**: {start_date} - {end_date} (共 {len(reports)} 天)",
        f"- **相关 Issues**: {total_issues} 个",
        f"- **相关 PRs**: {total_prs} 个",
        f"- **Releases**: {total_releases} 个",
        f"- **有更新的项目**: {len(github_updates)} 个",
        "",
        "### 每日更新量",
        "",
        "| 日期 | Issues | PRs | Releases |",
        "|------|--------|-----|----------|",
    ]

    for report in reports:
        lines.append(f"| {report['date']} | {report['issue_count']} | {report['pr_count']} | {report['release_count']} |")

    lines.extend([
        "",
        "---",
        "",
        "## 本周项目关键进展",
        ""
    ])

    for repo_name, updates in github_updates.items():
        if not updates:
            continue

        lines.append(f"### {repo_name}")
        lines.append("")

        important_issues = [u for u in updates if u['type'] == 'important_issues']
        if important_issues:
            lines.append("**重要 Issues**:")
            for update in important_issues[:5]:
                content_lines = update['content'].strip().split('\n')
                first_line = content_lines[0] if content_lines else ''
                lines.append(f"- {update['date']}: {first_line[:120]}")
            lines.append("")

        important_prs = [u for u in updates if u['type'] == 'important_prs']
        if important_prs:
            lines.append("**重要 PRs**:")
            for update in important_prs[:5]:
                content_lines = update['content'].strip().split('\n')
                first_line = content_lines[0] if content_lines else ''
                lines.append(f"- {update['date']}: {first_line[:120]}")
            lines.append("")

        release_updates = [u for u in updates if u['type'] == 'releases']
        if release_updates:
            lines.append("**版本发布**:")
            for update in release_updates[:3]:
                content_lines = update['content'].strip().split('\n')
                first_line = content_lines[0] if content_lines else ''
                lines.append(f"- {update['date']}: {first_line[:120]}")
            lines.append("")

    lines.extend([
        "",
        "---",
        "",
        "## 下周展望",
        "",
        "- 继续关注各项目的 Issue 和 PR 动态",
        "- 跟踪版本发布和性能优化进展",
        "- 关注推理加速和准确率提升相关的新技术",
        ""
    ])

    content = "\n".join(lines)

    if output_dir:
        output_path = Path(output_dir) / 'weekly' / f'{start_date}_{end_date}.md'
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"周报已保存到: {output_path}")

    return content


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Generate weekly report')
    parser.add_argument('--start-date', type=str)
    parser.add_argument('--end-date', type=str)
    parser.add_argument('--daily-dir', type=str, default='./reports/daily')
    parser.add_argument('--output-dir', type=str, default='./reports')

    args = parser.parse_args()

    end_date = args.end_date or datetime.now().strftime('%Y-%m-%d')
    start_date = args.start_date or (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=6)).strftime('%Y-%m-%d')

    content = generate_weekly_report(
        start_date=start_date,
        end_date=end_date,
        daily_dir=args.daily_dir,
        output_dir=args.output_dir
    )

    if content:
        print(f"\n周报生成完成! 总长度: {len(content)} 字符")
    else:
        print("\n周报生成失败")


if __name__ == '__main__':
    main()
