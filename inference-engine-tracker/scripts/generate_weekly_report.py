#!/usr/bin/env python3
"""
周报生成模块 v2

汇总本周的日报数据，生成按技术方向分组、去重、全中文的综合分析报告。

v2 改进：
- 按技术主题分组汇总（KV缓存优化、投机解码、量化技术等）
- 跨天去重（同一 PR/Issue 只出现一次，取最新状态）
- 每个技术方向提供中文趋势分析
- 周报总结与下周展望更有针对性
"""

import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from collections import defaultdict


# 技术主题分类
TECH_THEMES = {
    'KV缓存与显存优化': {
        'keywords': ['kv cache', 'kvcache', 'cache', 'memory', 'oom', 'offload', 'swap',
                     'hicache', 'hisparse', 'prefetch', 'h2d', 'd2h', 'peak memory',
                     'memory spike', 'memory efficient', 'radix'],
        'icon': '🗄️',
    },
    '投机解码与加速': {
        'keywords': ['speculative', 'speculation', 'draft', 'eagle', 'mtp', 'lookahead',
                     'suffix decoding', 'acceptance rate', 'token match'],
        'icon': '⚡',
    },
    '量化技术': {
        'keywords': ['quantization', 'quantize', 'fp8', 'fp4', 'int8', 'int4', 'nvfp4',
                     'awq', 'gptq', 'compression', 'compress'],
        'icon': '📐',
    },
    '注意力机制优化': {
        'keywords': ['attention', 'flash attention', 'flashattention', 'flashinfer', 'mla',
                     'gqa', 'mqa', 'sliding window', 'sparse attention', 'ring attention',
                     'sdpa', 'swa'],
        'icon': '🔍',
    },
    '并行与分布式推理': {
        'keywords': ['parallel', 'tensor parallel', 'pipeline parallel', 'disaggregated',
                     'disaggregation', 'prefill-decode', 'pd disagg', 'all-to-all', 'a2a',
                     'allreduce', 'distributed', 'scattered'],
        'icon': '🌐',
    },
    'MoE模型优化': {
        'keywords': ['moe', 'mixture of experts', 'expert', 'expert parallel'],
        'icon': '🧩',
    },
    '调度与批处理': {
        'keywords': ['scheduler', 'scheduling', 'batch', 'continuous batching', 'inflight'],
        'icon': '📋',
    },
    '部署与基准测试': {
        'keywords': ['deployment', 'deploy', 'helm', 'benchmark', 'serving', 'config',
                     'support matrix', 'llm-d'],
        'icon': '🚀',
    },
    '新模型与平台支持': {
        'keywords': ['amd', 'rocm', 'npu', 'cpu', 'blackwell', 'new model', 'vlm',
                     'diffusion', 'multimodal', 'ernie', 'kimi', 'deepseek'],
        'icon': '🆕',
    },
}


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


