"""Code templates for generating notebook cells.

Each function returns a Python code string that looks like something
a skilled data analyst would write in a Jupyter notebook.
"""
from __future__ import annotations

import json


def _plot_spec_runtime_guard() -> str:
    return '''try:
    emit_plot_spec
except NameError:
    def emit_plot_spec(*args, **kwargs):
        return None
'''


def load_dataset_code(filename: str, file_format: str = "csv") -> str:
    """Generate code to load a dataset."""
    if file_format in ("csv", "tsv"):
        sep = "\\t" if file_format == "tsv" else ","
        return f'''import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

df = pd.read_csv("{filename}"{f', sep="{sep}"' if file_format == "tsv" else ""})
print(f"Loaded {{len(df)}} rows x {{len(df.columns)}} columns")
df.head()'''
    elif file_format in ("xlsx", "xls"):
        return f'''import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

df = pd.read_excel("{filename}")
print(f"Loaded {{len(df)}} rows x {{len(df.columns)}} columns")
df.head()'''
    elif file_format == "json":
        return f'''import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

df = pd.read_json("{filename}")
print(f"Loaded {{len(df)}} rows x {{len(df.columns)}} columns")
df.head()'''
    elif file_format == "parquet":
        return f'''import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

df = pd.read_parquet("{filename}")
print(f"Loaded {{len(df)}} rows x {{len(df.columns)}} columns")
df.head()'''
    else:
        return f'''import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

df = pd.read_csv("{filename}")
print(f"Loaded {{len(df)}} rows x {{len(df.columns)}} columns")
df.head()'''


def inspect_dtypes_code() -> str:
    return '''print("Column types:")
print(df.dtypes)
print(f"\\nShape: {df.shape}")'''


def inspect_describe_code() -> str:
    return '''df.describe(include="all").T'''


def inspect_missing_code() -> str:
    return '''missing = df.isnull().sum()
missing_pct = (missing / len(df) * 100).round(2)
missing_report = pd.DataFrame({"missing": missing, "pct": missing_pct})
missing_report = missing_report[missing_report["missing"] > 0].sort_values("pct", ascending=False)
if len(missing_report) > 0:
    print(f"{len(missing_report)} columns with missing values:")
    print(missing_report)
else:
    print("No missing values found!")'''


def parse_datetime_code(col: str, format_str: str | None = None) -> str:
    fmt_arg = f', format="{format_str}"' if format_str else ""
    return f'''df["{col}"] = pd.to_datetime(df["{col}"], errors="coerce"{fmt_arg})
n_nat = df["{col}"].isna().sum()
print(f"Parsed '{col}' as datetime. {{n_nat}} unparseable values (NaT)")
if n_nat > 0 and n_nat < 20:
    print("Bad rows:")
    print(df[df["{col}"].isna()])
df = df.sort_values("{col}").reset_index(drop=True)
print(f"Date range: {{df['{col}'].min()}} to {{df['{col}'].max()}}")'''


def handle_missing_ffill_code(col: str) -> str:
    return f'''print(f"Before: {{df['{col}'].isna().sum()}} missing values in '{col}'")
df["{col}"] = df["{col}"].ffill()
print(f"After forward-fill: {{df['{col}'].isna().sum()}} missing")'''


def handle_missing_drop_code(col: str) -> str:
    return f'''n_before = len(df)
df = df.dropna(subset=["{col}"])
print(f"Dropped {{n_before - len(df)}} rows with missing '{col}' ({{len(df)}} remaining)")'''


def handle_missing_interpolate_code(col: str) -> str:
    return f'''print(f"Before: {{df['{col}'].isna().sum()}} missing values in '{col}'")
df["{col}"] = df["{col}"].interpolate(method="linear")
print(f"After interpolation: {{df['{col}'].isna().sum()}} missing")'''


def plot_time_series_code(time_col: str, value_cols: list[str]) -> str:
    cols_str = json.dumps(value_cols)
    return _plot_spec_runtime_guard() + f'''fig, axes = plt.subplots(len({cols_str}), 1, figsize=(14, 3 * len({cols_str})), sharex=True)
if len({cols_str}) == 1:
    axes = [axes]
for ax, col in zip(axes, {cols_str}):
    ax.plot(df["{time_col}"], df[col], linewidth=0.8)
    ax.set_ylabel(col)
    ax.set_title(col)
    emit_plot_spec(dict(kind="plotly", mime_type="application/vnd.plotly.v1+json", title=col, caption=f"Time series for {{col}}", chart_family="line", semantic_intent="trend", x_axis_role="time", y_axis_role="measure", source=dict(data=[dict(type="scatter", mode="lines", name=col, x=df["{time_col}"].astype(str).tolist(), y=df[col].tolist())], layout=dict(title=col, xaxis=dict(title="{time_col}"), yaxis=dict(title=col)))))
axes[-1].set_xlabel("{time_col}")
plt.tight_layout()
plt.show()'''


