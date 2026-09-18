"""Tests for Evaluator module."""

import pytest
from src.config import AppConfig, LimitsConfig, TagConfig, UnknownFrontierConfig
from src.evaluator import Evaluator
from src.github_client import DiscoveredRepo


@pytest.fixture
def test_config():
    return AppConfig(
        tags=[
            TagConfig(
                id="memory",
                name="記憶 / AIコンテキスト",
                status="重点",
                weight=2.0,
                keywords=["agent memory"],
            ),
            TagConfig(
                id="knowledge",
                name="ナレッジ",
                status="通常",
                weight=1.0,
                keywords=["knowledge graph"],
            ),
        ],
        unknown_frontier=UnknownFrontierConfig(
            enabled=True,
            min_star_velocity=20.0,
            created_within_days=30,
            min_stars_for_discovery=50,
        ),
        limits=LimitsConfig(
            max_pool_size=200,
            max_daily_notion_items=2,
            inactivity_days_threshold=7,
            inactive_velocity_threshold=1.0,
        ),
    )


def test_initial_pending_candidates_can_be_selected(test_config):
    evaluator = Evaluator(test_config)

    repo1 = DiscoveredRepo(
        repo_id="test/memory-agent",
        url="https://github.com/test/memory-agent",
        description="agent memory management",
        stars=1000,
        language="Python",
        created_at="2026-08-01T00:00:00Z",
        pushed_at="2026-09-01T00:00:00Z",
        topics=[],
        is_archived=False,
        is_fork=False,
    )

    repo2 = DiscoveredRepo(
        repo_id="test/knowledge-base",
        url="https://github.com/test/knowledge-base",
        description="knowledge graph tool",
        stars=500,
        language="Rust",
        created_at="2026-08-01T00:00:00Z",
        pushed_at="2026-09-01T00:00:00Z",
        topics=[],
        is_archived=False,
        is_fork=False,
    )

    c1 = evaluator.evaluate_candidate(
        repo1, velocity=None, velocity_type="pending", observed_days=0.0
    )
    c2 = evaluator.evaluate_candidate(
        repo2, velocity=None, velocity_type="pending", observed_days=0.0
    )

    assert c1.should_push_to_notion is True
    assert c2.should_push_to_notion is True
    # 重点タグの c1 の方がスコアが高い
    assert c1.score > c2.score

    selected = evaluator.select_daily_notion_batch([c1, c2], max_items=1)
    assert len(selected) == 1
    assert selected[0].repo_id == "test/memory-agent"
