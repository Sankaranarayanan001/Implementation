"""Step 3 – dataset inspection."""
from __future__ import annotations

import pandas as pd

from app.services.common.checks import blank_mask, col_kind
from app.services.common.io_utils import jsonable, records


def inspect_dataframe(df: pd.DataFrame) -> dict:
    columns = []
    for c in df.columns:
        s = df[c]
        nb = ~blank_mask(s)
        columns.append({
            "name": c,
            "dtype": str(s.dtype),
            "semantic_kind": col_kind(df, c),
            "non_null": int(s.notna().sum()),
            "null": int(s.isna().sum()),
            "unique": int(s.nunique()),
            "samples": jsonable(s[nb].drop_duplicates().head(3).tolist()),
        })
    rnd = df.sample(min(5, len(df)), random_state=7) if len(df) else df
    return {
        "row_count": int(len(df)),
        "column_count": int(df.shape[1]),
        "normalized_mixed_columns": df.attrs.get("normalized", []),
        "columns": columns,
        "samples": {"head": records(df.head(5)), "random": records(rnd)},
    }
    
