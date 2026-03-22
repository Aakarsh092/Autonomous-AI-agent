#!/usr/bin/env python3
"""
Autonomous AI Agent for GitHub Repository API Extraction
Extracts all API endpoints and their request/response schemas from a GitHub repo.
"""

import argparse
import sys
import json
import logging
from src.agent import APIExtractorAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

def main():
    parser = argparse.ArgumentParser(
        description="Autonomous AI Agent: Extract API endpoints and schemas from a GitHub repository"
    )
    parser.add_argument(
        "github_url",
        nargs="?",
        default="https://github.com/juice-shop/juice-shop",
        help="GitHub repository URL (default: OWASP Juice Shop)"
    )
    parser.add_argument(
        "--output", "-o",
        default="output/api_report.json",
        help="Output file path for the JSON report (default: output/api_report.json)"
    )
    parser.add_argument(
        "--format", "-f",
        choices=["json", "markdown", "both"],
        default="both",
        help="Output format: json, markdown, or both (default: both)"
    )
    parser.add_argument(
        "--token",
        default=None,
        help="GitHub Personal Access Token (optional, increases rate limit)"
    )

    args = parser.parse_args()

    print("\n" + "="*65)
    print("   AUTONOMOUS AI AGENT — GitHub API Endpoint Extractor")
    print("="*65)
    print(f"   Target Repository : {args.github_url}")
    print(f"   Output Format     : {args.format}")
    print(f"   Output Path       : {args.output}")
    print("="*65 + "\n")

    agent = APIExtractorAgent(github_url=args.github_url, github_token=args.token)
    report = agent.run()

    import os
    os.makedirs("output", exist_ok=True)

    if args.format in ("json", "both"):
        json_path = args.output if args.output.endswith(".json") else args.output + ".json"
        with open(json_path, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\n✅ JSON report saved to: {json_path}")

    if args.format in ("markdown", "both"):
        md_path = args.output.replace(".json", ".md") if args.output.endswith(".json") else args.output + ".md"
        from src.reporter import MarkdownReporter
        md_content = MarkdownReporter(report).generate()
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        print(f"✅ Markdown report saved to: {md_path}")

    endpoints = report.get("endpoints", [])
    print(f"\n📊 Summary: {len(endpoints)} API endpoints extracted from {args.github_url}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
