"""Tests for Storage and unified velocity calculation in JSONL mode."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from src.storage import SonarItem, Storage


@pytest.fixture
def temp_storage(tmp_path: Path) -> Storage:
    jsonl_path = tmp_path / "test_sonar.jsonl"
    return Storage(jsonl_path=jsonl_path)


def test_first_observation_pending(temp_storage: Storage):
    repo_id = "test/repo-1"
    now = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)

    item = temp_storage.upsert_candidate(
        repo_id=repo_id,
        url="https://github.com/test/repo-1",
        description="desc",
        language="Python",
        tags=["記憶 / AIコンテキスト"],
        judge_type="タグ一致",
        score=10.0,
        current_stars=100,
        now=now,
    )

    assert item.velocity is None
    assert item.velocity_type == "計測待ち"
    assert item.observed_days == 0.0
    assert len(item.history) == 1
    assert item.history[0]["stars"] == 100


def test_temporary_velocity_3days(temp_storage: Storage):
    repo_id = "test/repo-2"
    t0 = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)

    # 1日目: 100 stars
    temp_storage.upsert_candidate(
        repo_id=repo_id,
        url="https://github.com/test/repo-2",
        description="desc",
        language="Python",
        tags=["ハーネス"],
        judge_type="タグ一致",
        score=10.0,
        current_stars=100,
        now=t0,
    )

    # 2日目: 110 stars
    temp_storage.update_star_count(repo_id, current_stars=110, now=t0 + timedelta(days=1))

    # 4日目 (3日経過): 130 stars
    item = temp_storage.update_star_count(repo_id, current_stars=130, now=t3)

    assert item is not None
    assert item.velocity_type == "暫定"
    # (130 - 100) / 3.0 = 10.0 stars/day
    assert item.velocity == 10.0
    assert item.observed_days == 3.0


def test_confirmed_7d_velocity(temp_storage: Storage):
    repo_id = "test/repo-3"
    t0 = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)

    # 初日
    temp_storage.upsert_candidate(
        repo_id=repo_id,
        url="https://github.com/test/repo-3",
        description="desc",
        language="Rust",
        tags=["ナレッジ"],
        judge_type="タグ一致",
        score=10.0,
        current_stars=100,
        now=t0,
    )

    # 1日目〜6日目
    stars_series = [100, 110, 120, 135, 150, 170, 190, 210]
    for i, s in enumerate(stars_series[1:-1], 1):
        temp_storage.update_star_count(repo_id, current_stars=s, now=t0 + timedelta(days=i))

    # 7日目 (8回目の観測)
    t7 = t0 + timedelta(days=7)
    item = temp_storage.update_star_count(repo_id, current_stars=stars_series[-1], now=t7)

    assert item is not None
    assert item.velocity_type == "確定(7日)"
    # (210 - 100) / 7.0 = 15.7 stars/day
    assert item.velocity == 15.7
    assert item.observed_days == 7.0


def test_same_day_rerun_updates_and_does_not_divide_by_zero(temp_storage: Storage):
    repo_id = "test/repo-4"
    t0 = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)
    t1_rerun = datetime(2026, 9, 2, 16, 0, tzinfo=timezone.utc)

    # 1日目
    temp_storage.upsert_candidate(
        repo_id=repo_id,
        url="https://github.com/test/repo-4",
        description="desc",
        language="Python",
        tags=["ハーネス"],
        judge_type="タグ一致",
        score=10.0,
        current_stars=100,
        now=t0,
    )

    # 2日目朝 (1.0日経過: 120 stars) -> (120 - 100) / 1.0 = 20.0
    res1 = temp_storage.update_star_count(repo_id, current_stars=120, now=t1)
    assert res1.velocity == 20.0
    assert len(res1.history) == 2

    # 2日目夕方 再実行 (1.25日経過: 125 stars) -> 履歴の2日目レコードが125に更新され、ゼロ除算しない
    res2 = temp_storage.update_star_count(repo_id, current_stars=125, now=t1_rerun)
    assert len(res2.history) == 2  # 同日なのでレコード数は増えない
    assert res2.history[-1]["stars"] == 125
    assert res2.velocity == round((125 - 100) / 1.25, 1)


def test_atomic_save_and_load(tmp_path: Path):
    jsonl_path = tmp_path / "atomic_sonar.jsonl"
    storage1 = Storage(jsonl_path=jsonl_path)

    now = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
    storage1.upsert_candidate(
        repo_id="owner/repo-a",
        url="https://github.com/owner/repo-a",
        description="test a",
        language="Go",
        tags=["ツール"],
        judge_type="タグ一致",
        score=5.0,
        current_stars=500,
        now=now,
    )
    storage1.save()
    assert jsonl_path.exists()

    # 別インスタンスでロード
    storage2 = Storage(jsonl_path=jsonl_path)
    assert len(storage2.items) == 1
    assert "owner/repo-a" in storage2.items
    loaded = storage2.items["owner/repo-a"]
    assert loaded.current_stars == 500
    assert loaded.description == "test a"


def test_eviction_under_max_pool_size(temp_storage: Storage):
    now = datetime(2026, 9, 10, 10, 0, tzinfo=timezone.utc)

    # 3つのrepoを追加
    # 1. 活発なrepo
    item1 = temp_storage.upsert_candidate(
        repo_id="active/fast", url="", description="", language="", tags=[], judge_type="", score=10.0, current_stars=1000, now=now
    )
    item1.observed_days = 7.0
    item1.velocity = 50.0

    # 2. 休眠repo (7日以上 & velocity < 1.0)
    item2 = temp_storage.upsert_candidate(
        repo_id="dormant/slow", url="", description="", language="", tags=[], judge_type="", score=5.0, current_stars=50, now=now
    )
    item2.observed_days = 8.0
    item2.velocity = 0.2

    # 3. 普通のrepo
    item3 = temp_storage.upsert_candidate(
        repo_id="normal/mid", url="", description="", language="", tags=[], judge_type="", score=5.0, current_stars=200, now=now
    )
    item3.observed_days = 3.0
    item3.velocity = 5.0

    # 上限2件にして1件退役させる
    evicted = temp_storage.evict_if_needed(max_pool_size=2)
    assert len(evicted) == 1
    assert evicted[0] == "dormant/slow"
    assert temp_storage.items["dormant/slow"].status == "archived"
    assert len(temp_storage.list_active()) == 2
