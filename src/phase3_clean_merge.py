"""
Phase 3 — Clean & Merge
=======================
Inputs (raw exports), expected in the same folder as this script:
    video_metadata.csv   - per-video rich metadata (YouTube Data API export), 88 rows
    videos.csv           - per-video summary metrics (Analytics export), 107 rows
    daily_metrics.csv    - channel-level daily time series, 2019-08-01 -> present
    geography.csv        - channel-level totals broken out by country (one reporting window)
    traffic_sources.csv  - channel-level totals broken out by traffic source (one reporting window)
    comments.csv         - per-comment data, kept separate for later NLP work

NOTE ON SCOPE CHANGE vs. original Phase 3 plan:
    daily_metrics.csv, geography.csv, and traffic_sources.csv do NOT share a
    common key (no video_id in any of them, no date in geography/traffic_sources).
    They are channel-level, not per-video-per-day. Per user decision, these are
    cleaned and saved as THREE SEPARATE tables rather than force-merged.

Outputs (written to ./output/):
    master_video.csv        - video_metadata INNER JOIN videos on video_id
    daily_channel.csv       - cleaned daily_metrics.csv
    geography_clean.csv     - cleaned geography.csv
    traffic_sources_clean.csv - cleaned traffic_sources.csv
    comments_clean.csv      - cleaned comments.csv (dtypes standardized only)
"""

import re
import pandas as pd
import numpy as np
from pathlib import Path

IN_DIR = Path(".")
OUT_DIR = Path("output")
OUT_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_iso8601_duration(duration: str) -> float:
    """Convert an ISO 8601 duration string (e.g. 'PT4M13S', 'PT1H2M', 'PT46S')
    into total seconds. Returns NaN if unparseable or null."""
    if pd.isna(duration):
        return np.nan
    match = re.fullmatch(
        r"P(?:(?P<days>\d+)D)?T?(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?",
        duration.strip(),
    )
    if not match:
        return np.nan
    parts = match.groupdict(default="0")
    total = (
        int(parts["days"]) * 86400
        + int(parts["hours"]) * 3600
        + int(parts["minutes"]) * 60
        + int(parts["seconds"])
    )
    return float(total)


def standardize_video_id(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip()


def to_utc_datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, errors="coerce")


# ---------------------------------------------------------------------------
# 1. Load
# ---------------------------------------------------------------------------

video_metadata = pd.read_csv(IN_DIR / "video_metadata.csv")
videos = pd.read_csv(IN_DIR / "videos.csv")
daily_metrics = pd.read_csv(IN_DIR / "daily_metrics.csv")
geography = pd.read_csv(IN_DIR / "geography.csv")
traffic_sources = pd.read_csv(IN_DIR / "traffic_sources.csv")
comments = pd.read_csv(IN_DIR / "comments.csv")

print("Raw row counts:")
for name, df in [
    ("video_metadata", video_metadata),
    ("videos", videos),
    ("daily_metrics", daily_metrics),
    ("geography", geography),
    ("traffic_sources", traffic_sources),
    ("comments", comments),
]:
    print(f"  {name}: {len(df)}")


# ---------------------------------------------------------------------------
# 2. Standardize video_id + dates
# ---------------------------------------------------------------------------

video_metadata["video_id"] = standardize_video_id(video_metadata["video_id"])
videos["video_id"] = standardize_video_id(videos["video_id"])
comments["video_id"] = standardize_video_id(comments["video_id"])

video_metadata["published_at"] = to_utc_datetime(video_metadata["published_at"])
videos["published_at"] = to_utc_datetime(videos["published_at"])
comments["published_at"] = to_utc_datetime(comments["published_at"])
daily_metrics["day"] = to_utc_datetime(daily_metrics["day"])


# ---------------------------------------------------------------------------
# 3. duration_iso8601 -> seconds (video_metadata only; videos.csv already
#    has duration_seconds). We keep both for cross-validation.
# ---------------------------------------------------------------------------

video_metadata["duration_seconds_from_iso"] = video_metadata["duration_iso8601"].apply(
    parse_iso8601_duration
)


# ---------------------------------------------------------------------------
# 4. Merge video_metadata + videos -> master_video (inner join on video_id)
# ---------------------------------------------------------------------------

