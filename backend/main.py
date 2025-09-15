import argparse
import json
import os

import utilities.logging_config as logging_config
from app import create_app
from app.services.job_parser.job_parser import parse_job
from app.services.profile_search.profile_search import search_profiles

logger = logging_config.get_logger(__name__)

def main():
    # Ensure logging writes only to backend/app.log (no console output)
    logging_config.configure(
        log_file=os.path.join(os.path.dirname(__file__), "app.log"),
        add_console=False,
    )
    parser = argparse.ArgumentParser(description="Job Application Agent")
    parser.add_argument("--mode", choices=["cli", "api"], default="cli")
    parser.add_argument("--url", help="Job posting URL (for CLI mode)")
    args = parser.parse_args()

    if args.mode == "cli":
        if not args.url:
            logger.error("You must provide --url in CLI mode")
            return
        job = parse_job(args.url)
        if job:
            profiles = search_profiles(job["title"], job["company"], job["location"])
            with open(os.path.join(os.path.dirname(__file__), "profiles.json"), "w", encoding="utf-8") as f:
                json.dump(profiles, f, ensure_ascii=False, indent=2)
            logger.info("Profiles saved to profiles.json")

    elif args.mode == "api":
        app = create_app()
        app.run(host="0.0.0.0", port=8080, debug=True)

if __name__ == "__main__":
    main()