def load_analyzed_data(analyzed_dir: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """加载分析后的 JSON 数据，用于更精确的周报汇总"""
    data_list = []
    analyzed_path = Path(analyzed_dir)

    if not analyzed_path.exists():
        return []

    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')

    current = start
    while current <= end:
        date_str = current.strftime('%Y-%m-%d')
        data_file = analyzed_path / f'github_{date_str}.json'

        if data_file.exists():
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data_list.append({'date': date_str, 'data': data})

        current += timedelta(days=1)

    return data_list


def deduplicate_items(analyzed_data: List[Dict[str, Any]]) -> Dict[str, dict]:
    """跨天去重，同一 PR/Issue 只保留最新状态"""
    seen = {}  # key: "repo/type/number"

    for day_data in analyzed_data:
        date = day_data['date']
        for repo_name, repo_data in day_data['data'].items():
            for issue in repo_data.get('issues', []):
                analysis = issue.get('analysis', {})
                if not analysis.get('is_relevant'):
                    continue
                key = f"{repo_name}/issue/{issue.get('number', 0)}"
                seen[key] = {
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
                    'first_seen': seen.get(key, {}).get('first_seen', date),
                    'last_seen': date,
                }

            for pr in repo_data.get('pulls', []):
                analysis = pr.get('analysis', {})
                if not analysis.get('is_relevant'):
                    continue
                key = f"{repo_name}/pr/{pr.get('number', 0)}"
                seen[key] = {
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
                    'first_seen': seen.get(key, {}).get('first_seen', date),
                    'last_seen': date,
                }

    return seen


def classify_item_to_themes(item: dict) -> List[str]:
    """将条目分类到技术主题"""
    text = (item.get('title', '') + ' ' + ' '.join(item.get('key_points', []))).lower()
    matched_themes = []

    for theme_name, theme_config in TECH_THEMES.items():
        for kw in theme_config['keywords']:
            if kw in text:
                matched_themes.append(theme_name)
                break

    return matched_themes if matched_themes else ['其他技术更新']


def collect_releases(analyzed_data: List[Dict[str, Any]]) -> Dict[str, List[dict]]:
    """收集去重后的版本发布信息"""
    releases = {}  # key: "repo/tag"

    for day_data in analyzed_data:
        for repo_name, repo_data in day_data['data'].items():
            for release in repo_data.get('releases', []):
                tag = release.get('tag_name', '')
                key = f"{repo_name}/{tag}"
                if key not in releases:
                    releases[key] = {
                        'repo': repo_name,
                        'tag': tag,
                        'name': release.get('name', ''),
                        'url': release.get('url', ''),
                        'body': release.get('body', ''),
                        'published_at': release.get('published_at', ''),
                    }

    # 按仓库分组
    by_repo = defaultdict(list)
    for r in releases.values():
        by_repo[r['repo']].append(r)

    return dict(by_repo)


def generate_theme_section(theme_name: str, theme_config: dict, items: List[dict]) -> str:
    """生成单个技术主题的汇总"""
    icon = theme_config['icon']
    lines = [f"### {icon} {theme_name} ({len(items)} 项)\n"]

    # 按评分排序
    items.sort(key=lambda x: x['score'], reverse=True)

    for item in items[:10]:
        status_cn = ''
        if item['type'] == 'PR':
            status_cn = '已合并' if item.get('merged_at') else ('已关闭' if item['state'] == 'closed' else '进行中')
        else:
            status_cn = '已关闭' if item['state'] == 'closed' else '开放中'

        lines.append(
            f"- **[{item['repo']}]** [{item['type']} #{item['number']}: {item['title']}]({item['url']}) "
            f"[{status_cn}] @{item['author']}"
        )
        if item.get('explanation'):
            for exp_line in item['explanation'].split('\n'):
                exp_line = exp_line.strip()
                if exp_line:
                    lines.append(f"  > {exp_line}")
        if item.get('metrics'):
            metrics_str = '、'.join(item['metrics'][:3])
            lines.append(f"  > 📊 性能数据: {metrics_str}")

    lines.append("")
    return "\n".join(lines)


def generate_weekly_summary(theme_counts: Dict[str, int], total_items: int,
                            merged_count: int) -> str:
    """生成本周技术趋势总结"""
    lines = ["## 本周技术趋势总结\n"]

    # 按数量排序
    sorted_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)

    if sorted_themes:
        top_theme = sorted_themes[0]
        lines.append(f"本周共追踪到 **{total_items}** 个去重后的相关技术更新，"
                     f"其中 **{merged_count}** 个 PR 已合并。\n")
        lines.append("**各技术方向活跃度:**\n")
        lines.append("| 技术方向 | 更新数量 | 占比 |")
        lines.append("|---------|---------|------|")

        for theme, count in sorted_themes:
            if count > 0:
                pct = count / total_items * 100 if total_items > 0 else 0
                icon = TECH_THEMES.get(theme, {}).get('icon', '')
                lines.append(f"| {icon} {theme} | {count} | {pct:.0f}% |")

        lines.append("")
        lines.append(f"**重点关注:** 本周 **{top_theme[0]}** 方向最为活跃（{top_theme[1]}项更新），"
                     f"建议重点跟进该方向的进展。\n")

    return "\n".join(lines)


