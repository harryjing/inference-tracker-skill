#!/usr/bin/env python3
"""
快速分析脚本 - 基于关键词匹配筛选与推理加速/准确率相关的内容
无需调用 LLM API，使用关键词匹配进行快速筛选

v2: 增强描述生成（基于 title/body 摘要）+ 多维评分 + 量化指标提取
"""

import json
import re
from pathlib import Path

# 关键词配置
PERFORMANCE_KEYWORDS = [
    # 性能相关
    'performance', 'optimize', 'optimization', 'speed', 'fast', 'faster', 'latency',
    'throughput', 'efficient', 'efficiency', 'improve', 'accelerate', 'boost',
    'reduce', 'decrease', 'lower', 'minimize',

    # 内存相关
    'kv cache', 'kvcache', 'cache', 'memory', 'quantize', 'quantization',
    'fp8', 'fp4', 'int8', 'int4', 'nvfp4', 'compression', 'compress',
    'offload', 'swap', 'memory efficient',

    # 并行/分布式
    'parallel', 'tensor parallel', 'pipeline parallel', 'disaggregated',
    'disaggregation', 'prefill-decode', 'pd disagg', 'speculative',
    'speculation', 'draft', 'eagle', 'lookahead',

    # Attention 优化
    'attention', 'flash attention', 'flashattention', 'mla', 'gqa', 'mqa',
    'sliding window', 'sparse attention', 'ring attention', 'radix attention',

    # 调度/批处理
    'batch', 'scheduling', 'scheduler', 'continuous batching', 'inflight',

    # MoE 相关
    'moe', 'mixture of experts', 'expert', 'all-to-all', 'a2a',

    # 准确率相关
    'accuracy', 'correctness', 'precision', 'recall', 'quality',
    'acceptance rate', 'token match', 'exact match',

    # 新功能/模型支持
    'support', 'add', 'new model', 'new feature', 'implement',
    'benchmark', 'serving', 'deployment', 'config',
]

HIGH_VALUE_KEYWORDS = [
    'performance', 'optimize', 'latency', 'throughput', 'kv cache',
    'quantization', 'fp8', 'nvfp4', 'speculative', 'moe',
    'accuracy', 'acceptance rate',
]

# 排除关键词（降低相关性）
EXCLUDE_KEYWORDS = [
    'test', 'testing', 'unittest', 'ci', 'pipeline', 'infra', 'chore',
    'bump version', 'lock file', 'attribution', 'documentation', 'doc',
    'typo', 'format', 'lint', 'style', 'refactor', 'clean up', 'cleanup',
    'revert', 'merge branch', 'wip', 'work in progress'
]

# 高权重标签
BOOST_LABELS = {'performance', 'enhancement', 'feature', 'optimization', 'perf'}

# 量化指标正则
METRIC_PATTERNS = [
    # 百分比变化: "30% faster", "reduce 50%", "2x speedup"
    re.compile(r'(\d+(?:\.\d+)?)\s*%\s*(faster|slower|improvement|reduction|decrease|increase|speedup|less|more)', re.I),
    re.compile(r'(\d+(?:\.\d+)?)\s*[xX]\s*(speedup|faster|improvement|throughput)', re.I),
    re.compile(r'(reduce|decrease|lower|cut|save)s?\s+(?:by\s+)?(\d+(?:\.\d+)?)\s*%', re.I),
    # 绝对数值: "latency from 200ms to 100ms"
    re.compile(r'from\s+(\d+(?:\.\d+)?)\s*(ms|s|sec|gb|mb|tokens?/s)\s+to\s+(\d+(?:\.\d+)?)\s*\2', re.I),
    # 模型规模: "70B", "405B parameters"
    re.compile(r'(\d+)[bB]\s*(?:param|model|parameter)?', re.I),
    # GPU 内存: "saves 2GB", "peak memory 8GB"
    re.compile(r'(\d+(?:\.\d+)?)\s*(GB|MB|GiB|MiB)\s*(memory|VRAM|GPU|peak|saving|saved|reduction)', re.I),
    re.compile(r'(peak|GPU|memory)\s*(usage|consumption)?\s*(?:of|:)?\s*(\d+(?:\.\d+)?)\s*(GB|MB)', re.I),
]


