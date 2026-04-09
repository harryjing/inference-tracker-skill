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


# 英文技术术语 → 中文翻译映射
TECH_TERM_MAP = {
    # KV Cache 相关
    'kv cache': 'KV缓存', 'kvcache': 'KV缓存', 'cache': '缓存',
    'prefill': '预填充', 'decode': '解码', 'prefill-decode': '预填充-解码分离',
    'pd disagg': '预填充解码分离', 'disaggregated': '分离式', 'disaggregation': '分离架构',
    'radix attention': '基数注意力', 'radix tree': '基数树',
    'hicache': '分层缓存(HiCache)', 'hisparse': '稀疏缓存(hiSparse)',
    'offload': '卸载到主机内存', 'swap': '交换(GPU↔CPU)', 'h2d': '主机到设备传输',
    'd2h': '设备到主机传输', 'dtod': '设备间拷贝',
    # 量化相关
    'quantization': '量化', 'quantize': '量化', 'fp8': 'FP8量化', 'fp4': 'FP4量化',
    'int8': 'INT8量化', 'int4': 'INT4量化', 'nvfp4': 'NVFP4量化',
    'awq': 'AWQ量化', 'gptq': 'GPTQ量化', 'compression': '压缩',
    # 注意力机制
    'attention': '注意力机制', 'flash attention': 'FlashAttention',
    'flashattention': 'FlashAttention', 'flashinfer': 'FlashInfer',
    'mla': '多头潜在注意力(MLA)', 'gqa': '分组查询注意力(GQA)',
    'mqa': '多查询注意力(MQA)', 'sliding window': '滑动窗口注意力',
    'sparse attention': '稀疏注意力', 'ring attention': '环形注意力',
    'sdpa': '缩放点积注意力(SDPA)',
    # 投机解码
    'speculative': '投机解码', 'speculation': '投机解码', 'draft': '草稿模型',
    'eagle': 'EAGLE投机解码', 'eagle3': 'EAGLE3投机解码',
    'lookahead': '前瞻解码', 'mtp': '多Token预测(MTP)',
    'suffix decoding': '后缀解码', 'acceptance rate': '接受率',
    # 并行与分布式
    'tensor parallel': '张量并行(TP)', 'pipeline parallel': '流水线并行(PP)',
    'data parallel': '数据并行(DP)', 'expert parallel': '专家并行(EP)',
    'parallel': '并行', 'distributed': '分布式',
    'all-to-all': 'All-to-All通信', 'a2a': 'All-to-All通信',
    'allreduce': 'AllReduce通信',
    # MoE 相关
    'moe': '混合专家模型(MoE)', 'mixture of experts': '混合专家模型',
    'expert': '专家层', 'scattered mlp': '分散式MLP',
    # 调度与批处理
    'scheduler': '调度器', 'scheduling': '调度', 'batch': '批处理',
    'continuous batching': '连续批处理', 'inflight': '在飞批处理',
    # 性能相关
    'latency': '延迟', 'throughput': '吞吐量', 'ttft': '首Token延迟(TTFT)',
    'tpot': '每Token延迟(TPOT)', 'memory': '内存/显存',
    'oom': '显存溢出(OOM)', 'peak memory': '峰值显存',
    'memory spike': '显存峰值', 'memory efficient': '显存高效',
    'speedup': '加速', 'overlap': '计算通信重叠',
    # 模型与架构
    'rope': '旋转位置编码(RoPE)', 'checkpoint': '检查点',
    'checkpoint prefetch': '检查点预取', 'gemm': '矩阵乘法(GEMM)',
    # 平台
    'rocm': 'AMD ROCm', 'cuda': 'NVIDIA CUDA', 'blackwell': 'Blackwell架构',
    'benchmark': '基准测试', 'serving': '推理服务',
    'deployment': '部署', 'helm': 'Helm部署',
    # 模型名
    'deepseek': 'DeepSeek', 'kimi-vl': 'Kimi-VL', 'llama': 'LLaMA',
    'diffusion': '扩散模型', 'vlm': '视觉语言模型(VLM)',
}


