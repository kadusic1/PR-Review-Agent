import os
import re
import logging
import requests
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


# --- Diff Compression Parameters ---
MAX_DIFF_LENGTH = 24000  # Global hard limit on returned characters
CONTEXT_LINES = 3  # Unchanged context lines to keep around a change
MAX_CONSECUTIVE_ADDED = 30  # Collapse huge added blocks larger than this
MAX_CONSECUTIVE_REMOVED = 30  # Collapse huge removed blocks larger than this
MAX_HUNKS_PER_FILE = 12  # Keep at most this many hunks per file (drop rest with a note)

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

# Pre-compiled Regex Patterns
file_header_pattern = re.compile(r"^diff --git a/(.*) b/(.*)")
hunk_header_pattern = re.compile(r"^@@\s*(-\d+(?:,\d+)?)\s*\+(\d+(?:,\d+)?)\s*@@")


def _is_text_extension(filename: str) -> bool:
    """
    Checks if a file extension is considered a text file suitable for diff processing.

    Args:
        filename (str): The name of the file to check.

    Returns:
        bool: True if the file is a text file (not in EXCLUDED_EXTENSIONS), False otherwise.

    Example:
        >>> _is_text_extension("src/main.py")
        True
        >>> _is_text_extension("package-lock.json")
        False
    """
    ext = os.path.splitext(filename)[1].lower()
    return ext not in EXCLUDED_EXTENSIONS


def _collapse_sequence(seq_lines: list, prefix_char: str, max_keep: int = 10) -> list:
    """
    Collapses a long consecutive sequence of added ('+') or removed ('-') lines.

    Preserves the first few and last few lines (head and tail), inserting a
    placeholder summary in the middle to save tokens.

    Args:
        seq_lines (list): List of diff lines (all expected to start with prefix_char).
        prefix_char (str): Either '+' or '-' to indicate the line type.
        max_keep (int): Maximum number of lines to keep in total (head + tail).

    Returns:
        list: The collapsed list of lines including the placeholder.

    Example:
        >>> lines = ['+line1', '+line2', '+line3', '+line4', '+line5']
        >>> _collapse_sequence(lines, '+', max_keep=2)
        ['+line1', '+ ... [5 lines added collapsed] ...', '+line5']
    """
    n = len(seq_lines)
    if n <= max_keep:
        return seq_lines

    keep_head = max_keep // 2
    keep_tail = max_keep - keep_head
    placeholder = [
        f"{prefix_char} ... [{n} lines {'added' if prefix_char == '+' else 'removed'} collapsed] ..."
    ]

    return seq_lines[:keep_head] + placeholder + seq_lines[-keep_tail:]


