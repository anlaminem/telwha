import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


class ArchetypeScoringEngine:
    def __init__(self, spec_path):
        self.spec_path = Path(spec_path)
        self.spec: Dict[str, Any] = {}
        self.archetypes: Dict[str, Dict[str, Any]] = {}
        self.archetype_order: List[str] = []
        self.heavy_gates: Dict[str, Dict[str, Any]] = {}
        self._load_spec()

    def _normalize_scale_name(self, value: Any) -> str:
        text = str(value).strip()
        if not text:
            return ""
        text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
        text = text.lower()
        text = re.sub(r"[^a-z0-9]+", "", text)
        return text

    def _load_spec(self):
        if not self.spec_path.exists():
            raise FileNotFoundError(f"Spec file not found: {self.spec_path}")

        with open(self.spec_path, "r", encoding="utf-8") as f:
            self.spec = json.load(f)

        archetypes = self.spec.get("archetypes", [])
        if not isinstance(archetypes, list) or not archetypes:
            raise ValueError("Spec must contain a non-empty 'archetypes' list")

        seen_ids = set()
        parsed: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []

        for idx, row in enumerate(archetypes):
            if not isinstance(row, dict):
                raise ValueError(f"Spec archetypes[{idx}] must be an object")

            archetype_id = str(row.get("id", "")).strip()
            if not archetype_id:
                raise ValueError(f"Spec archetypes[{idx}] missing non-empty 'id'")
            if archetype_id in seen_ids:
                raise ValueError(f"Duplicate archetype id in spec: {archetype_id}")

            seen_ids.add(archetype_id)
            order.append(archetype_id)
            parsed[archetype_id] = {
                "id": archetype_id,
                "required_scales": self._normalize_scale_list(row.get("required_scales", []), f"{archetype_id}.required_scales"),
                "boost_scales": self._normalize_scale_list(row.get("boost_scales", []), f"{archetype_id}.boost_scales"),
                "exclusion_scales": self._normalize_scale_list(row.get("exclusion_scales", []), f"{archetype_id}.exclusion_scales"),
                "threshold_group": row.get("threshold_group", "default"),
                "primary_min_score": self._to_optional_float(row.get("primary_min_score")),
                "secondary_min_score": self._to_optional_float(row.get("secondary_min_score")),
                "mix_flag_within_primary_points": self._to_optional_float(row.get("mix_flag_within_primary_points")),
                "excl_threshold": self._to_optional_float(row.get("excl_threshold")),
                "required_weight": self._to_optional_float(row.get("required_weight"), default=0.60),
                "boost_weight": self._to_optional_float(row.get("boost_weight"), default=0.40),
                "exclusion_penalty_points": self._to_optional_float(row.get("exclusion_penalty_points"), default=20.0),
            }

        self.archetypes = parsed
        self.archetype_order = order

        heavy_gates = self.spec.get("heavy_archetype_safety_gates", {})
        if heavy_gates is None:
            heavy_gates = {}
        if not isinstance(heavy_gates, dict):
            raise ValueError("'heavy_archetype_safety_gates' must be an object if provided")
        self.heavy_gates = heavy_gates

    def _normalize_scale_list(self, values: Any, field_name: str) -> List[str]:
        if values is None:
            return []
        if not isinstance(values, list):
            raise ValueError(f"{field_name} must be a list")

        normalized = []
        for value in values:
            text = self._normalize_scale_name(value)
            if text:
                normalized.append(text)
        return normalized

    def _to_optional_float(self, value: Any, default: Optional[float] = None) -> Optional[float]:
        if value is None:
            return default
        try:
            if pd.isna(value):
                return default
        except Exception:
            pass

        if isinstance(value, str) and not value.strip():
            return default

        try:
            return float(value)
        except Exception as exc:
            raise ValueError(f"Cannot convert value to float: {value!r}") from exc

    def _avg(self, values: List[Any]) -> Optional[float]:
        vals = []
        for v in values:
            try:
                if pd.notna(v):
                    vals.append(float(v))
            except Exception:
                continue
        return sum(vals) / len(vals) if vals else None

    def _get_scale_map(self, scales_df, scale_col: str = "scale_name", value_col: str = "score") -> Dict[str, Any]:
        if scales_df is None or scales_df.empty:
            return {}
        if scale_col not in scales_df.columns or value_col not in scales_df.columns:
            raise ValueError(f"scales_df must contain '{scale_col}' and '{value_col}' columns")

        scale_series = scales_df[scale_col].apply(self._normalize_scale_name)
        if scale_series.duplicated().any():
            duplicates = scale_series[scale_series.duplicated(keep=False)].unique().tolist()
            raise ValueError(f"scales_df contains duplicate scale_name values after normalization: {duplicates}")

        return dict(zip(scale_series, scales_df[value_col]))

    def _score_one_archetype(self, archetype_id: str, scale_map: Dict[str, Any]) -> Dict[str, Any]:
        a = self.archetypes[archetype_id]

        required_scales = a.get("required_scales", [])
        boost_scales = a.get("boost_scales", [])
        exclusion_scales = a.get("exclusion_scales", [])

        req_vals = [scale_map.get(s) for s in required_scales]
        boost_vals = [scale_map.get(s) for s in boost_scales]
        excl_vals = [scale_map.get(s) for s in exclusion_scales]

        required_avg = self._avg(req_vals)
        boost_avg = self._avg(boost_vals)
        exclusion_avg = self._avg(excl_vals)

        required_weight = a.get("required_weight", 0.60) or 0.60
        boost_weight = a.get("boost_weight", 0.40) or 0.40
        exclusion_penalty_points = a.get("exclusion_penalty_points", 20.0) or 20.0
        excl_threshold = a.get("excl_threshold")

        penalty = 0.0
        if exclusion_avg is not None and excl_threshold is not None and exclusion_avg > excl_threshold:
            penalty = float(exclusion_penalty_points)

        score = None
        if required_avg is not None:
            score = (required_avg * required_weight) + ((boost_avg or 0.0) * boost_weight) - penalty

        gate_ok = True
        gate_reason = ""
        gate_values: Dict[str, Any] = {}

        gate_spec = self.heavy_gates.get(archetype_id, {})
        if gate_spec:
            gate_scales = gate_spec.get("core_scales_any_ge_70", []) or []
            if not isinstance(gate_scales, list):
                raise ValueError(f"heavy_archetype_safety_gates[{archetype_id}].core_scales_any_ge_70 must be a list")
            gate_scales = [self._normalize_scale_name(s) for s in gate_scales if self._normalize_scale_name(s)]
            gate_values = {s: scale_map.get(s) for s in gate_scales}
            gate_ok = any(pd.notna(v) and float(v) >= 70 for v in gate_values.values())
            if not gate_ok:
                gate_reason = "failed heavy archetype safety gate"

        return {
            "archetype": archetype_id,
            "required_scales": required_scales,
            "boost_scales": boost_scales,
            "exclusion_scales": exclusion_scales,
            "required_avg": round(required_avg, 2) if required_avg is not None else None,
            "boost_avg": round(boost_avg, 2) if boost_avg is not None else None,
            "exclusion_avg": round(exclusion_avg, 2) if exclusion_avg is not None else None,
            "required_weight": required_weight,
            "boost_weight": boost_weight,
            "excl_threshold": excl_threshold,
            "penalty": round(penalty, 2),
            "score": round(score, 2) if score is not None else None,
            "threshold_group": a.get("threshold_group"),
            "primary_min_score": a.get("primary_min_score"),
            "secondary_min_score": a.get("secondary_min_score"),
            "mix_flag_within_primary_points": a.get("mix_flag_within_primary_points"),
            "gate_ok": bool(gate_ok),
            "gate_reason": gate_reason,
            "gate_values": gate_values,
        }

    def score_archetypes(self, scales_df: pd.DataFrame) -> pd.DataFrame:
        scale_map = self._get_scale_map(scales_df)
        rows = [self._score_one_archetype(archetype_id, scale_map) for archetype_id in self.archetype_order]
        result_df = pd.DataFrame(rows)

        if result_df.empty:
            return result_df

        result_df["_score_sort"] = pd.to_numeric(result_df["score"], errors="coerce")
        result_df["_gate_sort"] = result_df["gate_ok"].astype(int)
        result_df = result_df.sort_values(
            by=["_gate_sort", "_score_sort", "archetype"],
            ascending=[False, False, True],
            na_position="last",
        ).reset_index(drop=True)
        result_df = result_df.drop(columns=["_score_sort", "_gate_sort"])
        return result_df

    def assign_primary_secondary(self, archetype_scores_df: pd.DataFrame) -> Dict[str, Any]:
        if archetype_scores_df is None or archetype_scores_df.empty:
            return {
                "primary_archetype": None,
                "primary_score": None,
                "secondary_archetype": None,
                "secondary_score": None,
                "mix_flag": False,
                "reason": "no archetype rows",
            }

        df = archetype_scores_df.copy()
        if "score" not in df.columns or "archetype" not in df.columns:
            raise ValueError("archetype_scores_df must contain 'archetype' and 'score'")

        df["_score_sort"] = pd.to_numeric(df["score"], errors="coerce")
        if "gate_ok" in df.columns:
            df["_gate_sort"] = df["gate_ok"].astype(int)
        else:
            df["_gate_sort"] = 1

        df = df.sort_values(
            by=["_gate_sort", "_score_sort", "archetype"],
            ascending=[False, False, True],
            na_position="last",
        ).reset_index(drop=True)

        top1 = df.iloc[0]
        top1_score = top1.get("score")
        top1_primary_min = top1.get("primary_min_score")
        top1_gate_ok = bool(top1.get("gate_ok", True))

        primary = None
        reason = ""

        if pd.isna(top1_score):
            reason = "top archetype has null score"
        elif top1_primary_min is None or pd.isna(top1_primary_min):
            reason = "top archetype missing primary_min_score"
        elif not top1_gate_ok:
            reason = top1.get("gate_reason") or "top archetype failed safety gate"
        elif float(top1_score) < float(top1_primary_min):
            reason = "top archetype failed primary threshold"
        else:
            primary = top1["archetype"]

        secondary = None
        secondary_score = None
        mix_flag = False

        if primary and len(df) > 1:
            top2 = df.iloc[1]
            top2_score = top2.get("score")
            top2_secondary_min = top2.get("secondary_min_score")
            top2_mix_gap = top2.get("mix_flag_within_primary_points")
            top2_gate_ok = bool(top2.get("gate_ok", True))

            gap = None
            if pd.notna(top1_score) and pd.notna(top2_score):
                gap = float(top1_score) - float(top2_score)

            if (
                pd.notna(top2_score)
                and top2_secondary_min is not None
                and pd.notna(top2_secondary_min)
                and top2_mix_gap is not None
                and pd.notna(top2_mix_gap)
                and gap is not None
                and top2_gate_ok
                and float(top2_score) >= float(top2_secondary_min)
                and gap <= float(top2_mix_gap)
            ):
                secondary = top2["archetype"]
                secondary_score = round(float(top2_score), 2)
                mix_flag = True

        return {
            "primary_archetype": primary,
            "primary_score": round(float(top1_score), 2) if primary and pd.notna(top1_score) else None,
            "secondary_archetype": secondary,
            "secondary_score": secondary_score,
            "mix_flag": mix_flag,
            "reason": reason,
        }


