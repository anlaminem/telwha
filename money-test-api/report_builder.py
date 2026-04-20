import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


class ReportBuilder:
    def __init__(self, result_schema_path, narrative_content_path=None):
        self.result_schema_path = Path(result_schema_path)
        self.result_schema = self._load_json(self.result_schema_path)

        self.schema_title = self.result_schema.get("title") if isinstance(self.result_schema, dict) else None
        self.schema_id = self.result_schema.get("$id") if isinstance(self.result_schema, dict) else None

        # Short vs full schema: short = кластерний рівень, full = 13 архетипів
        self.is_short_schema = bool(self.schema_id == "survey-result-short-v1.json") or bool(
            self.schema_title and "Short Form" in self.schema_title
        )

        # narrative_content розділяємо на дві секції
        self.narrative_content: Dict[str, Any] = {}
        self.full_archetypes_content: Dict[str, Any] = {}
        self.short_clusters_content: Dict[str, Any] = {}

        if narrative_content_path:
            narrative_path = Path(narrative_content_path)
            if narrative_path.exists():
                self._load_narrative_content(narrative_path)

    # ---------- базові утиліти ----------

    def _load_json(self, path: Path) -> Any:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"JSON file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_narrative_content(self, path: Path) -> None:
        """Читає narrative і розкладає його на full_archetypes / short_clusters."""
        data = self._load_json(path)
        if not isinstance(data, dict):
            self.narrative_content = {}
            self.full_archetypes_content = {}
            self.short_clusters_content = {}
            return

        # Зберігаємо raw для debug
        self.narrative_content = {str(k).strip(): v for k, v in data.items() if k != "_meta"}

        full_block = data.get("full_archetypes", {})
        short_block = data.get("short_clusters", {})

        if isinstance(full_block, dict):
            self.full_archetypes_content = {str(k).strip(): v for k, v in full_block.items()}
        else:
            self.full_archetypes_content = {}

        if isinstance(short_block, dict):
            self.short_clusters_content = {str(k).strip(): v for k, v in short_block.items()}
        else:
            self.short_clusters_content = {}

    def _clean_value(self, value: Any) -> Any:
        if isinstance(value, pd.DataFrame):
            return [
                self._clean_value(row)
                for row in value.where(pd.notnull(value), None).to_dict(orient="records")
            ]

        if isinstance(value, pd.Series):
            return self._clean_value(value.where(pd.notnull(value), None).to_dict())

        if isinstance(value, dict):
            return {k: self._clean_value(v) for k, v in value.items()}

        if isinstance(value, (list, tuple)):
            return [self._clean_value(v) for v in value]

        if isinstance(value, pd.Timestamp):
            return value.isoformat()

        if hasattr(value, "item") and callable(getattr(value, "item")):
            try:
                return self._clean_value(value.item())
            except Exception:
                pass

        if isinstance(value, float):
            if pd.isna(value) or value == float("inf") or value == float("-inf"):
                return None
            return float(value)

        try:
            if pd.isna(value):
                return None
        except Exception:
            pass

        return value

    def _safe_float(self, value: Any) -> Optional[float]:
        try:
            if pd.isna(value):
                return None
        except Exception:
            pass
        if value is None:
            return None
        try:
            return float(value)
        except Exception:
            return None

    def _safe_int(self, value: Any) -> Optional[int]:
        try:
            if pd.isna(value):
                return None
        except Exception:
            pass
        if value is None:
            return None
        try:
            return int(value)
        except Exception:
            return None

    # ---------- конвертація dataframes ----------

    def _df_to_scale_dict(self, scales_df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
        if scales_df is None or scales_df.empty:
            return {}

        out: Dict[str, Dict[str, Any]] = {}
        for _, row in scales_df.iterrows():
            scale_name = str(row.get("scale_name", "")).strip()
            if not scale_name:
                continue
            out[scale_name] = {
                "score": self._safe_float(row.get("score")),
                "n_items_total": self._safe_int(row.get("n_items_total")),
                "n_items_answered": self._safe_int(row.get("n_items_answered")),
            }
        return out

    def _df_to_archetype_rows(self, archetype_df: pd.DataFrame) -> List[Dict[str, Any]]:
        if archetype_df is None or archetype_df.empty:
            return []

        rows = []
        for _, row in archetype_df.iterrows():
            rows.append(
                {
                    "archetype": str(row.get("archetype", "")).strip() or None,
                    "score": self._safe_float(row.get("score")),
                    "required_avg": self._safe_float(row.get("required_avg")),
                    "boost_avg": self._safe_float(row.get("boost_avg")),
                    "exclusion_avg": self._safe_float(row.get("exclusion_avg")),
                    "penalty": self._safe_float(row.get("penalty")),
                    "threshold_group": row.get("threshold_group"),
                    "primary_min_score": self._safe_float(row.get("primary_min_score")),
                    "secondary_min_score": self._safe_float(row.get("secondary_min_score")),
                    "mix_flag_within_primary_points": self._safe_float(
                        row.get("mix_flag_within_primary_points")
                    ),
                    "gate_ok": bool(row.get("gate_ok", True)),
                    "gate_reason": row.get("gate_reason"),
                    "required_scales": row.get("required_scales", []),
                    "boost_scales": row.get("boost_scales", []),
                    "exclusion_scales": row.get("exclusion_scales", []),
                }
            )
        return self._clean_value(rows)

    # ---------- вибір narrative ----------

    def _get_archetype_content(self, archetype_code: Optional[str]) -> Dict[str, Any]:
        """
        Для full-schema шукаємо в full_archetypes_content (ключі типу 'ZP', 'FS'...).
        Для short-schema шукаємо в short_clusters_content (ключі типу 'ZP_CLUSTER'...).
        """
        if not archetype_code:
            return {}

        if self.is_short_schema:
            content = self.short_clusters_content.get(archetype_code, {})
        else:
            content = self.full_archetypes_content.get(archetype_code, {})

        return content if isinstance(content, dict) else {}

    # ---------- діставання частин narrative ----------

    def _extract_profile_summary(self, content: Dict[str, Any]) -> Dict[str, Any]:
        screen_1 = content.get("screen_1", {}) if isinstance(content, dict) else {}
        return {
            "title": screen_1.get("title"),
            "subtitle": screen_1.get("subtitle"),
            "intro_paragraphs": screen_1.get("intro_paragraphs", []),
            "key_strength": screen_1.get("key_strength"),
            "key_vulnerability": screen_1.get("key_vulnerability"),
        }

    def _extract_biases(self, content: Dict[str, Any]) -> List[Any]:
        return content.get("screen_3", {}).get("top_biases", []) if isinstance(content, dict) else []

    def _extract_break_contexts(self, content: Dict[str, Any]) -> List[Any]:
        return content.get("screen_4", {}).get("break_contexts", []) if isinstance(content, dict) else []

    def _extract_health_relationships(self, content: Dict[str, Any]) -> Dict[str, Any]:
        screen_5 = content.get("screen_5", {}) if isinstance(content, dict) else {}
        return {
            "health_text": screen_5.get("health_text"),
            "relationships_text": screen_5.get("relationships_text"),
        }

    def _extract_honesty(self, content: Dict[str, Any]) -> Dict[str, Any]:
        screen_6 = content.get("screen_6", {}) if isinstance(content, dict) else {}
        return {"honesty_text": screen_6.get("honesty_text")}

    def _extract_actions(self, content: Dict[str, Any]) -> List[Any]:
        return content.get("screen_7", {}).get("actions", []) if isinstance(content, dict) else []

    def _extract_meta(self, content: Dict[str, Any]) -> Dict[str, Any]:
        meta = content.get("meta", {}) if isinstance(content, dict) else {}
        context_modifiers = meta.get("context_modifiers", {}) if isinstance(meta, dict) else {}
        return {
            "base_emotion": meta.get("base_emotion"),
            "signature_phrases": meta.get("signature_phrases", []),
            "context_modifiers": {
                "employment": context_modifiers.get("employment", []),
                "mobility": context_modifiers.get("mobility", []),
                "age": context_modifiers.get("age", []),
                "resources": context_modifiers.get("resources", []),
                "debt_savings_investing_block": context_modifiers.get(
                    "debt_savings_investing_block", {}
                ),
                "behavioral_tax": context_modifiers.get("behavioral_tax", {}),
                "red_flags": context_modifiers.get("red_flags", []),
            },
        }

    # ---------- формування user_report ----------

    def _make_user_report(self, primary: Optional[str], primary_content: Dict[str, Any]) -> Dict[str, Any]:
        profile = self._extract_profile_summary(primary_content)
        actions = self._extract_actions(primary_content)
        meta = self._extract_meta(primary_content)
        biases = self._extract_biases(primary_content)
        break_contexts = self._extract_break_contexts(primary_content)

        top_strengths: List[str] = []
        if profile.get("key_strength"):
            top_strengths.append(profile.get("key_strength"))
        top_strengths.extend(meta.get("context_modifiers", {}).get("resources", [])[:2])

        top_risks: List[str] = []
        if profile.get("key_vulnerability"):
            top_risks.append(profile.get("key_vulnerability"))
        top_risks.extend(break_contexts[:2])

        next_best_action: Optional[str] = None
        if actions:
            first_action = actions[0]
            if isinstance(first_action, dict):
                next_best_action = (
                    first_action.get("title")
                    or first_action.get("text")
                    or first_action.get("action")
                )
            elif isinstance(first_action, str):
                next_best_action = first_action

        return {
            "report_title": profile.get("title") or primary,
            "report_summary_short": profile.get("subtitle"),
            "report_summary_long": "\n\n".join(profile.get("intro_paragraphs", []))
            if profile.get("intro_paragraphs")
            else None,
            "top_strengths": top_strengths,
            "top_risks": top_risks,
            "money_scripts": meta.get("signature_phrases", []),
            "nervous_system_pattern": meta.get("base_emotion"),
            "micro_actions_7d": [
                a.get("title") if isinstance(a, dict) else a
                for a in actions[:2]
                if (
                    isinstance(a, dict)
                    and (a.get("title") or a.get("text") or a.get("action"))
                )
                or isinstance(a, str)
            ],
            "micro_actions_30d": [
                a.get("title") if isinstance(a, dict) else a
                for a in actions[2:4]
                if (
                    isinstance(a, dict)
                    and (a.get("title") or a.get("text") or a.get("action"))
                )
                or isinstance(a, str)
            ],
            "priority_area": None,
            "next_best_action": next_best_action,
            "cta_variant": None,
            "dominant_biases": [
                b.get("name") if isinstance(b, dict) else b
                for b in biases[:3]
                if (isinstance(b, dict) and b.get("name")) or isinstance(b, str)
            ],
            "dominant_triggers": break_contexts[:3],
        }

    # ---------- debug і фінальний report ----------

    def _build_debug(self, assignment: Dict[str, Any]) -> Dict[str, Any]:
        # Для дебага корисно знати, які ключі доступні в обох секціях
        return {
            "assignment_reason": assignment.get("reason"),
            "schema_loaded": True,
            "schema_title": self.schema_title,
            "schema_id": self.schema_id,
            "is_short_schema": self.is_short_schema,
            "narrative_content_loaded": bool(self.narrative_content),
            "full_archetypes_available": sorted(list(self.full_archetypes_content.keys())),
            "short_clusters_available": sorted(list(self.short_clusters_content.keys())),
        }

    def build_report(self, case_id, scales_df, archetype_df, assignment):
        primary = assignment.get("primary_archetype")
        secondary = assignment.get("secondary_archetype")

        primary_content = self._get_archetype_content(primary)
        secondary_content = self._get_archetype_content(secondary)

        scales = self._df_to_scale_dict(scales_df)
        archetypes_ranked = self._df_to_archetype_rows(archetype_df)
        user_report = self._make_user_report(primary, primary_content)

        report = {
            "case_id": case_id,
            "profile_summary": {
                "primary_archetype": primary,
                "primary_score": assignment.get("primary_score"),
                "secondary_archetype": secondary,
                "secondary_score": assignment.get("secondary_score"),
                "mix_flag": assignment.get("mix_flag", False),
                "primary_content": self._extract_profile_summary(primary_content)
                if primary_content
                else {},
                "secondary_overlay": (
                    {
                        "title": secondary_content.get("screen_1", {}).get("title"),
                        "subtitle": secondary_content.get("screen_1", {}).get("subtitle"),
                    }
                    if secondary_content
                    else None
                ),
            },
            "scales": scales,
            "archetypes_ranked": archetypes_ranked,
            "primary_archetype_report": (
                {
                    "screen_1": primary_content.get("screen_1", {}),
                    "screen_3": {"top_biases": self._extract_biases(primary_content)},
                    "screen_4": {"break_contexts": self._extract_break_contexts(primary_content)},
                    "screen_5": self._extract_health_relationships(primary_content),
                    "screen_6": self._extract_honesty(primary_content),
                    "screen_7": {"actions": self._extract_actions(primary_content)},
                    "meta": self._extract_meta(primary_content),
                }
                if primary_content
                else {}
            ),
            "secondary_archetype_overlay": (
                {
                    "screen_1": secondary_content.get("screen_1", {}),
                    "meta": self._extract_meta(secondary_content),
                }
                if secondary_content
                else {}
            ),
            "user_report": user_report,
            "debug": self._build_debug(assignment),
        }

        return self._clean_value(report)

    def save_report_json(self, report: Dict[str, Any], output_path):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        clean_report = self._clean_value(report)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(clean_report, f, ensure_ascii=False, indent=2)
        return output_path