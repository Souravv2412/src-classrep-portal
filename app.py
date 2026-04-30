from collections import Counter, defaultdict
from datetime import datetime
from functools import lru_cache
import io
import json
import os
import shutil
import sys
import threading
import traceback

import pandas as pd
from flask import Flask, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.exceptions import HTTPException

BASE_DIR = os.path.dirname(__file__)


def load_local_env():
    env_path = os.path.join(BASE_DIR, ".env.local")
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        pass


load_local_env()


def resolve_persistent_root():
    def can_write(directory):
        test_file = os.path.join(directory, ".write_test")
        try:
            with open(test_file, "w", encoding="utf-8") as handle:
                handle.write("ok")
            os.remove(test_file)
            return True
        except Exception:
            return False

    explicit_root = os.environ.get("SRC_PORTAL_DATA_ROOT")
    candidates = []
    if explicit_root:
        candidates.append(explicit_root)
    appdata = os.environ.get("APPDATA")
    localappdata = os.environ.get("LOCALAPPDATA")
    if appdata:
        candidates.append(os.path.join(appdata, "SRCClassRepPortal"))
    if localappdata:
        candidates.append(os.path.join(localappdata, "SRCClassRepPortal"))
    candidates.append(os.path.join(BASE_DIR, "persistent_data"))

    for candidate in candidates:
        try:
            os.makedirs(candidate, exist_ok=True)
            if can_write(candidate):
                return candidate
        except Exception:
            continue
    fallback = os.path.join(BASE_DIR, "persistent_data")
    os.makedirs(fallback, exist_ok=True)
    return fallback


PERSISTENT_ROOT = resolve_persistent_root()
DATA_DIR = os.path.join(PERSISTENT_ROOT, "data")
UPLOAD_FOLDER = os.path.join(PERSISTENT_ROOT, "uploads")
BACKUP_DIR = os.path.join(PERSISTENT_ROOT, "backups")
LOG_DIR = os.path.join(PERSISTENT_ROOT, "logs")
LOG_FILE = os.path.join(LOG_DIR, "portal.log")
DATA_FILE = os.path.join(DATA_DIR, "classreps.json")
TRACKING_FILE = os.path.join(DATA_DIR, "tracking.json")
MEETINGS_FILE = os.path.join(DATA_DIR, "meetings.json")
AWARDS_FILE = os.path.join(DATA_DIR, "awards.json")
EMAILS_FILE = os.path.join(DATA_DIR, "emails.json")

JSON_CACHE = {}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

LEGACY_DATA_DIR = os.path.join(BASE_DIR, "data")
LEGACY_UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")


def migrate_legacy_storage():
    try:
        if os.path.isdir(LEGACY_DATA_DIR) and not os.listdir(DATA_DIR):
            for name in os.listdir(LEGACY_DATA_DIR):
                src = os.path.join(LEGACY_DATA_DIR, name)
                dst = os.path.join(DATA_DIR, name)
                if os.path.isfile(src) and not os.path.exists(dst):
                    shutil.copy2(src, dst)
        if os.path.isdir(LEGACY_UPLOAD_DIR) and not os.listdir(UPLOAD_FOLDER):
            for name in os.listdir(LEGACY_UPLOAD_DIR):
                src = os.path.join(LEGACY_UPLOAD_DIR, name)
                dst = os.path.join(UPLOAD_FOLDER, name)
                if os.path.isfile(src) and not os.path.exists(dst):
                    shutil.copy2(src, dst)
    except Exception:
        pass


migrate_legacy_storage()

INTAKE_MONTHS = {
    "Winter": [1, 2, 3, 4],
    "Spring/Summer": [5, 6, 7, 8],
    "Fall": [9, 10, 11, 12],
}
MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
TRACKING_TEMPLATE = {
    "meetings": [],
    "relay_count": 0,
    "relay_history": [],
    "notes": "",
    "awards": [],
    "volunteer_points": 0,
    "contributions": [],
}

COLUMN_MAP = {
    "Reference #": "ref",
    "Status": "status",
    "Campus:": "campus",
    "Student Name:": "name",
    "Student Number:": "student_number",
    "Program:": "program",
    "Course Code": "course_code",
    "Class Section": "class_section",
    "Current Year:": "current_year",
    "Current Semester of Study": "semester_of_study",
    "Professor:": "professor",
    "St. Clair Email:": "email",
    "Phone Number:": "phone",
    "Mailing Address:": "address",
    "City:": "city",
    "Province:": "province",
    "Postal Code:": "postal_code",
    "How did you hear about this opportunity?": "hear_about",
    "Date": "date",
    "Start Time": "start_time",
    "Finish Time": "finish_time",
    "Duration (s)": "duration",
    "User": "user_ip",
    "Browser": "browser",
    "Device": "device",
    "Referrer": "referrer",
}

