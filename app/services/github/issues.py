from app.services.github import GitHubApiService


class GitHubIssueService(GitHubApiService):
    async def create_comment(self, owner: str, repo: str, issue_number: int, body: str) -> dict:
        return await self._post(
            f"{self.settings.github_api_base}/repos/{owner}/{repo}/issues/{issue_number}/comments",
            json={"body": body},
        )

    async def add_labels(self, owner: str, repo: str, issue_number: int, labels: list[str]) -> dict:
        return await self._post(
            f"{self.settings.github_api_base}/repos/{owner}/{repo}/issues/{issue_number}/labels",
            json={"labels": labels},
        )
