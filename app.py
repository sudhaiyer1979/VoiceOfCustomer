#!/usr/bin/env python3
"""Voice of Customer - WS8: Brand Perception Analyzer (Flask wrapper).

Turns the existing WS2-WS7 pipeline into a marketer-facing product: enter a
game name (and optionally a Steam URL), watch live progress on the right,
then open the generated brand perception dashboard.

Run with:
    python app.py

Open:
    http://127.0.0.1:5000

Reuses valid existing data/*.json and output/*.html rather than
regenerating them -- see resolve_game() and the *_valid() helpers below.
"""

import json
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"
SCRIPTS = ROOT / "scripts"

STEAM_SEARCH_URL = "https://store.steampowered.com/api/storesearch/"
STEAM_APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"
USER_AGENT = "VoiceOfCustomer/1.0 (brand perception analyzer; +https://github.com/)"
APP_URL_RE = re.compile(r"/app/(\d+)")

app = Flask(__name__)

JOBS = {}
JOBS_LOCK = threading.Lock()


# --------------------------------------------------------------------------
# Steam resolution
# --------------------------------------------------------------------------

class ResolutionError(Exception):
    pass


def extract_app_id_from_url(url):
    match = APP_URL_RE.search(url)
    if not match:
        raise ResolutionError(
            "That doesn't look like a Steam store URL (expected something like "
            "https://store.steampowered.com/app/12345)."
        )
    return match.group(1)


def steam_search_app_id(game_name):
    params = {"term": game_name, "cc": "us", "l": "english"}
    url = STEAM_SEARCH_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        raise ResolutionError(f"Could not reach Steam to look up '{game_name}'.") from e
    items = payload.get("items") or []
    if not items:
        raise ResolutionError(f"Could not find '{game_name}' on Steam.")
    return str(items[0]["id"])


def verify_steam_app(app_id):
    params = {"appids": app_id, "l": "english"}
    url = STEAM_APPDETAILS_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        raise ResolutionError(f"Could not verify Steam App ID {app_id}.") from e
    entry = payload.get(app_id)
    if not entry or not entry.get("success"):
        raise ResolutionError(f"Steam App ID {app_id} could not be verified.")
    return entry["data"].get("name") or "Unknown Game"


def load_json_safe(path):
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def cached_identity():
    data = load_json_safe(DATA / "reviews.json")
    if not data:
        return None
    app_id = data.get("app_id")
    game_name = data.get("game_name")
    source_url = data.get("source_url")
    if not app_id or not game_name:
        return None
    return {"app_id": str(app_id), "game_name": game_name, "source_url": source_url}


def resolve_game(game_name, source_url, emit_active, emit_done):
    game_name = (game_name or "").strip()
    source_url = (source_url or "").strip()

    cached = cached_identity()
    if cached and cached["game_name"].strip().lower() == game_name.lower():
        if source_url:
            try:
                given_app_id = extract_app_id_from_url(source_url)
            except ResolutionError:
                given_app_id = None
            if given_app_id and given_app_id != cached["app_id"]:
                cached = None
    else:
        cached = None

    if cached:
        resolved = cached
    else:
        emit_active("Connecting to source")
        if source_url:
            app_id = extract_app_id_from_url(source_url)
        else:
            app_id = steam_search_app_id(game_name)
        canonical_name = verify_steam_app(app_id)
        resolved = {
            "app_id": app_id,
            "game_name": canonical_name,
            "source_url": f"https://store.steampowered.com/app/{app_id}",
        }

    emit_done(f"Product identified: {resolved['game_name']}")
    emit_done(f"Source confirmed\n  {resolved['source_url']}")
    return resolved


# --------------------------------------------------------------------------
# Pipeline stage validity checks
# --------------------------------------------------------------------------

def reviews_valid(app_id):
    data = load_json_safe(DATA / "reviews.json")
    return bool(data and str(data.get("app_id")) == app_id and data.get("reviews"))


def marketing_valid(app_id):
    data = load_json_safe(DATA / "marketing.json")
    if not data or not data.get("claims"):
        return False
    match = APP_URL_RE.search(data.get("source_url") or "")
    return bool(match and match.group(1) == app_id)


def file_exists(name):
    return (DATA / name).is_file()


def run_script(script_name, *args):
    cmd = [sys.executable, str(SCRIPTS / script_name), *args]
    result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        tail = (result.stderr.strip() or result.stdout.strip())[-800:]
        raise RuntimeError(tail or f"{script_name} failed with no output")
    return result.stdout


# --------------------------------------------------------------------------
# Job state
# --------------------------------------------------------------------------

