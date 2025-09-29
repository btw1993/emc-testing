#%%
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd

def summarize_xyz(  data_dir: str | Path = "DATA",
                    pattern: str = "*.csv",
                    out_csv: str = "summary.csv",
                    ) -> pd.DataFrame:

    data_dir = Path(data_dir)
    rows: list[dict[str, float | str]] = []

    for f in sorted(data_dir.glob(pattern)):
        # Load only the expected columns; fail fast if missing
        try:
            df = pd.read_csv(f, usecols=["X", "Y", "Z"])
        except Exception as e:
            print(f"Skipping {f.name}: {e}")
            continue

        # Ensure floats and drop rows where all X,Y,Z are NaN
        df = df.astype(float)
        df = df.dropna(how="all", subset=["X", "Y", "Z"])

        if df.empty:
            print(f"Skipping {f.name}: no valid X/Y/Z data")
            continue

        counts = df[["X", "Y", "Z"]].count()
        means = df[["X", "Y", "Z"]].mean()
        stds = df[["X", "Y", "Z"]].std(ddof=1)  # sample std

        # Only report std if there’s more than one value; else NaN
        xstd = stds["X"] if counts["X"] > 1 else np.nan
        ystd = stds["Y"] if counts["Y"] > 1 else np.nan
        zstd = stds["Z"] if counts["Z"] > 1 else np.nan

        rows.append({
            "Name": f.name,
            "X": means["X"],
            "Y": means["Y"],
            "Z": means["Z"],
            "xstd": xstd,
            "ystd": ystd,
            "zstd": zstd,
        })

    summary = pd.DataFrame(rows, columns=["Name", "X", "Y", "Z", "xstd", "ystd", "zstd"])
    summary.to_csv(out_csv, index=False)
    print(f"Wrote {len(summary)} rows to {out_csv}")
    return summary

#%%
summarize_xyz()
# %%
