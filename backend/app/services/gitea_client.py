"""Gitea API 封装 (httpx)。"""
from __future__ import annotations

import httpx

from ..config import get_settings


class GiteaError(RuntimeError):
    pass


class GiteaClient:
    def __init__(self, base_api: str | None = None, token: str | None = None):
        settings = get_settings()
        self.base_api = (base_api or settings.gitea_api_base).rstrip("/")
        self.token = token or settings.gitea_token

    def _headers(self, accept: str = "application/json") -> dict[str, str]:
        headers = {"Accept": accept}
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        return headers

    def get_pull_request(self, owner: str, repo: str, index: int) -> dict:
        url = f"{self.base_api}/repos/{owner}/{repo}/pulls/{index}"
        with httpx.Client(timeout=30) as client:
            resp = client.get(url, headers=self._headers())
        if resp.status_code != 200:
            raise GiteaError(f"获取 PR 失败 ({resp.status_code}): {resp.text}")
        return resp.json()

    def get_pull_diff(self, owner: str, repo: str, index: int) -> str:
        url = f"{self.base_api}/repos/{owner}/{repo}/pulls/{index}.diff"
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            resp = client.get(url, headers=self._headers(accept="text/plain"))
        if resp.status_code != 200:
            raise GiteaError(f"获取 diff 失败 ({resp.status_code}): {resp.text}")
        return resp.text

    def create_issue_comment(self, owner: str, repo: str, index: int, body: str) -> dict:
        """在 PR/issue 下发布一条评论(汇总评审结论)。"""
        url = f"{self.base_api}/repos/{owner}/{repo}/issues/{index}/comments"
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, headers=self._headers(), json={"body": body})
        if resp.status_code not in (200, 201):
            raise GiteaError(f"发布评论失败 ({resp.status_code}): {resp.text}")
        return resp.json()
