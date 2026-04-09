#!/usr/bin/env python3
"""
GitHub 项目进展追踪器 CLI

主入口脚本，协调各个模块完成：
1. 获取 GitHub 更新（Issues、PRs、Releases）
2. 关键词分析筛选
3. 生成日报/周报

Usage:
    python tracker_cli.py --mode daily
    python tracker_cli.py --mode weekly
    python tracker_cli.py --mode daily --dry-run
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# 添加脚本目录到路径
scripts_dir = Path(__file__).parent
sys.path.insert(0, str(scripts_dir))

from fetch_github_updates import fetch_all_updates as fetch_github
from generate_daily_report import generate_daily_report
from generate_weekly_report import generate_weekly_report


def setup_directories(base_dir: Optional[str] = None) -> dict:
    """设置目录结构"""
    if base_dir is None:
        base_dir = os.environ.get('TRACKER_DATA_DIR', './tracker_data')

    base = Path(base_dir)
    dirs = {
        'base': base,
        'raw': base / 'raw',
        'analyzed': base / 'analyzed',
        'reports': base / 'reports',
        'daily': base / 'reports' / 'daily',
        'weekly': base / 'reports' / 'weekly'
    }

    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    return dirs


def _has_relevant_updates(github_data: dict) -> bool:
    """检查是否有相关更新"""
    for repo_data in github_data.values():
        total_items = (
            len(repo_data.get('issues', [])) +
            len(repo_data.get('pulls', [])) +
            len(repo_data.get('releases', []))
        )
        if total_items > 0:
            return True
    return False


def _count_updates(github_data: dict) -> dict:
    """统计更新数量"""
    counts = {'issues': 0, 'pulls': 0, 'releases': 0, 'repos': 0}

    for repo_data in github_data.values():
        issues = len(repo_data.get('issues', []))
        pulls = len(repo_data.get('pulls', []))
        releases = len(repo_data.get('releases', []))

        counts['issues'] += issues
        counts['pulls'] += pulls
        counts['releases'] += releases

        if issues + pulls + releases > 0:
            counts['repos'] += 1

    return counts


def run_daily_tracking(
    date: str,
    days: int = 1,
    dirs: Optional[dict] = None,
    dry_run: bool = False,
    skip_analysis: bool = False,
    auto_expand: bool = True,
    github_token: Optional[str] = None
) -> bool:
    """执行每日追踪"""
    print("=" * 60)
    print(f"GitHub 项目进展日报 - {date}")
    print("=" * 60)

    if dirs is None:
        dirs = setup_directories()

    github_data = {}

    # 尝试不同的时间范围
    time_ranges = [days]
    if auto_expand and days == 1:
        time_ranges = [1, 3, 7]

    for attempt_days in time_ranges:
        print(f"\n获取最近 {attempt_days} 天的数据...")

        try:
            github_data = fetch_github(days=attempt_days, dry_run=dry_run, token=github_token)

            if not dry_run and github_data:
                github_raw_path = dirs['raw'] / f'github_{date}.json'
                with open(github_raw_path, 'w', encoding='utf-8') as f:
                    json.dump(github_data, f, ensure_ascii=False, indent=2)
                print(f"   已保存: {github_raw_path}")
        except Exception as e:
            print(f"   错误: {e}")

        counts = _count_updates(github_data)
        print(f"\n本次获取: {counts['issues']} issues, {counts['pulls']} PRs, "
              f"{counts['releases']} releases, {counts['repos']} 个项目有更新")

        if _has_relevant_updates(github_data):
            print(f"获取到内容，使用 {attempt_days} 天的数据")
            break
        elif attempt_days < time_ranges[-1]:
            next_days = time_ranges[time_ranges.index(attempt_days) + 1]
            print(f"未获取到内容，扩大时间范围到 {next_days} 天")
        else:
            print("即使扩大时间范围也未获取到内容，将生成空报告")
            break

    # 分析
    github_analyzed = github_data
    if not skip_analysis and not dry_run and github_data:
        print("\n分析内容...")
        try:
            from quick_analyze import analyze_github_data
            github_analyzed = analyze_github_data(github_data)
            analyzed_path = dirs['analyzed'] / f'github_{date}.json'
            with open(analyzed_path, 'w', encoding='utf-8') as f:
                json.dump(github_analyzed, f, ensure_ascii=False, indent=2)
            print(f"   分析完成: {analyzed_path}")
        except Exception as e:
            print(f"   分析错误: {e}")
            github_analyzed = github_data

    # 生成日报
    print("\n生成日报...")
    try:
        if dry_run:
            print("   [DRY RUN] 跳过报告生成")
            return True

        content = generate_daily_report(
            date=date,
            github_updates=github_analyzed,
            output_dir=str(dirs['reports'])
        )
        print(f"   报告长度: {len(content)} 字符")
        return True

    except Exception as e:
        print(f"   错误: {e}")
        return False


def run_weekly_tracking(
    end_date: Optional[str] = None,
    dirs: Optional[dict] = None
) -> bool:
    """执行每周追踪"""
    print("=" * 60)
    print("GitHub 项目进展周报")
    print("=" * 60)

    if dirs is None:
        dirs = setup_directories()

    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')

    end = datetime.strptime(end_date, '%Y-%m-%d')
    start = end - timedelta(days=6)
    start_date = start.strftime('%Y-%m-%d')

    print(f"\n统计周期: {start_date} 至 {end_date}")

    print("\n生成周报...")
    try:
        content = generate_weekly_report(
            start_date=start_date,
            end_date=end_date,
            daily_dir=str(dirs['daily']),
            output_dir=str(dirs['reports'])
        )

        if content:
            print(f"   报告长度: {len(content)} 字符")
            return True
        else:
            print("   无数据生成报告")
            return False

    except Exception as e:
        print(f"   错误: {e}")
        return False


def _get_yesterday() -> str:
    yesterday = datetime.now() - timedelta(days=1)
    return yesterday.strftime('%Y-%m-%d')


def main():
    parser = argparse.ArgumentParser(
        description='GitHub Project Progress Tracker',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tracker_cli.py --mode daily
  python tracker_cli.py --mode daily --date 2026-04-09
  python tracker_cli.py --mode daily --dry-run
  python tracker_cli.py --mode weekly
  python tracker_cli.py --mode weekly --end-date 2026-04-09
        """
    )

    parser.add_argument('--mode', choices=['daily', 'weekly'], required=True,
                        help='运行模式: daily 或 weekly')
    parser.add_argument('--date', type=str, default=_get_yesterday(),
                        help='日期 (YYYY-MM-DD)，默认昨天')
    parser.add_argument('--end-date', type=str,
                        help='结束日期 (YYYY-MM-DD)，仅用于 weekly 模式')
    parser.add_argument('--days', type=int, default=1,
                        help='回溯天数 (默认: 1)')
    parser.add_argument('--data-dir', type=str, default='./tracker_data',
                        help='数据目录 (默认: ./tracker_data)')
    parser.add_argument('--dry-run', action='store_true',
                        help='测试模式，不保存数据')
    parser.add_argument('--skip-analysis', action='store_true',
                        help='跳过分析')
    parser.add_argument('--no-auto-expand', action='store_true',
                        help='禁用自动扩大时间范围')

    args = parser.parse_args()

    # GitHub Token
    github_token = os.environ.get('GITHUB_TOKEN')

    dirs = setup_directories(args.data_dir)
    print(f"数据目录: {dirs['base'].absolute()}")

    if args.mode == 'daily':
        success = run_daily_tracking(
            date=args.date,
            days=args.days,
            dirs=dirs,
            dry_run=args.dry_run,
            skip_analysis=args.skip_analysis,
            auto_expand=not args.no_auto_expand,
            github_token=github_token
        )
    else:
        success = run_weekly_tracking(
            end_date=args.end_date,
            dirs=dirs
        )

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
