"""
GitHub API Client
Handles fetching repository structure and file contents via the GitHub REST API.
"""

import logging
import time
import re
from typing import Optional
import requests

logger = logging.getLogger(__name__)


class GitHubClient:
    """
    Thin wrapper around the GitHub REST API.
    Supports unauthenticated (60 req/hr) and authenticated (5000 req/hr) access.
    """

    BASE_URL = "https://api.github.com"

    def __init__(self, token: Optional[str] = None):
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "juice-shop-api-extractor/1.0",
        })
        if token:
            self.session.headers["Authorization"] = f"token {token}"
            logger.info("GitHub client initialized with authentication token.")
        else:
            logger.info("GitHub client initialized without token (rate-limited to 60 req/hr).")

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def parse_repo_url(self, url: str) -> tuple[str, str]:
        """Extract owner and repo name from a GitHub URL."""
        url = url.rstrip("/").replace(".git", "")
        match = re.search(r"github\.com[/:]([^/]+)/([^/]+)", url)
        if not match:
            raise ValueError(f"Cannot parse GitHub URL: {url}")
        return match.group(1), match.group(2)

    def get_default_branch(self, owner: str, repo: str) -> str:
        data = self._get(f"/repos/{owner}/{repo}")
        return data.get("default_branch", "master")

    def get_tree(self, owner: str, repo: str, branch: str) -> list[dict]:
        """Return the full recursive file tree for a repo branch."""
        url = f"/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
        data = self._get(url)
        if data.get("truncated"):
            logger.warning("Repository tree was truncated by GitHub API. Some files may be missing.")
        return data.get("tree", [])

    def get_file_content(self, owner: str, repo: str, path: str) -> Optional[str]:
        """Return the decoded text content of a file, or None on error."""
        import base64
        try:
            data = self._get(f"/repos/{owner}/{repo}/contents/{path}")
            if data.get("encoding") == "base64":
                return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            return data.get("content", "")
        except Exception as e:
            logger.debug(f"Could not fetch {path}: {e}")
            return None

    def get_raw_url(self, owner: str, repo: str, branch: str, path: str) -> Optional[str]:
        """Return the raw.githubusercontent.com URL for a file."""
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"

    def fetch_raw(self, url: str) -> Optional[str]:
        """Fetch content from a raw URL."""
        try:
            resp = self.session.get(url, timeout=20)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.debug(f"Raw fetch failed for {url}: {e}")
            return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get(self, path: str, retry: int = 3) -> dict:
        url = self.BASE_URL + path
        for attempt in range(retry):
            resp = self.session.get(url, timeout=20)
            if resp.status_code == 403 and "rate limit" in resp.text.lower():
                wait = 60 * (attempt + 1)
                logger.warning(f"Rate limited. Waiting {wait}s before retry {attempt+1}/{retry}...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError(f"Failed to GET {url} after {retry} retries.")
