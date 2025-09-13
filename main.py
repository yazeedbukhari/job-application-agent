import os
import requests
from bs4 import BeautifulSoup
import json
from serpapi import GoogleSearch
from playwright.sync_api import sync_playwright
import subprocess
import json
import re

API_KEY = os.getenv("SERPAPI_KEY")

def fetch_html(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)
        html = page.content()
        browser.close()
        return html
    
def ask_llm(prompt, model="mistral:7b"):
    result = subprocess.run(
        ["ollama", "run", model],
        input=prompt.encode("utf-8"),
        stdout=subprocess.PIPE
    )
    return result.stdout.decode("utf-8")

REQUIRED_KEYS = [
    "title",
    "location",
    "company",
    "salary range",
    "hiring manager",
    "department",
]

def extract_json_object(text):
    try:
        return json.loads(text)
    except Exception:
        pass

    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if m:
        candidate = m.group(1)
        try:
            return json.loads(candidate)
        except Exception:
            pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = text[start:end + 1]
        try:
            return json.loads(snippet)
        except Exception:
            pass

    return None

def normalize_job_data(d):
    out = {}
    for k in REQUIRED_KEYS:
        v = d.get(k, "") if isinstance(d, dict) else ""
        if v is None:
            v = ""
        elif not isinstance(v, str):
            v = str(v)
        else:
            v = v.strip()
        out[k] = v
    return out

def parse_job(url):
    html = fetch_html(url)

    #with open("html.txt", "w", encoding="utf-8") as f:
    #    f.write(html)

    with open("prompt.txt", "r", encoding="utf-8") as f:
        prompt = f.read()
        prompt += f"""
            HTML:
            {html[:10000]}
            """
        
    raw_output = ask_llm(prompt)

    data = extract_json_object(raw_output)
    if not isinstance(data, dict):
        data = {}

    data = normalize_job_data(data)

    #with open("parsed.txt", "w", encoding="utf-8") as f:
    #    json.dump(data, f, ensure_ascii=False, indent=2)

    return data

def search_profiles(job_title, company):
    query = f'site:linkedin.com/in "{job_title}" "{company}"'
    search = GoogleSearch({"q": query, "engine": "google", "api_key": API_KEY})
    results = search.get_dict().get("organic_results", [])
    profiles = [{"title": r["title"], "url": r["link"]} for r in results]
    return profiles

if __name__ == "__main__":
    # Example: replace with a real job link
    job_url = "https://sunlife.wd3.myworkdayjobs.com/en-US/Campus/job/Toronto-Ontario/Student--Junior-Software-Engineer--Winter-2026-_JR00114373?utm_source=Simplify&ref=Simplify"
    job = parse_job(job_url)
    print("Parsed Job:", job)

    if job:
        profiles = search_profiles(job["title"], job["company"])
        print("Candidate Profiles:")
        for p in profiles:
            print(p)