def compress_diff(raw_diff: str) -> str:
    """
    Compresses a raw unified diff string for efficient review and LLM token usage.

    The compression strategy involves:
    1. Skipping files with excluded extensions (binary, lockfiles).
    2. Truncating the global output if it exceeds MAX_DIFF_LENGTH.
    3. Parsing individual "hunks" within files to:
       - Collapse long blocks of unchanged context lines.
       - Collapse large blocks of added or removed lines.
       - Preserve Python class/function definitions even inside collapsed blocks.
       - Limit the number of hunks per file.

    Args:
        raw_diff (str): The raw unified diff string obtained from GitHub.

    Returns:
        str: A compressed and cleaned diff string.

    Example:
        >>> raw = (
        ...     "diff --git a/main.py b/main.py\\n"
        ...     "index 123..456 100644\\n"
        ...     "--- a/main.py\\n"
        ...     "+++ b/main.py\\n"
        ...     "@@ -1,50 +1,50 @@\\n"
        ...     " def main():\\n"
        ...     "     print('Start')\\n"
        ...     "     # ... 40 unchanged lines ...\\n"
        ...     "     return True"
        ... )
        >>> print(compress_diff(raw))
        diff --git a/main.py b/main.py
        index 123..456 100644
        --- a/main.py
        +++ b/main.py
        @@ -1,50 +1,50 @@
         def main():
         print('Start')
          ... [40 unchanged lines collapsed] ...
         return True
    """
    lines = raw_diff.splitlines()
    out_lines = []
    idx = 0
    total_chars = 0

    while idx < len(lines):
        line = lines[idx]
        header_match = file_header_pattern.match(line)

        if header_match:
            filename = header_match.group(1)

            # 1. Skip excluded files
            if not _is_text_extension(filename):
                logging.info(f"Skipping binary/excluded diff for {filename}")
                idx += 1
                # Fast-forward until next diff header or EOF
                while idx < len(lines) and not file_header_pattern.match(lines[idx]):
                    idx += 1
                continue

            # 2. Collect current file block
            file_block = [line]
            idx += 1
            while idx < len(lines) and not file_header_pattern.match(lines[idx]):
                file_block.append(lines[idx])
                idx += 1

            # 3. Process the file block
            processed_file_lines = _process_file_block(filename, file_block)

            # 4. Append and check global limit
            for l in processed_file_lines:
                out_lines.append(l)
                total_chars += len(l) + 1  # +1 for newline

                if total_chars >= MAX_DIFF_LENGTH:
                    out_lines.append("\n... [DIFF TRUNCATED DUE TO SIZE LIMIT] ...")
                    logging.warning("Diff truncated due to size limit.")
                    return "\n".join(out_lines)

        else:
            # Metadata lines (e.g., initial headers before any file diff)
            out_lines.append(line)
            total_chars += len(line) + 1
            if total_chars >= MAX_DIFF_LENGTH:
                out_lines.append("\n... [DIFF TRUNCATED DUE TO SIZE LIMIT] ...")
                logging.warning("Diff truncated due to size limit.")
                return "\n".join(out_lines)
            idx += 1

    return "\n".join(out_lines)


def _process_file_block(filename: str, block_lines: list) -> list:
    """
    Parses a single file's diff lines into hunks and applies compression.

    Args:
        filename (str): Name of the file.
        block_lines (list): List of strings representing the raw diff for this file.

    Returns:
        list: A list of strings representing the compressed diff for this file.
    """
    out = []
    hunks = []
    cur_hunk = None
    header_lines = []

    # Split block into Headers and Hunks
    for line in block_lines:
        if hunk_header_pattern.match(line):
            cur_hunk = {"header": line, "lines": []}
            hunks.append(cur_hunk)
        else:
            if cur_hunk is None:
                header_lines.append(line)
            else:
                cur_hunk["lines"].append(line)

    # Always keep file headers (index, ---, +++)
    if header_lines:
        out.extend(header_lines)

    if not hunks:
        return out

    # Limit the number of hunks per file
    if len(hunks) > MAX_HUNKS_PER_FILE:
        keep = hunks[:MAX_HUNKS_PER_FILE]
        dropped = len(hunks) - MAX_HUNKS_PER_FILE
        logging.info(
            f"File {filename}: {dropped} hunks omitted due to MAX_HUNKS_PER_FILE."
        )
    else:
        keep = hunks
        dropped = 0

    # Check if we should apply Python-specific signature preservation
    is_python = filename.lower().endswith(".py")

    for h in keep:
        out.append(h["header"])
        compressed = _compress_hunk_lines(h["lines"], is_python)
        out.extend(compressed)

    if dropped > 0:
        out.append(f"... [ {dropped} additional hunks omitted for {filename} ]")

    return out


