import os
import sys
from dotenv import load_dotenv
from core.graph import build_graph
from core.state import make_initial_state
from utils.github_client import get_pr_diff

# Učitaj .env (samo za lokalno testiranje, na GitHubu ovo ne radi ništa jer nema .env fajla)
load_dotenv()


def main():
    """
    Entry point for GitHub Action.
    """
    pr_url = os.getenv("PR_URL")

    if not pr_url:
        print("Error: PR_URL environment variable not set.")
        sys.exit(1)
    # ---------------------------------------

    print(f"Starting Analysis for: {pr_url}")

    try:
        # 3. Dohvati Diff
        try:
            diff_data = get_pr_diff(pr_url)
        except Exception as e:
            print(f"Error fetching PR diff: {e}")
            sys.exit(1)
        pr_diff = diff_data.get("diff", "")

        if not pr_diff:
            print("Error: Could not retrieve PR diff.")
            sys.exit(1)

        # 4. Pokreni Graf
        state = make_initial_state(pr_diff, pr_url)
        app = build_graph()

        result = app.invoke(state)

        # Logika za ispis rezultata (ToolNode će već objaviti komentar na GitHub)
        if "final_report" in result:
            print("✅ Workflow finished. Report generated.")
            # Opcionalno ispiši report u logove
            # print(result["final_report"])

    except Exception as e:
        print(f"❌ Critical Error in main executiiion: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
