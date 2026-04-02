import httpx

from app.core.config import get_settings


class GitHubPullRequestService:
    def __init__(self, token: str) -> None:
        self.settings = get_settings()
        self.token = token

    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.settings.github_api_base}/repos/{owner}/{repo}/pulls",
                headers=self._headers(),
                json={"title": title, "body": body, "head": head, "base": base},
            )
            response.raise_for_status()
            return response.json()

    async def merge_pull_request(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        merge_method: str = "squash",
    ) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.put(
                f"{self.settings.github_api_base}/repos/{owner}/{repo}/pulls/{pull_number}/merge",
                headers=self._headers(),
                json={"merge_method": merge_method},
            )
            response.raise_for_status()
            return response.json()

    async def get_pull_request(
        self,
        owner: str,
        repo: str,
        pull_number: int,
    ) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{self.settings.github_api_base}/repos/{owner}/{repo}/pulls/{pull_number}",
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