def identify_tech_domain(title: str, body: str, matched_keywords: list) -> str:
    """识别主要技术领域，返回中文标签"""
    combined = (title + ' ' + ' '.join(matched_keywords)).lower()

    # 按优先级匹配，先匹配更具体的
    domain_rules = [
        (['speculative', 'speculation', 'mtp', 'eagle', 'draft', 'suffix decoding', 'lookahead'], '投机解码'),
        (['kv cache', 'kvcache', 'hicache', 'hisparse', 'radix'], 'KV缓存'),
        (['quantization', 'quantize', 'fp8', 'fp4', 'int8', 'int4', 'nvfp4', 'awq', 'gptq'], '量化'),
        (['attention', 'flash attention', 'flashattention', 'flashinfer', 'mla', 'gqa', 'sdpa', 'swa'], '注意力机制'),
        (['moe', 'mixture of experts', 'expert', 'all-to-all', 'a2a'], 'MoE'),
        (['parallel', 'tensor parallel', 'disaggregated', 'disaggregation', 'allreduce'], '分布式推理'),
        (['scheduler', 'scheduling', 'continuous batching'], '调度'),
        (['memory', 'oom', 'offload', 'swap'], '显存管理'),
        (['cache', 'prefetch'], '缓存优化'),
        (['batch', 'batching'], '批处理'),
        (['benchmark', 'support matrix'], '基准测试'),
        (['deploy', 'deployment', 'helm', 'serving'], '部署'),
        (['diffusion'], '扩散模型'),
        (['amd', 'rocm'], 'AMD平台'),
        (['rope'], '位置编码'),
    ]

    for keywords, domain in domain_rules:
        for kw in keywords:
            if kw in combined:
                return domain

    return '推理优化'


def generate_action_description(title: str, body: str) -> str:
    """从 title 和 body 中提取核心动作，生成中文动作描述"""
    combined = (title + ' ' + (body or '')[:500]).lower()

    # 动作模式匹配，越具体越优先
    action_patterns = [
        # 消除/避免
        (r'eliminate\s+.*?copy', '消除数据拷贝开销'),
        (r'eliminate\s+.*?allocation', '消除内存分配开销'),
        (r'avoid\s+.*?recompute', '避免重复计算'),
        (r'avoid\s+.*?copy', '避免数据拷贝'),
        # 重叠/并行
        (r'overlap\s+.*?transfer.*?attention', '将数据传输与注意力计算重叠执行'),
        (r'overlap\s+.*?h2d', '将主机到设备传输与计算重叠'),
        (r'overlap\s+.*?compute', '将通信与计算重叠'),
        # 缓存
        (r'cache\s+.*?rope', '缓存RoPE位置编码避免每步重算'),
        (r'cache\s+.*?coord', '缓存坐标信息避免重复计算'),
        (r'incremental\s+.*?kv\s*cache\s+.*?transfer', '增量传输KV缓存降低通信量'),
        (r'kv\s*cache\s+.*?capacity\s+.*?check', '检查KV缓存容量防止超额分配'),
        (r'kv\s*cache\s+.*?transfer', '优化KV缓存传输效率'),
        (r'prefetch.*?buffer', '添加预取缓冲区减少内存重复占用'),
        # 投机解码
        (r'speculative\s+decoding.*?hisparse', '在hiSparse稀疏缓存上支持投机解码'),
        (r'mtp.*?speculative', '结合MTP多Token预测与投机解码'),
        (r'suffix\s+decoding', '实现基于后缀树的免草稿模型投机解码'),
        # 量化
        (r'awq.*?refactor', '重构AWQ量化方案，分离kernel调用与权重初始化'),
        (r'nvfp4.*?backend', '为NVFP4量化添加PyTorch后端支持'),
        (r'quantization\s+refactor', '重构量化框架，提升可扩展性'),
        # 显存
        (r'oom.*?multi.?image', '修复多图推理显存溢出问题'),
        (r'oom', '修复显存溢出问题'),
        (r'reduce.*?peak.*?memory', '降低峰值GPU显存占用'),
        (r'reduce.*?memory.*?spike', '消除显存使用峰值'),
        (r'memory\s+spike', '解决训练/推理显存峰值问题'),
        # 通信
        (r'allreduce\s+fusion', '优化AllReduce通信融合策略'),
        (r'all.to.all\s+sharding', '使用All-to-All分片降低通信开销'),
        # 部署
        (r'checkpoint\s+prefetch', '为网络文件系统添加检查点协调预取'),
        (r'deployment\s+target', '扩展部署目标支持'),
        (r'llm-d\s+deployment', '添加llm-d推理部署目标支持'),
        # 平台支持
        (r'rocm.*?fa[23]', '在AMD ROCm平台上启用FlashAttention支持'),
        (r'suffix\s+decoding.*?rocm', '在AMD ROCm平台上添加后缀解码支持'),
        # 基准测试
        (r'support\s+matrix', '更新兼容性测试矩阵'),
        (r'collector.*?data', '更新基准数据采集器和测试数据'),
        # 通用
        (r'add\s+support\s+for', '添加新功能支持'),
        (r'fix\s+.*?deployment', '修复部署相关问题'),
    ]

    for pattern, description in action_patterns:
        if re.search(pattern, combined):
            return description

    return ''


