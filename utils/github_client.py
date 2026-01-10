import os
import requests
import logging
import re
from github import Github
from urllib.parse import urlparse
from dotenv import load_dotenv
from langchain_core.tools import tool

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

# Unwanted files
EXCLUDED_EXTENSIONS = {
    ".lock",
    ".json",
    ".csv",
    ".svg",
    ".png",
    ".jpg",
    ".map",
    ".min.js",
    ".min.css",
    ".pyc",
    ".md",
}
# Maksimalan broj karaktera koji šaljemo LLM-u
MAX_DIFF_LENGTH = 24000


def clean_and_reduce_diff(raw_diff: str) -> str:
    """
    Parsira sirovi diff, uklanja fajlove sa zabranjenim ekstenzijama
    i siječe diff ako pređe maksimalnu dužinu.
    """
    cleaned_lines = []
    current_length = 0
    skip_current_file = False

    # Regex za hvatanje početka novog fajla u diff-u
    # Format je obično: diff --git a/path/to/file b/path/to/file
    file_header_pattern = re.compile(r"^diff --git a/(.*) b/(.*)")

    lines = raw_diff.split("\n")

    for line in lines:
        match = file_header_pattern.match(line)

        # Ako je ovo početak novog fajla, provjeravamo ekstenziju
        if match:
            filename = match.group(1)  # Uzimamo putanju fajla
            ext = os.path.splitext(filename)[1].lower()

            if ext in EXCLUDED_EXTENSIONS:
                skip_current_file = True
                logging.info(f"Skipping file in diff: {filename}")
            else:
                skip_current_file = False

        # Ako trenutni fajl nije za preskakanje, dodajemo liniju
        if not skip_current_file:
            cleaned_lines.append(line)
            current_length += len(line)

            # Hard stop ako pređemo limit
            if current_length >= MAX_DIFF_LENGTH:
                cleaned_lines.append("\n... [DIFF TRUNCATED DUE TO SIZE LIMIT] ...")
                logging.warning("Diff truncated due to size limit.")
                break

    return "\n".join(cleaned_lines)


def get_pr_diff(pr_url: str) -> dict:
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
        diff_url = pr_url.rstrip("/") + ".diff"
        headers = {"Authorization": f"token {GITHUB_TOKEN}"}
        resp = requests.get(diff_url, headers=headers)
        resp.raise_for_status()

        raw_diff = resp.text
        reduced_diff = clean_and_reduce_diff(raw_diff)

        logging.info(
            f"SUCCESS: get_pr_diff for PR {pr_url}. Original size: {len(raw_diff)}, Reduced: {len(reduced_diff)}"
        )

        return {"owner": owner, "pr_id": int(pr_number), "diff": reduced_diff}

    except Exception as e:
        logging.error(f"FAIL: get_pr_diff for PR {pr_url} - {e}")
        raise


@tool
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
