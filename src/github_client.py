"""GitHub API client module with rate-limiting and retry support."""

from dataclasses import dataclass
import logging
import time
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger("sonar.github")


@dataclass
class DiscoveredRepo:
    repo_id: str  # "owner/name"
    url: str
    description: Optional[str]
    stars: int
    language: Optional[str]
    created_at: str
    pushed_at: str
    topics: List[str]
    is_archived: bool
    is_fork: bool


class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(self, token: Optional[str] = None, request_delay: float = 2.0):
        self.token = token
        self.request_delay = request_delay
        self.client = httpx.Client(
            base_url=self.BASE_URL,
            headers=self._build_headers(),
            timeout=15.0,
        )

    def _build_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "sonar-mvp/1.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        else:
            logger.warning(
                "GITHUB_TOKEN is not set. Requests are limited to unauthenticated rate limits (10/min search, 60/hr core)."
            )
        return headers

    def _request_with_retry(
        self, method: str, path: str, params: Optional[Dict[str, Any]] = None, max_retries: int = 3
    ) -> Optional[httpx.Response]:
        for attempt in range(max_retries):
            try:
                # レート制限対策のウェイト
                if self.request_delay > 0:
                    time.sleep(self.request_delay)

                response = self.client.request(method, path, params=params)

                # レート制限ヘッダーのログ（デバッグ用）
                remaining = response.headers.get("x-ratelimit-remaining")
                if remaining and int(remaining) < 5:
                    logger.warning(f"GitHub API remaining limit is low: {remaining}")

                if response.status_code == 200:
                    return response

                # レート制限 (403, 429) のハンドリング
                if response.status_code in (403, 429):
                    retry_after = response.headers.get("Retry-After")
                    sleep_time = int(retry_after) if retry_after else (2 ** (attempt + 1))
                    logger.warning(
                        f"GitHub rate limit hit ({response.status_code}). Backing off for {sleep_time}s (Attempt {attempt+1}/{max_retries})"
                    )
                    time.sleep(sleep_time)
                    continue

                # その他のエラー
                logger.error(
                    f"GitHub API error {response.status_code} for {path}: {response.text[:200]}"
                )
                return None

            except (httpx.RequestError, httpx.TimeoutException) as exc:
                sleep_time = 2 ** (attempt + 1)
                logger.warning(
                    f"Network error on {path}: {exc}. Retrying in {sleep_time}s (Attempt {attempt+1}/{max_retries})"
                )
                time.sleep(sleep_time)

        logger.error(f"Failed {path} after {max_retries} attempts.")
        return None

    def search_repositories(
        self, query: str, sort: str = "stars", order: str = "desc", per_page: int = 15
    ) -> List[DiscoveredRepo]:
        """Search GitHub repositories matching the query."""
        path = "/search/repositories"
        params = {
            "q": query,
            "sort": sort,
            "order": order,
            "per_page": min(per_page, 30),
        }
        res = self._request_with_retry("GET", path, params=params)
        if not res:
            return []

        data = res.json()
        items = data.get("items", [])
        results: List[DiscoveredRepo] = []

        for item in items:
            # 最低限の裏取り（アーカイブとフォークは除外）
            if item.get("archived", False) or item.get("fork", False):
                continue

            results.append(
                DiscoveredRepo(
                    repo_id=item["full_name"],
                    url=item["html_url"],
                    description=item.get("description"),
                    stars=int(item.get("stargazers_count", 0)),
                    language=item.get("language"),
                    created_at=item.get("created_at", ""),
                    pushed_at=item.get("pushed_at", ""),
                    topics=item.get("topics", []),
                    is_archived=item.get("archived", False),
                    is_fork=item.get("fork", False),
                )
            )

        return results

    def get_repository(self, owner_repo: str) -> Optional[DiscoveredRepo]:
        """Fetch latest metadata for a single repository."""
        path = f"/repos/{owner_repo}"
        res = self._request_with_retry("GET", path)
        if not res:
            return None

        item = res.json()
        if item.get("archived", False):
            return None

        return DiscoveredRepo(
            repo_id=item["full_name"],
            url=item["html_url"],
            description=item.get("description"),
            stars=int(item.get("stargazers_count", 0)),
            language=item.get("language"),
            created_at=item.get("created_at", ""),
            pushed_at=item.get("pushed_at", ""),
            topics=item.get("topics", []),
            is_archived=item.get("archived", False),
            is_fork=item.get("fork", False),
        )

    def close(self) -> None:
        self.client.close()