def plot_distributions_code(numeric_cols: list[str]) -> str:
    cols_str = json.dumps(numeric_cols[:8])  # max 8 plots
    return _plot_spec_runtime_guard() + f'''cols = {cols_str}
n = len(cols)
ncols_plot = min(n, 4)
nrows_plot = (n + ncols_plot - 1) // ncols_plot
fig, axes = plt.subplots(nrows_plot, ncols_plot, figsize=(4 * ncols_plot, 3 * nrows_plot))
axes = np.array(axes).flatten() if n > 1 else [axes]
for i, col in enumerate(cols):
    axes[i].hist(df[col].dropna(), bins=30, edgecolor="black", alpha=0.7)
    axes[i].set_title(col)
    axes[i].axvline(df[col].mean(), color="red", linestyle="--", label="mean")
    axes[i].legend(fontsize=8)
    emit_plot_spec(dict(kind="plotly", mime_type="application/vnd.plotly.v1+json", title=col, caption=f"Distribution for {{col}}", chart_family="histogram", semantic_intent="distribution", x_axis_role="numeric", y_axis_role="count", source=dict(data=[dict(type="histogram", name=col, x=df[col].dropna().tolist())], layout=dict(title=col, xaxis=dict(title=col), yaxis=dict(title="Count")))))
for j in range(i + 1, len(axes)):
    axes[j].set_visible(False)
plt.tight_layout()
plt.show()'''


def seasonality_code(time_col: str, value_col: str) -> str:
    return _plot_spec_runtime_guard() + f'''from scipy import stats

df["_hour"] = df["{time_col}"].dt.hour
df["_dow"] = df["{time_col}"].dt.day_name()
df["_month"] = df["{time_col}"].dt.month

fig, axes = plt.subplots(1, 3, figsize=(16, 4))

# Hourly pattern
if df["_hour"].nunique() > 1:
    hourly = df.groupby("_hour")["{value_col}"].mean()
    axes[0].bar(hourly.index, hourly.values)
    axes[0].set_title("Avg by Hour")
    axes[0].set_xlabel("Hour")
    emit_plot_spec(dict(kind="plotly", mime_type="application/vnd.plotly.v1+json", title="Avg by Hour", caption="Average by hour of day", chart_family="bar", semantic_intent="comparison", x_axis_role="ordinal", y_axis_role="measure", source=dict(data=[dict(type="bar", name="{value_col}", x=hourly.index.astype(int).tolist(), y=hourly.values.tolist())], layout=dict(title="Avg by Hour", xaxis=dict(title="Hour"), yaxis=dict(title="Average {value_col}")))))

# Day of week pattern
if df["_dow"].nunique() > 1:
    dow_order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    dow_data = df.groupby("_dow")["{value_col}"].mean().reindex(dow_order).dropna()
    axes[1].bar(range(len(dow_data)), dow_data.values)
    axes[1].set_xticks(range(len(dow_data)))
    axes[1].set_xticklabels([d[:3] for d in dow_data.index], rotation=45)
    axes[1].set_title("Avg by Day of Week")
    emit_plot_spec(dict(kind="plotly", mime_type="application/vnd.plotly.v1+json", title="Avg by Day of Week", caption="Average by weekday", chart_family="bar", semantic_intent="comparison", x_axis_role="ordinal", y_axis_role="measure", source=dict(data=[dict(type="bar", name="{value_col}", x=dow_data.index.tolist(), y=dow_data.values.tolist())], layout=dict(title="Avg by Day of Week", xaxis=dict(title="Day"), yaxis=dict(title="Average {value_col}")))))

# Monthly pattern
if df["_month"].nunique() > 1:
    monthly = df.groupby("_month")["{value_col}"].mean()
    axes[2].bar(monthly.index, monthly.values)
    axes[2].set_title("Avg by Month")
    axes[2].set_xlabel("Month")
    emit_plot_spec(dict(kind="plotly", mime_type="application/vnd.plotly.v1+json", title="Avg by Month", caption="Average by month", chart_family="bar", semantic_intent="comparison", x_axis_role="ordinal", y_axis_role="measure", source=dict(data=[dict(type="bar", name="{value_col}", x=monthly.index.astype(int).tolist(), y=monthly.values.tolist())], layout=dict(title="Avg by Month", xaxis=dict(title="Month"), yaxis=dict(title="Average {value_col}")))))

plt.tight_layout()
plt.show()

# Clean up temp columns
df.drop(columns=["_hour", "_dow", "_month"], inplace=True, errors="ignore")'''


