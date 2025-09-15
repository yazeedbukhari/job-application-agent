import utilities.extraction as extraction
import utilities.llm as llm
import utilities.logging_config as logging_config

logger = logging_config.get_logger(__name__)


def parse_job(url):
    logger.info(f"Fetching HTML from {url}")
    html = extraction.fetch_html(url)
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