def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and PyInstaller."""
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)

app = Flask(__name__, 
            template_folder=get_resource_path('templates'),
            static_folder=get_resource_path('static'))
app.secret_key = "src-classrep-2025-secret"
AUTH_USERNAME = os.environ.get("SRC_PORTAL_ADMIN_USERNAME", "").strip()
AUTH_PASSWORD = os.environ.get("SRC_PORTAL_ADMIN_PASSWORD", "").strip()

def now_local():
    return datetime.now()


def auth_enabled():
    return bool(AUTH_USERNAME and AUTH_PASSWORD)


@app.before_request
def require_login():
    if not auth_enabled():
        return None
    if request.path.startswith("/static/"):
        return None
    if request.path in {"/login", "/health"}:
        return None
    if session.get("is_authenticated") is True:
        return None
    return redirect(url_for("login", next=request.path))


def log_error(message):
    try:
        timestamp = now_local().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as log_file:
            log_file.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass


@lru_cache(maxsize=8192)
def parse_dt(value):
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return pd.to_datetime(text).to_pydatetime()
    except Exception:
        return None


def month_name_to_number(month_name):
    try:
        return MONTH_NAMES.index(str(month_name).strip()) + 1
    except ValueError:
        return None


@lru_cache(maxsize=256)
def normalize_campus(campus_str):
    s = str(campus_str or "").strip().lower()
    if "south" in s:
        return "South Windsor Campus"
    if "downtown" in s or "td student" in s or "down" in s:
        return "Downtown Windsor Campus"
    if not s or s == "all":
        return "All"
    return str(campus_str).strip()


def detect_intake(date_str, semester_str=""):
    semester_str = str(semester_str or "").strip().lower()
    if "fall" in semester_str or "sep" in semester_str or semester_str == "f":
        return "Fall"
    if "winter" in semester_str or "jan" in semester_str or semester_str == "w":
        return "Winter"
    if "spring" in semester_str or "summer" in semester_str or semester_str == "s":
        return "Spring/Summer"
    dt = parse_dt(date_str)
    if not dt:
        return "Unknown"
    for intake, months in INTAKE_MONTHS.items():
        if dt.month in months:
            return intake
    return "Unknown"


@lru_cache(maxsize=8192)
def get_term_for_date(value):
    dt = parse_dt(value)
    if not dt:
        return None
    if dt.month in INTAKE_MONTHS["Winter"]:
        start = datetime(dt.year, 1, 1)
        end = datetime(dt.year, 4, 30, 23, 59, 59)
        intake = "Winter"
    elif dt.month in INTAKE_MONTHS["Spring/Summer"]:
        start = datetime(dt.year, 5, 1)
        end = datetime(dt.year, 8, 31, 23, 59, 59)
        intake = "Spring/Summer"
    else:
        start = datetime(dt.year, 9, 1)
        end = datetime(dt.year, 12, 31, 23, 59, 59)
        intake = "Fall"
    return {
        "start": start,
        "end": end,
        "intake": intake,
        "year": start.year,
        "code": f"{intake}-{start.year}",
        "label": f"{intake} {start.year}",
    }


def get_current_term():
    return get_term_for_date(now_local())


def get_application_year(rep):
    if rep.get("_application_year"):
        return rep.get("_application_year")
    dt = parse_dt(rep.get("date"))
    return dt.year if dt else None


def get_rep_term(rep):
    return get_term_for_date(rep.get("_parsed_date") or rep.get("date"))


def get_dynamic_years(reps):
    years = sorted({get_application_year(rep) for rep in reps if get_application_year(rep)})
    current_year = now_local().year
    valid_years = []
    for year in years:
        try:
            parsed_year = int(year)
        except (TypeError, ValueError):
            continue
        if parsed_year <= current_year:
            valid_years.append(parsed_year)
    start_year = min(valid_years) if valid_years else current_year
    return [str(year) for year in range(start_year, current_year + 1)]


def load_json(path, default_value):
    if os.path.exists(path):
        try:
            stat = os.stat(path)
            cache_key = (path, stat.st_mtime_ns, stat.st_size)
            if cache_key in JSON_CACHE:
                return json.loads(json.dumps(JSON_CACHE[cache_key]))
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)
            JSON_CACHE.clear()
            JSON_CACHE[cache_key] = data
            return json.loads(json.dumps(data))
        except json.JSONDecodeError as exc:
            log_error(f"Corrupted JSON in {path}: {exc}")
            try:
                corrupted_copy = f"{path}.corrupt-{now_local().strftime('%Y%m%d%H%M%S')}"
                shutil.copy2(path, corrupted_copy)
            except Exception:
                pass
            return json.loads(json.dumps(default_value))
        except Exception as exc:
            log_error(f"Failed to read JSON {path}: {exc}")
            return json.loads(json.dumps(default_value))
    return json.loads(json.dumps(default_value))


def save_json(path, data):
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    temp_path = f"{path}.tmp"
    try:
        with open(temp_path, "w", encoding="utf-8") as file:
            json.dump(data, file, default=str, indent=2)
        os.replace(temp_path, path)
        JSON_CACHE.clear()
    except PermissionError as exc:
        log_error(f"Permission error saving JSON {path}: {exc}")
        try:
            with open(path, "w", encoding="utf-8") as file:
                json.dump(data, file, default=str, indent=2)
            JSON_CACHE.clear()
        except Exception as inner_exc:
            log_error(f"Fallback write failed for {path}: {inner_exc}")
            recovery_path = f"{path}.pending-{now_local().strftime('%Y%m%d%H%M%S')}"
            with open(recovery_path, "w", encoding="utf-8") as file:
                json.dump(data, file, default=str, indent=2)
            log_error(f"Saved pending data to {recovery_path}")
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def load_data():
    reps = load_json(DATA_FILE, [])
    for rep in reps:
        parsed = parse_dt(rep.get("date"))
        term = get_term_for_date(rep.get("date"))
        rep["_parsed_date"] = parsed.isoformat() if parsed else ""
        rep["_application_year"] = parsed.year if parsed else ""
        rep["_term_code"] = term["code"] if term else ""
        rep["_term_label"] = term["label"] if term else ""
    return reps


def save_data(data):
    save_json(DATA_FILE, data)


def ensure_tracking_entry(entry=None):
    merged = dict(TRACKING_TEMPLATE)
    merged.update(entry or {})
    merged["meetings"] = list(merged.get("meetings", []))
    merged["relay_history"] = list(merged.get("relay_history", []))
    merged["awards"] = list(merged.get("awards", []))
    merged["contributions"] = list(merged.get("contributions", []))
    merged["relay_count"] = len(merged["relay_history"]) if merged["relay_history"] else int(merged.get("relay_count", 0) or 0)
    merged["volunteer_points"] = sum(int(item.get("points", 0) or 0) for item in merged["contributions"])
    return merged


def load_tracking():
    tracking = load_json(TRACKING_FILE, {})
    changed = False
    for ref, entry in tracking.items():
        normalized = ensure_tracking_entry(entry)
        if normalized != entry:
            tracking[ref] = normalized
            changed = True
    if changed:
        save_tracking(tracking)
    return tracking


def save_tracking(data):
    save_json(TRACKING_FILE, data)


def get_tracking_entry(tracking, ref):
    ref = str(ref)
    if ref not in tracking:
        tracking[ref] = ensure_tracking_entry()
    else:
        tracking[ref] = ensure_tracking_entry(tracking[ref])
    return tracking[ref]


def hydrate_meeting(meeting):
    changed = False
    meeting_term = get_term_for_date(meeting.get("date")) or get_current_term()
    if not meeting.get("intake"):
        meeting["intake"] = meeting_term["intake"]
        changed = True
    if not meeting.get("year"):
        meeting["year"] = str(meeting_term["year"])
        changed = True
    if not meeting.get("status"):
        meeting["status"] = "completed" if meeting_term["end"] < now_local() else "scheduled"
        changed = True
    meeting["campus"] = normalize_campus(meeting.get("campus"))
    return changed

def load_meetings():
    meetings = load_json(MEETINGS_FILE, [])
    changed = False
    for meeting in meetings:
        if hydrate_meeting(meeting):
            changed = True
    if changed:
        save_meetings(meetings)
    return meetings


def save_meetings(data):
    save_json(MEETINGS_FILE, data)


def load_awards():
    awards = load_json(AWARDS_FILE, [])
    changed = False
    for award in awards:
        if not award.get("type"):
            award["type"] = "monthly"
            changed = True
        if not award.get("award_date"):
            month_number = month_name_to_number(award.get("month")) or 1
            year = int(award.get("year") or now_local().year)
            award["award_date"] = datetime(year, month_number, 1).date().isoformat()
            changed = True
    if changed:
        save_awards(awards)
    return awards


def save_awards(data):
    save_json(AWARDS_FILE, data)


def load_emails():
    return load_json(EMAILS_FILE, [])


def save_emails(data):
    save_json(EMAILS_FILE, data)


def match_campus(value, campus_filter):
    if not campus_filter:
        return True
    value = str(value or "").lower()
    campus_filter = campus_filter.lower()
    if campus_filter == "all":
        return True
    return campus_filter in value


def filter_reps(reps, campus_filter="", intake_filter="", year_filter="", search="", only_active=False):
    current_term = get_current_term()
    filtered = []
    for rep in reps:
        rep_term = get_rep_term(rep)
        app_year = get_application_year(rep)
        if campus_filter and not match_campus(rep.get("campus"), campus_filter):
            continue
        if intake_filter and rep.get("intake") != intake_filter:
            continue
        if year_filter and str(app_year or "") != str(year_filter):
            continue
        if search:
            haystack = " ".join([
                str(rep.get("name", "")),
                str(rep.get("program", "")),
                str(rep.get("course_code", "")),
                str(rep.get("email", "")),
                str(rep.get("student_number", "")),
            ]).lower()
            if search.lower() not in haystack:
                continue
        if only_active and (not rep_term or rep_term["code"] != current_term["code"]):
            continue
        filtered.append(rep)
    filtered.sort(key=lambda rep: rep.get("_parsed_date", ""), reverse=True)
    return filtered


def filter_meetings_for_rep(rep, meetings):
    rep_term = get_rep_term(rep)
    rep_campus = normalize_campus(rep.get("campus"))
    filtered = []
    for meeting in meetings:
        hydrate_meeting(meeting)
        if rep_term and meeting.get("intake") != rep_term["intake"]:
            continue
        if rep_term and str(meeting.get("year")) != str(rep_term["year"]):
            continue
        meeting_campus = normalize_campus(meeting.get("campus"))
        if meeting_campus != "All" and meeting_campus != rep_campus:
            continue
        filtered.append(meeting)
    filtered.sort(key=lambda item: (item.get("date", ""), item.get("time", "")))
    return filtered


def get_award_term(award):
    if award.get("award_date"):
        return get_term_for_date(award.get("award_date"))
    month_number = month_name_to_number(award.get("month"))
    if month_number and award.get("year"):
        return get_term_for_date(f"{award['year']}-{month_number:02d}-01")
    return None


def get_rep_score(rep, tracking_entry, awards, term_code=None):
    score = 0
    meeting_counts = {"attended": 0, "notified": 0, "absent": 0, "pending": 0}

    for item in tracking_entry.get("meetings", []):
        item_term = get_term_for_date(item.get("updated"))
        if term_code and (not item_term or item_term["code"] != term_code):
            continue
        status = item.get("status", "pending")
        if status == "attended":
            score += 10
        elif status == "notified":
            score += 4
        elif status == "absent":
            score -= 2
        meeting_counts[status] = meeting_counts.get(status, 0) + 1

    for relay in tracking_entry.get("relay_history", []):
        relay_term = get_term_for_date(relay.get("date"))
        if term_code and (not relay_term or relay_term["code"] != term_code):
            continue
        score += 3

    for contribution in tracking_entry.get("contributions", []):
        contribution_term = get_term_for_date(contribution.get("date"))
        if term_code and (not contribution_term or contribution_term["code"] != term_code):
            continue
        score += int(contribution.get("points", 0) or 0)

    for award in awards:
        award_term = get_award_term(award)
        if term_code and (not award_term or award_term["code"] != term_code):
            continue
        score += 35 if award.get("type") == "yearly" else 15

    return score, meeting_counts


def build_points_history(rep, tracking_entry, awards, meetings, term_code=None):
    meeting_map = {str(meeting.get("id")): meeting for meeting in meetings}
    history = []

    for item in tracking_entry.get("meetings", []):
        status = item.get("status", "pending")
        points = 0
        if status == "attended":
            points = 10
        elif status == "notified":
            points = 4
        elif status == "absent":
            points = -2
        if points == 0:
            continue
        event_term = get_term_for_date(item.get("updated"))
        if term_code and (not event_term or event_term.get("code") != term_code):
            continue
        meeting = meeting_map.get(str(item.get("meeting_id")), {})
        history.append(
            {
                "date": item.get("updated", ""),
                "category": "Meeting",
                "points": points,
                "title": meeting.get("title", "Class Rep Meeting"),
                "reason": f"Attendance status: {status.title()}",
            }
        )

    for relay in tracking_entry.get("relay_history", []):
        event_term = get_term_for_date(relay.get("date"))
        if term_code and (not event_term or event_term.get("code") != term_code):
            continue
        history.append(
            {
                "date": relay.get("date", ""),
                "category": "Information Relay",
                "points": 3,
                "title": "Information relayed to class",
                "reason": relay.get("proof", "") or "Relay confirmed by VP",
            }
        )

    for contribution in tracking_entry.get("contributions", []):
        points = int(contribution.get("points", 0) or 0)
        event_term = get_term_for_date(contribution.get("date"))
        if term_code and (not event_term or event_term.get("code") != term_code):
            continue
        history.append(
            {
                "date": contribution.get("date", ""),
                "category": "Engagement / Volunteer",
                "points": points,
                "title": "Extra contribution",
                "reason": contribution.get("description", "") or "Volunteer contribution",
            }
        )

    for award in awards:
        points = 35 if award.get("type") == "yearly" else 15
        event_term = get_award_term(award)
        if term_code and (not event_term or event_term.get("code") != term_code):
            continue
        history.append(
            {
                "date": award.get("award_date", ""),
                "category": "Award",
                "points": points,
                "title": f"{award.get('type', 'monthly').title()} award",
                "reason": award.get("reason", "") or f"{award.get('month', '')} {award.get('year', '')}".strip(),
            }
        )

    history.sort(key=lambda item: item.get("date", ""), reverse=True)
    return history


def build_rep_summary(rep, tracking, awards, meetings):
    ref = str(rep.get("ref"))
    tracking_entry = get_tracking_entry(tracking, ref)
    rep_awards = [award for award in awards if str(award.get("ref")) == ref]
    rep_meetings = filter_meetings_for_rep(rep, meetings)
    term = get_rep_term(rep)
    score, meeting_counts = get_rep_score(rep, tracking_entry, rep_awards, term["code"] if term else None)
    application_dt = parse_dt(rep.get("date"))

    summary = dict(rep)
    summary["_term"] = term
    summary["_application_year"] = application_dt.year if application_dt else ""
    summary["_application_date"] = application_dt.date().isoformat() if application_dt else ""
    summary["_current_score"] = score
    summary["_meetings_attended"] = meeting_counts.get("attended", 0)
    summary["_meetings_notified"] = meeting_counts.get("notified", 0)
    summary["_meetings_absent"] = meeting_counts.get("absent", 0)
    summary["_relayed"] = len(tracking_entry.get("relay_history", []))
    summary["_awards"] = rep_awards
    summary["_volunteer_points"] = sum(int(item.get("points", 0) or 0) for item in tracking_entry.get("contributions", []))
    summary["_active"] = bool(term and term["code"] == get_current_term()["code"])
    summary["_status_label"] = "Active term" if summary["_active"] else "Completed term"
    summary["_meetings"] = rep_meetings
    summary["_points_history"] = build_points_history(rep, tracking_entry, rep_awards, meetings, term["code"] if term else None)
    return summary


def build_rankings(reps, tracking, awards, meetings):
    current_term = get_current_term()
    active_reps = []
    archive = defaultdict(list)
    for rep in reps:
        ref = str(rep.get("ref"))
        rep_term = get_rep_term(rep)
        if not rep_term:
            continue
        rep_awards = [award for award in awards if str(award.get("ref")) == ref]
        tracking_entry = get_tracking_entry(tracking, ref)
        score, meeting_counts = get_rep_score(rep, tracking_entry, rep_awards, rep_term["code"])
        entry = {
            "ref": ref,
            "name": rep.get("name", "Unknown"),
            "program": rep.get("program", ""),
            "campus": rep.get("campus", ""),
            "intake": rep_term["intake"],
            "year": rep_term["year"],
            "label": rep_term["label"],
            "score": score,
            "meetings_attended": meeting_counts.get("attended", 0),
            "relays": len([item for item in tracking_entry.get("relay_history", []) if get_term_for_date(item.get("date")) and get_term_for_date(item.get("date"))["code"] == rep_term["code"]]),
            "volunteer_points": sum(int(item.get("points", 0) or 0) for item in tracking_entry.get("contributions", []) if get_term_for_date(item.get("date")) and get_term_for_date(item.get("date"))["code"] == rep_term["code"]),
            "award_count": len([award for award in rep_awards if get_award_term(award) and get_award_term(award)["code"] == rep_term["code"]]),
        }
        if rep_term["code"] == current_term["code"]:
            active_reps.append(entry)
        else:
            archive[rep_term["code"]].append(entry)

    active_reps.sort(key=lambda item: (-item["score"], item["name"]))
    archived_terms = []
    for term_code, term_entries in archive.items():
        term_entries.sort(key=lambda item: (-item["score"], item["name"]))
        archived_terms.append({"term_code": term_code, "label": term_entries[0]["label"], "leaders": term_entries[:5]})
    archived_terms.sort(key=lambda item: item["term_code"], reverse=True)
    return active_reps[:10], archived_terms


def build_meeting_progress(meeting, reps, tracking):
    hydrate_meeting(meeting)
    eligible_reps = []
    counts = Counter()
    for rep in reps:
        rep_term = get_rep_term(rep)
        if not rep_term:
            continue
        if rep_term["intake"] != meeting.get("intake") or str(rep_term["year"]) != str(meeting.get("year")):
            continue
        meeting_campus = normalize_campus(meeting.get("campus"))
        rep_campus = normalize_campus(rep.get("campus"))
        if meeting_campus != "All" and rep_campus != meeting_campus:
            continue

        entry = get_tracking_entry(tracking, rep.get("ref"))
        attendance = next((item for item in entry.get("meetings", []) if str(item.get("meeting_id")) == str(meeting.get("id"))), None)
        status = attendance.get("status") if attendance else "pending"
        counts[status] += 1
        eligible_reps.append({
            "ref": rep.get("ref"),
            "name": rep.get("name"),
            "program": rep.get("program"),
            "campus": rep.get("campus"),
            "email": rep.get("email"),
            "status": status,
            "note": attendance.get("note", "") if attendance else "",
        })

    eligible_reps.sort(key=lambda item: (item["status"] != "attended", item["name"] or ""))
    total = len(eligible_reps)
    summary = {
        "total": total,
        "attended": counts.get("attended", 0),
        "notified": counts.get("notified", 0),
        "absent": counts.get("absent", 0),
        "pending": counts.get("pending", 0),
        "attendance_rate": round((counts.get("attended", 0) / total) * 100, 1) if total else 0,
    }
    return eligible_reps, summary


def get_logo_asset():
    candidates = ["src-logo.png", "src-logo.svg", "src-logo.jpg", "src-logo.jpeg", "logo.png", "logo.svg"]
    for filename in candidates:
        path = os.path.join(BASE_DIR, "static", "img", filename)
        if os.path.exists(path):
            return url_for("static", filename=f"img/{filename}")
    return url_for("static", filename="img/src-logo-placeholder.svg")

@app.route("/")
def index():
    return render_template("splash.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if not auth_enabled():
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        next_url = request.form.get("next") or url_for("dashboard")
        if username == AUTH_USERNAME and password == AUTH_PASSWORD:
            session["is_authenticated"] = True
            flash("Signed in successfully.", "success")
            return redirect(next_url)
        flash("Invalid username or password.", "error")
    return render_template("login.html", next=request.args.get("next", url_for("dashboard")))


@app.route("/logout")
def logout():
    session.pop("is_authenticated", None)
    flash("Signed out.", "success")
    return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    reps = load_data()
    tracking = load_tracking()
    awards = load_awards()
    meetings = load_meetings()
    current_ranking, archived_rankings = build_rankings(reps, tracking, awards, meetings)
    return render_template(
        "dashboard.html",
        years=get_dynamic_years(reps),
        current_ranking=current_ranking[:5],
        archived_rankings=archived_rankings[:3],
        current_term=get_current_term(),
    )


@app.route("/class-reps")
def class_reps():
    if session.get("just_uploaded"):
        session.pop("just_uploaded")

    reps = load_data()
    tracking = load_tracking()
    awards = load_awards()
    meetings = load_meetings()

    campus_filter = request.args.get("campus", "")
    intake_filter = request.args.get("intake", "")
    year_filter = request.args.get("year", "")
    search = request.args.get("search", "").strip()

    filtered = filter_reps(reps, campus_filter, intake_filter, year_filter, search)
    summaries = [build_rep_summary(rep, tracking, awards, meetings) for rep in filtered]

    return render_template(
        "class_reps.html",
        reps=summaries,
        total=len(summaries),
        all_years=get_dynamic_years(reps),
        filters={"campus": campus_filter, "intake": intake_filter, "year": year_filter, "search": search},
        current_term=get_current_term(),
    )


@app.route("/class-rep/<ref>")
def class_rep_detail(ref):
    reps = load_data()
    rep = next((item for item in reps if str(item.get("ref")) == str(ref)), None)
    if not rep:
        flash("Class representative not found.", "error")
        return redirect(url_for("class_reps"))

    tracking = load_tracking()
    awards = load_awards()
    meetings = load_meetings()

    summary = build_rep_summary(rep, tracking, awards, meetings)
    tracking_entry = get_tracking_entry(tracking, ref)
    rep_awards = [award for award in awards if str(award.get("ref")) == str(ref)]
    current_ranking, archived_rankings = build_rankings(reps, tracking, awards, meetings)
    rank_position = next((index + 1 for index, item in enumerate(current_ranking) if str(item.get("ref")) == str(ref)), None)

    return render_template(
        "rep_detail.html",
        rep=summary,
        tracking=tracking_entry,
        awards=sorted(rep_awards, key=lambda award: award.get("award_date", ""), reverse=True),
        meetings=summary["_meetings"],
        rank_position=rank_position,
        current_term=get_current_term(),
        archived_rankings=archived_rankings[:3],
    )


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        if "file" not in request.files:
            flash("No file selected.", "error")
            return redirect(request.url)
        file = request.files["file"]
        if file.filename == "":
            flash("No file selected.", "error")
            return redirect(request.url)
        if not file.filename.endswith((".xlsx", ".xls", ".csv")):
            flash("Please upload an Excel (.xlsx/.xls) or CSV file.", "error")
            return redirect(request.url)

        try:
            dataframe = pd.read_csv(file) if file.filename.endswith(".csv") else pd.read_excel(file)
            dataframe.rename(columns=COLUMN_MAP, inplace=True)

            records = []
            for _, row in dataframe.iterrows():
                record = {}
                for column in COLUMN_MAP.values():
                    value = row.get(column, "")
                    if pd.isna(value) if not isinstance(value, str) else False:
                        value = ""
                    record[column] = str(value) if value != "" else ""
                record["campus"] = normalize_campus(record.get("campus"))
                record["intake"] = detect_intake(record.get("date"), record.get("semester_of_study"))
                records.append(record)

            existing = load_data()
            existing_by_ref = {str(item.get("ref")): item for item in existing}
            new_count = 0
            for record in records:
                ref = str(record.get("ref"))
                if ref not in existing_by_ref:
                    new_count += 1
                existing_by_ref[ref] = record

            merged = list(existing_by_ref.values())
            merged.sort(key=lambda rep: parse_dt(rep.get("date")) or datetime.min, reverse=True)
            save_data(merged)

            flash(f"Successfully imported {len(records)} records ({new_count} new).", "success")
            session["just_uploaded"] = True
            return redirect(url_for("class_reps"))
        except Exception as exc:
            flash(f"Error processing file: {exc}", "error")
            return redirect(request.url)

    return render_template("upload.html")


@app.route("/meetings", methods=["GET", "POST"])
def meetings():
    meetings_data = load_meetings()
    reps = load_data()
    tracking = load_tracking()

    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            meeting = {
                "id": str(int(now_local().timestamp())),
                "title": request.form.get("title", "").strip(),
                "date": request.form.get("date", ""),
                "time": request.form.get("time", ""),
                "location": request.form.get("location", "").strip(),
                "campus": normalize_campus(request.form.get("campus", "All")),
                "intake": request.form.get("intake", ""),
                "year": request.form.get("year", ""),
                "notes": request.form.get("notes", "").strip(),
                "created": now_local().isoformat(),
            }
            hydrate_meeting(meeting)
            meetings_data.append(meeting)
            save_meetings(meetings_data)
            flash("Meeting added successfully.", "success")
        elif action == "delete":
            meeting_id = request.form.get("meeting_id")
            meetings_data = [meeting for meeting in meetings_data if str(meeting.get("id")) != str(meeting_id)]
            save_meetings(meetings_data)
            flash("Meeting deleted.", "success")
        return redirect(url_for("meetings"))

    decorated = []
    for meeting in meetings_data:
        attendees, summary = build_meeting_progress(meeting, reps, tracking)
        decorated.append({**meeting, "summary": summary, "attendees_preview": attendees[:5]})
    decorated.sort(key=lambda item: (item.get("date", ""), item.get("time", "")), reverse=True)

    return render_template("meetings.html", meetings=decorated, current_term=get_current_term(), all_years=get_dynamic_years(reps))


@app.route("/meetings/<meeting_id>/progress")
def meeting_progress(meeting_id):
    meetings_data = load_meetings()
    meeting = next((item for item in meetings_data if str(item.get("id")) == str(meeting_id)), None)
    if not meeting:
        flash("Meeting not found.", "error")
        return redirect(url_for("meetings"))

    reps = load_data()
    tracking = load_tracking()
    attendees, summary = build_meeting_progress(meeting, reps, tracking)
    return render_template("meeting_progress.html", meeting=meeting, attendees=attendees, summary=summary)


@app.route("/update-attendance", methods=["POST"])
def update_attendance():
    data = request.json or {}
    ref = str(data.get("ref", ""))
    meeting_id = str(data.get("meeting_id", ""))
    status = data.get("status", "pending")
    note = data.get("note", "")

    tracking = load_tracking()
    entry = get_tracking_entry(tracking, ref)
    existing = next((item for item in entry["meetings"] if str(item.get("meeting_id")) == meeting_id), None)
    if existing:
        existing["status"] = status
        existing["note"] = note
        existing["updated"] = now_local().isoformat()
    else:
        entry["meetings"].append({"meeting_id": meeting_id, "status": status, "note": note, "updated": now_local().isoformat()})
    save_tracking(tracking)
    return jsonify({"success": True})


@app.route("/update-relay", methods=["POST"])
def update_relay():
    data = request.json or {}
    ref = str(data.get("ref", ""))
    proof = data.get("proof", "").strip()

    tracking = load_tracking()
    entry = get_tracking_entry(tracking, ref)
    entry["relay_history"].append({"date": now_local().isoformat(), "proof": proof})
    entry["relay_count"] = len(entry["relay_history"])
    save_tracking(tracking)
    return jsonify({"success": True, "relay_count": entry["relay_count"]})

@app.route("/awards", methods=["GET", "POST"])
def awards():
    reps = load_data()
    awards_data = load_awards()
    tracking = load_tracking()

    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            ref = request.form.get("ref", "")
            year_input = request.form.get("year", str(now_local().year)).strip()
            try:
                year_int = int(year_input)
            except ValueError:
                flash("Invalid award year.", "error")
                return redirect(url_for("awards"))
            if year_int > now_local().year:
                flash("Future year awards cannot be added yet.", "error")
                return redirect(url_for("awards"))
            year = str(year_int)
            month_name = request.form.get("month", MONTH_NAMES[now_local().month - 1])
            month_number = month_name_to_number(month_name) or 1
            award = {
                "id": str(int(now_local().timestamp())),
                "ref": ref,
                "name": request.form.get("name", ""),
                "type": request.form.get("award_type", "monthly"),
                "month": month_name,
                "year": year,
                "reason": request.form.get("reason", "").strip(),
                "award_date": datetime(int(year), month_number, 1).date().isoformat(),
                "created": now_local().isoformat(),
            }
            awards_data.append(award)
            entry = get_tracking_entry(tracking, ref)
            entry["awards"].append(award["id"])
            save_tracking(tracking)
            save_awards(awards_data)
            flash("Award added successfully.", "success")
        elif action == "delete":
            award_id = request.form.get("award_id")
            awards_data = [award for award in awards_data if str(award.get("id")) != str(award_id)]
            save_awards(awards_data)
            flash("Award removed.", "success")
        return redirect(url_for("awards"))

    campus_filter = request.args.get("campus", "")
    year_filter = request.args.get("year", "")
    month_filter = request.args.get("month", "")
    type_filter = request.args.get("type", "")

    rep_map = {str(rep.get("ref")): rep for rep in reps}
    filtered_awards = []
    for award in awards_data:
        rep = rep_map.get(str(award.get("ref")))
        if not rep:
            continue
        if campus_filter and not match_campus(rep.get("campus"), campus_filter):
            continue
        if year_filter and str(award.get("year")) != str(year_filter):
            continue
        if month_filter and award.get("month") != month_filter:
            continue
        if type_filter and award.get("type") != type_filter:
            continue
        filtered_awards.append({**award, "rep_name": rep.get("name", "Unknown"), "campus": rep.get("campus", ""), "program": rep.get("program", "")})
    filtered_awards.sort(key=lambda award: (award.get("year", ""), award.get("award_date", ""), award.get("created", "")), reverse=True)

    monthly_winners = [award for award in filtered_awards if award.get("type") == "monthly"]
    yearly_winners = [award for award in filtered_awards if award.get("type") == "yearly"]

    return render_template(
        "awards.html",
        awards=filtered_awards,
        reps=filter_reps(reps, campus_filter, "", year_filter, ""),
        filters={"campus": campus_filter, "year": year_filter, "month": month_filter, "type": type_filter},
        all_years=get_dynamic_years(reps),
        month_names=MONTH_NAMES,
        monthly_winners=monthly_winners,
        yearly_winners=yearly_winners,
    )


@app.route("/engagement", methods=["GET", "POST"])
def engagement():
    reps = load_data()
    tracking = load_tracking()
    awards = load_awards()
    meetings = load_meetings()

    if request.method == "POST":
        ref = str(request.form.get("ref", ""))
        description = request.form.get("description", "").strip()
        event_date = request.form.get("date") or now_local().date().isoformat()
        points_raw = request.form.get("points", "5")
        try:
            points = int(points_raw or 5)
        except ValueError:
            flash("Points must be a valid number.", "error")
            return redirect(url_for("engagement"))
        entry = get_tracking_entry(tracking, ref)
        entry["contributions"].append({
            "id": str(int(now_local().timestamp())),
            "description": description,
            "date": event_date,
            "points": points,
            "created": now_local().isoformat(),
        })
        entry["volunteer_points"] = sum(int(item.get("points", 0) or 0) for item in entry["contributions"])
        save_tracking(tracking)
        flash("Volunteer contribution saved.", "success")
        return redirect(url_for("engagement"))

    campus_filter = request.args.get("campus", "")
    intake_filter = request.args.get("intake", "")
    year_filter = request.args.get("year", "")
    filtered_reps = filter_reps(reps, campus_filter, intake_filter, year_filter, "")
    rep_map = {str(rep.get("ref")): rep for rep in reps}

    contribution_rows = []
    for ref, entry in tracking.items():
        for contribution in ensure_tracking_entry(entry).get("contributions", []):
            rep = rep_map.get(str(ref))
            if not rep:
                continue
            if campus_filter and not match_campus(rep.get("campus"), campus_filter):
                continue
            if intake_filter and rep.get("intake") != intake_filter:
                continue
            if year_filter and str(get_application_year(rep) or "") != str(year_filter):
                continue
            contribution_rows.append({
                "ref": ref,
                "name": rep.get("name"),
                "program": rep.get("program"),
                "campus": rep.get("campus"),
                "description": contribution.get("description", ""),
                "date": contribution.get("date", ""),
                "points": contribution.get("points", 0),
            })
    contribution_rows.sort(key=lambda item: item.get("date", ""), reverse=True)

    current_ranking, archived_rankings = build_rankings(reps, tracking, awards, meetings)
    return render_template(
        "engagement.html",
        reps=filtered_reps,
        contributions=contribution_rows,
        filters={"campus": campus_filter, "intake": intake_filter, "year": year_filter},
        all_years=get_dynamic_years(reps),
        current_ranking=current_ranking,
        archived_rankings=archived_rankings,
        current_term=get_current_term(),
    )


@app.route("/emails", methods=["GET", "POST"])
def emails():
    reps = load_data()
    emails_log = load_emails()

    campus_filter = request.values.get("campus", "")
    intake_filter = request.values.get("intake", "")
    year_filter = request.values.get("year", "")
    selected_refs_query = request.args.get("selected_refs", "")
    selected_refs = {item for item in selected_refs_query.split(",") if item}
    filtered_reps = filter_reps(reps, campus_filter, intake_filter, year_filter, "")

    if request.method == "POST" and request.form.get("action") == "log_email":
        selected_refs = request.form.getlist("selected_refs")
        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "").strip()
        scheduled_time = request.form.get("scheduled_time", "")
        rep_map = {str(rep.get("ref")): rep for rep in reps}

        recipients = []
        for ref in selected_refs:
            rep = rep_map.get(str(ref))
            if rep:
                recipients.append({"ref": rep.get("ref"), "name": rep.get("name"), "email": rep.get("email")})

        if not recipients:
            flash("Please select at least one recipient.", "error")
            return redirect(url_for("emails", campus=campus_filter, intake=intake_filter, year=year_filter))

        emails_log.append({
            "id": str(int(now_local().timestamp())),
            "subject": subject,
            "body": body,
            "recipients": recipients,
            "scheduled_time": scheduled_time,
            "status": "scheduled" if scheduled_time else "logged",
            "created": now_local().isoformat(),
            "campus_filter": campus_filter,
            "intake_filter": intake_filter,
            "year_filter": year_filter,
        })
        save_emails(emails_log)
        flash(f"Email {'scheduled' if scheduled_time else 'saved'} for {len(recipients)} recipient(s).", "success")
        return redirect(url_for("emails", campus=campus_filter, intake=intake_filter, year=year_filter))

    emails_log.sort(key=lambda item: item.get("created", ""), reverse=True)
    return render_template(
        "emails.html",
        reps=filtered_reps,
        emails_log=emails_log,
        filters={"campus": campus_filter, "intake": intake_filter, "year": year_filter},
        all_years=get_dynamic_years(reps),
        selected_refs=selected_refs,
    )

@app.route("/api/stats")
def api_stats():
    reps = load_data()
    tracking = load_tracking()
    awards = load_awards()
    meetings = load_meetings()

    campus_filter = request.args.get("campus", "")
    intake_filter = request.args.get("intake", "")
    year_filter = request.args.get("year", "")
    month_filter = request.args.get("month", "")

    filtered = filter_reps(reps, campus_filter, intake_filter, year_filter, "")
    if month_filter:
        filtered = [rep for rep in filtered if parse_dt(rep.get("date")) and str(parse_dt(rep.get("date")).month) == str(month_filter)]

    programs = Counter(rep.get("program", "Unknown") or "Unknown" for rep in filtered)
    campuses = Counter(rep.get("campus", "Unknown") or "Unknown" for rep in filtered)
    intakes = Counter(rep.get("intake", "Unknown") or "Unknown" for rep in filtered)
    by_year = Counter(str(get_application_year(rep) or "Unknown") for rep in filtered)
    study_year = Counter(str(rep.get("current_year") or "Unknown") for rep in filtered)

    current_ranking, _ = build_rankings(reps, tracking, awards, meetings)
    current_term_code = get_current_term()["code"]
    current_term_reps = [rep for rep in reps if get_rep_term(rep) and get_rep_term(rep)["code"] == current_term_code]

    return jsonify({
        "total": len(filtered),
        "south": sum(1 for rep in filtered if "south" in str(rep.get("campus", "")).lower()),
        "downtown": sum(1 for rep in filtered if "downtown" in str(rep.get("campus", "")).lower()),
        "fall": intakes.get("Fall", 0),
        "winter": intakes.get("Winter", 0),
        "spring": intakes.get("Spring/Summer", 0),
        "kpis": {
            "total": len(filtered),
            "south": sum(1 for rep in filtered if "south" in str(rep.get("campus", "")).lower()),
            "downtown": sum(1 for rep in filtered if "downtown" in str(rep.get("campus", "")).lower()),
            "fall": intakes.get("Fall", 0),
            "winter": intakes.get("Winter", 0),
            "spring": intakes.get("Spring/Summer", 0),
            "total_meetings": len(meetings),
            "total_awards": len(awards),
            "active_term_reps": len(current_term_reps),
            "ranked_reps": len(current_ranking),
        },
        "programs": dict(programs.most_common(10)),
        "intakes": {key: intakes.get(key, 0) for key in ["Fall", "Winter", "Spring/Summer"]},
        "campuses": dict(campuses),
        "by_year": dict(sorted(by_year.items())),
        "study_year": dict(sorted(study_year.items())),
    })


@app.route("/health")
def health():
    return jsonify({"ok": True, "timestamp": now_local().isoformat()})


@app.route("/shutdown", methods=["POST"])
def shutdown():
    remote_addr = request.remote_addr or ""
    if remote_addr not in {"127.0.0.1", "::1", "localhost"}:
        return jsonify({"success": False, "error": "Forbidden"}), 403

    shutdown_callback = app.config.get("SERVER_SHUTDOWN")
    if shutdown_callback:
        threading.Thread(target=shutdown_callback, daemon=True).start()
        return jsonify({"success": True})

    return jsonify({"success": False, "error": "Shutdown unavailable"}), 503


@app.route("/export")
def export():
    fmt = request.args.get("format", "xlsx")
    campus_filter = request.args.get("campus", "")
    intake_filter = request.args.get("intake", "")
    year_filter = request.args.get("year", "")

    reps = load_data()
    tracking = load_tracking()
    awards = load_awards()
    meetings = load_meetings()
    filtered = filter_reps(reps, campus_filter, intake_filter, year_filter, "")

    rows = []
    for rep in filtered:
        summary = build_rep_summary(rep, tracking, awards, meetings)
        rows.append({
            "Reference #": rep.get("ref", ""),
            "Name": rep.get("name", ""),
            "Campus": rep.get("campus", ""),
            "Program": rep.get("program", ""),
            "Course Code": rep.get("course_code", ""),
            "Section": rep.get("class_section", ""),
            "Application Year": summary.get("_application_year", ""),
            "Intake": rep.get("intake", ""),
            "Professor": rep.get("professor", ""),
            "Email": rep.get("email", ""),
            "Phone": rep.get("phone", ""),
            "Meetings Attended": summary.get("_meetings_attended", 0),
            "Excused Regrets": summary.get("_meetings_notified", 0),
            "Relay Count": summary.get("_relayed", 0),
            "Volunteer Points": summary.get("_volunteer_points", 0),
            "Awards": len(summary.get("_awards", [])),
            "Performance Score": summary.get("_current_score", 0),
            "Date Applied": rep.get("date", ""),
        })

    dataframe = pd.DataFrame(rows)
    filename_base = f"classreps_{now_local().strftime('%Y%m%d_%H%M')}"

    if fmt == "xlsx":
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            dataframe.to_excel(writer, index=False, sheet_name="Class Reps")
            workbook = writer.book
            worksheet = writer.sheets["Class Reps"]
            header_format = workbook.add_format({"bold": True, "bg_color": "#006838", "font_color": "white", "border": 1})
            for column_index, value in enumerate(dataframe.columns.values):
                worksheet.write(0, column_index, value, header_format)
            worksheet.set_column(0, len(dataframe.columns) - 1, 18)
        buffer.seek(0)
        return send_file(buffer, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name=f"{filename_base}.xlsx")

    if fmt == "pdf":
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        buffer = io.BytesIO()
        document = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=20, rightMargin=20, topMargin=30, bottomMargin=30)
        styles = getSampleStyleSheet()
        elements = [
            Paragraph("<b>SRC Class Representative Report</b>", styles["Title"]),
            Spacer(1, 12),
            Paragraph(f"Generated: {now_local().strftime('%B %d, %Y %H:%M')} | Total: {len(rows)}", styles["Normal"]),
            Spacer(1, 12),
        ]
        columns = ["Reference #", "Name", "Campus", "Program", "Email", "Intake", "Meetings Attended", "Performance Score"]
        table_data = [columns]
        for row in rows:
            table_data.append([str(row.get(column, "")) for column in columns])
        table = Table(table_data, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#006838")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3FAF5")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elements.append(table)
        document.build(elements)
        buffer.seek(0)
        return send_file(buffer, mimetype="application/pdf", as_attachment=True, download_name=f"{filename_base}.pdf")

    return redirect(url_for("class_reps"))


@app.route("/api/reps-autocomplete")
def reps_autocomplete():
    query = request.args.get("q", "").lower()
    reps = load_data()
    results = []
    for rep in reps:
        haystack = " ".join([str(rep.get("name", "")), str(rep.get("ref", "")), str(rep.get("email", ""))]).lower()
        if query in haystack:
            results.append({"ref": rep.get("ref"), "name": rep.get("name"), "email": rep.get("email")})
        if len(results) >= 10:
            break
    return jsonify(results)


@app.route("/api/delete-all", methods=["POST"])
def delete_all():
    save_data([])
    flash("All class representative data cleared.", "success")
    return jsonify({"success": True})


@app.route("/api/save-notes", methods=["POST"])
def save_notes():
    data = request.json or {}
    ref = str(data.get("ref", ""))
    notes = data.get("notes", "")
    tracking = load_tracking()
    entry = get_tracking_entry(tracking, ref)
    entry["notes"] = notes
    save_tracking(tracking)
    return jsonify({"success": True})


@app.errorhandler(500)
def internal_error(error):
    log_error("Internal Server Error")
    log_error(traceback.format_exc())
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "Internal server error"}), 500
    return render_template("error.html", code=500, message="Something went wrong. Please try again."), 500


@app.errorhandler(Exception)
def unhandled_exception(error):
    if isinstance(error, SystemExit):
        raise error
    if isinstance(error, HTTPException):
        return error
    log_error(f"Unhandled exception: {repr(error)}")
    log_error(traceback.format_exc())
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "error": "Unexpected server error"}), 500
    return render_template("error.html", code=500, message="Unexpected server error. Please retry."), 500


@app.context_processor
def inject_globals():
    now = now_local()
    return {
        "now": now,
        "now_date": now.strftime("%Y-%m-%d"),
        "logo_asset": get_logo_asset(),
        "auth_enabled": auth_enabled(),
    }


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False, threaded=True)
