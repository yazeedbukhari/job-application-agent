from flask import Blueprint, request, jsonify
from app.services.job_parser import parse_job
from app.services.profile_search import search_profiles

bp = Blueprint("api", __name__)

@bp.route("/parse-job", methods=["POST"])
def parse_job_endpoint():
    data = request.get_json()
    url = data.get("url")
    if not url:
        return jsonify({"error": "Missing job URL"}), 400
    job = parse_job(url)
    return jsonify(job)

@bp.route("/search-profiles", methods=["POST"])
def search_profiles_endpoint():
    data = request.get_json()
    title = data.get("title", "")
    company = data.get("company", "")
    location = data.get("location", "")
    profiles = search_profiles(title, company, location)
    return jsonify(profiles)