def extract_metrics(text: str) -> list:
    """从文本中提取量化性能指标"""
    if not text:
        return []

    metrics = []
    for pattern in METRIC_PATTERNS:
        for match in pattern.finditer(text):
            metric_str = match.group(0).strip()
            if len(metric_str) > 5 and metric_str not in metrics:
                metrics.append(metric_str)

    return metrics[:5]


def classify_change_type(title: str, body: str) -> str:
    """根据 title 前缀和内容判断变更类型"""
    title_lower = title.lower().strip()

    # 常见前缀模式
    prefix_map = {
        '[perf]': '性能优化',
        '[performance]': '性能优化',
        '[feature]': '新功能',
        '[feat]': '新功能',
        '[fix]': 'Bug修复',
        '[bug]': 'Bug修复',
        '[bugfix]': 'Bug修复',
        '[refactor]': '重构',
        '[amd]': 'AMD适配',
        '[npu]': 'NPU适配',
        '[cpu]': 'CPU适配',
        '[mlx]': 'MLX适配',
        '[diffusion]': 'Diffusion',
        '[whisper]': 'Whisper',
        '[sgl]': 'SGLang核心',
    }

    for prefix, label in prefix_map.items():
        if title_lower.startswith(prefix):
            return label

    # 基于关键词推断
    if any(w in title_lower for w in ['fix', 'bug', 'crash', 'deadlock', 'regression']):
        return 'Bug修复'
    if any(w in title_lower for w in ['feat:', 'add ', 'support ', 'implement', 'enable']):
        return '新功能'
    if any(w in title_lower for w in ['perf', 'optim', 'speed', 'fast', 'overlap',
                                       'reduce memory', 'reduce latency', 'reduce peak',
                                       'reduce gpu', 'memory spike', 'memory efficient']):
        return '性能优化'
    if any(w in title_lower for w in ['instruction', 'guide', 'how to', 'tutorial']):
        return '指南/教程'
    if any(w in title_lower for w in ['update', 'upgrade', 'bump']):
        return '版本更新'

    # 从 body 中补充判断
    body_lower = body.lower()[:500] if body else ''
    if any(w in body_lower for w in ['this pr optimizes', 'this pr improves', 'this pr reduces',
                                      'speedup', 'throughput improvement', 'latency reduction']):
        return '性能优化'

    return '更新'


def extract_title_summary(title: str) -> str:
    """清理 title，去除前缀标签，保留核心描述"""
    # 去除 [xxx] 前缀
    cleaned = re.sub(r'^\s*\[[^\]]*\]\s*', '', title).strip()
    # 去除 "feat:", "fix:" 等 conventional commit 前缀
    cleaned = re.sub(r'^(feat|fix|perf|chore|refactor|docs|ci|test|build)\s*[:\(]\s*', '', cleaned, flags=re.I).strip()
    # 去除末尾省略号
    cleaned = cleaned.rstrip('…').rstrip('.')
    return cleaned if cleaned else title


def extract_body_context(body: str, title: str, max_sentences: int = 2) -> str:
    """从 body 中提取最有价值的上下文信息，补充 title 不包含的内容"""
    if not body:
        return ''

    # 清理 HTML 和 markdown
    text = re.sub(r'<[^>]+>', ' ', body)
    text = re.sub(r'```[\s\S]*?```', '', text)  # 去除代码块
    text = re.sub(r'#{1,6}\s+', '', text)  # 去除 markdown 标题
    text = re.sub(r'\[([^\]]*)\]\([^\)]*\)', r'\1', text)  # 链接转文本
    text = re.sub(r'- \[[ x]\].*', '', text)  # 去除 checklist
    text = re.sub(r'\s+', ' ', text).strip()

    # 排除模板内容
    skip_phrases = [
        'checklist', 'searched related issues', 'bug persists',
        'please use english', 'otherwise, it will be closed',
        'describe the bug', 'minimal reproducible', 'environment info',
    ]

    sentences = re.split(r'[.。\n]+', text)
    useful = []
    title_lower = title.lower()

    for s in sentences:
        s = s.strip()
        if len(s) < 15 or len(s) > 200:
            continue
        s_lower = s.lower()
        if any(skip in s_lower for skip in skip_phrases):
            continue
        # 避免重复 title 内容
        if len(set(s_lower.split()) & set(title_lower.split())) > len(s_lower.split()) * 0.6:
            continue
        useful.append(s)
        if len(useful) >= max_sentences:
            break

    return '。'.join(useful[:max_sentences])