def generate_weekly_report(
    start_date: str,
    end_date: str,
    daily_dir: str,
    output_dir: Optional[str] = None
) -> str:
    """生成周报（增强版：按技术主题分组、去重、全中文）"""
    reports = collect_daily_reports(daily_dir, start_date, end_date)

    if not reports:
        print(f"警告: 未找到 {start_date} 到 {end_date} 的日报")
        return ""

    print(f"收集到 {len(reports)} 天的日报")

    # 尝试加载分析后的 JSON 数据
    analyzed_dir = str(Path(daily_dir).parent.parent / 'analyzed')
    analyzed_data = load_analyzed_data(analyzed_dir, start_date, end_date)

    # 统计每日数据
    total_issues = sum(r['issue_count'] for r in reports)
    total_prs = sum(r['pr_count'] for r in reports)
    total_releases = sum(r['release_count'] for r in reports)

    lines = [
        f"# GitHub 项目进展周报 - {start_date} 至 {end_date}",
        "",
        f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"> 聚焦方向: 推理加速、显存优化、量化技术、投机解码与准确率提升",
        "",
        "---",
        "",
        "## 本周数据概览",
        "",
        f"- **统计周期**: {start_date} 至 {end_date}（共 {len(reports)} 天有数据）",
        f"- **相关 Issues 总计**: {total_issues} 个",
        f"- **相关 PRs 总计**: {total_prs} 个",
        f"- **版本发布**: {total_releases} 个",
        "",
        "### 每日更新量",
        "",
        "| 日期 | Issues | PRs | Releases |",
        "|------|--------|-----|----------|",
    ]

    for report in reports:
        lines.append(
            f"| {report['date']} | {report['issue_count']} | "
            f"{report['pr_count']} | {report['release_count']} |"
        )

    lines.extend(["", "---", ""])

    # 如果有分析数据，按技术主题汇总
    if analyzed_data:
        deduped = deduplicate_items(analyzed_data)
        all_items = list(deduped.values())
        merged_count = sum(1 for item in all_items if item.get('merged_at'))

        # 按技术主题分组
        theme_items = defaultdict(list)
        for item in all_items:
            themes = classify_item_to_themes(item)
            for theme in themes:
                theme_items[theme].append(item)

        # 统计
        theme_counts = {theme: len(items) for theme, items in theme_items.items()}

        # 技术趋势总结
        lines.append(generate_weekly_summary(theme_counts, len(all_items), merged_count))
        lines.extend(["---", ""])

        # 各技术方向详情
        lines.append("## 各技术方向详情\n")
        for theme_name, theme_config in TECH_THEMES.items():
            items = theme_items.get(theme_name, [])
            if items:
                lines.append(generate_theme_section(theme_name, theme_config, items))

        # 其他
        other_items = theme_items.get('其他技术更新', [])
        if other_items:
            lines.append(generate_theme_section('其他技术更新', {'icon': '📝'}, other_items))

        # 版本发布汇总
        releases_by_repo = collect_releases(analyzed_data)
        if releases_by_repo:
            lines.extend(["---", "", "## 本周版本发布\n"])
            for repo_name, releases in releases_by_repo.items():
                lines.append(f"### {repo_name}\n")
                for r in releases:
                    pub_date = r['published_at'][:10] if r['published_at'] else '未知'
                    lines.append(f"- **[{r['tag']}]({r['url']})** {r['name']}（发布于 {pub_date}）")
                    # 提取 release highlights
                    if r.get('body'):
                        body_lines = r['body'].split('\n')
                        highlights = []
                        for bl in body_lines:
                            bl = bl.strip()
                            if re.match(r'^[-*]\s+', bl) or re.match(r'^\d+\.\s+', bl):
                                cleaned = re.sub(r'^[-*\d.]+\s+', '', bl).strip()
                                if 10 < len(cleaned) < 200:
                                    highlights.append(cleaned)
                                    if len(highlights) >= 5:
                                        break
                        if highlights:
                            lines.append(f"  > 主要变更:")
                            for h in highlights:
                                lines.append(f"  > - {h}")
                        else:
                            snippet = r['body'][:150].replace('\n', ' ').strip()
                            if snippet:
                                lines.append(f"  > {snippet}...")
                lines.append("")

    else:
        # 回退：从日报 markdown 中提取（兼容旧格式）
        lines.append("## 本周项目关键进展\n")
        lines.append("*（未找到分析数据，以下从日报中提取）*\n")

        github_updates = _extract_updates_from_reports(reports)
        for repo_name, updates in github_updates.items():
            if not updates:
                continue
            lines.append(f"### {repo_name}\n")
            for update in updates[:8]:
                lines.append(f"- **{update['date']}** [{update['type_cn']}] {update['content'][:150]}")
            lines.append("")

    # 下周展望
    lines.extend([
        "",
        "---",
        "",
        "## 下周关注方向",
        "",
    ])

    if analyzed_data and theme_counts:
        sorted_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)
        for theme, count in sorted_themes[:3]:
            icon = TECH_THEMES.get(theme, {}).get('icon', '📌')
            lines.append(f"- {icon} **{theme}**: 本周活跃度高（{count}项），建议持续跟踪")
        lines.append(f"- 📦 关注各项目的新版本发布与性能回归测试结果")
        lines.append(f"- 🔬 跟进已合并 PR 的实际效果反馈")
    else:
        lines.extend([
            "- 继续关注各项目的 Issue 和 PR 动态",
            "- 跟踪版本发布和性能优化进展",
            "- 关注推理加速和准确率提升相关的新技术",
        ])

    lines.extend([
        "",
        "---",
        "",
        "*本报告聚焦推理加速、显存优化、量化技术、投机解码与准确率提升等核心技术方向*",
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


def _extract_updates_from_reports(reports: List[Dict[str, Any]]) -> Dict[str, List[dict]]:
    """从日报 markdown 中提取更新（回退方案）"""
    updates = defaultdict(list)

    type_map = {
        'Issues': '问题',
        'PRs': 'PR',
        '版本发布': '发布',
    }

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

            for section_name, type_cn in type_map.items():
                pattern = rf'### .*{re.escape(section_name)}.*\n(.*?)(?=\n###|\n---|\Z)'
                section_match = re.search(pattern, repo_content, re.DOTALL)
                if section_match:
                    section_lines = section_match.group(1).strip().split('\n')
                    for line in section_lines:
                        line = line.strip()
                        if line.startswith('- '):
                            updates[repo_name].append({
                                'date': date,
                                'type_cn': type_cn,
                                'content': line[2:].strip(),
                            })

    return dict(updates)


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
