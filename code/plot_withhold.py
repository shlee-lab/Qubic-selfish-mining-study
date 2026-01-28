import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FixedLocator

# ===== Match style with your hourly_validity_timeline plot =====
plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["hatch.linewidth"] = 2.6

# spacing constants (same as your other script)
LABEL_PAD = 10
TICK_PAD = 6

path = r"data\blocks-proof.csv"
df = pd.read_csv(path)

def parse_best_datetime_column(df: pd.DataFrame):
    candidates = [c for c in df.columns if any(k in c.lower() for k in ["time", "timestamp", "date", "utc"])]
    if not candidates:
        candidates = list(df.columns)

    best = None
    best_nonnull = -1
    best_dt = None

    for c in candidates:
        s = df[c]
        dt = None

        if pd.api.types.is_numeric_dtype(s):
            vals = pd.to_numeric(s, errors="coerce")
            finite = np.isfinite(vals.values)
            med = np.nanmedian(vals.values[finite]) if finite.any() else np.nan

            if np.isfinite(med):
                if med > 1e14:
                    dt = pd.to_datetime(vals, unit="ns", utc=True, errors="coerce")
                elif med > 1e12:
                    dt = pd.to_datetime(vals, unit="ms", utc=True, errors="coerce")
                elif med > 1e9:
                    dt = pd.to_datetime(vals, unit="s", utc=True, errors="coerce")
                else:
                    dt = pd.to_datetime(vals, utc=True, errors="coerce")
        else:
            dt = pd.to_datetime(s, utc=True, errors="coerce")

        nonnull = dt.notna().sum()
        if nonnull > best_nonnull:
            best_nonnull = nonnull
            best = c
            best_dt = dt

    return best, best_dt

def infer_is_orphan(df: pd.DataFrame):
    cols = [c for c in df.columns if any(k in c.lower() for k in ["orphan", "status", "main", "in_main", "chain"])]

    for c in cols:
        if "orphan" in c.lower():
            s = df[c]
            if pd.api.types.is_bool_dtype(s):
                return s.fillna(False)
            if pd.api.types.is_numeric_dtype(s):
                vals = pd.to_numeric(s, errors="coerce")
                uniq = set(vals.dropna().unique().tolist())
                if uniq.issubset({0, 1}):
                    return vals.fillna(0).astype(int).astype(bool)
            ss = s.astype(str).str.lower()
            return ss.str.contains("orphan") | ss.isin(["true", "t", "yes", "y", "1"])

    for c in cols:
        ss = df[c].astype(str).str.lower()
        if ss.str.contains("orphan").any():
            return ss.str.contains("orphan")

    return pd.Series([True] * len(df), index=df.index)

def infer_is_qubic(df: pd.DataFrame):
    for c in df.columns:
        cl = c.lower()
        if cl in ["is_qubic", "qubic"] and pd.api.types.is_bool_dtype(df[c]):
            return df[c].fillna(False)
        if "qubic" in cl and pd.api.types.is_bool_dtype(df[c]):
            return df[c].fillna(False)

    for c in df.columns:
        if any(k in c.lower() for k in ["miner", "pool", "source", "tag", "label", "attribution", "entity"]):
            ss = df[c].astype(str).str.lower()
            if ss.str.contains("qubic").any():
                return ss.str.contains("qubic")

    return pd.Series([True] * len(df), index=df.index)

_, dt = parse_best_datetime_column(df)
is_orphan = infer_is_orphan(df)
is_qubic = infer_is_qubic(df)

# ---- infer year from data ----
dt_valid = dt.dropna()
if len(dt_valid) > 0:
    in_jul_oct = dt_valid[(dt_valid.dt.month >= 7) & (dt_valid.dt.month <= 10)]
    if len(in_jul_oct) > 0:
        year_choice = int(in_jul_oct.dt.year.value_counts().idxmax())
    else:
        year_choice = int(dt_valid.dt.year.mode().iloc[0])
else:
    year_choice = 2025

# ---- DATA WINDOW: 7/30 ~ 10/21 (inclusive) ----
start_data = pd.Timestamp(year=year_choice, month=7, day=30, tz="UTC")
end_data_inclusive = pd.Timestamp(year=year_choice, month=10, day=20, tz="UTC")
end_data_exclusive = end_data_inclusive + pd.Timedelta(days=1)

mask = (
    is_qubic.astype(bool)
    & is_orphan.astype(bool)
    & dt.notna()
    & (dt >= start_data)
    & (dt < end_data_exclusive)
)
dt_f = dt[mask]

# Hourly counts in full data window
hourly = dt_f.dt.floor("H").value_counts().sort_index()

all_hours = pd.date_range(
    start=start_data,
    end=end_data_exclusive - pd.Timedelta(hours=1),
    freq="H",
    tz="UTC",
)
hourly = hourly.reindex(all_hours, fill_value=0).astype(int)

# STRICT ON/OFF: ON if >=1 orphan in that hour
on_bin = (hourly >= 1).astype(int)

# Contiguous ON segments
segments = []
idx = on_bin.index
v = on_bin.values
n = len(v)

i = 0
while i < n:
    if v[i] == 0:
        i += 1
        continue
    j = i
    while j < n and v[j] == 1:
        j += 1
    segments.append((idx[i], idx[j - 1] + pd.Timedelta(hours=1)))
    i = j

# ---- Plot ----
fig, ax = plt.subplots(figsize=(15, 4.2))

for a, b in segments:
    ax.axvspan(
        a.tz_convert(None).to_pydatetime(),
        b.tz_convert(None).to_pydatetime(),
        ymin=0, ymax=1,
        facecolor=(0, 0, 0, 0),   # transparent
        edgecolor="tab:blue",     # hatch color
        hatch="||||",             # vertical stripes
        linewidth=0.0,            # no border outline
        zorder=2,
    )

# keep full data window on x-axis (no cropping)
ax.set_xlim(
    start_data.tz_convert(None).to_pydatetime(),
    end_data_exclusive.tz_convert(None).to_pydatetime(),
)
ax.set_ylim(0, 1)

# ---- X-axis ticks ONLY: 8/04 ~ 10/20 weekly ----
tick_start = pd.Timestamp(year=year_choice, month=8, day=4, tz="UTC")
tick_end   = pd.Timestamp(year=year_choice, month=10, day=20, tz="UTC")
ticks = pd.date_range(tick_start, tick_end, freq="7D", tz="UTC")
ticks_naive = ticks.tz_convert(None).to_pydatetime()

ax.xaxis.set_major_locator(FixedLocator(mdates.date2num(ticks_naive)))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

# ---- Match label/tick styling with your other figure ----
ax.set_ylabel("Withholding state (binary)", fontsize=14, labelpad=LABEL_PAD)
ax.tick_params(axis="both", pad=TICK_PAD)

# y-axis: show only 0 and 1
ax.set_yticks([0, 1])
ax.set_yticklabels(["0", "1"])

# boxed frame
for spine in ax.spines.values():
    spine.set_visible(True)
    spine.set_linewidth(1.2)

fig.subplots_adjust(left=0.08, right=0.99, bottom=0.22, top=0.98) 

# ===== Export to PDF =====
out_pdf = r"fig/qubic_withhold_timeline.pdf"
fig.savefig(out_pdf, format="pdf", bbox_inches="tight")

plt.show()
print("Saved:", out_pdf)