def calculate_relevance(text: str, labels: list = None, comments: int = 0,
                        merged_at: str = None, item_type: str = 'issue') -> tuple:
    """
    计算文本与推理加速/准确率的相关性（增强版）

    返回: (is_relevant, score, matched_keywords)
    """
    if not text:
        return False, 0.0, []

    text_lower = text.lower()
    labels = labels or []
    labels_lower = {l.lower() for l in labels}

    exclude_count = sum(1 for kw in EXCLUDE_KEYWORDS if kw in text_lower)
    if exclude_count >= 2:
        return False, 0.0, []

    matched = []
    for kw in PERFORMANCE_KEYWORDS:
        if kw in text_lower:
            matched.append(kw)

    # 基础关键词分数
    score = len(matched) * 0.2

    # 高价值关键词额外加分
    for kw in HIGH_VALUE_KEYWORDS:
        if kw in text_lower:
            score += 0.3

    # 标签加权
    if labels_lower & BOOST_LABELS:
        score += 0.2

    # 评论数加权（社区关注度）
    if comments > 10:
        score += 0.2
    elif comments > 5:
        score += 0.1

    # 已合并 PR 加权
    if item_type == 'pr' and merged_at:
        score += 0.15

    # body 中包含 benchmark 数据
    if any(w in text_lower for w in ['benchmark', 'throughput:', 'latency:', 'tokens/s', 'tok/s', 'speedup']):
        score += 0.15

    score = min(score, 1.0)
    is_relevant = score >= 0.3 or len(matched) >= 2

    return is_relevant, score, matched


def generate_chinese_explanation(title: str, body: str, matched_keywords: list,
                                  item_type: str = 'issue', author: str = '') -> str:
    """基于 title 和 body 内容生成具体的中文摘要描述"""
    change_type = classify_change_type(title, body)
    core_title = extract_title_summary(title)
    body_context = extract_body_context(body, title)
    metrics = extract_metrics(body)

    parts = []

    # 变更类型标签
    parts.append(f'[{change_type}]')

    # 核心描述：优先用清理后的 title
    parts.append(core_title)

    # 补充 body 上下文（如果 title 不够具体）
    if body_context and len(core_title) < 40:
        parts.append(f'— {body_context}')

    # 量化指标
    if metrics:
        metric_str = '、'.join(metrics[:3])
        parts.append(f'(指标: {metric_str})')

    return ' '.join(parts)


