"""
Autonomous API Extractor Agent
Orchestrates: GitHub fetching → file filtering → parsing → schema building → reporting.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from .github_client import GitHubClient
from .parser import EndpointParser

logger = logging.getLogger(__name__)

# Files/directories to skip (node_modules, build artifacts, etc.)
SKIP_DIRS = {
    "node_modules", "dist", ".git", "coverage", "__pycache__",
    ".nyc_output", "build", ".angular", "frontend/dist",
}

# Source file extensions and names worth scanning
PARSEABLE_EXTENSIONS = {".ts", ".js", ".yaml", ".yml", ".json"}
PARSEABLE_NAMES = {"server.ts", "server.js", "app.ts", "app.js"}

# Route-related path keywords (prioritize scanning these files first)
ROUTE_KEYWORDS = {
    "route", "router", "server", "app", "api",
    "controller", "handler", "middleware", "endpoint",
    "spec", "test", "frisby", "swagger", "openapi",
}


class APIExtractorAgent:
    """
    Autonomous agent that:
    1. Fetches repo file tree from GitHub
    2. Identifies source files likely to contain route definitions
    3. Downloads and parses each file
    4. Builds structured API endpoint + schema report
    """

    def __init__(self, github_url: str, github_token: Optional[str] = None):
        self.github_url = github_url.strip()
        self.client = GitHubClient(token=github_token)
        self.parser = EndpointParser()

    def run(self) -> dict:
        logger.info(f"🤖 Agent starting for: {self.github_url}")

        # Step 1: Parse repo coordinates
        owner, repo = self.client.parse_repo_url(self.github_url)
        logger.info(f"📦 Repository: {owner}/{repo}")

        # Step 2: Get default branch
        branch = self.client.get_default_branch(owner, repo)
        logger.info(f"🌿 Default branch: {branch}")

        # Step 3: Fetch full file tree
        logger.info("🗂  Fetching repository file tree...")
        tree = self.client.get_tree(owner, repo, branch)
        logger.info(f"   Found {len(tree)} items in tree")

        # Step 4: Filter relevant files
        target_files = self._select_files(tree)
        logger.info(f"🔍 Selected {len(target_files)} files to analyze")

        # Step 5: Parse each file
        all_endpoints = []
        for i, file_path in enumerate(target_files, start=1):
            logger.info(f"   [{i}/{len(target_files)}] Parsing: {file_path}")
            raw_url = self.client.get_raw_url(owner, repo, branch, file_path)
            content = self.client.fetch_raw(raw_url)
            if not content:
                logger.debug(f"   Skipping (empty or error): {file_path}")
                continue
            endpoints = self.parser.parse_file(file_path, content)
            if endpoints:
                logger.info(f"   → Found {len(endpoints)} endpoint(s)")
            all_endpoints.extend(endpoints)

        # Step 6: Sort and deduplicate
        all_endpoints.sort(key=lambda e: (e.tags[0] if e.tags else "", e.path, e.method))

        logger.info(f"\n✅ Extraction complete. Total endpoints: {len(all_endpoints)}")

        return self._build_report(
            owner=owner,
            repo=repo,
            branch=branch,
            endpoints=all_endpoints,
            files_scanned=target_files,
        )

    # ------------------------------------------------------------------
    # File selection logic
    # ------------------------------------------------------------------

    def _select_files(self, tree: list[dict]) -> list[str]:
        """
        Filter the repo tree to find files worth scanning.
        Priority order: server entry points → route files → test specs → openapi specs.
        """
        high_priority: list[str] = []
        medium_priority: list[str] = []
        low_priority: list[str] = []

        for item in tree:
            if item.get("type") != "blob":
                continue

            path: str = item.get("path", "")
            parts = path.split("/")

            # Skip ignored directories
            if any(d in parts for d in SKIP_DIRS):
                continue

            filename = parts[-1].lower()
            ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""

            if ext not in PARSEABLE_EXTENSIONS:
                continue

            # High priority: server entry point, known route files
            if filename in {"server.ts", "server.js", "app.ts", "app.js", "routes.ts", "routes.js"}:
                high_priority.append(path)
            elif any(kw in path.lower() for kw in ROUTE_KEYWORDS):
                medium_priority.append(path)
            elif ext in {".yaml", ".yml"} and any(kw in path.lower() for kw in {"api", "swagger", "openapi"}):
                high_priority.append(path)
            elif ext == ".json" and "swagger" in path.lower():
                high_priority.append(path)
            elif ext in {".ts", ".js"}:
                low_priority.append(path)

        # Cap low priority to avoid fetching thousands of UI files
        return high_priority + medium_priority + low_priority[:80]

    # ------------------------------------------------------------------
    # Report builder
    # ------------------------------------------------------------------

    def _build_report(
        self,
        owner: str,
        repo: str,
        branch: str,
        endpoints: list,
        files_scanned: list[str],
    ) -> dict:
        endpoint_dicts = [ep.to_dict() for ep in endpoints]

        # Collect unique tags for summary
        all_tags: set[str] = set()
        for ep in endpoints:
            all_tags.update(ep.tags)

        methods_count: dict[str, int] = {}
        for ep in endpoints:
            methods_count[ep.method] = methods_count.get(ep.method, 0) + 1

        return {
            "meta": {
                "repository": f"https://github.com/{owner}/{repo}",
                "owner": owner,
                "repo": repo,
                "branch": branch,
                "extracted_at": datetime.now(timezone.utc).isoformat(),
                "agent_version": "1.0.0",
                "files_scanned": len(files_scanned),
                "total_endpoints": len(endpoints),
            },
            "summary": {
                "total_endpoints": len(endpoints),
                "by_method": methods_count,
                "by_tag": {
                    tag: sum(1 for ep in endpoints if tag in ep.tags)
                    for tag in sorted(all_tags)
                },
                "auth_required_count": sum(1 for ep in endpoints if ep.auth_required),
                "source_files": list(set(ep.source_file for ep in endpoints)),
            },
            "endpoints": endpoint_dicts,
        }
