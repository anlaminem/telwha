from pathlib import Path
from typing import Any, Dict, Optional, List
from uuid import uuid4
from datetime import datetime, timezone, timedelta
import hashlib
import json

import pandas as pd
from fastapi import Body, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from coding import CodingEngine
from scale_scoring import ScaleScoringEngine
from archetype_scoring import ArchetypeScoringEngine
from report_builder import ReportBuilder


BASE_DIR = Path(__file__).resolve().parent

WORKBOOK_PATH = BASE_DIR / "scoring_workbook_full_questions_v2-1.xlsx"
SPEC_PATH = BASE_DIR / "scoring_formula_spec_v3_thresholds.json"
NARRATIVE_CONTENT_PATH = BASE_DIR / "archetype_report_content_v1.json"
SHORT_SCHEMA_PATH = BASE_DIR / "survey-result-short-v1.json"
FULL_SCHEMA_PATH = BASE_DIR / "survey-result-schema.v1.json"

SUBMISSIONS_PATH = BASE_DIR / "survey_submissions.jsonl"

RESPONDENT_COOKIE_NAME = "finlab_rid"
COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365

MIN_ITEMS_FOR_VALID_SUBMISSION = 10
DEFAULT_ANALYTICS_WINDOW_DAYS = 45
DEFAULT_MIN_COMPLETION_SECONDS = 60


