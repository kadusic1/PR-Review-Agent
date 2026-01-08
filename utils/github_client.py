# Funkcije za GitHub API (dohvati PR kod, postavi komentar)
import os
import requests
from github import Github
from urllib.parse import urlparse
from dotenv import load_dotenv
import logging


load_dotenv()

# Configure audit logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [AUDIT] %(levelname)s: %(message)s",
)

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    raise RuntimeError("GITHUB_TOKEN not found in environment variables.")

g = Github(GITHUB_TOKEN)


def get_pr_diff(pr_url: str) -> str:
    """
    Fetches the raw diff of a pull request from GitHub and returns owner, PR id, and diff.

    Args:
            pr_url (str): URL to the pull request (e.g. https://github.com/owner/repo/pull/123)
    Returns:
            dict: {"owner": str, "pr_id": int, "diff": str}
    Example:
            result = get_pr_diff("https://github.com/octocat/Hello-World/pull/1347")
            # result = {"owner": "octocat", "pr_id": 1347, "diff": "..."}
    """
    try:
        parsed = urlparse(pr_url)
        if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
            raise ValueError("PR URL must be from github.com.")
        path_parts = parsed.path.strip("/").split("/")
        if len(path_parts) < 4 or path_parts[2] != "pull":
            raise ValueError("Invalid PR URL format.")
        owner, _, _, pr_number = path_parts[:4]
        diff_url = pr_url + ".diff"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        resp = requests.get(diff_url, headers=headers)
        resp.raise_for_status()
        logging.info(f"SUCCESS: get_pr_diff for PR {pr_url}")
        return {"owner": owner, "pr_id": int(pr_number), "diff": resp.text}
    except Exception as e:
        logging.error(f"FAIL: get_pr_diff for PR {pr_url} - {e}")
        raise


def post_comment(pr_url: str, comment_body: str):
    """
    Posts a comment to a pull request using the GitHub API.

    Args:
            pr_url (str): URL to the pull request.
            comment_body (str): The comment text.
    Returns:
            None
    Example:
            post_comment("https://github.com/octocat/Hello-World/pull/1347", "Nice work!")
    """
    try:
        parsed = urlparse(pr_url)
        if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
            raise ValueError("PR URL must be from github.com.")
        path_parts = parsed.path.strip("/").split("/")
        if len(path_parts) < 4 or path_parts[2] != "pull":
            raise ValueError("Invalid PR URL format.")
        owner, repo, _, pr_number = path_parts[:4]
        repo_obj = g.get_repo(f"{owner}/{repo}")
        pr = repo_obj.get_pull(int(pr_number))
        pr.create_issue_comment(comment_body)
        logging.info(f"SUCCESS: post_comment to PR {pr_url}")
    except Exception as e:
        logging.error(f"FAIL: post_comment to PR {pr_url} - {e}")
        raise