if __name__ == "__main__":
    import tempfile

    from coding import CodingEngine
    from scale_scoring import ScaleScoringEngine

    workbook = Path(
        "/home/user/workspace/space_files/collection_5a65eee3-bfc1-461b-8b1f-0d7c0fc032b4/939bf41e-fc2d-49f9-bac7-6c125711f45a/scoring_workbook_full_questions_v2-1.xlsx"
    )

    spec = {
        "archetypes": [
            {
                "id": "ZP",
                "required_scales": ["financial_visibility_score", "reserve_discipline_score"],
                "boost_scales": ["stress_index"],
                "exclusion_scales": ["honesty_index"],
                "primary_min_score": 55,
                "secondary_min_score": 50,
                "mix_flag_within_primary_points": 5,
                "excl_threshold": 80,
            },
            {
                "id": "FS",
                "required_scales": ["omission_index"],
                "boost_scales": ["opportunity_loss_index"],
                "exclusion_scales": [],
                "primary_min_score": 55,
                "secondary_min_score": 50,
                "mix_flag_within_primary_points": 5,
            },
        ],
        "heavy_archetype_safety_gates": {
            "FS": {
                "core_scales_any_ge_70": ["omission_index"]
            }
        },
    }

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
        json.dump(spec, tmp, ensure_ascii=False, indent=2)
        spec_path = Path(tmp.name)

    coding_engine = CodingEngine(workbook)
    scale_engine = ScaleScoringEngine(workbook)
    archetype_engine = ArchetypeScoringEngine(spec_path)

    demo_answers = {
        "FA1": {"item_id": "FA1", "raw": None, "option_code": 3},
        "FA2": {"item_id": "FA2", "raw": None, "option_code": 2},
        "FA3": {"item_id": "FA3", "raw": 4, "option_code": None},
        "FH1": {"item_id": "FH1", "raw": 2, "option_code": None},
        "PA2": {"item_id": "PA2", "raw": 3, "option_code": None},
        "PA5": {"item_id": "PA5", "raw": None, "option_code": 5},
        "ST2": {"item_id": "ST2", "raw": None, "option_code": 5},
        "HO7": {"item_id": "HO7", "raw": None, "option_code": 1},
    }

    coded_df = coding_engine.code_answers_dict(demo_answers)
    scales_df = scale_engine.score_scales_from_coded_df(coded_df)
    archetype_df = archetype_engine.score_archetypes(scales_df)
    assignment = archetype_engine.assign_primary_secondary(archetype_df)

    print(archetype_df.to_string(index=False))
    print("ASSIGNMENT:")
    print(assignment)