app = FastAPI(
    title="Money Test API",
    version="1.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://YOUR-GITHUB-USERNAME.github.io",
        "https://YOUR-DOMAIN.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

coding_engine: Optional[CodingEngine] = None
scale_engine: Optional[ScaleScoringEngine] = None
archetype_engine: Optional[ArchetypeScoringEngine] = None
report_builder: Optional[ReportBuilder] = None
active_schema_path: Optional[Path] = None


def clean_for_json(obj: Any):
    if isinstance(obj, pd.DataFrame):
        return clean_for_json(obj.where(pd.notnull(obj), None).to_dict(orient="records"))

    if isinstance(obj, pd.Series):
        return clean_for_json(obj.where(pd.notnull(obj), None).to_dict())

    if isinstance(obj, dict):
        return {k: clean_for_json(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [clean_for_json(v) for v in obj]

    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()

    if hasattr(obj, "item") and callable(getattr(obj, "item")):
        try:
            return clean_for_json(obj.item())
        except Exception:
            pass

    if isinstance(obj, float):
        if pd.isna(obj) or obj == float("inf") or obj == float("-inf"):
            return None
        return obj

    try:
        if pd.isna(obj):
            return None
    except Exception:
        pass

    return obj


def require_file(path: Path, label: str) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def resolve_schema_path() -> Path:
    if SHORT_SCHEMA_PATH.exists():
        return SHORT_SCHEMA_PATH
    if FULL_SCHEMA_PATH.exists():
        return FULL_SCHEMA_PATH
    raise FileNotFoundError(
        "Schema file not found. Expected one of: "
        f"{SHORT_SCHEMA_PATH.name}, {FULL_SCHEMA_PATH.name}"
    )


def normalize_item_id(value: Any) -> str:
    if value is None or pd.isna(value):
        raise ValueError("item_id cannot be null")
    item_id = str(value).strip().upper()
    if not item_id:
        raise ValueError("item_id cannot be blank")
    return item_id


def normalize_answers_payload(answers_payload: Any) -> Dict[str, Dict[str, Any]]:
    if isinstance(answers_payload, dict):
        normalized: Dict[str, Dict[str, Any]] = {}
        for key, value in answers_payload.items():
            if not isinstance(value, dict):
                raise ValueError(
                    f"answers[{key!r}] must be an object like "
                    f"{{'item_id': ..., 'raw': ..., 'option_code': ...}}"
                )

            record = dict(value)
            record.setdefault("item_id", key)
            item_id = normalize_item_id(record.get("item_id"))

            if item_id in normalized:
                raise ValueError(f"Duplicate item_id in answers: {item_id}")

            normalized[item_id] = {
                "item_id": item_id,
                "raw": record.get("raw"),
                "option_code": record.get("option_code"),
            }
        return normalized

    if isinstance(answers_payload, list):
        normalized = {}
        for idx, value in enumerate(answers_payload):
            if not isinstance(value, dict):
                raise ValueError(
                    f"answers[{idx}] must be an object like "
                    f"{{'item_id': ..., 'raw': ..., 'option_code': ...}}"
                )
            if "item_id" not in value:
                raise ValueError(f"answers[{idx}] must contain 'item_id'")

            item_id = normalize_item_id(value.get("item_id"))
            if item_id in normalized:
                raise ValueError(f"Duplicate item_id in answers: {item_id}")

            normalized[item_id] = {
                "item_id": item_id,
                "raw": value.get("raw"),
                "option_code": value.get("option_code"),
            }
        return normalized

    raise ValueError(
        "'answers' must be either an object keyed by item_id or a list of answer records"
    )


def ensure_engines_initialized():
    if (
        coding_engine is None
        or scale_engine is None
        or archetype_engine is None
        or report_builder is None
    ):
        raise RuntimeError("Scoring engines are not initialized")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def make_attempt_id() -> str:
    return f"att_{uuid4().hex}"


def make_respondent_token() -> str:
    return f"finlab_rt_{uuid4().hex}"


def get_or_create_respondent_token(request: Request, payload: Dict[str, Any]) -> str:
    payload_candidates = [
        payload.get("respondent_token"),
        payload.get("respondent_id"),
    ]

    response_control = payload.get("response_control")
    if isinstance(response_control, dict):
        payload_candidates.append(response_control.get("respondent_token"))

    for candidate in payload_candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    cookie_value = request.cookies.get(RESPONDENT_COOKIE_NAME)
    if cookie_value and isinstance(cookie_value, str) and cookie_value.strip():
        return cookie_value.strip()

    return make_respondent_token()


def set_respondent_cookie(response: Response, respondent_token: str):
    response.set_cookie(
        key=RESPONDENT_COOKIE_NAME,
        value=respondent_token,
        max_age=COOKIE_MAX_AGE_SECONDS,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )


def ensure_submissions_store_exists():
    if not SUBMISSIONS_PATH.exists():
        SUBMISSIONS_PATH.touch()


def load_all_submissions() -> List[Dict[str, Any]]:
    ensure_submissions_store_exists()
    rows: List[Dict[str, Any]] = []
    with SUBMISSIONS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def append_submission(record: Dict[str, Any]) -> None:
    ensure_submissions_store_exists()
    with SUBMISSIONS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(clean_for_json(record), ensure_ascii=False) + "\n")


def count_answer_fingerprint(answers: Dict[str, Dict[str, Any]]) -> str:
    canonical = []
    for item_id in sorted(answers.keys()):
        answer = answers[item_id]
        canonical.append(
            {
                "item_id": item_id,
                "raw": answer.get("raw"),
                "option_code": answer.get("option_code"),
            }
        )
    raw = json.dumps(canonical, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_submissions_for_respondent(respondent_token: str) -> List[Dict[str, Any]]:
    submissions = load_all_submissions()
    matched = [
        s for s in submissions
        if s.get("respondent_token") == respondent_token
        or s.get("respondent_id") == respondent_token
    ]
    matched.sort(key=lambda x: x.get("submitted_at", ""))
    return matched


def is_valid_submission(items_answered: int) -> bool:
    return items_answered >= MIN_ITEMS_FOR_VALID_SUBMISSION


def extract_completion_seconds(payload: Dict[str, Any]) -> Optional[int]:
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        duration = metadata.get("duration_seconds")
        if duration is not None:
            try:
                return max(0, int(duration))
            except Exception:
                pass

    started_at = parse_iso_datetime(payload.get("started_at")) or parse_iso_datetime(
        metadata.get("started_at") if isinstance(metadata, dict) else None
    )
    completed_at = parse_iso_datetime(payload.get("completed_at")) or parse_iso_datetime(
        metadata.get("completed_at") if isinstance(metadata, dict) else None
    )

    if started_at and completed_at:
        return max(0, int((completed_at - started_at).total_seconds()))

    return None


def detect_same_option_pattern(answers: Dict[str, Dict[str, Any]]) -> bool:
    values = []
    for answer in answers.values():
        raw = answer.get("raw")
        option_code = answer.get("option_code")
        if raw is not None:
            values.append(("raw", raw))
        elif option_code is not None:
            values.append(("option_code", option_code))

    if len(values) < 8:
        return False

    first = values[0]
    return all(v == first for v in values)


def build_response_control(
    respondent_token: str,
    attempt_id: str,
    previous_submissions: List[Dict[str, Any]],
    items_answered: int,
    valid_submission: bool,
    duration_seconds: Optional[int],
    analytics_window_days: int,
    answers: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    now = utc_now()

    prior_attempt_count = len(previous_submissions)
    prior_completed = [
        s for s in previous_submissions
        if (s.get("metadata") or {}).get("completion_status") == "completed"
        or s.get("valid_submission") is True
    ]
    prior_completed_count = len(prior_completed)

    last_completed_at = None
    completed_dates = []
    for row in prior_completed:
        dt = parse_iso_datetime((row.get("metadata") or {}).get("completed_at")) or parse_iso_datetime(
            row.get("submitted_at")
        )
        if dt:
            completed_dates.append(dt)

    if completed_dates:
        last_completed_dt = max(completed_dates)
        last_completed_at = last_completed_dt.isoformat()
    else:
        last_completed_dt = None

    is_repeat = prior_attempt_count > 0
    is_repeat_window = False
    if last_completed_dt is not None:
        is_repeat_window = (now - last_completed_dt) <= timedelta(days=analytics_window_days)

    too_fast = duration_seconds is not None and duration_seconds < DEFAULT_MIN_COMPLETION_SECONDS
    incomplete = not valid_submission
    same_option_pattern = detect_same_option_pattern(answers)

    include_in_aggregate = bool(
        valid_submission
        and not too_fast
        and not same_option_pattern
        and not is_repeat_window
    )

    if include_in_aggregate:
        aggregate_status = "unique_valid"
    elif too_fast:
        aggregate_status = "excluded_too_fast"
    elif same_option_pattern:
        aggregate_status = "excluded_same_option_pattern"
    elif is_repeat_window:
        aggregate_status = "excluded_repeat_window"
    elif incomplete:
        aggregate_status = "excluded_incomplete"
    else:
        aggregate_status = "excluded_other"

    return {
        "respondent_token": respondent_token,
        "attempt_id": attempt_id,
        "is_repeat": is_repeat,
        "is_repeat_window": is_repeat_window,
        "prior_attempt_count": prior_attempt_count,
        "prior_completed_count": prior_completed_count,
        "last_completed_at": last_completed_at,
        "include_in_aggregate": include_in_aggregate,
        "aggregate_status": aggregate_status,
        "quality_flags": {
            "too_fast": too_fast,
            "incomplete": incomplete,
            "same_option_pattern": same_option_pattern,
        },
    }


@app.on_event("startup")
def startup_event():
    global coding_engine, scale_engine, archetype_engine, report_builder, active_schema_path

    require_file(WORKBOOK_PATH, "Workbook")
    require_file(SPEC_PATH, "Spec file")
    require_file(NARRATIVE_CONTENT_PATH, "Narrative content file")

    active_schema_path = resolve_schema_path()

    coding_engine = CodingEngine(WORKBOOK_PATH)
    scale_engine = ScaleScoringEngine(WORKBOOK_PATH)
    archetype_engine = ArchetypeScoringEngine(SPEC_PATH)
    report_builder = ReportBuilder(active_schema_path, NARRATIVE_CONTENT_PATH)

    ensure_submissions_store_exists()


@app.get("/")
def root():
    return {
        "ok": True,
        "message": "Money Test API is running",
        "schema": active_schema_path.name if active_schema_path else None,
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "schema": active_schema_path.name if active_schema_path else None,
    }


@app.get("/admin/submissions-summary")
def submissions_summary():
    submissions = load_all_submissions()
    total = len(submissions)

    unique_respondents = len(
        {
            s.get("respondent_token") or s.get("respondent_id")
            for s in submissions
            if s.get("respondent_token") or s.get("respondent_id")
        }
    )

    included = sum(
        1
        for s in submissions
        if ((s.get("response_control") or {}).get("include_in_aggregate") is True)
        or (s.get("include_in_public_stats") is True)
    )

    repeats = sum(
        1
        for s in submissions
        if ((s.get("response_control") or {}).get("is_repeat") is True)
        or (s.get("is_repeat") is True)
    )

    repeat_window = sum(
        1
        for s in submissions
        if ((s.get("response_control") or {}).get("is_repeat_window") is True)
    )

    return {
        "ok": True,
        "total_submissions": total,
        "unique_respondents": unique_respondents,
        "included_in_aggregate": included,
        "repeat_submissions": repeats,
        "repeat_window_submissions": repeat_window,
    }


@app.post("/score")
def score(
    request: Request,
    response: Response,
    payload: dict = Body(...),
):
    try:
        if not isinstance(payload, dict):
            raise ValueError("Payload must be a JSON object")

        ensure_engines_initialized()

        case_id = str(payload.get("case_id", "web_case")).strip() or "web_case"

        answers_payload = payload.get("answers")
        if answers_payload is None and "raw_answers" in payload:
            answers_payload = payload.get("raw_answers")

        if answers_payload is None:
            raise ValueError("Payload must contain 'answers' or 'raw_answers'")

        answers = normalize_answers_payload(answers_payload)

        respondent_token = get_or_create_respondent_token(request, payload)
        attempt_id = str(payload.get("attempt_id") or "").strip() or make_attempt_id()

        items_answered = len(answers)
        valid_submission = is_valid_submission(items_answered)
        answer_fingerprint = count_answer_fingerprint(answers)

        analytics_window_days = DEFAULT_ANALYTICS_WINDOW_DAYS
        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            try:
                analytics_window_days = int(
                    metadata.get("analytics_window_days", DEFAULT_ANALYTICS_WINDOW_DAYS)
                )
            except Exception:
                analytics_window_days = DEFAULT_ANALYTICS_WINDOW_DAYS

        duration_seconds = extract_completion_seconds(payload)

        coded_df = coding_engine.code_answers_dict(answers)
        scales_df = scale_engine.score_scales_from_coded_df(coded_df)
        archetype_df = archetype_engine.score_archetypes(scales_df)
        assignment = archetype_engine.assign_primary_secondary(archetype_df)

        report = report_builder.build_report(
            case_id=case_id,
            scales_df=scales_df,
            archetype_df=archetype_df,
            assignment=assignment,
        )

        previous_submissions = load_submissions_for_respondent(respondent_token)
        response_control = build_response_control(
            respondent_token=respondent_token,
            attempt_id=attempt_id,
            previous_submissions=previous_submissions,
            items_answered=items_answered,
            valid_submission=valid_submission,
            duration_seconds=duration_seconds,
            analytics_window_days=analytics_window_days,
            answers=answers,
        )

        now_iso = utc_now_iso()
        completion_status = (
            "completed" if valid_submission else ("partial" if items_answered > 0 else "abandoned")
        )

        metadata_out = {
            "duration_seconds": duration_seconds,
            "completion_status": completion_status,
            "answered_count": items_answered,
            "required_count": payload.get("metadata", {}).get("required_count", None)
            if isinstance(payload.get("metadata"), dict)
            else None,
            "started_at": (
                payload.get("metadata", {}).get("started_at")
                if isinstance(payload.get("metadata"), dict)
                else None
            ),
            "completed_at": (
                payload.get("metadata", {}).get("completed_at")
                if isinstance(payload.get("metadata"), dict)
                else now_iso
            ),
            "analytics_window_days": analytics_window_days,
        }

        submission_record = {
            "attempt_id": attempt_id,
            "respondent_token": respondent_token,
            "respondent_id": respondent_token,
            "case_id": case_id,
            "submitted_at": now_iso,
            "items_answered": items_answered,
            "valid_submission": valid_submission,
            "include_in_public_stats": response_control["include_in_aggregate"],
            "is_repeat": response_control["is_repeat"],
            "answer_fingerprint": answer_fingerprint,
            "metadata": metadata_out,
            "response_control": response_control,
            "assignment": clean_for_json(assignment),
            "answers": clean_for_json(answers),
            "incoming_payload_meta": clean_for_json(payload.get("metadata", {})),
        }

        append_submission(submission_record)
        set_respondent_cookie(response, respondent_token)

        response_payload = {
            "ok": True,
            "case_id": case_id,
            "attempt_id": attempt_id,
            "respondent_token": respondent_token,
            "respondent_id": respondent_token,
            "items_answered": items_answered,
            "valid_submission": valid_submission,
            "response_control": response_control,
            "include_in_aggregate": response_control["include_in_aggregate"],
            "assignment": assignment,
            "report": report,
            "debug_tables": {
                "coded_answers": coded_df,
                "scales": scales_df,
                "archetypes": archetype_df,
            },
        }

        return clean_for_json(response_payload)

    except HTTPException:
        raise
    except (ValueError, TypeError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)