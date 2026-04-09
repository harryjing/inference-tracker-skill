---
name: inference-engine-tracker
description: 自动追踪 SGLang、SpecForge、AIConfigurator 的 GitHub Issues/PRs/Releases 更新，筛选推理加速和准确率相关技术，生成日报和周报
version: 2.0.0
author: Claude
---

# GitHub 项目进展追踪器

## Overview

自动追踪 SGLang、SpecForge、AIConfigurator 的 GitHub 仓库更新（Issues、PRs、Releases），筛选与推理加速或准确率提升相关的技术进展，生成结构化的中文日报和周报。

### 监控仓库

| 项目 | 仓库 | 关注方向 |
|------|------|----------|
| SGLang | sgl-project/sglang | 推理引擎性能优化、调度、KV Cache 等 |
| SpecForge | sgl-project/SpecForge | 投机解码、准确率、加速比 |
| AIConfigurator | ai-dynamo/aiconfigurator | 推理配置优化、部署、Benchmark |

### 追踪内容

- **Issues**: 新提出的功能请求、Bug 报告、性能问题讨论
- **Pull Requests**: 新提交和已合并的 PR
- **Releases**: 版本发布

### 筛选标准

自动筛选与以下方向相关的更新：
- 推理性能优化（延迟、吞吐量、内存）
- 量化技术（FP8、INT8 等）
- KV Cache 优化
- 投机解码与准确率
- 并行与分布式推理
- Attention 优化
- 调度与批处理
- MoE 相关优化

## When to Use

- 想要获取最新项目进展时
- 需要了解推理优化领域的最新技术动态时
- 需要生成定期进展报告时

## 执行前必选步骤

**在执行前，必须先确认 GitHub Token！**

### 流程

1. **询问用户**: "请问你有 GitHub Token 吗？"
   - **有** → 请用户提供 Token，设置 `GITHUB_TOKEN` 环境变量后执行
   - **没有** → 提示用户在 https://github.com/settings/tokens 创建（只需 `public_repo` 权限）

### 示例

```
Claude: 请问你有 GitHub Token 吗？

用户: 有，GITHUB_TOKEN=ghp_xxxxxxxx

Claude: 好的，我来使用你的 Token 生成日报。
[执行: GITHUB_TOKEN=ghp_xxxxxxxx python scripts/tracker_cli.py --mode daily]

---

用户: 没有

Claude: 请前往 https://github.com/settings/tokens 创建一个 Token（勾选 public_repo 即可）。
```

## CLI Usage

```bash
# 生成昨日日报（默认）
python scripts/tracker_cli.py --mode daily

# 生成指定日期的日报
python scripts/tracker_cli.py --mode daily --date 2026-04-09

# 测试模式（不保存数据）
python scripts/tracker_cli.py --mode daily --dry-run

# 生成本周周报
python scripts/tracker_cli.py --mode weekly

# 生成指定结束日期的周报
python scripts/tracker_cli.py --mode weekly --end-date 2026-04-09

# 跳过分析（仅获取原始数据）
python scripts/tracker_cli.py --mode daily --skip-analysis

# 禁用自动扩大时间范围
python scripts/tracker_cli.py --mode daily --no-auto-expand
```

## Configuration

### repositories.yaml

```yaml
repositories:
  - name: SGLang
    owner: sgl-project
    repo: sglang
    track:
      - issues
      - pulls
      - releases
    keywords:
      - performance
      - optimize
      - kv cache
      - speculative
      # ...

settings:
  max_issues: 30
  max_releases: 5
  max_pulls: 30
  request_delay: 0.5
  pr_state: all
```

## Report Format

### 日报

```markdown
# GitHub 项目进展日报 - {date}

> 相关 Issues: X 个 | 相关 PRs: X 个 | Releases: X 个

## [SGLang](https://github.com/sgl-project/sglang)

### 重要 Issues
- **[O]** [#123: 标题](url)
  > 中文解释

### 重要 PRs
- **[merged]** [#456: 标题](url)
  > 中文解释

### 版本发布
- **[v1.0.0](url)** 版本名称
```

### 周报

汇总本周日报数据，包含每日更新量统计表和各项目关键进展汇总。

## Output Structure

```
tracker_data/
├── raw/                    # 原始数据
│   └── github_YYYY-MM-DD.json
├── analyzed/               # 分析结果
│   └── github_YYYY-MM-DD.json
└── reports/
    ├── daily/
    │   └── YYYY-MM-DD.md
    └── weekly/
        └── start_end.md
```

## Dependencies

```
pyyaml>=6.0
python-dateutil>=2.8.0
requests>=2.31.0
```

## Workflow

```
GitHub API → raw/github_{date}.json → quick_analyze → analyzed/github_{date}.json → generate_daily_report → reports/daily/{date}.md
```

## Notes

- GitHub API 有 rate limit，使用 token 可以提高限制（未认证 60/h → 认证 5000/h）
- 日报会自动去重，同一内容不会重复记录
- 默认获取前一天的数据（可通过 `--date` 指定）
- 如果当天无数据，会自动扩大到 3 天、7 天范围