def _compress_hunk_lines(hunk_lines: list, is_python: bool) -> list:
    """
    Compresses the lines within a single hunk.

    Logic:
    - Collapses long sequences of unchanged context lines (starting with ' ').
    - Collapses long sequences of added ('+') or removed ('-') lines.
    - If is_python is True, attempts to rescue 'def'/'class' lines from being collapsed.

    Args:
        hunk_lines (list): Lines inside the hunk (excluding the @@ header).
        is_python (bool): Whether to look for Python function/class signatures.

    Returns:
        list: Compressed lines.
    """
    out = []
    i = 0
    n = len(hunk_lines)

    while i < n:
        line = hunk_lines[i]

        # --- Unchanged Lines (Context) ---
        if line.startswith(" "):
            j = i
            while j < n and hunk_lines[j].startswith(" "):
                j += 1
            seq = hunk_lines[i:j]

            if len(seq) > CONTEXT_LINES * 2:
                # Keep head and tail, collapse middle
                out.extend(seq[:CONTEXT_LINES])
                out.append(
                    f"  ... [{len(seq) - 2*CONTEXT_LINES} unchanged lines collapsed] ..."
                )
                out.extend(seq[-CONTEXT_LINES:])
            else:
                out.extend(seq)
            i = j

        # --- Added Lines ---
        elif line.startswith("+"):
            j = i
            while j < n and hunk_lines[j].startswith("+"):
                j += 1
            seq = hunk_lines[i:j]

            if is_python:
                # Regex to find 'def function():' or 'class Class:'
                sig_pattern = r"^\+(\s*)def\s+\w+\s*\(|^\+(\s*)class\s+\w+\s*[:\(]"
                sig_lines = [s for s in seq if re.match(sig_pattern, s)]

                if sig_lines and len(seq) > MAX_CONSECUTIVE_ADDED:
                    # Collapse, but try to re-insert signatures
                    sig_set = set(sig_lines)
                    merged = _collapse_sequence(seq, "+", max_keep=10)

                    # Ensure signature lines are present in the final output
                    # Note: We use a simple list check. If the signature was collapsed,
                    # we insert it back.
                    final_merged = []
                    # First, populate from the collapsed result
                    for ln in merged:
                        final_merged.append(ln)

                    # Now inject missing signatures.
                    # We insert them before the last element (tail) to keep them somewhat in context,
                    # or append if list is short.
                    for s in sig_set:
                        if s not in final_merged:
                            # Insert before the last item if possible to keep it visible
                            if len(final_merged) > 1:
                                final_merged.insert(-1, s)
                            else:
                                final_merged.append(s)
                    out.extend(final_merged)
                else:
                    out.extend(
                        _collapse_sequence(seq, "+", max_keep=MAX_CONSECUTIVE_ADDED)
                    )
            else:
                out.extend(_collapse_sequence(seq, "+", max_keep=MAX_CONSECUTIVE_ADDED))
            i = j

        # --- Removed Lines ---
        elif line.startswith("-"):
            j = i
            while j < n and hunk_lines[j].startswith("-"):
                j += 1
            seq = hunk_lines[i:j]
            out.extend(_collapse_sequence(seq, "-", max_keep=MAX_CONSECUTIVE_REMOVED))
            i = j

        # --- Metadata/Header Lines ---
        else:
            out.append(line)
            i += 1

    return out


def get_pr_diff(pr_url: str) -> dict:
    """
    Fetches the raw diff of a pull request from GitHub, compresses it, and returns the data.

    Args:
        pr_url (str): URL to the pull request (e.g., https://github.com/owner/repo/pull/123).

    Returns:
        dict: A dictionary containing:
            - "owner": The repository owner.
            - "pr_id": The pull request number.
            - "diff": The compressed diff string.

    Raises:
        ValueError: If the URL is invalid.
        requests.exceptions.RequestException: If the GitHub API call fails.

    Example:
        >>> result = get_pr_diff("https://github.com/octocat/Hello-World/pull/1347")
        >>> print(result["diff"])
        diff --git a/README.md b/README.md
        ...
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
        compressed_diff = compress_diff(raw_diff)

        logging.info(
            f"SUCCESS: get_pr_diff for PR {pr_url}. Original size: {len(raw_diff)}, Compressed: {len(compressed_diff)}"
        )

        return {"owner": owner, "pr_id": int(pr_number), "diff": compressed_diff}

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
