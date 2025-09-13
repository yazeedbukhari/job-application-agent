from bs4 import BeautifulSoup
import json
import re
from urllib.parse import urlparse

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