def generate_technical_insight(title: str, body: str, matched_keywords: list) -> str:
    """生成影响说明：这个变更的实际价值和影响"""
    combined = (title + ' ' + (body or '')[:1500]).lower()

    insights = []

    # 性能影响
    if any(w in combined for w in ['eliminate', 'avoid', 'remove', 'skip']) and any(w in combined for w in ['copy', 'recompute', 'allocation']):
        insights.append('减少冗余操作，直接提升推理吞吐/降低延迟')

    if 'overlap' in combined and any(w in combined for w in ['transfer', 'h2d', 'compute', 'attention']):
        insights.append('隐藏数据搬运延迟，提升GPU利用率')

    if 'oom' in combined or 'memory spike' in combined or 'memory growth' in combined:
        insights.append('提升大模型/多图场景推理稳定性')

    if 'speculative' in combined or 'mtp' in combined:
        insights.append('加速自回归解码，降低生成延迟')

    if 'kv cache' in combined and ('disagg' in combined or 'transfer' in combined or 'incremental' in combined):
        insights.append('提升预填充-解码分离架构效率')

    if any(w in combined for w in ['quantization', 'awq', 'nvfp4', 'fp8']):
        insights.append('降低模型显存占用和计算量')

    if 'all-to-all' in combined or 'allreduce' in combined:
        insights.append('优化多GPU通信效率')

    if 'benchmark' in combined or 'support matrix' in combined:
        insights.append('为模型选型和配置优化提供数据参考')

    if ('deployment' in combined or 'helm' in combined) and ('target' in combined or 'llm-d' in combined):
        insights.append('简化推理服务部署流程')

    if 'batch' in combined and ('capacity' in combined or 'oversubscription' in combined):
        insights.append('防止因批次过大导致OOM崩溃')

    if 'checkpoint' in combined and 'prefetch' in combined:
        insights.append('加速模型加载，减少冷启动时间')

    return insights[0] if insights else ''


def generate_chinese_explanation(title: str, body: str, matched_keywords: list,
                                  item_type: str = 'issue', author: str = '') -> str:
    """基于 title 和 body 内容生成全中文技术摘要"""
    change_type = classify_change_type(title, body)
    tech_domain = identify_tech_domain(title, body, matched_keywords)
    action_desc = generate_action_description(title, body)
    insight = generate_technical_insight(title, body, matched_keywords)
    metrics = extract_metrics(body)

    # 构造完整中文描述
    parts = [f'[{change_type}]']

    if action_desc:
        parts.append(f'【{tech_domain}】{action_desc}')
    else:
        # 回退：用原标题 + 技术领域
        core_title = extract_title_summary(title)
        parts.append(f'【{tech_domain}】{core_title}')

    if metrics:
        metric_str = '、'.join(metrics[:3])
        parts.append(f'（{metric_str}）')

    explanation = ' '.join(parts)

    if insight:
        explanation += f'\n     核心价值: {insight}'

    return explanation


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