master_video = video_metadata.merge(
    videos,
    on="video_id",
    how="inner",
    suffixes=("_meta", "_analytics"),
)

# published_at / category_id are duplicated across both sources; keep one
# canonical version and drop the redundant analytics copy after sanity check.
mismatched_pub = (
    master_video["published_at_meta"] != master_video["published_at_analytics"]
).sum()
mismatched_cat = (
    master_video["category_id_meta"] != master_video["category_id_analytics"]
).sum()
print(f"\npublished_at mismatches between sources: {mismatched_pub}")
print(f"category_id mismatches between sources: {mismatched_cat}")

master_video = master_video.rename(
    columns={
        "published_at_meta": "published_at",
        "category_id_meta": "category_id",
        "title_meta": "title",
    }
)
master_video = master_video.drop(
    columns=["published_at_analytics", "category_id_analytics", "title_analytics"],
    errors="ignore",
)

# duration cross-check: flag any video where the two duration sources disagree
master_video["duration_mismatch"] = (
    master_video["duration_seconds_from_iso"] != master_video["duration_seconds"]
)
n_dur_mismatch = master_video["duration_mismatch"].sum()
print(f"duration_seconds mismatches (iso-parsed vs. videos.csv): {n_dur_mismatch}")


# ---------------------------------------------------------------------------
# 5. Derived features on master_video
# ---------------------------------------------------------------------------

now = pd.Timestamp.now(tz="UTC")
master_video["days_since_publish"] = (
    (now - master_video["published_at"]).dt.total_seconds() / 86400
).round(1)

# use the analytics view_count as canonical (guaranteed present for all 88 rows)
master_video["views_per_day"] = (
    master_video["views"] / master_video["days_since_publish"].replace(0, np.nan)
).round(3)

master_video["engagement_rate"] = (
    (master_video["likes"] + master_video["comments"]) / master_video["views"].replace(0, np.nan)
).round(5)

master_video["like_rate"] = (
    master_video["likes"] / master_video["views"].replace(0, np.nan)
).round(5)

master_video["comment_rate"] = (
    master_video["comments"] / master_video["views"].replace(0, np.nan)
).round(5)

master_video["duration_minutes"] = (master_video["duration_seconds"] / 60).round(2)


# ---------------------------------------------------------------------------
# 6. Clean the three channel-level tables (kept separate — no shared key)
# ---------------------------------------------------------------------------

daily_metrics = daily_metrics.rename(columns={"day": "date"}).sort_values("date")
daily_metrics["views_7d_avg"] = (
    daily_metrics["views"].rolling(7, min_periods=1).mean().round(2)
)

geography = geography.sort_values("views", ascending=False).reset_index(drop=True)
geography["pct_of_total_views"] = (
    geography["views"] / geography["views"].sum() * 100
).round(2)

traffic_sources = traffic_sources.sort_values("views", ascending=False).reset_index(drop=True)
traffic_sources["pct_of_total_views"] = (
    traffic_sources["views"] / traffic_sources["views"].sum() * 100
).round(2)


# ---------------------------------------------------------------------------
# 7. Clean comments.csv (kept separate for later sentiment/topic work)
# ---------------------------------------------------------------------------

comments["is_reply"] = comments["parent_id"].notna()


# ---------------------------------------------------------------------------
# 8. Write outputs
# ---------------------------------------------------------------------------

master_video.to_csv(OUT_DIR / "master_video.csv", index=False)
daily_metrics.to_csv(OUT_DIR / "daily_channel.csv", index=False)
geography.to_csv(OUT_DIR / "geography_clean.csv", index=False)
traffic_sources.to_csv(OUT_DIR / "traffic_sources_clean.csv", index=False)
comments.to_csv(OUT_DIR / "comments_clean.csv", index=False)

print("\nOutput row counts:")
print(f"  master_video.csv: {len(master_video)}")
print(f"  daily_channel.csv: {len(daily_metrics)}")
print(f"  geography_clean.csv: {len(geography)}")
print(f"  traffic_sources_clean.csv: {len(traffic_sources)}")
print(f"  comments_clean.csv: {len(comments)}")

print("\nmaster_video columns:")
print(list(master_video.columns))
