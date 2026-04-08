"""GitHub integration services."""

import httpx

from app.core.config import get_settings


class GitHubApiService:
    """Base class for GitHub API services with common HTTP client functionality."""

    def __init__(self, token: str) -> None:
        self.settings = get_settings()
        self.token = token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _post(self, url: str, json: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, headers=self._headers(), json=json)
            response.raise_for_status()
            return response.json()

    async def _get(self, url: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, headers=self._headers())
            response.raise_for_status()
            return response.json()

    async def _put(self, url: str, json: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.put(url, headers=self._headers(), json=json)
            response.raise_for_status()
            return response.json()
