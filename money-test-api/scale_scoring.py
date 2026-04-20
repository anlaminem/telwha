import pandas as pd
from pathlib import Path
from typing import Union


class ScaleScoringEngine:
    def __init__(self, workbook_path: Union[str, Path], scale_sheet_name: str = "ScaleScores"):
        self.workbook_path = Path(workbook_path)
        self.scale_sheet_name = scale_sheet_name
        self.scale_items_df = self._load_scale_items()

    def _load_scale_items(self) -> pd.DataFrame:
        if not self.workbook_path.exists():
            raise FileNotFoundError(f"Workbook not found: {self.workbook_path}")

        scale_df = pd.read_excel(self.workbook_path, sheet_name=self.scale_sheet_name)
        required_cols = {"scale_name", "items"}
        missing_cols = required_cols - set(scale_df.columns)
        if missing_cols:
            raise ValueError(
                f"Sheet '{self.scale_sheet_name}' must contain columns {sorted(required_cols)}; "
                f"missing: {sorted(missing_cols)}"
            )

        rows = []
        for _, row in scale_df.iterrows():
            scale_name = str(row["scale_name"]).strip()
            items_raw = row["items"]

            if not scale_name or scale_name.lower() == "nan":
                continue

            if pd.isna(items_raw):
                continue

            item_ids = [
                item.strip().upper()
                for item in str(items_raw).split(",")
                if str(item).strip()
            ]

            for item_id in item_ids:
                rows.append({"scale_name": scale_name, "item_id": item_id})

        if not rows:
            raise ValueError(
                f"No scale items could be parsed from sheet '{self.scale_sheet_name}' in {self.workbook_path}"
            )

        out = pd.DataFrame(rows).drop_duplicates().reset_index(drop=True)
        return out

    def get_scale_item_map(self) -> pd.DataFrame:
        return self.scale_items_df.copy()

    def score_scales_from_coded_df(
        self,
        coded_df: pd.DataFrame,
        item_col: str = "item_id",
        score_col: str = "coded_0_100"
    ) -> pd.DataFrame:
        base = self.scale_items_df.copy()

        if coded_df is None or coded_df.empty:
            out = (
                base.groupby("scale_name", dropna=False)
                .agg(
                    score=("item_id", lambda _: float("nan")),
                    n_items_total=("item_id", "size"),
                    n_items_answered=("item_id", lambda s: 0),
                )
                .reset_index()
                .sort_values("scale_name")
                .reset_index(drop=True)
            )
            return out

        df = coded_df.copy()
        if item_col not in df.columns or score_col not in df.columns:
            raise ValueError(f"coded_df must contain '{item_col}' and '{score_col}' columns")

        df[item_col] = df[item_col].astype(str).str.strip().str.upper()
        df[score_col] = pd.to_numeric(df[score_col], errors="coerce")

        duplicate_ids = df.loc[df[item_col].duplicated(keep=False), item_col].dropna().unique().tolist()
        if duplicate_ids:
            raise ValueError(
                "coded_df contains duplicate item_id values; expected one coded score per item. "
                f"Duplicates: {duplicate_ids}"
            )

        merged = base.merge(
            df[[item_col, score_col]],
            how="left",
            left_on="item_id",
            right_on=item_col,
        )

        out = (
            merged.groupby("scale_name", dropna=False)
            .agg(
                score=(score_col, "mean"),
                n_items_total=("item_id", "size"),
                n_items_answered=(score_col, lambda s: int(s.notna().sum())),
            )
            .reset_index()
            .sort_values("scale_name")
            .reset_index(drop=True)
        )

        out["score"] = out["score"].round(2)
        return out