import os
import requests
from bs4 import BeautifulSoup
import json
from serpapi import GoogleSearch
from playwright.sync_api import sync_playwright
import subprocess
import json
import re
import logging
from urllib.parse import urlparse

REQUIRED_KEYS = [
    "title",
    "location",
    "company",
    "salary range",
    "hiring manager",
    "department",
]

API_KEY = os.getenv("SERPAPI_KEY")

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # default level
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log", encoding="utf-8"),  # logs to file
        logging.StreamHandler()  # logs to console
    ]
)

logger = logging.getLogger(__name__)

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
    
def ask_llm(prompt, model="mistral:7b"):
    result = subprocess.run(
        ["ollama", "run", model],
        input=prompt.encode("utf-8"),
        stdout=subprocess.PIPE
    )
    return result.stdout.decode("utf-8")

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

def build_json_skeleton() -> str:
    return json.dumps({k: "" for k in REQUIRED_KEYS}, ensure_ascii=False, indent=2)

def derive_company_from_url(url: str) -> str:
    """Best-effort company name derivation strictly from URL.
    - Handles common ATS hosts (workday, greenhouse, lever, etc.)
    - Falls back to registered domain's second-level label.
    - Normalizes by replacing hyphens/underscores with spaces and title-casing.
    """
    try:
        u = urlparse(url)
        host = (u.hostname or "").lower()
        path = (u.path or "/").strip("/")
        parts = host.split(".")

        def norm(name: str) -> str:
            name = name.replace("-", " ").replace("_", " ")
            name = re.sub(r"\s+", " ", name).strip()
            return name.title()

        # Known aggregators / ATS patterns where company is in subdomain or path
        skip_subs = {"www", "jobs", "careers", "app", "boards"}
        if host.endswith("myworkdayjobs.com"):
            # <company>.wdN.myworkdayjobs.com
            subs = parts[:-3]  # drop myworkdayjobs.com
            subs = [s for s in subs if not re.fullmatch(r"wd\d+", s) and s not in skip_subs]
            if subs:
                return norm(subs[-1])
        if host.endswith("workable.com") or host.endswith("recruitee.com") \
           or host.endswith("bamboohr.com") or host.endswith("teamtailor.com"):
            subs = [s for s in parts[:-2] if s not in skip_subs]
            if subs:
                return norm(subs[-1])
        if host.endswith("greenhouse.io"):
            # boards.greenhouse.io/<company>
            segs = path.split("/") if path else []
            if segs and segs[0]:
                return norm(segs[0])
        if host.endswith("lever.co") or host.endswith("ashbyhq.com") or host.endswith("smartrecruiters.com"):
            # jobs.lever.co/<company>, jobs.ashbyhq.com/<company>, careers.smartrecruiters.com/<company>
            segs = path.split("/") if path else []
            if segs and segs[0]:
                return norm(segs[0])

        # Fallback to second-level domain as company (e.g., stripe.com -> Stripe)
        if len(parts) >= 2:
            candidate = parts[-2]
            if candidate not in {"co", "com", "net", "org"}:
                return norm(candidate)
    except Exception:
        pass
    return ""

def extract_from_json_ld(html: str) -> dict:
    """Extract title and location city from JSON-LD JobPosting if present."""
    try:
        soup = BeautifulSoup(html, "html.parser")
        scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
        for s in scripts:
            try:
                data = json.loads(s.string or s.text or "{}")
            except Exception:
                continue
            candidates = data if isinstance(data, list) else [data]
            for obj in candidates:
                if not isinstance(obj, dict):
                    continue
                t = obj.get("@type") or obj.get("type")
                if isinstance(t, list):
                    types = [x.lower() for x in t if isinstance(x, str)]
                else:
                    types = [str(t).lower()]
                if any("jobposting" in x for x in types):
                    title = (obj.get("title") or obj.get("name") or "").strip()
                    city = ""
                    job_loc = obj.get("jobLocation")
                    loc_objs = job_loc if isinstance(job_loc, list) else [job_loc] if job_loc else []
                    for loc in loc_objs:
                        if not isinstance(loc, dict):
                            continue
                        addr = loc.get("address", {})
                        if isinstance(addr, dict):
                            city = (addr.get("addressLocality") or "").strip()
                            if city:
                                break
                    return {"title": title, "location": city}
    except Exception:
        pass
    return {}

def extract_title_location_from_html(html: str) -> dict:
    """Heuristic extraction for title and city from HTML when LLM fails."""
    result = {"title": "", "location": ""}
    try:
        soup = BeautifulSoup(html, "html.parser")
        # Title heuristics
        meta_title = (
            soup.find("meta", attrs={"property": "og:title"})
            or soup.find("meta", attrs={"name": "twitter:title"})
        )
        if meta_title and meta_title.get("content"):
            result["title"] = meta_title["content"].strip()
        if not result["title"]:
            h1 = soup.find("h1")
            if h1 and h1.get_text(strip=True):
                result["title"] = h1.get_text(strip=True)
        if not result["title"]:
            if soup.title and soup.title.string:
                result["title"] = soup.title.string.strip()

        # Location heuristics
        # schema.org via JSON-LD first
        jd = extract_from_json_ld(html)
        if jd.get("location"):
            result["location"] = jd["location"].strip()
        if not result["location"]:
            # itemprop addressLocality
            loc_el = soup.find(attrs={"itemprop": "addressLocality"})
            if loc_el and loc_el.get_text(strip=True):
                result["location"] = loc_el.get_text(strip=True)
        if not result["location"]:
            # Find elements containing the label 'Location'
            label = soup.find(lambda tag: tag.name in ["div","li","p","span","dt","th"] and tag.get_text(strip=True).lower().startswith("location"))
            if label:
                # Try next sibling or nearby text
                sib = label.find_next_sibling(text=True) or label.find_next_sibling()
                txt = ""
                if isinstance(sib, str):
                    txt = sib.strip()
                elif sib:
                    txt = sib.get_text(strip=True)
                result["location"] = txt
        # Keep only city-like first chunk (split by commas)
        if result["location"]:
            result["location"] = result["location"].split(",")[0].strip()
    except Exception:
        pass
    return result

