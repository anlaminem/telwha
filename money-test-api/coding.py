import pandas as pd
from pathlib import Path
from typing import Union, Optional, Dict, Any

DIRECT_MAP = {1: 0, 2: 25, 3: 50, 4: 75, 5: 100}
REVERSE_MAP = {1: 100, 2: 75, 3: 50, 4: 25, 5: 0}
DIRECT_0_4_MAP = {0: 0, 1: 25, 2: 50, 3: 75, 4: 100}
BINARY_0_1_MAP = {0: 0, 1: 100}

RULE_BY_INPUT_TYPE = {
    "cat": {"mapped_cat_to_1_5_then_0_100"},
    "1-5": {"direct_1_5_to_0_100", "reverse_1_5_to_0_100", "mapped_cat_to_1_5_then_0_100"},
    "0-4": {"direct_0_4_to_0_100"},
    "0-1": {"binary_0_1_to_0_100"},
}


class CodingEngine:
    def __init__(self, workbook_path: Union[str, Path]):
        self.workbook_path = Path(workbook_path)
        self.inputs_df = None
        self.mapping_df = None
        self.coding_df = None
        self.item_rules: Dict[str, str] = {}
        self.item_input_types: Dict[str, str] = {}
        self.category_maps: Dict[str, Dict[str, int]] = {}
        self._load_workbook()

    def _load_workbook(self):
        if not self.workbook_path.exists():
            raise FileNotFoundError(f"Workbook not found: {self.workbook_path}")

        xl = pd.read_excel(self.workbook_path, sheet_name=None)
        self.inputs_df = self._require_sheet(xl, "Inputs")
        self.mapping_df = self._require_sheet(xl, "Mapping")
        self.coding_df = self._require_sheet(xl, "Coding")
        self._build_input_types()
        self._build_item_rules()
        self._build_category_maps()
        self._validate_workbook_consistency()

    def _require_sheet(self, sheets: dict, sheet_name: str) -> pd.DataFrame:
        if sheet_name not in sheets:
            raise ValueError(f"Required sheet not found: {sheet_name}")
        return sheets[sheet_name].copy()

    def _normalize_item_id(self, value: Any) -> str:
        if pd.isna(value):
            raise ValueError("item_id cannot be null")
        item_id = str(value).strip().upper()
        if not item_id:
            raise ValueError("item_id cannot be blank")
        return item_id

    def _normalize_option_code(self, value: Any) -> Optional[str]:
        if pd.isna(value) or value is None:
            return None
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        if isinstance(value, int):
            return str(value)
        return str(value).strip()

    def _normalize_int_like(self, value: Any, field_name: str) -> int:
        if pd.isna(value) or value is None:
            raise ValueError(f"{field_name} is required")
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                raise ValueError(f"{field_name} cannot be blank")
        try:
            num = float(value)
        except Exception as exc:
            raise ValueError(f"{field_name} must be numeric, got {value!r}") from exc
        if not num.is_integer():
            raise ValueError(f"{field_name} must be an integer-like value, got {value!r}")
        return int(num)

    def _build_input_types(self):
        df = self.inputs_df.copy()
        df.columns = [str(c).strip().lower() for c in df.columns]
        required = {"item_id", "input_type"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Inputs sheet must contain {required}, got {set(df.columns)}")

        df["item_id"] = df["item_id"].apply(self._normalize_item_id)
        df["input_type"] = df["input_type"].astype(str).str.strip()

        duplicate_ids = df.loc[df["item_id"].duplicated(keep=False), "item_id"].unique().tolist()
        if duplicate_ids:
            raise ValueError(f"Inputs sheet contains duplicate item_id values: {duplicate_ids}")

        for _, row in df.iterrows():
            item_id = row["item_id"]
            input_type = row["input_type"]
            if input_type not in RULE_BY_INPUT_TYPE:
                raise ValueError(f"Unsupported input_type for {item_id}: {input_type}")
            self.item_input_types[item_id] = input_type

    def _build_item_rules(self):
        df = self.coding_df.copy()
        df.columns = [str(c).strip().lower() for c in df.columns]
        required = {"item_id", "coding_rule"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Coding sheet must contain {required}, got {set(df.columns)}")

        df["item_id"] = df["item_id"].apply(self._normalize_item_id)
        df["coding_rule"] = df["coding_rule"].astype(str).str.strip()

        duplicate_ids = df.loc[df["item_id"].duplicated(keep=False), "item_id"].unique().tolist()
        if duplicate_ids:
            raise ValueError(f"Coding sheet contains duplicate item_id values: {duplicate_ids}")

        for _, row in df.iterrows():
            self.item_rules[row["item_id"]] = row["coding_rule"]

    def _build_category_maps(self):
        df = self.mapping_df.copy()
        df.columns = [str(c).strip().lower() for c in df.columns]
        required = {"item_id", "option_code", "normalized_score_1_5"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Mapping sheet must contain {required}, got {set(df.columns)}")

        for _, row in df.iterrows():
            if pd.isna(row["item_id"]) or pd.isna(row["option_code"]) or pd.isna(row["normalized_score_1_5"]):
                continue

            item_id = self._normalize_item_id(row["item_id"])
            option_code = self._normalize_option_code(row["option_code"])
            mapped_1_5 = self._normalize_int_like(row["normalized_score_1_5"], "normalized_score_1_5")

            if mapped_1_5 not in DIRECT_MAP:
                raise ValueError(f"Invalid normalized_score_1_5 for {item_id}: {mapped_1_5}")

            self.category_maps.setdefault(item_id, {})[option_code] = mapped_1_5

    def _validate_workbook_consistency(self):
        input_ids = set(self.item_input_types)
        coding_ids = set(self.item_rules)

        missing_in_coding = sorted(input_ids - coding_ids)
        missing_in_inputs = sorted(coding_ids - input_ids)

        if missing_in_coding:
            raise ValueError(f"Items present in Inputs but missing in Coding: {missing_in_coding}")
        if missing_in_inputs:
            raise ValueError(f"Items present in Coding but missing in Inputs: {missing_in_inputs}")

        for item_id in sorted(input_ids):
            input_type = self.item_input_types[item_id]
            coding_rule = self.item_rules[item_id]
            allowed_rules = RULE_BY_INPUT_TYPE[input_type]
            if coding_rule not in allowed_rules:
                raise ValueError(
                    f"Incompatible input_type/coding_rule for {item_id}: input_type={input_type}, coding_rule={coding_rule}"
                )

            if coding_rule == "mapped_cat_to_1_5_then_0_100" and item_id not in self.category_maps:
                raise ValueError(f"Category mapping missing for mapped category item_id={item_id}")

    def get_item_spec(self, item_id: Any) -> Dict[str, Any]:
        normalized_item_id = self._normalize_item_id(item_id)
        if normalized_item_id not in self.item_rules:
            raise KeyError(f"Unknown item_id: {normalized_item_id}")
        return {
            "item_id": normalized_item_id,
            "input_type": self.item_input_types[normalized_item_id],
            "coding_rule": self.item_rules[normalized_item_id],
        }

    def code_answer_record(self, answer_record: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(answer_record, dict):
            raise TypeError("answer_record must be a dict")
        if "item_id" not in answer_record:
            raise ValueError("answer_record must contain 'item_id'")

        item_id = self._normalize_item_id(answer_record.get("item_id"))
        spec = self.get_item_spec(item_id)
        input_type = spec["input_type"]
        coding_rule = spec["coding_rule"]

        raw = answer_record.get("raw")
        option_code = answer_record.get("option_code")
        normalized_option_code = self._normalize_option_code(option_code)

        if coding_rule == "mapped_cat_to_1_5_then_0_100":
            if raw is not None and not pd.isna(raw):
                raise ValueError(f"Mapped category item {item_id} must have raw=None; got {raw!r}")
            if normalized_option_code is None:
                raise ValueError(f"Mapped category item {item_id} requires option_code")
            normalized_score_1_5 = self.category_maps[item_id].get(normalized_option_code)
            if normalized_score_1_5 is None:
                raise KeyError(f"No mapped category rule for item_id={item_id}, option_code={normalized_option_code}")
            coded_0_100 = DIRECT_MAP[normalized_score_1_5]
            source_value = normalized_option_code
        else:
            if normalized_option_code is not None:
                raise ValueError(f"Numeric scale item {item_id} must have option_code=None; got {option_code!r}")
            raw_int = self._normalize_int_like(raw, f"raw for {item_id}")
            if coding_rule == "direct_1_5_to_0_100":
                if raw_int not in DIRECT_MAP:
                    raise ValueError(f"Invalid direct raw value for {item_id}: {raw_int}")
                coded_0_100 = DIRECT_MAP[raw_int]
            elif coding_rule == "reverse_1_5_to_0_100":
                if raw_int not in REVERSE_MAP:
                    raise ValueError(f"Invalid reverse raw value for {item_id}: {raw_int}")
                coded_0_100 = REVERSE_MAP[raw_int]
            elif coding_rule == "direct_0_4_to_0_100":
                if raw_int not in DIRECT_0_4_MAP:
                    raise ValueError(f"Invalid direct_0_4 raw value for {item_id}: {raw_int}")
                coded_0_100 = DIRECT_0_4_MAP[raw_int]
            elif coding_rule == "binary_0_1_to_0_100":
                if raw_int not in BINARY_0_1_MAP:
                    raise ValueError(f"Invalid binary_0_1 raw value for {item_id}: {raw_int}")
                coded_0_100 = BINARY_0_1_MAP[raw_int]
            else:
                raise ValueError(
                    f"Unsupported coding_rule for {item_id}: {coding_rule}"
                )
            normalized_score_1_5 = None
            source_value = raw_int

        return {
            "item_id": item_id,
            "input_type": input_type,
            "coding_rule": coding_rule,
            "source_value": source_value,
            "normalized_score_1_5": normalized_score_1_5,
            "coded_0_100": coded_0_100,
        }

    def code_answers_dict(self, answers: Dict[str, Dict[str, Any]]) -> pd.DataFrame:
        rows = []
        for item_id, answer_record in answers.items():
            if not isinstance(answer_record, dict):
                raise TypeError(
                    f"answers[{item_id!r}] must be a dict like {{'item_id': ..., 'raw': ..., 'option_code': ...}}"
                )
            record = dict(answer_record)
            record.setdefault("item_id", item_id)
            rows.append(self.code_answer_record(record))
        return pd.DataFrame(rows)

    def code_answers_dataframe(
        self,
        answers_df: pd.DataFrame,
        item_col: str = "item_id",
        raw_col: str = "raw",
        option_code_col: str = "option_code"
    ) -> pd.DataFrame:
        df = answers_df.copy()
        required_cols = {item_col, raw_col, option_code_col}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(f"answers_df must contain columns {sorted(required_cols)}; missing: {sorted(missing)}")

        rows = []
        for _, row in df.iterrows():
            rows.append(
                self.code_answer_record(
                    {
                        "item_id": row[item_col],
                        "raw": row[raw_col],
                        "option_code": row[option_code_col],
                    }
                )
            )
        return pd.DataFrame(rows)


if __name__ == "__main__":
    workbook = Path("/home/user/workspace/space_files/collection_5a65eee3-bfc1-461b-8b1f-0d7c0fc032b4/939bf41e-fc2d-49f9-bac7-6c125711f45a/scoring_workbook_full_questions_v2-1.xlsx")
    engine = CodingEngine(workbook)

    demo_answers = {
        "FA1": {"item_id": "FA1", "raw": None, "option_code": 3},
        "FA2": {"item_id": "FA2", "raw": None, "option_code": 2},
        "FA3": {"item_id": "FA3", "raw": 4, "option_code": None},
        "FH1": {"item_id": "FH1", "raw": 2, "option_code": None},
        "PA2": {"item_id": "PA2", "raw": 3, "option_code": None},
    }

    coded = engine.code_answers_dict(demo_answers)
    print(coded.to_string(index=False))
