"""Storage and Star tracking module for Sonar using JSONL as single source of truth."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("sonar.storage")


@dataclass
class StarSnapshot:
    date: str  # YYYY-MM-DD
    stars: int
    recorded_at: str  # ISO 8601


@dataclass
class SonarItem:
    repo: str
    url: str
    description: Optional[str] = None
    language: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    judge_type: str = "タグ一致"  # "タグ一致" or "未知枠"
    score: float = 0.0
    current_stars: int = 0
    velocity: Optional[float] = None
    velocity_type: str = "計測待ち"  # "確定(7日)", "暫定", "計測待ち"
    observed_days: float = 0.0
    latest_observed_at: str = ""
    first_observed_at: str = ""
    history: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "active"  # "active" or "archived"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SonarItem":
        # 互換性のためのデフォルト値補正
        return cls(
            repo=data["repo"],
            url=data.get("url", f"https://github.com/{data['repo']}"),
            description=data.get("description"),
            language=data.get("language"),
            tags=data.get("tags", []),
            judge_type=data.get("judge_type", "タグ一致"),
            score=float(data.get("score", 0.0)),
            current_stars=int(data.get("current_stars", 0)),
            velocity=float(data["velocity"]) if data.get("velocity") is not None else None,
            velocity_type=data.get("velocity_type", "計測待ち"),
            observed_days=float(data.get("observed_days", 0.0)),
            latest_observed_at=data.get("latest_observed_at", ""),
            first_observed_at=data.get("first_observed_at", ""),
            history=data.get("history", []),
            status=data.get("status", "active"),
        )


class Storage:
    def __init__(self, jsonl_path: Path):
        self.jsonl_path = jsonl_path
        self.items: Dict[str, SonarItem] = {}
        self.load()

    def load(self) -> Dict[str, SonarItem]:
        """Load items from JSONL file into memory."""
        self.items = {}
        if not self.jsonl_path.exists():
            logger.info(f"JSONL file not found at {self.jsonl_path}, starting with empty storage.")
            return self.items

        with open(self.jsonl_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    item = SonarItem.from_dict(data)
                    self.items[item.repo] = item
                except Exception as e:
                    logger.warning(f"Failed to parse line {line_num} in {self.jsonl_path}: {e}")

        logger.info(f"Loaded {len(self.items)} items from {self.jsonl_path}")
        return self.items

    def save(self) -> None:
        """Atomically write in-memory items to JSONL file."""
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        # 一時ファイルに書き出してからアトミックにリネーム（ファイル破損を防止）
        temp_dir = self.jsonl_path.parent
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=temp_dir, delete=False) as tf:
            temp_path = Path(tf.name)
            for item in self.items.values():
                line = json.dumps(item.to_dict(), ensure_ascii=False)
                tf.write(line + "\n")

        # アトミック置換
        temp_path.replace(self.jsonl_path)
        logger.info(f"Saved {len(self.items)} items atomically to {self.jsonl_path}")

    @staticmethod
    def calculate_velocity(
        history: List[Dict[str, Any]], current_stars: int, now: Optional[datetime] = None
    ) -> Tuple[Optional[float], str, float, List[Dict[str, Any]]]:
        """Unified velocity calculation algorithm.

        Returns: (velocity, velocity_type, observed_days, updated_history)
        """
        if now is None:
            now = datetime.now(timezone.utc)
        today_str = now.strftime("%Y-%m-%d")
        now_iso = now.isoformat()

        # 1. 履歴の更新（同日再実行なら当日スナップショットを最新値で更新）
        new_history: List[Dict[str, Any]] = []
        found_today = False
        for snap in history:
            if snap.get("date") == today_str:
                new_history.append({"date": today_str, "stars": current_stars, "recorded_at": now_iso})
                found_today = True
            else:
                new_history.append(snap)

        if not found_today:
            new_history.append({"date": today_str, "stars": current_stars, "recorded_at": now_iso})

        # 日付昇順でソート
        new_history.sort(key=lambda s: s.get("recorded_at", s.get("date", "")))

        # 2. 当日以外の過去レコードを取得
        past_snaps = [s for s in new_history if s.get("date") != today_str]

        # 最古レコード
        earliest_snap = new_history[0]
        earliest_time_str = earliest_snap.get("recorded_at")
        if earliest_time_str:
            try:
                earliest_time = datetime.fromisoformat(earliest_time_str)
            except Exception:
                earliest_time = datetime.strptime(earliest_snap["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            earliest_time = datetime.strptime(earliest_snap["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)

        total_observed_days = max(0.1, (now - earliest_time).total_seconds() / 86400.0)

        if not past_snaps:
            # 初回観測日
            return None, "計測待ち", 0.0, new_history

        seven_days_ago = now - timedelta(days=7)

        # 3. 7日以上前の観測点（6.5日以上前）を探す
        older_than_7d = []
        for s in past_snaps:
            s_time_str = s.get("recorded_at")
            if s_time_str:
                try:
                    s_time = datetime.fromisoformat(s_time_str)
                except Exception:
                    s_time = datetime.strptime(s["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            else:
                s_time = datetime.strptime(s["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)

            diff_sec = (now - s_time).total_seconds()
            if diff_sec >= 6.5 * 86400:
                older_than_7d.append((s, s_time, diff_sec))

        if older_than_7d:
            # 7日前に最も近い過去観測点を選択（7日確定日速）
            base_snap, base_time, _ = min(
                older_than_7d, key=lambda x: abs((x[1] - seven_days_ago).total_seconds())
            )
            dt_days = max(1.0, (now - base_time).total_seconds() / 86400.0)
            star_diff = current_stars - base_snap["stars"]
            velocity = round(star_diff / dt_days, 1)
            return velocity, "確定(7日)", round(total_observed_days, 1), new_history
        else:
            # 7日未満（2〜6日目）：初回観測点（最古の過去レコード）をベースとする（暫定日速）
            base_snap = past_snaps[0]
            s_time_str = base_snap.get("recorded_at")
            if s_time_str:
                try:
                    base_time = datetime.fromisoformat(s_time_str)
                except Exception:
                    base_time = datetime.strptime(base_snap["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            else:
                base_time = datetime.strptime(base_snap["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)

            dt_days = max(0.5, (now - base_time).total_seconds() / 86400.0)
            star_diff = current_stars - base_snap["stars"]
            velocity = round(star_diff / dt_days, 1)
            return velocity, "暫定", round(total_observed_days, 1), new_history

    def update_star_count(
        self, repo_id: str, current_stars: int, now: Optional[datetime] = None
    ) -> Optional[SonarItem]:
        """Update stars, recalculate velocity, and update history for an existing or active repo."""
        if repo_id not in self.items:
            return None

        if now is None:
            now = datetime.now(timezone.utc)

        item = self.items[repo_id]
        vel, vel_type, obs_days, new_hist = self.calculate_velocity(
            history=item.history, current_stars=current_stars, now=now
        )

        item.current_stars = current_stars
        item.velocity = vel
        item.velocity_type = vel_type
        item.observed_days = obs_days
        item.latest_observed_at = now.isoformat()
        item.history = new_hist
        return item

    def upsert_candidate(
        self,
        repo_id: str,
        url: str,
        description: Optional[str],
        language: Optional[str],
        tags: List[str],
        judge_type: str,
        score: float,
        current_stars: int,
        now: Optional[datetime] = None,
    ) -> SonarItem:
        """Insert or update candidate repository in pool."""
        if now is None:
            now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        if repo_id in self.items:
            item = self.items[repo_id]
            item.description = description or item.description
            item.language = language or item.language
            if not item.tags and tags:
                item.tags = tags
            item.score = score
            item.status = "active"
            self.update_star_count(repo_id, current_stars, now)
            return item

        # 新規作成
        vel, vel_type, obs_days, hist = self.calculate_velocity(
            history=[], current_stars=current_stars, now=now
        )
        item = SonarItem(
            repo=repo_id,
            url=url,
            description=description,
            language=language,
            tags=tags,
            judge_type=judge_type,
            score=score,
            current_stars=current_stars,
            velocity=vel,
            velocity_type=vel_type,
            observed_days=obs_days,
            latest_observed_at=now_iso,
            first_observed_at=now_iso,
            history=hist,
            status="active",
        )
        self.items[repo_id] = item
        return item

    def evict_if_needed(self, max_pool_size: int, incoming_count: int = 0) -> List[str]:
        """Evict lowest-performing active repos if total active count exceeds max_pool_size.

        Returns list of evicted repo names.
        """
        active_items = [item for item in self.items.values() if item.status == "active"]
        excess = (len(active_items) + incoming_count) - max_pool_size
        if excess <= 0:
            return []

        # 退役優先度:
        # 1. 観測7日以上で日速が低いもの（特に1.0未満の休眠repo）
        # 2. 日速（またはスコア）が全体で低いもの
        def eviction_sort_key(item: SonarItem) -> Tuple[int, float, float]:
            is_dormant = 1 if (item.observed_days >= 7.0 and (item.velocity or 0.0) < 1.0) else 2
            vel = item.velocity if item.velocity is not None else 0.0
            return (is_dormant, vel, item.score)

        sorted_candidates = sorted(active_items, key=eviction_sort_key)
        evicted_items = sorted_candidates[:excess]
        evicted_repos = []
        for item in evicted_items:
            item.status = "archived"
            evicted_repos.append(item.repo)

        logger.info(f"Evicted {len(evicted_repos)} repos from active pool to stay under {max_pool_size}")
        return evicted_repos

    def list_active(self) -> List[SonarItem]:
        return [item for item in self.items.values() if item.status == "active"]
