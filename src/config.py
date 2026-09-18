"""Configuration module for Sonar."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml


@dataclass
class TagConfig:
    id: str
    name: str
    status: str  # "重点", "通常", "休眠"
    weight: float
    keywords: List[str]


@dataclass
class UnknownFrontierConfig:
    enabled: bool
    min_star_velocity: float
    created_within_days: int
    min_stars_for_discovery: int


@dataclass
class LimitsConfig:
    max_pool_size: int
    max_daily_notion_items: int
    inactivity_days_threshold: int
    inactive_velocity_threshold: float


@dataclass
class AppConfig:
    tags: List[TagConfig]
    unknown_frontier: UnknownFrontierConfig
    limits: LimitsConfig
    github_token: Optional[str] = None
    notion_api_key: Optional[str] = None
    notion_database_id: Optional[str] = None
    project_root: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent)

    @property
    def jsonl_path(self) -> Path:
        data_dir = self.project_root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "sonar.jsonl"

    @property
    def db_path(self) -> Path:
        data_dir = self.project_root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir / "sonar.db"

    @property
    def backup_dir(self) -> Path:
        b_dir = self.project_root / "data" / "backup"
        b_dir.mkdir(parents=True, exist_ok=True)
        return b_dir

    @property
    def logs_dir(self) -> Path:
        l_dir = self.project_root / "logs"
        l_dir.mkdir(parents=True, exist_ok=True)
        return l_dir


def load_config(config_file: Optional[Path] = None) -> AppConfig:
    project_root = Path(__file__).resolve().parent.parent
    if config_file is None:
        config_file = project_root / "config" / "tags.yaml"

    with open(config_file, "r", encoding="utf-8") as f:
        data: Dict[str, Any] = yaml.safe_load(f)

    tags: List[TagConfig] = []
    for t in data.get("tags", []):
        tags.append(
            TagConfig(
                id=t["id"],
                name=t["name"],
                status=t.get("status", "通常"),
                weight=float(t.get("weight", 1.0)),
                keywords=t.get("keywords", []),
            )
        )

    uf_raw = data.get("unknown_frontier", {})
    unknown_frontier = UnknownFrontierConfig(
        enabled=uf_raw.get("enabled", True),
        min_star_velocity=float(uf_raw.get("min_star_velocity", 20.0)),
        created_within_days=int(uf_raw.get("created_within_days", 30)),
        min_stars_for_discovery=int(uf_raw.get("min_stars_for_discovery", 50)),
    )

    limits_raw = data.get("limits", {})
    limits = LimitsConfig(
        max_pool_size=int(limits_raw.get("max_pool_size", 200)),
        max_daily_notion_items=int(limits_raw.get("max_daily_notion_items", 5)),
        inactivity_days_threshold=int(limits_raw.get("inactivity_days_threshold", 7)),
        inactive_velocity_threshold=float(limits_raw.get("inactive_velocity_threshold", 1.0)),
    )

    # .env や os.environ からトークン類を取得
    github_token = os.environ.get("GITHUB_TOKEN")
    notion_api_key = os.environ.get("NOTION_API_KEY")
    notion_database_id = os.environ.get("NOTION_DATABASE_ID")

    # .env ファイルが存在すれば補助的に読み込む
    env_path = project_root / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k == "GITHUB_TOKEN" and not github_token:
                    github_token = v
                elif k == "NOTION_API_KEY" and not notion_api_key:
                    notion_api_key = v
                elif k == "NOTION_DATABASE_ID" and not notion_database_id:
                    notion_database_id = v

    return AppConfig(
        tags=tags,
        unknown_frontier=unknown_frontier,
        limits=limits,
        github_token=github_token,
        notion_api_key=notion_api_key,
        notion_database_id=notion_database_id,
        project_root=project_root,
    )


def get_discovery_date_filter(days_ago: int = 30) -> str:
    """Return YYYY-MM-DD relative to current UTC date."""
    target_date = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return target_date.strftime("%Y-%m-%d")