def correlation_code(numeric_cols: list[str]) -> str:
    cols_str = json.dumps(numeric_cols[:15])
    return _plot_spec_runtime_guard() + f'''corr = df[{cols_str}].corr()
fig, ax = plt.subplots(figsize=(10, 8))
im = ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)
ax.set_xticks(range(len(corr.columns)))
ax.set_yticks(range(len(corr.columns)))
ax.set_xticklabels(corr.columns, rotation=45, ha="right", fontsize=8)
ax.set_yticklabels(corr.columns, fontsize=8)
plt.colorbar(im, ax=ax)
ax.set_title("Correlation Matrix")
emit_plot_spec(dict(kind="plotly", mime_type="application/vnd.plotly.v1+json", title="Correlation Matrix", caption="Pairwise correlation heatmap", chart_family="heatmap", semantic_intent="matrix", x_axis_role="category", y_axis_role="category", source=dict(data=[dict(type="heatmap", name="Correlation", x=list(corr.columns), y=list(corr.index), z=corr.values.tolist(), colorscale="RdBu_r", zmin=-1, zmax=1)], layout=dict(title="Correlation Matrix", xaxis=dict(title="Variables"), yaxis=dict(title="Variables")))))
plt.tight_layout()
plt.show()

# Flag strong correlations
strong = []
for i in range(len(corr.columns)):
    for j in range(i+1, len(corr.columns)):
        r = corr.iloc[i, j]
        if abs(r) > 0.8:
            strong.append((corr.columns[i], corr.columns[j], round(r, 3)))
if strong:
    print("Strong correlations (|r| > 0.8):")
    for c1, c2, r in sorted(strong, key=lambda x: -abs(x[2])):
        print(f"  {{c1}} <-> {{c2}}: r={{r}}")
else:
    print("No strong correlations found (|r| > 0.8)")'''


def rolling_stats_code(time_col: str, value_col: str, window: int = 30) -> str:
    return _plot_spec_runtime_guard() + f'''rolling_mean = df["{value_col}"].rolling({window}, center=True).mean()
rolling_std = df["{value_col}"].rolling({window}, center=True).std()

fig, ax = plt.subplots(figsize=(14, 5))
ax.plot(df["{time_col}"], df["{value_col}"], alpha=0.3, label="Raw", linewidth=0.5)
ax.plot(df["{time_col}"], rolling_mean, label=f"{window}-pt Rolling Mean", color="red")
ax.fill_between(df["{time_col}"], rolling_mean - rolling_std, rolling_mean + rolling_std, alpha=0.2, color="red", label="\u00b11 Std")
ax.set_title(f"{value_col} \u2014 Rolling Statistics (window={window})")
ax.legend()
ax.set_xlabel("{time_col}")
emit_plot_spec(dict(kind="plotly", mime_type="application/vnd.plotly.v1+json", title="{value_col} Rolling Statistics", caption="Raw series with rolling mean and spread", chart_family="line", semantic_intent="trend", x_axis_role="time", y_axis_role="measure", source=dict(data=[dict(type="scatter", mode="lines", name="Raw", x=df["{time_col}"].astype(str).tolist(), y=df["{value_col}"].tolist()), dict(type="scatter", mode="lines", name=f"{window}-pt Rolling Mean", x=df["{time_col}"].astype(str).tolist(), y=rolling_mean.tolist())], layout=dict(title="{value_col} Rolling Statistics", xaxis=dict(title="{time_col}"), yaxis=dict(title="{value_col}")))))
plt.tight_layout()
plt.show()'''


def outlier_detection_code(value_col: str) -> str:
    return f'''Q1 = df["{value_col}"].quantile(0.25)
Q3 = df["{value_col}"].quantile(0.75)
IQR = Q3 - Q1
lower = Q1 - 1.5 * IQR
upper = Q3 + 1.5 * IQR
outliers = df[(df["{value_col}"] < lower) | (df["{value_col}"] > upper)]
print(f"Outliers in '{value_col}': {{len(outliers)}} ({{len(outliers)/len(df)*100:.1f}}%)")
print(f"Bounds: [{{lower:.2f}}, {{upper:.2f}}]")
if len(outliers) > 0 and len(outliers) <= 20:
    print(outliers[["{value_col}"]].describe())'''


def train_test_split_code(time_col: str, train_ratio: float = 0.8) -> str:
    return f'''split_idx = int(len(df) * {train_ratio})
train = df.iloc[:split_idx]
test = df.iloc[split_idx:]
print(f"Train: {{len(train)}} rows ({{df['{time_col}'].iloc[0]}} to {{df['{time_col}'].iloc[split_idx-1]}})")
print(f"Test:  {{len(test)}} rows ({{df['{time_col}'].iloc[split_idx]}} to {{df['{time_col}'].iloc[-1]}}")'''


def summary_markdown(findings: list[dict]) -> str:
    lines = [
        "---\n",
        "## EDA Summary\n",
        "| Phase | Finding |",
        "| --- | --- |",
    ]
    for f in findings:
        # Escape pipes in finding text for markdown table
        finding_text = f['finding'].replace("|", "\\|")
        lines.append(f"| **{f['phase']}** | {finding_text} |")
    lines.append("")
    return "\n".join(lines)
