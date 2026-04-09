#!/usr/bin/env python3
"""
快速分析脚本 - 基于关键词匹配筛选与推理加速/准确率相关的内容
无需调用 LLM API，使用关键词匹配进行快速筛选
"""

import json
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

# 排除关键词（降低相关性）
EXCLUDE_KEYWORDS = [
    'test', 'testing', 'unittest', 'ci', 'pipeline', 'infra', 'chore',
    'bump version', 'lock file', 'attribution', 'documentation', 'doc',
    'typo', 'format', 'lint', 'style', 'refactor', 'clean up', 'cleanup',
    'revert', 'merge branch', 'wip', 'work in progress'
]


def calculate_relevance(text: str) -> tuple:
    """
    计算文本与推理加速/准确率的相关性

    返回: (is_relevant, score, matched_keywords)
    """
    if not text:
        return False, 0.0, []

    text_lower = text.lower()

    exclude_count = sum(1 for kw in EXCLUDE_KEYWORDS if kw in text_lower)
    if exclude_count >= 2:
        return False, 0.0, []

    matched = []
    for kw in PERFORMANCE_KEYWORDS:
        if kw in text_lower:
            matched.append(kw)

    score = len(matched) * 0.2

    high_value = ['performance', 'optimize', 'latency', 'throughput', 'kv cache',
                  'quantization', 'fp8', 'nvfp4', 'speculative', 'moe',
                  'accuracy', 'acceptance rate']
    for kw in high_value:
        if kw in text_lower:
            score += 0.3

    score = min(score, 1.0)
    is_relevant = score >= 0.3 or len(matched) >= 2

    return is_relevant, score, matched


def generate_chinese_explanation(text: str, matched_keywords: list, item_type: str = "issue") -> str:
    """基于匹配的关键词生成中文解释"""
    keyword_explanations = {
        'performance': '优化了推理性能',
        'optimize': '对推理流程进行了优化',
        'optimization': '实现了性能优化',
        'latency': '降低了推理延迟',
        'throughput': '提高了系统吞吐量',
        'kv cache': '优化了KV缓存机制',
        'memory': '改善了内存使用',
        'quantization': '应用了量化技术',
        'fp8': '支持FP8精度格式',
        'speculative': '引入了投机解码',
        'parallel': '优化了并行处理',
        'disaggregated': '采用了分离式架构',
        'attention': '优化了注意力计算',
        'flash attention': '集成了FlashAttention',
        'radix attention': '优化了Radix Attention',
        'batch': '优化了批处理策略',
        'scheduler': '实现了高效调度器',
        'moe': '支持混合专家模型',
        'accuracy': '提升了推理准确率',
        'acceptance rate': '提高了投机解码接受率',
        'correctness': '改善了推理正确性',
        'benchmark': '提供了性能基准测试',
        'serving': '优化了模型服务',
        'deployment': '改进了部署方案',
        'config': '优化了配置管理',
    }

    unique_explanations = set()
    for kw in matched_keywords:
        if kw in keyword_explanations:
            unique_explanations.add(keyword_explanations[kw])

    if unique_explanations:
        explanations = list(unique_explanations)[:2]

        if 'fix' in text.lower() or 'bug' in text.lower():
            explanations.append('修复了相关问题，提升了系统稳定性')
        elif 'feat' in text.lower() or 'feature' in text.lower():
            explanations.append('增强了框架功能，扩展了应用场景')
        else:
            explanations.append('有助于提升LLM推理的整体性能和效率')

        return '；'.join(explanations[:3]) + '。'

    if 'fix' in text.lower() or 'bug' in text.lower():
        return '修复了推理过程中的问题，提升了系统稳定性和正确性。'
    elif 'add' in text.lower() or 'support' in text.lower():
        return '新增功能支持，扩展了推理引擎的能力和适用范围。'
    elif 'optimize' in text.lower() or 'improve' in text.lower():
        return '优化了推理性能，有助于提升吞吐量和降低延迟。'
    else:
        return '与LLM推理优化相关，有助于提升模型部署和推理效率。'


def analyze_github_data(github_data: dict) -> dict:
    """分析 GitHub 数据，标记相关性"""
    analyzed = {}

    for repo_name, repo_data in github_data.items():
        analyzed[repo_name] = repo_data.copy()

        # 分析 issues
        analyzed_issues = []
        for issue in repo_data.get('issues', []):
            text = issue.get('title', '') + ' ' + issue.get('body', '')
            is_relevant, score, matched = calculate_relevance(text)

            issue_copy = issue.copy()
            issue_copy['analysis'] = {
                'is_relevant': is_relevant,
                'relevance_score': score,
                'category': 'performance' if is_relevant else 'other',
                'summary': issue.get('title', '')[:100],
                'key_points': matched[:5],
                'impact_level': 'high' if score >= 0.7 else ('medium' if score >= 0.4 else 'low'),
                'chinese_explanation': generate_chinese_explanation(text, matched, 'issue') if is_relevant else ''
            }
            analyzed_issues.append(issue_copy)
        analyzed[repo_name]['issues'] = analyzed_issues

        # 分析 releases
        analyzed_releases = []
        for release in repo_data.get('releases', []):
            text = release.get('name', '') + ' ' + release.get('body', '')
            is_relevant, score, matched = calculate_relevance(text)

            release_copy = release.copy()
            release_copy['analysis'] = {
                'is_relevant': is_relevant,
                'relevance_score': score,
                'category': 'feature' if is_relevant else 'other',
                'summary': release.get('name', ''),
                'key_points': matched[:5],
                'impact_level': 'high' if score >= 0.7 else ('medium' if score >= 0.4 else 'low'),
                'chinese_explanation': generate_chinese_explanation(text, matched, 'release') if is_relevant else ''
            }
            analyzed_releases.append(release_copy)
        analyzed[repo_name]['releases'] = analyzed_releases

        # 分析 PRs
        analyzed_pulls = []
        for pr in repo_data.get('pulls', []):
            text = pr.get('title', '') + ' ' + pr.get('body', '')
            is_relevant, score, matched = calculate_relevance(text)

            pr_copy = pr.copy()
            pr_copy['analysis'] = {
                'is_relevant': is_relevant,
                'relevance_score': score,
                'category': 'performance' if is_relevant else 'other',
                'summary': pr.get('title', '')[:100],
                'key_points': matched[:5],
                'impact_level': 'high' if score >= 0.7 else ('medium' if score >= 0.4 else 'low'),
                'chinese_explanation': generate_chinese_explanation(text, matched, 'pr') if is_relevant else ''
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
