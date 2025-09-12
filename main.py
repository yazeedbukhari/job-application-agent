import os
import requests
from bs4 import BeautifulSoup
import json
from serpapi import GoogleSearch
from playwright.sync_api import sync_playwright

API_KEY = os.getenv("SERPAPI_KEY")

def fetch_html(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        html = page.content()
        browser.close()
        return html

def parse_job(url):
    html = fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")
    print(soup.prettify()[:1000])  # first 1000 chars

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get("@type") == "JobPosting":
                return {
                    "title": data.get("title"),
                    "company": data.get("hiringOrganization", {}).get("name"),
                    "location": data.get("jobLocation", [{}])[0].get("address", {}).get("addressLocality"),
                }
        except Exception:
            continue
    return {}

def search_profiles(job_title, company):
    query = f'site:linkedin.com/in "{job_title}" "{company}"'
    search = GoogleSearch({"q": query, "engine": "google", "api_key": API_KEY})
    results = search.get_dict().get("organic_results", [])
    profiles = [{"title": r["title"], "url": r["link"]} for r in results]
    return profiles

if __name__ == "__main__":
    # Example: replace with a real job link
    job_url = "https://boards.greenhouse.io/example/jobs/123456"
    job = parse_job(job_url)
    print("Parsed Job:", job)

    if job:
        profiles = search_profiles(job["title"], job["company"])
        print("Candidate Profiles:")
        for p in profiles:
            print(p)