def analyze_github_data(github_data: dict) -> dict:
    """分析 GitHub 数据，标记相关性"""
    analyzed = {}

    for repo_name, repo_data in github_data.items():
        analyzed[repo_name] = repo_data.copy()

        # 分析 issues
        analyzed_issues = []
        for issue in repo_data.get('issues', []):
            text = issue.get('title', '') + ' ' + issue.get('body', '')
            labels = issue.get('labels', [])
            comments = issue.get('comments', 0)

            is_relevant, score, matched = calculate_relevance(
                text, labels=labels, comments=comments, item_type='issue'
            )

            issue_copy = issue.copy()
            issue_copy['analysis'] = {
                'is_relevant': is_relevant,
                'relevance_score': round(score, 2),
                'category': 'performance' if is_relevant else 'other',
                'summary': issue.get('title', '')[:100],
                'key_points': matched[:5],
                'impact_level': 'high' if score >= 0.7 else ('medium' if score >= 0.4 else 'low'),
                'chinese_explanation': generate_chinese_explanation(
                    issue.get('title', ''), issue.get('body', ''),
                    matched, 'issue', issue.get('author', '')
                ) if is_relevant else '',
                'metrics': extract_metrics(issue.get('body', '')) if is_relevant else [],
            }
            analyzed_issues.append(issue_copy)
        analyzed[repo_name]['issues'] = analyzed_issues

        # 分析 releases
        analyzed_releases = []
        for release in repo_data.get('releases', []):
            text = release.get('name', '') + ' ' + release.get('body', '')
            is_relevant, score, matched = calculate_relevance(text, item_type='release')

            release_copy = release.copy()
            release_copy['analysis'] = {
                'is_relevant': is_relevant,
                'relevance_score': round(score, 2),
                'category': 'feature' if is_relevant else 'other',
                'summary': release.get('name', ''),
                'key_points': matched[:5],
                'impact_level': 'high' if score >= 0.7 else ('medium' if score >= 0.4 else 'low'),
                'chinese_explanation': generate_chinese_explanation(
                    release.get('name', ''), release.get('body', ''),
                    matched, 'release', release.get('author', '')
                ) if is_relevant else '',
                'metrics': [],
            }
            analyzed_releases.append(release_copy)
        analyzed[repo_name]['releases'] = analyzed_releases

        # 分析 PRs
        analyzed_pulls = []
        for pr in repo_data.get('pulls', []):
            text = pr.get('title', '') + ' ' + pr.get('body', '')
            labels = pr.get('labels', [])
            merged_at = pr.get('merged_at')

            is_relevant, score, matched = calculate_relevance(
                text, labels=labels, merged_at=merged_at, item_type='pr'
            )

            pr_copy = pr.copy()
            pr_copy['analysis'] = {
                'is_relevant': is_relevant,
                'relevance_score': round(score, 2),
                'category': 'performance' if is_relevant else 'other',
                'summary': pr.get('title', '')[:100],
                'key_points': matched[:5],
                'impact_level': 'high' if score >= 0.7 else ('medium' if score >= 0.4 else 'low'),
                'chinese_explanation': generate_chinese_explanation(
                    pr.get('title', ''), pr.get('body', ''),
                    matched, 'pr', pr.get('author', '')
                ) if is_relevant else '',
                'metrics': extract_metrics(pr.get('body', '')) if is_relevant else [],
            }
            analyzed_pulls.append(pr_copy)
        analyzed[repo_name]['pulls'] = analyzed_pulls

    return analyzed


def main():
    import argparse

    parser = argparse.ArgumentParser(description='快速分析 GitHub 数据')
    parser.add_argument('--input', type=str, required=True, help='GitHub 原始数据 JSON 文件')
    parser.add_argument('--output', type=str, required=True, help='分析结果输出文件')
    parser.add_argument('--stats', action='store_true', help='只显示统计信息')

    args = parser.parse_args()

    with open(args.input, 'r', encoding='utf-8') as f:
        github_data = json.load(f)

    analyzed = analyze_github_data(github_data)

    total_relevant = 0
    for repo_name, repo_data in analyzed.items():
        relevant_issues = sum(1 for i in repo_data.get('issues', []) if i.get('analysis', {}).get('is_relevant'))
        relevant_releases = sum(1 for r in repo_data.get('releases', []) if r.get('analysis', {}).get('is_relevant'))
        relevant_pulls = sum(1 for p in repo_data.get('pulls', []) if p.get('analysis', {}).get('is_relevant'))

        total = relevant_issues + relevant_releases + relevant_pulls
        total_relevant += total

        if total > 0:
            print(f"{repo_name}: {relevant_issues} issues, {relevant_releases} releases, {relevant_pulls} PRs")

    print(f"\n总计找到 {total_relevant} 个与推理加速/准确率相关的更新")

    if not args.stats:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(analyzed, f, ensure_ascii=False, indent=2)
        print(f"分析结果已保存到: {args.output}")


if __name__ == '__main__':
    main()
