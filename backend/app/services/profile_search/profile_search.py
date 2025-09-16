import os
from serpapi import GoogleSearch
import utilities.logging_config as logging_config

API_KEY = os.getenv("SERPAPI_KEY")
logger = logging_config.get_logger(__name__)

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
        {"title": r.get("title", ""), "url": r.get("link", ""), "queryType": "individual_contributor", "company": company_q}
        for r in results
        if r.get("link")
    ]

    # Query 2: lead/manager
    managers_term = '("lead" OR "manager")'
    query_mgr = f"{site_q} software {managers_term} {company_q} {location_q} {filters_q}".strip()
    logger.info(f"Searching profiles (lead/manager) with query: {query_mgr}")
    search = GoogleSearch({"q": query_mgr, "engine": "google", "api_key": API_KEY})
    results = search.get_dict().get("organic_results", [])
    profiles_mgr = [
        {"title": r.get("title", ""), "url": r.get("link", ""), "queryType": "lead_manager", "company": company_q}
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
