import os
import json
from serpapi import GoogleSearch
import logging

import utilities.logging_config as logging_config
from app.services.job_parser import parse_job
from app.services.profile_search import search_profiles

API_KEY = os.getenv("SERPAPI_KEY")

logging_config.configure(level=logging.INFO, log_file="app.log")
logger = logging_config.get_logger(__name__)

if __name__ == "__main__":
    job_url = "https://sunlife.wd3.myworkdayjobs.com/en-US/Campus/job/Toronto-Ontario/Student--Junior-Software-Engineer--Winter-2026-_JR00114373?utm_source=Simplify&ref=Simplify"
    
    logger.info(f"Starting job parsing: {job_url}")
    job = parse_job(job_url)

    if job:
        profiles = search_profiles(job["title"], job["company"], job["location"])
        logger.info(f"Found {len(profiles)} candidate profiles")
        with open("profiles.json", "w", encoding="utf-8") as f:
            json.dump(profiles, f, ensure_ascii=False, indent=2)
