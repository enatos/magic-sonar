"""Migration script to convert existing SQLite database (sonar.db) to sonar.jsonl."""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
import sys

# プロジェクトルートをsys.pathに追加
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.storage import SonarItem, Storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migrate")


def migrate():
    db_path = PROJECT_ROOT / "data" / "sonar.db"
    jsonl_path = PROJECT_ROOT / "data" / "sonar.jsonl"

    if not db_path.exists():
        logger.error(f"Database file not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    repos = conn.execute("SELECT * FROM repos").fetchall()
    logger.info(f"Found {len(repos)} repos in SQLite database.")

    storage = Storage(jsonl_path=jsonl_path)
    migrated_count = 0
    now = datetime.now(timezone.utc)

    for r in repos:
        repo_id = r["repo_id"]
        snapshots = conn.execute(
            "SELECT recorded_date, recorded_at, stars FROM star_snapshots WHERE repo_id = ? ORDER BY recorded_date ASC",
            (repo_id,),
        ).fetchall()

        history = [
            {
                "date": s["recorded_date"],
                "stars": s["stars"],
                "recorded_at": s["recorded_at"],
            }
            for s in snapshots
        ]

        if snapshots:
            latest_snap = snapshots[-1]
            current_stars = latest_snap["stars"]
            latest_observed_at = latest_snap["recorded_at"]
        else:
            current_stars = 0
            latest_observed_at = r["last_observed_at"]

        vel, vel_type, obs_days, updated_history = Storage.calculate_velocity(
            history=history, current_stars=current_stars, now=now
        )

        tags = [t.strip() for t in (r["matched_tags"] or "").split(",") if t.strip()]
        judge_type = "未知枠" if r["is_unknown"] else "タグ一致"

        item = SonarItem(
            repo=repo_id,
            url=r["url"],
            description=r["description"],
            language=r["language"],
            tags=tags,
            judge_type=judge_type,
            score=10.0 if tags else 5.0,
            current_stars=current_stars,
            velocity=vel,
            velocity_type=vel_type,
            observed_days=obs_days,
            latest_observed_at=latest_observed_at,
            first_observed_at=r["first_observed_at"],
            history=updated_history,
            status=r["status"] or "active",
        )
        storage.items[repo_id] = item
        migrated_count += 1

    storage.save()
    logger.info(f"Migration completed successfully! Migrated {migrated_count} repos to {jsonl_path}")


if __name__ == "__main__":
    migrate()
