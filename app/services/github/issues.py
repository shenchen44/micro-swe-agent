import httpx

from app.core.config import get_settings


class GitHubIssueService:
    def __init__(self, token: str) -> None:
        self.settings = get_settings()
        self.token = token

    async def create_comment(self, owner: str, repo: str, issue_number: int, body: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.settings.github_api_base}/repos/{owner}/{repo}/issues/{issue_number}/comments",
                headers=self._headers(),
                json={"body": body},
            )
            response.raise_for_status()
            return response.json()

    async def add_labels(self, owner: str, repo: str, issue_number: int, labels: list[str]) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.settings.github_api_base}/repos/{owner}/{repo}/issues/{issue_number}/labels",
                headers=self._headers(),
                json={"labels": labels},
            )
            response.raise_for_status()
            return response.json()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
