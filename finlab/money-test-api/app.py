from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from fastapi import Body, FastAPI, HTTPException
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


app = FastAPI(
    title="Money Test API",
    version="1.1.0",
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
                    f"answers[{key!r}] must be an object like {{'item_id': ..., 'raw': ..., 'option_code': ...}}"
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
                    f"answers[{idx}] must be an object like {{'item_id': ..., 'raw': ..., 'option_code': ...}}"
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

    raise ValueError("'answers' must be either an object keyed by item_id or a list of answer records")


def ensure_engines_initialized():
    if coding_engine is None or scale_engine is None or archetype_engine is None or report_builder is None:
        raise RuntimeError("Scoring engines are not initialized")


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


@app.post("/score")
def score(payload: dict = Body(...)):
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

        response_payload = {
            "ok": True,
            "case_id": case_id,
            "items_answered": len(answers),
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