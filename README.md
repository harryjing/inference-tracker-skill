# Inference Tracker Skill

自动追踪 SGLang、SpecForge、AIConfigurator 的 GitHub 仓库更新，筛选与 **推理加速** 和 **准确率提升** 相关的技术进展，生成结构化的中文日报和周报。

## 监控仓库

| 项目 | 仓库 | 关注方向 |
|------|------|----------|
| **SGLang** | [sgl-project/sglang](https://github.com/sgl-project/sglang) | 推理引擎性能优化、调度、KV Cache、投机解码 |
| **SpecForge** | [sgl-project/SpecForge](https://github.com/sgl-project/SpecForge) | 投机解码训练、准确率、加速比 |
| **AIConfigurator** | [ai-dynamo/aiconfigurator](https://github.com/ai-dynamo/aiconfigurator) | 推理配置优化、部署、Benchmark |

## 追踪内容

- **Issues** - 功能请求、Bug 报告、性能问题讨论
- **Pull Requests** - 新提交和已合并的 PR
- **Releases** - 版本发布

通过关键词匹配自动筛选与推理加速/准确率相关的更新，并生成中文解释。

## 快速开始

### 1. 安装依赖

```bash
pip install pyyaml python-dateutil requests
```

### 2. 获取 GitHub Token

前往 [GitHub Settings > Tokens](https://github.com/settings/tokens) 创建 Personal Access Token（勾选 `public_repo` 即可）。

### 3. 生成日报

```bash
cd inference-engine-tracker

# 生成昨日日报
GITHUB_TOKEN=ghp_xxx python3 scripts/tracker_cli.py --mode daily

# 生成指定日期
GITHUB_TOKEN=ghp_xxx python3 scripts/tracker_cli.py --mode daily --date 2026-04-08

# 测试模式（不保存）
python3 scripts/tracker_cli.py --mode daily --dry-run
```

### 4. 生成周报

```bash
# 生成本周周报
GITHUB_TOKEN=ghp_xxx python3 scripts/tracker_cli.py --mode weekly

# 指定结束日期
GITHUB_TOKEN=ghp_xxx python3 scripts/tracker_cli.py --mode weekly --end-date 2026-04-08
```

## CLI 参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--mode` | `daily` 或 `weekly` | 必填 |
| `--date` | 日报日期 (YYYY-MM-DD) | 昨天 |
| `--end-date` | 周报结束日期 | 今天 |
| `--days` | 回溯天数 | 1 |
| `--data-dir` | 数据目录 | `./tracker_data` |
| `--dry-run` | 测试模式，不保存 | - |
| `--skip-analysis` | 跳过关键词分析 | - |
| `--no-auto-expand` | 禁用自动扩大时间范围 | - |

## 输出结构

```
tracker_data/
├── raw/                    # GitHub API 原始数据
│   └── github_2026-04-08.json
├── analyzed/               # 关键词分析后的数据
│   └── github_2026-04-08.json
└── reports/
    ├── daily/              # 日报 (Markdown)
    │   └── 2026-04-08.md
    └── weekly/             # 周报 (Markdown)
        └── 2026-04-03_2026-04-09.md
```

## 日报示例

```markdown
# GitHub 项目进展日报 - 2026-04-08

> 相关 Issues: 4 个 | 相关 PRs: 28 个 | Releases: 1 个

## SGLang

### 版本发布
- **v0.5.10.post1**

### 重要 PRs
- **[open]** [#22411: Support MTP/speculative decoding with hiSparse](...)
  > 引入了投机解码；优化了批处理策略。
- **[open]** [#22410: Overlap H2D transfer with hit-attention](...)
  > 优化了注意力计算；优化了并行处理。
```

## 筛选关键词

自动筛选包含以下方向关键词的更新：

- **性能**: performance, optimize, latency, throughput, speed
- **量化**: quantization, fp8, int8, fp4, nvfp4
- **缓存**: kv cache, radix attention, cache
- **投机解码**: speculative, draft, eagle, acceptance rate
- **并行**: parallel, disaggregated, prefill-decode
- **注意力**: attention, flash attention, mla, gqa
- **调度**: scheduler, batch, continuous batching
- **MoE**: moe, mixture of experts, expert
- **准确率**: accuracy, correctness, precision

## 作为 Claude Code Skill 使用

本项目同时是一个 Claude Code Skill，可在 Claude Code 中通过 `/inference-engine-tracker` 命令调用，自动执行日报/周报生成流程。

## License

MIT