def extract_relevant_text(html: str, max_chars: int = 8000) -> str:
    """Reduce HTML to relevant visible text.
    - Removes script/style/etc.
    - Prefers <main> or containers with job/description hints
    - Collapses whitespace and trims length
    """
    try:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "img", "video", "iframe"]):
            tag.decompose()

        def score(el):
            text = el.get_text(" ", strip=True)
            return len(text)

        candidates = []
        if soup.main:
            candidates.append(soup.main)

        def looks_relevant(el):
            attrs = " ".join([el.get("id", ""), " ".join(el.get("class", []))]).lower()
            return any(k in attrs for k in [
                "job", "posting", "description", "jd", "apply", "vacancy", "position", "role", "opening"
            ])

        for el in soup.find_all(["section", "div", "article"]):
            try:
                if looks_relevant(el):
                    candidates.append(el)
            except Exception:
                continue

        if soup.body:
            candidates.append(soup.body)

        best = max(candidates, key=score) if candidates else soup
        text = best.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
    except Exception:
        return html[:max_chars]

def parse_job(url):
    html = fetch_html(url)
    logger.debug("Fetched HTML content for prompting")

    # Load base prompt template
    with open("prompt.txt", "r", encoding="utf-8") as f:
        base_prompt = f.read()

    # Derive company strictly from URL in code to avoid hallucinations
    derived_company = derive_company_from_url(url)
    logger.info(f"URL-derived company (code): {derived_company}")

    # Prompt 2: HTML-only parsing (using relevant text excerpt)
    relevant_text = extract_relevant_text(html)
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
    raw_html_output = ask_llm(html_prompt)
    html_data = extract_json_object(raw_html_output)
    if not isinstance(html_data, dict):
        logger.info("HTML prompt returned non-JSON/prose. Re-prompting for JSON-only output.")
        skeleton = build_json_skeleton()
        repair_prompt = (
            f"{base_prompt}\n\n"
            "Output exactly one JSON object and nothing else.\n"
            "Use this template and fill in values (keep missing values as empty strings):\n"
            f"{skeleton}\n\n"
            "PAGE CONTENT:\n"
            f"{relevant_text}\n"
        )
        raw_html_output = ask_llm(repair_prompt)
        html_data = extract_json_object(raw_html_output) or {}
    html_data = normalize_job_data(html_data)

    # Merge results: prefer company from URL (derived); others from HTML prompt
    final_data = html_data.copy()
    # Enforce company strictly from URL by code as well
    final_data["company"] = derived_company

    # Fallbacks if HTML model did not comply
    if not final_data.get("title") or not final_data.get("location"):
        heur = extract_title_location_from_html(html)
        if not final_data.get("title") and heur.get("title"):
            final_data["title"] = heur["title"]
        if not final_data.get("location") and heur.get("location"):
            final_data["location"] = heur["location"]

    logger.info(f"Extracted job data: {final_data}")
    return final_data

def search_profiles(job_title, company, location):
    if   "ml" in job_title.lower() or "machine learning" in job_title.lower():
        job_title = '"Machine Learning" OR ML'
    elif "ai" in job_title.lower() or "artificial intelligence" in job_title.lower():
        job_title = '"Artificial Intelligence" OR AI'
    else:
        job_title = f'software OR SWE OR SDE OR "Software Engineer" OR "Software Developer"'

    query_swes = f'site:linkedin.com/in {job_title} "{company}" "{location}" -student -intern'
    logger.info(f"Searching profiles with query: {query_swes}")
    search = GoogleSearch({"q": query_swes, "engine": "google", "api_key": API_KEY})
    results = search.get_dict().get("organic_results", [])
    profiles_swes = [{"title": r["title"],  "queryType": "swe","url": r["link"]} for r in results]

    query_managers = f'site:linkedin.com/in software "{company}" "{location}" lead or manager'
    logger.info(f"Searching profiles with query: {query_managers}")
    search = GoogleSearch({"q": query_managers, "engine": "google", "api_key": API_KEY})
    results = search.get_dict().get("organic_results", [])
    profiles_managers = [{"title": r["title"], "queryType": "manager", "url": r["link"]} for r in results]

    profiles = profiles_swes + profiles_managers
    return profiles

if __name__ == "__main__":
    job_url = "https://sunlife.wd3.myworkdayjobs.com/en-US/Campus/job/Toronto-Ontario/Student--Junior-Software-Engineer--Winter-2026-_JR00114373?utm_source=Simplify&ref=Simplify"
    
    logger.info(f"Starting job parsing: {job_url}")
    job = parse_job(job_url)

    if job:
        profiles = search_profiles(job["title"], job["company"], job["location"])
        logger.info(f"Found {len(profiles)} candidate profiles")
        with open("profiles.json", "w", encoding="utf-8") as f:
            json.dump(profiles, f, ensure_ascii=False, indent=2)
