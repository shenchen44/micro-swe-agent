from urllib.parse import quote


def build_clone_url(owner: str, name: str, token: str | None = None) -> str:
    if token:
        return f"https://x-access-token:{quote(token)}@github.com/{owner}/{name}.git"
    return f"https://github.com/{owner}/{name}.git"