def new_job():
    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {
            "lines": [],
            "current": None,
            "done": False,
            "error": None,
        }
    return job_id


def emit_active(job_id, text):
    with JOBS_LOCK:
        JOBS[job_id]["current"] = f"→ {text}"


def emit_done(job_id, text):
    with JOBS_LOCK:
        job = JOBS[job_id]
        job["current"] = None
        job["lines"].append(f"✓ {text}")


def finish_job(job_id, error=None):
    with JOBS_LOCK:
        job = JOBS[job_id]
        job["current"] = None
        job["done"] = True
        job["error"] = error


def run_pipeline(job_id, game_name, source_url):
    def active(text):
        emit_active(job_id, text)

    def done(text):
        emit_done(job_id, text)

    try:
        resolved = resolve_game(game_name, source_url, active, done)
        app_id = resolved["app_id"]
        resolved_name = resolved["game_name"]
        resolved_url = resolved["source_url"]

        # --- reviews ---
        reviews_ok = reviews_valid(app_id)
        if reviews_ok:
            done("Customer review data found — reusing existing data")
            reviews_fresh = False
        else:
            active("Collecting customer reviews")
            run_script("collect_reviews.py", resolved_url, resolved_name)
            done("Customer review data collected")
            reviews_fresh = True

        # --- marketing ---
        marketing_ok = (not reviews_fresh) and marketing_valid(app_id)
        if marketing_ok:
            done("Brand messaging found — reusing existing data")
            marketing_fresh = False
        else:
            active("Collecting brand messaging")
            run_script("collect_marketing.py", resolved_url, resolved_name)
            done("Brand messaging collected")
            marketing_fresh = True

        # --- themes / gaps / vocab ("customer analysis") ---
        themes_ok = (not reviews_fresh) and file_exists("review_themes.json")
        themes_fresh = reviews_fresh or not themes_ok

        gaps_ok = (not themes_fresh) and (not marketing_fresh) and file_exists("gaps.json")
        gaps_fresh = themes_fresh or marketing_fresh or not gaps_ok

        vocab_ok = (not reviews_fresh) and (not marketing_fresh) and file_exists("vocabulary.json")
        vocab_fresh = reviews_fresh or marketing_fresh or not vocab_ok

        analysis_fresh = themes_fresh or gaps_fresh or vocab_fresh

        if not analysis_fresh:
            done("Customer analysis already available — reusing results")
        else:
            if themes_fresh:
                active("Identifying customer themes")
                run_script("find_themes.py")
                done("Customer themes identified")
            else:
                done("Customer themes found — reusing existing data")

            if gaps_fresh or vocab_fresh:
                active("Comparing customer perception with brand positioning")
                if gaps_fresh:
                    run_script("find_gaps.py")
                if vocab_fresh:
                    run_script("vocab_gap.py")
                done("Customer perception compared with brand positioning")
            else:
                done("Customer perception comparison found — reusing existing data")

        # --- marketing insights ---
        insights_ok = (not analysis_fresh) and file_exists("marketing_insights.json")
        if insights_ok:
            done("Marketing recommendations already available — reusing insights")
            insights_fresh = False
        else:
            active("Using Claude to create marketing insights")
            run_script("prepare_marketing_insights.py")
            done("Marketing recommendations created")
            insights_fresh = True

        # --- marketing dashboard ---
        dashboard_ok = (not insights_fresh) and (OUTPUT / "marketing_dashboard.html").is_file()
        if dashboard_ok:
            done("Brand perception dashboard already available — reusing dashboard")
        else:
            active("Creating brand perception dashboard")
            run_script("build_marketing_dashboard.py")
            done("Brand perception dashboard created")

        finish_job(job_id)
    except (ResolutionError, RuntimeError) as e:
        finish_job(job_id, error=str(e))
    except Exception as e:  # noqa: BLE001 - surface unexpected errors to the UI
        finish_job(job_id, error=f"Unexpected error: {e}")


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    payload = request.get_json(silent=True) or {}
    game_name = (payload.get("game_name") or "").strip()
    source_url = (payload.get("source_url") or "").strip()

    if not game_name:
        return jsonify({"error": "Game Name is required."}), 400

    job_id = new_job()
    thread = threading.Thread(
        target=run_pipeline, args=(job_id, game_name, source_url), daemon=True
    )
    thread.start()
    return jsonify({"job_id": job_id})


@app.route("/api/status/<job_id>")
def api_status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            abort(404)
        return jsonify(dict(job))


@app.route("/dashboard")
def dashboard():
    path = OUTPUT / "marketing_dashboard.html"
    if not path.is_file():
        abort(404)
    return send_file(path)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
