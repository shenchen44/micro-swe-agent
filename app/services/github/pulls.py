from app.services.github import GitHubApiService


class GitHubPullRequestService(GitHubApiService):
    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> dict:
        return await self._post(
            f"{self.settings.github_api_base}/repos/{owner}/{repo}/pulls",
            json={"title": title, "body": body, "head": head, "base": base},
        )

    async def merge_pull_request(
        self,
        owner: str,
        repo: str,
        pull_number: int,
        merge_method: str = "squash",
    ) -> dict:
        return await self._put(
            f"{self.settings.github_api_base}/repos/{owner}/{repo}/pulls/{pull_number}/merge",
            json={"merge_method": merge_method},
        )

    async def get_pull_request(
        self,
        owner: str,
        repo: str,
        pull_number: int,
    ) -> dict:
        return await self._get(
            f"{self.settings.github_api_base}/repos/{owner}/{repo}/pulls/{pull_number}",
        )
