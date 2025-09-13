import os
import json
from serpapi import GoogleSearch
from playwright.sync_api import sync_playwright
import logging

import helper.extraction as extraction
import helper.llm as llm
import helper.logging_config as logging_config

API_KEY = os.getenv("SERPAPI_KEY")

# Configure logging via helper
logging_config.configure(level=logging.INFO, log_file="app.log")
logger = logging_config.get_logger(__name__)

def fetch_html(url):
    logger.info(f"Fetching HTML from {url}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        html = page.content()
        browser.close()
    logger.debug(f"Fetched {len(html)} characters of HTML")
    return html

def parse_job(url):
    html = fetch_html(url)
    logger.debug("Fetched HTML content for prompting")

    # Load base prompt template
    with open("prompt.txt", "r", encoding="utf-8") as f:
        base_prompt = f.read()

    # Derive company strictly from URL in code to avoid hallucinations
    derived_company = extraction.derive_company_from_url(url)
    logger.info(f"URL-derived company (code): {derived_company}")

    # Prompt 2: HTML-only parsing (using relevant text excerpt)
    relevant_text = extraction.extract_relevant_text(html)
    logger.debug(f"Relevant text length: {len(relevant_text)}")
    html_prompt = (
        f"{base_prompt}\n\n"
        "You are analyzing ONLY the following page content excerpt (plain text extracted from HTML).\n"
        "Your response MUST be a single JSON object (no prose, no code fences).\n"
        "- Do NOT infer 'company' from this content; set 'company' to an empty string.\n"
        "- For 'location', return only the city if present.\n\n"
        "PAGE CONTENT:\n"
        f"{relevant_text}\n"
    )
    logger.debug("Sending HTML-only prompt to LLM")
    raw_html_output = llm.ask(html_prompt)
    html_data = extraction.extract_json_object(raw_html_output)
    if not isinstance(html_data, dict):
        logger.info("HTML prompt returned non-JSON/prose. Re-prompting for JSON-only output.")
        skeleton = extraction.build_json_skeleton()
        repair_prompt = (
            f"{base_prompt}\n\n"
            "Output exactly one JSON object and nothing else.\n"
            "Use this template and fill in values (keep missing values as empty strings):\n"
            f"{skeleton}\n\n"
            "PAGE CONTENT:\n"
            f"{relevant_text}\n"
        )
        raw_html_output = llm.ask(repair_prompt)
        html_data = extraction.extract_json_object(raw_html_output) or {}
    html_data = extraction.normalize_job_data(html_data)

    # Merge results: prefer company from URL (derived); others from HTML prompt
    final_data = html_data.copy()
    final_data["company"] = derived_company

    # Fallbacks if HTML model did not comply
    if not final_data.get("title") or not final_data.get("location"):
        heur = extraction.extract_title_location_from_html(html)
        if not final_data.get("title") and heur.get("title"):
            final_data["title"] = heur["title"]
        if not final_data.get("location") and heur.get("location"):
            final_data["location"] = heur["location"]

    logger.info(f"Extracted job data: {final_data}")
    return final_data

def search_profiles(job_title, company, location):
    # Build base job query tokens
    jt = (job_title or "").lower()
    if "machine learning" in jt or " ml" in jt or jt.startswith("ml"):
        base_job_query = '"Machine Learning" OR ML OR "Machine Learning Engineer"'
    elif "artificial intelligence" in jt or " ai" in jt or jt.startswith("ai"):
        base_job_query = '"Artificial Intelligence" OR AI OR "AI Engineer"'
    else:
        base_job_query = 'software OR SWE OR SDE OR "Software Engineer" OR "Software Developer"'

    company_q = f'"{company}"' if company else ''
    location_q = f'"{location}"' if location else ''
    site_q = 'site:linkedin.com/in'
    filters_q = '-student -intern'

    # Query 1: individual contributor
    query_ic = f"{site_q} ({base_job_query}) {company_q} {location_q} {filters_q}".strip()
    logger.info(f"Searching profiles (IC) with query: {query_ic}")
    search = GoogleSearch({"q": query_ic, "engine": "google", "api_key": API_KEY})
    results = search.get_dict().get("organic_results", [])
    profiles_ic = [
        {"title": r.get("title", ""), "url": r.get("link", ""), "queryType": "ic"}
        for r in results
        if r.get("link")
    ]

    # Query 2: lead/manager
    managers_term = '("lead" OR "manager")'
    query_mgr = f"{site_q} ({base_job_query}) {managers_term} {company_q} {location_q} {filters_q}".strip()
    logger.info(f"Searching profiles (lead/manager) with query: {query_mgr}")
    search = GoogleSearch({"q": query_mgr, "engine": "google", "api_key": API_KEY})
    results = search.get_dict().get("organic_results", [])
    profiles_mgr = [
        {"title": r.get("title", ""), "url": r.get("link", ""), "queryType": "lead_manager"}
        for r in results
        if r.get("link")
    ]

    # Combine and deduplicate by URL
    seen = set()
    combined = []
    for p in profiles_ic + profiles_mgr:
        u = p["url"]
        if u not in seen:
            combined.append(p)
            seen.add(u)
    return combined

if __name__ == "__main__":
    job_url = "https://sunlife.wd3.myworkdayjobs.com/en-US/Campus/job/Toronto-Ontario/Student--Junior-Software-Engineer--Winter-2026-_JR00114373?utm_source=Simplify&ref=Simplify"
    
    logger.info(f"Starting job parsing: {job_url}")
    job = parse_job(job_url)

    if job:
        profiles = search_profiles(job["title"], job["company"], job["location"])
        logger.info(f"Found {len(profiles)} candidate profiles")
        with open("profiles.json", "w", encoding="utf-8") as f:
            json.dump(profiles, f, ensure_ascii=False, indent=2)
