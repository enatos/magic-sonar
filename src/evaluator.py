"""Evaluation, scoring, and candidate selection module for Sonar."""

from dataclasses import dataclass
import logging
from typing import Any, Dict, List, Optional, Tuple
from src.config import AppConfig, TagConfig
from src.github_client import DiscoveredRepo

logger = logging.getLogger("sonar.evaluator")


@dataclass
class EvaluatedCandidate:
    repo_id: str
    url: str
    description: Optional[str]
    language: Optional[str]
    created_at: str
    latest_stars: int
    velocity: Optional[float]
    velocity_type: str
    observed_days: float
    matched_tags: List[str]
    max_weight: float
    is_unknown: bool
    score: float
    should_push_to_notion: bool
    push_reason: str


class Evaluator:
    def __init__(self, config: AppConfig):
        self.config = config

    def match_tags(self, repo: DiscoveredRepo) -> Tuple[List[str], float]:
        """Match repository text against tags and return matched tag names and maximum weight."""
        matched: List[TagConfig] = []
        text_to_search = f"{repo.repo_id} {repo.description or ''} {' '.join(repo.topics)}".lower()

        for tag in self.config.tags:
            if tag.status == "休眠":
                continue
            for kw in tag.keywords:
                if kw.lower() in text_to_search:
                    matched.append(tag)
                    break

        if not matched:
            return [], 0.0

        matched_names = [t.name for t in matched]
        max_weight = max(t.weight for t in matched)
        return matched_names, max_weight

    def evaluate_candidate(
        self,
        repo: DiscoveredRepo,
        velocity: Optional[float],
        velocity_type: str,
        observed_days: float,
        is_unknown_candidate: bool = False,
        allow_initial_pending_push: bool = True,
    ) -> EvaluatedCandidate:
        """Evaluate candidate score and decide whether it should be pushed to Notion."""
        matched_tags, max_weight = self.match_tags(repo)
        vel = velocity or 0.0

        is_unknown = False
        should_push = False
        push_reason = ""

        if matched_tags:
            # タグ一致枠
            if velocity is not None and vel > 0:
                score = vel * max_weight
                should_push = True
                push_reason = f"タグ一致 ({', '.join(matched_tags)}), 日速 {vel} stars/day"
            elif velocity is None and allow_initial_pending_push:
                # 初回観測時: 初期投入枠として重点タグ優先でスコアリング
                score = max_weight * 100.0 + min(repo.stars / 100.0, 50.0)
                should_push = True
                push_reason = f"タグ一致 ({', '.join(matched_tags)}), 初回投入（計測待ち）"
            else:
                score = 0.0
                push_reason = f"タグ一致 ({', '.join(matched_tags)}), 計測待ち/日速ゼロ"
        elif is_unknown_candidate and self.config.unknown_frontier.enabled:
            # 未知枠
            if velocity is not None and vel >= self.config.unknown_frontier.min_star_velocity:
                score = vel * 1.0
                is_unknown = True
                should_push = True
                push_reason = f"未知枠急上昇: 日速 {vel} >= {self.config.unknown_frontier.min_star_velocity}"
            else:
                score = 0.0
                push_reason = f"未知枠候補: 日速 {vel} (急上昇基準未達)"
        else:
            score = 0.0
            push_reason = "対象外"

        return EvaluatedCandidate(
            repo_id=repo.repo_id,
            url=repo.url,
            description=repo.description,
            language=repo.language,
            created_at=repo.created_at,
            latest_stars=repo.stars,
            velocity=velocity,
            velocity_type=velocity_type,
            observed_days=observed_days,
            matched_tags=matched_tags,
            max_weight=max_weight,
            is_unknown=is_unknown,
            score=round(score, 2),
            should_push_to_notion=should_push,
            push_reason=push_reason,
        )

    def select_daily_notion_batch(
        self, candidates: List[EvaluatedCandidate], max_items: Optional[int] = None
    ) -> List[EvaluatedCandidate]:
        """Select top candidates for Notion registration, strictly respecting the max cap."""
        if max_items is None:
            max_items = self.config.limits.max_daily_notion_items

        eligible = [c for c in candidates if c.should_push_to_notion]
        eligible.sort(key=lambda c: c.score, reverse=True)

        selected = eligible[:max_items]
        logger.info(
            f"Selected {len(selected)} candidates for Notion (eligible: {len(eligible)}, cap: {max_items})"
        )
        return selected
