#!/usr/bin/env python3
"""
Open-Source Telemetry Dashboard Updater
Fetches real-time status of upstream pull requests authored by dulanachathurma
and updates assets/oss-dashboard.svg accordingly.
"""

import os
import re
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path

# Tracked Upstream Open-Source PRs
TRACKED_PRS = [
    {"repo": "wso2/oxygen-ui", "number": 704, "title": "AIAssistant & Copilot Suite"},
    {"repo": "wso2/apim-apps", "number": 1437, "title": "Scope Pagination & Hardened Utilities"},
    {"repo": "ballerina-platform/ballerina-dev-website", "number": 10487, "title": "Platform Guides & References"},
    {"repo": "openchoreo/openchoreo", "number": 5430, "title": "CLI stdin streaming & dry-run"},
    {"repo": "doocs/leetcode", "number": 6231, "title": "Trapping Rain Water Solution"},
]

# Upstream Open-Source Organizations to include when auto-discovering PRs
TRACKED_ORGS = {
    "wso2",
    "openchoreo",
    "ballerina-platform",
    "doocs",
}

GITHUB_USERNAME = "dulanachathurma"
ROOT_DIR = Path(__file__).resolve().parent.parent
SVG_PATH = ROOT_DIR / "assets" / "oss-dashboard.svg"


def fetch_url(url: str, token: str | None = None) -> dict | None:
    headers = {
        "User-Agent": "OSS-Telemetry-Dashboard-Updater/1.0",
        "Accept": "application/vnd.github.v3+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"[WARN] HTTP {e.code} fetching {url}: {e.reason}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[WARN] Failed fetching {url}: {e}", file=sys.stderr)
        return None


def fetch_pr_status(repo: str, number: int, token: str | None = None) -> dict:
    url = f"https://api.github.com/repos/{repo}/pulls/{number}"
    data = fetch_url(url, token)
    if data:
        is_merged = data.get("merged", False) or data.get("merged_at") is not None
        state = data.get("state", "open")
        return {
            "repo": repo,
            "number": number,
            "state": state,
            "merged": is_merged,
        }
    return {"repo": repo, "number": number, "state": "unknown", "merged": False}


def search_upstream_prs(username: str, token: str | None = None) -> list[dict]:
    query = f"author:{username}+type:pr+-user:{username}"
    url = f"https://api.github.com/search/issues?q={query}"
    data = fetch_url(url, token)
    prs = []
    if data and "items" in data:
        for item in data["items"]:
            repo_url = item.get("repository_url", "")
            repo_name = "/".join(repo_url.split("/")[-2:])
            org = repo_name.split("/")[0].lower() if "/" in repo_name else ""
            
            # Only include upstream PRs from tracked open-source organizations
            if org not in TRACKED_ORGS:
                continue

            pull_data = item.get("pull_request", {})
            is_merged = pull_data.get("merged_at") is not None
            prs.append({
                "repo": repo_name,
                "number": item.get("number"),
                "state": item.get("state", "open"),
                "merged": is_merged,
            })
    return prs


def calculate_metrics(token: str | None = None) -> tuple[int, int, int]:
    merged_count = 0
    in_review_count = 0
    seen_keys = set()

    # 1. Check known tracked upstream PRs
    for item in TRACKED_PRS:
        key = (item["repo"], item["number"])
        seen_keys.add(key)
        status = fetch_pr_status(item["repo"], item["number"], token)
        if status["state"] != "unknown":
            if status["merged"]:
                merged_count += 1
            elif status["state"] == "open":
                in_review_count += 1
        else:
            # Fallback based on known baselines if API unavailable
            if item["repo"] == "doocs/leetcode":
                merged_count += 1
            else:
                in_review_count += 1

    # 2. Check search API to discover additional upstream PRs in tracked orgs
    discovered_prs = search_upstream_prs(GITHUB_USERNAME, token)
    for pr in discovered_prs:
        key = (pr["repo"], pr["number"])
        if key not in seen_keys:
            seen_keys.add(key)
            if pr["merged"]:
                merged_count += 1
            elif pr["state"] == "open":
                in_review_count += 1

    total_count = merged_count + in_review_count
    return total_count, merged_count, in_review_count


def update_svg(svg_file: Path, total: int, merged: int, in_review: int) -> bool:
    if not svg_file.exists():
        print(f"[ERROR] SVG file not found at {svg_file}", file=sys.stderr)
        return False

    content = svg_file.read_text(encoding="utf-8")

    # Format numbers
    total_str = f"{total:02d}"
    breakdown_str = f"{merged} MERGED | {in_review} IN REVIEW"

    # Regex 1: Upstream PR count (font-size="46")
    pattern_count = r'(<text\s+x="125"\s+y="102"[^>]*font-size="46"[^>]*>)[^<]*(</text>)'
    new_content, count_subs = re.subn(pattern_count, rf"\g<1>{total_str}\g<2>", content)

    # Regex 2: Status breakdown (font-size="9.5")
    pattern_status = (
        r'(<text\s+x="125"\s+y="151"[^>]*font-size="9.5"[^>]*>)\s*[^<]*\s*(</text>)'
    )
    new_content, status_subs = re.subn(pattern_status, rf"\g<1>\n    {breakdown_str}\n  \g<2>", new_content)

    if count_subs == 0 or status_subs == 0:
        print(f"[WARN] Regex replacement warnings: count_subs={count_subs}, status_subs={status_subs}")

    if content != new_content:
        svg_file.write_text(new_content, encoding="utf-8")
        print(f"[SUCCESS] Updated {svg_file.name}: {total_str} PRs ({breakdown_str})")
        return True
    else:
        print(f"[INFO] No changes required in {svg_file.name}. Current metrics: {total_str} PRs ({breakdown_str})")
        return False


def main():
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    print(f"--- Upstream Telemetry Dashboard Updater ---")
    print(f"Target user : {GITHUB_USERNAME}")
    print(f"Target SVG  : {SVG_PATH}")
    print(f"Tracked Orgs: {', '.join(sorted(TRACKED_ORGS))}")
    print(f"Auth token  : {'Provided' if token else 'None (unauthenticated)'}")

    total, merged, in_review = calculate_metrics(token)
    print(f"Computed metrics -> Total: {total:02d} | Merged: {merged} | In Review: {in_review}")

    update_svg(SVG_PATH, total, merged, in_review)


if __name__ == "__main__":
    main()
