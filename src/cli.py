"""CLI entry point and pipeline orchestrator for Sonar (JSONL Edition)."""

import argparse
from datetime import datetime, timezone
import logging
import sys
from typing import List, Optional
from src.config import AppConfig, get_discovery_date_filter, load_config
from src.evaluator import EvaluatedCandidate, Evaluator
from src.github_client import DiscoveredRepo, GitHubClient
from src.storage import SonarItem, Storage


def setup_logging(config: AppConfig, verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    log_file = config.logs_dir / f"sonar_{today_str}.log"

    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


class SonarPipeline:
    def __init__(self, config: AppConfig, dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run
        self.storage = Storage(jsonl_path=config.jsonl_path)
        self.github = GitHubClient(token=config.github_token)
        self.evaluator = Evaluator(config=config)
        self.logger = logging.getLogger("sonar.pipeline")

    def run(self) -> None:
        self.logger.info("=== Sonar Pipeline (JSONL Mode) Started ===")
        now = datetime.now(timezone.utc)

        # 1. GitHubから候補repoの探索 (Discovery)
        date_filter = get_discovery_date_filter(self.config.unknown_frontier.created_within_days)
        discovered_map = {}

        # 1-a. タグ一致枠の探索
        self.logger.info("Searching GitHub for interest tags...")
        for tag in self.config.tags:
            if tag.status == "休眠":
                continue
            for kw in tag.keywords[:2]:  # レート制限を考慮し主要キーワードで検索
                query = f'"{kw}" in:name,description,topics pushed:>{date_filter} stars:>10'
                repos = self.github.search_repositories(query, sort="stars", per_page=5)
                for r in repos:
                    discovered_map[r.repo_id] = (r, False)

        # 1-b. 未知枠の探索（直近作成 × Star数急上昇候補）
        if self.config.unknown_frontier.enabled:
            self.logger.info("Searching GitHub for unknown frontier candidates...")
            min_stars = self.config.unknown_frontier.min_stars_for_discovery
            uf_query = f"created:>{date_filter} stars:>{min_stars}"
            uf_repos = self.github.search_repositories(uf_query, sort="stars", per_page=10)
            for r in uf_repos:
                if r.repo_id not in discovered_map:
                    discovered_map[r.repo_id] = (r, True)

        self.logger.info(f"Discovered {len(discovered_map)} candidate repositories in total.")

        # 2. 観測プールへの投入
        for repo_id, (repo, is_unknown) in discovered_map.items():
            matched_tags, score = self.evaluator.match_tags(repo)
            judge_type = "未知枠" if is_unknown else "タグ一致"
            self.storage.upsert_candidate(
                repo_id=repo.repo_id,
                url=repo.url,
                description=repo.description,
                language=repo.language,
                tags=matched_tags,
                judge_type=judge_type,
                score=score,
                current_stars=repo.stars,
                now=now,
            )

        # 3. 200件上限入替 (Eviction)
        evicted = self.storage.evict_if_needed(self.config.limits.max_pool_size)
        if evicted:
            self.logger.info(f"Evicted {len(evicted)} low-priority repos from active pool: {evicted}")

        # 4. アクティブな観測プール全件の最新Star数・日速計算
        active_items = self.storage.list_active()
        self.logger.info(f"Updating stars for {len(active_items)} active repositories in pool...")

        for item in active_items:
            # 個別Repoの詳細取得（最新Star数）
            repo_detail = self.github.get_repository(item.repo)
            if not repo_detail:
                # アーカイブされたかアクセス不可
                continue

            # 最新Star数で更新 ＆ 統一日速計算
            self.storage.update_star_count(item.repo, current_stars=repo_detail.stars, now=now)
            # スコア再判定
            _, score = self.evaluator.match_tags(repo_detail)
            item.score = score

        # 5. 保存
        if self.dry_run:
            self.logger.info("[NOTE] This was a dry-run. JSONL file was NOT modified.")
        else:
            self.storage.save()
            self.logger.info(f"Successfully updated and saved {self.config.jsonl_path}")

        # 6. サマリー出力
        confirmed_count = sum(1 for item in self.storage.list_active() if item.velocity_type == "確定(7日)")
        temporary_count = sum(1 for item in self.storage.list_active() if item.velocity_type == "暫定")
        pending_count = sum(1 for item in self.storage.list_active() if item.velocity_type == "計測待ち")

        self.logger.info("=== Sonar Pipeline Summary ===")
        self.logger.info(f"Active Pool Size: {len(self.storage.list_active())} / {self.config.limits.max_pool_size}")
        self.logger.info(f"  - 確定(7日): {confirmed_count} repos")
        self.logger.info(f"  - 暫定: {temporary_count} repos")
        self.logger.info(f"  - 計測待ち: {pending_count} repos")

        # 上位日速トップ5の表示
        top_v = sorted(
            [item for item in self.storage.list_active() if item.velocity is not None],
            key=lambda x: x.velocity or 0.0,
            reverse=True,
        )[:5]
        self.logger.info("Top Velocity Repositories:")
        for t in top_v:
            self.logger.info(f"  * {t.repo:<35} | +{t.velocity:<6.1f} stars/day ({t.velocity_type}) | {t.tags}")

    def watch(self, owner_repo: str) -> None:
        """Manually add an existing repository to the observation pool."""
        self.logger.info(f"Adding {owner_repo} to observation pool...")
        repo = self.github.get_repository(owner_repo)
        if not repo:
            self.logger.error(f"Could not find repo {owner_repo} or it is archived.")
            return

        now = datetime.now(timezone.utc)
        matched_tags, score = self.evaluator.match_tags(repo)

        item = self.storage.upsert_candidate(
            repo_id=repo.repo_id,
            url=repo.url,
            description=repo.description,
            language=repo.language,
            tags=matched_tags,
            judge_type="タグ一致",
            score=score,
            current_stars=repo.stars,
            now=now,
        )
        self.storage.save()
        self.logger.info(
            f"Successfully added {item.repo} (Stars: {item.current_stars}, Velocity: {item.velocity_type})"
        )

    def print_status(self, show_all: bool = False) -> None:
        """Display current pool status."""
        active = self.storage.list_active()
        print(f"\n📡 Sonar Status (JSONL: {self.config.jsonl_path})")
        print(f"Total Active Pool Size: {len(active)} / {self.config.limits.max_pool_size}")
        print("-" * 80)
        print(f"{'Repository':<35} | {'Stars':<7} | {'Velocity':<15} | {'ObsDays':<7} | {'Tags'}")
        print("-" * 80)

        # 日速順でソート
        sorted_active = sorted(
            active,
            key=lambda x: (x.velocity if x.velocity is not None else -1.0),
            reverse=True,
        )

        display_limit = len(sorted_active) if show_all else 20
        for item in sorted_active[:display_limit]:
            vel_str = f"+{item.velocity:.1f}/d ({item.velocity_type})" if item.velocity is not None else "計測待ち"
            tags_str = ", ".join(item.tags[:2])
            print(
                f"{item.repo:<35} | {item.current_stars:<7} | {vel_str:<15} | {item.observed_days:<7.1f} | {tags_str}"
            )

        if not show_all and len(sorted_active) > 20:
            print(f"... and {len(sorted_active) - 20} more (use `status --all` to show all).")


def main():
    parser = argparse.ArgumentParser(description="なんとかソナー CLI (JSONL Edition)")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # run command
    run_parser = subparsers.add_parser("run", help="Run the sonar pipeline")
    run_parser.add_argument(
        "--dry-run", action="store_true", help="Perform a dry-run without writing to JSONL"
    )
    run_parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    # watch command
    watch_parser = subparsers.add_parser("watch", help="Add a repo to watch list")
    watch_parser.add_argument("repo", help="Repository in owner/name format")

    # status command
    status_parser = subparsers.add_parser("status", help="Show pool status")
    status_parser.add_argument("--all", "-a", action="store_true", help="Show all repositories in pool")

    args = parser.parse_args()
    config = load_config()

    if args.command == "run":
        setup_logging(config, verbose=args.verbose)
        pipeline = SonarPipeline(config=config, dry_run=args.dry_run)
        pipeline.run()
    elif args.command == "watch":
        setup_logging(config)
        pipeline = SonarPipeline(config=config)
        pipeline.watch(args.repo)
    elif args.command == "status":
        pipeline = SonarPipeline(config=config)
        pipeline.print_status(show_all=args.all)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
