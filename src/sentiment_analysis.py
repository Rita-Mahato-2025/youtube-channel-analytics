"""
Phase 4 — Analysis
===================
1. Sentiment analysis on comments_clean.csv (VADER lexicon-based)
2. Engagement & trend analysis on master_video.csv + daily_channel.csv
3. Chart generation (PNG, for the PDF exec summary)
4. Dashboard data export (JSON, for the React dashboard artifact)

Outputs -> ./output/
    comments_sentiment.csv
    video_analysis.csv          (master_video + sentiment rollup per video)
    summary_stats.json          (headline numbers used in both deliverables)
    charts/*.png
    dashboard_data.json         (compact payload for the React dashboard)
"""

import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from pathlib import Path

OUT = Path("output")
CHARTS = OUT / "charts"
CHARTS.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "axes.edgecolor": "#333333",
    "axes.grid": True,
    "grid.color": "#e5e5e5",
    "grid.linewidth": 0.6,
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.titleweight": "bold",
})
ACCENT = "#2E5EAA"
ACCENT2 = "#D9822B"
ACCENT3 = "#4E9E5B"
ACCENT4 = "#B23A48"

# ---------------------------------------------------------------------------
# Load cleaned Phase 3 outputs
# ---------------------------------------------------------------------------

master_video = pd.read_csv("master_video.csv", parse_dates=["published_at"])
daily_channel = pd.read_csv("daily_channel.csv", parse_dates=["date"])
geography = pd.read_csv("geography_clean.csv")
traffic_sources = pd.read_csv("traffic_sources_clean.csv")
comments = pd.read_csv("comments_clean.csv", parse_dates=["published_at"])

for c in ["video_id"]:
    master_video[c] = master_video[c].astype(str)
    comments[c] = comments[c].astype(str)


# ---------------------------------------------------------------------------
# 1. Sentiment analysis on comments
# ---------------------------------------------------------------------------

analyzer = SentimentIntensityAnalyzer()

def score_sentiment(text):
    if pd.isna(text) or not str(text).strip():
        return pd.Series({"compound": 0.0, "label": "neutral"})
    s = analyzer.polarity_scores(str(text))
    compound = s["compound"]
    if compound >= 0.05:
        label = "positive"
    elif compound <= -0.05:
        label = "negative"
    else:
        label = "neutral"
    return pd.Series({"compound": compound, "label": label})

sentiment_scores = comments["text"].apply(score_sentiment)
comments_sentiment = pd.concat([comments, sentiment_scores], axis=1)
comments_sentiment.to_csv(OUT / "comments_sentiment.csv", index=False)

sentiment_counts = comments_sentiment["label"].value_counts()
sentiment_pct = (sentiment_counts / len(comments_sentiment) * 100).round(1)

# per-video rollup
video_sentiment = (
    comments_sentiment.groupby("video_id")
    .agg(
        n_comments_scored=("compound", "size"),
        avg_compound=("compound", "mean"),
        pct_positive=("label", lambda s: (s == "positive").mean() * 100),
        pct_negative=("label", lambda s: (s == "negative").mean() * 100),
    )
    .reset_index()
)


# ---------------------------------------------------------------------------
# 2. Engagement & trend analysis
# ---------------------------------------------------------------------------

video_analysis = master_video.merge(video_sentiment, on="video_id", how="left")
video_analysis.to_csv(OUT / "video_analysis.csv", index=False)

# Correlations of interest
corr_duration_engagement = master_video["duration_seconds"].corr(master_video["engagement_rate"])
corr_duration_views = master_video["duration_seconds"].corr(master_video["views"])
corr_recency_views_per_day = master_video["days_since_publish"].corr(master_video["views_per_day"])

top5_engagement = master_video.nlargest(5, "engagement_rate")[["video_id", "title", "engagement_rate", "views", "likes", "comments"]]
top5_views = master_video.nlargest(5, "views")[["video_id", "title", "views", "engagement_rate"]]
bottom5_engagement = master_video.nsmallest(5, "engagement_rate")[["video_id", "title", "engagement_rate", "views"]]

# category performance
YOUTUBE_CATEGORY_NAMES = {
    19: "Travel & Events", 22: "People & Blogs", 24: "Entertainment",
    25: "News & Politics", 27: "Education", 28: "Science & Technology",
    10: "Music", 17: "Sports", 20: "Gaming", 23: "Comedy", 26: "Howto & Style",
}
master_video["category_name"] = master_video["category_id"].map(YOUTUBE_CATEGORY_NAMES).fillna(master_video["category_id"].astype(str))

cat_perf = (
    master_video.groupby(["category_id", "category_name"])
    .agg(n_videos=("video_id", "size"), avg_views=("views", "mean"), avg_engagement=("engagement_rate", "mean"))
    .reset_index()
    .sort_values("avg_views", ascending=False)
)
cat_perf_reliable = cat_perf[cat_perf["n_videos"] >= 3].sort_values("avg_views", ascending=False)

# publish cadence: videos per month
master_video["publish_month"] = master_video["published_at"].dt.to_period("M").astype(str)
cadence = master_video.groupby("publish_month").size()

# daily channel trend: last 90 days vs prior period, growth
daily_channel_sorted = daily_channel.sort_values("date")
last_90 = daily_channel_sorted.tail(90)
prior_90 = daily_channel_sorted.iloc[-180:-90] if len(daily_channel_sorted) >= 180 else daily_channel_sorted.head(0)
views_last_90 = last_90["views"].sum()
views_prior_90 = prior_90["views"].sum() if len(prior_90) else np.nan
pct_change_90 = ((views_last_90 - views_prior_90) / views_prior_90 * 100) if views_prior_90 else np.nan

total_subs_gained = daily_channel["subscribersGained"].sum()
total_subs_lost = daily_channel["subscribersLost"].sum()
net_subs = total_subs_gained - total_subs_lost


# ---------------------------------------------------------------------------
# 3. Charts
# ---------------------------------------------------------------------------

# 3a. Daily views trend with 7-day rolling avg
fig, ax = plt.subplots(figsize=(9, 4))
plot_df = daily_channel_sorted[daily_channel_sorted["date"] >= daily_channel_sorted["date"].max() - pd.Timedelta(days=365)]
ax.bar(plot_df["date"], plot_df["views"], color=ACCENT, alpha=0.25, width=1, label="Daily views")
ax.plot(plot_df["date"], plot_df["views_7d_avg"], color=ACCENT, linewidth=2, label="7-day avg")
ax.set_title("Daily Channel Views — Last 12 Months")
ax.set_ylabel("Views")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
ax.legend(frameon=False)
fig.autofmt_xdate()
fig.tight_layout()
fig.savefig(CHARTS / "daily_views_trend.png", dpi=150)
plt.close(fig)

# 3b. Engagement rate distribution
fig, ax = plt.subplots(figsize=(6, 4))
ax.hist(master_video["engagement_rate"] * 100, bins=20, color=ACCENT2, edgecolor="white")
ax.axvline(master_video["engagement_rate"].mean() * 100, color=ACCENT4, linestyle="--", linewidth=1.5, label="Mean")
ax.set_title("Engagement Rate Distribution")
ax.set_xlabel("Engagement rate (%)")
ax.set_ylabel("Number of videos")
ax.legend(frameon=False)
fig.tight_layout()
fig.savefig(CHARTS / "engagement_distribution.png", dpi=150)
plt.close(fig)

# 3c. Top 10 videos by views
top10 = master_video.nlargest(10, "views").sort_values("views")
fig, ax = plt.subplots(figsize=(8, 5))
labels = [t[:35] + ("…" if len(t) > 35 else "") for t in top10["title"]]
ax.barh(labels, top10["views"], color=ACCENT3)
ax.set_title("Top 10 Videos by Views")
ax.set_xlabel("Views")
fig.tight_layout()
fig.savefig(CHARTS / "top10_views.png", dpi=150)
plt.close(fig)

# 3d. Geography (top 10 countries)
geo_top = geography.nlargest(10, "views")
fig, ax = plt.subplots(figsize=(6, 4))
ax.bar(geo_top["country"], geo_top["views"], color=ACCENT)
ax.set_title("Views by Country (Top 10)")
ax.set_ylabel("Views")
fig.tight_layout()
fig.savefig(CHARTS / "geography_top10.png", dpi=150)
plt.close(fig)

# 3e. Traffic sources pie
fig, ax = plt.subplots(figsize=(6, 6))
ts_sorted = traffic_sources.sort_values("views", ascending=False)
colors = plt.cm.Set2(np.linspace(0, 1, len(ts_sorted)))
ax.pie(ts_sorted["views"], labels=ts_sorted["insightTrafficSourceType"], autopct="%1.0f%%", colors=colors, textprops={"fontsize": 8})
ax.set_title("Views by Traffic Source")
fig.tight_layout()
fig.savefig(CHARTS / "traffic_sources_pie.png", dpi=150)
plt.close(fig)

# 3f. Sentiment breakdown
fig, ax = plt.subplots(figsize=(5, 4))
order = ["positive", "neutral", "negative"]
colors_map = {"positive": ACCENT3, "neutral": "#999999", "negative": ACCENT4}
vals = [sentiment_counts.get(k, 0) for k in order]
ax.bar(order, vals, color=[colors_map[k] for k in order])
ax.set_title("Comment Sentiment Breakdown")
ax.set_ylabel("Number of comments")
fig.tight_layout()
fig.savefig(CHARTS / "sentiment_breakdown.png", dpi=150)
plt.close(fig)

# 3g. Duration vs engagement scatter
fig, ax = plt.subplots(figsize=(6, 4.5))
ax.scatter(master_video["duration_minutes"], master_video["engagement_rate"] * 100, color=ACCENT, alpha=0.7, edgecolor="white")
ax.set_title("Video Duration vs. Engagement Rate")
ax.set_xlabel("Duration (minutes)")
ax.set_ylabel("Engagement rate (%)")
fig.tight_layout()
fig.savefig(CHARTS / "duration_vs_engagement.png", dpi=150)
plt.close(fig)


# ---------------------------------------------------------------------------
# 4. Summary stats (shared by PDF + dashboard)
# ---------------------------------------------------------------------------

summary = {
    "n_videos": int(len(master_video)),
    "total_views": int(master_video["views"].sum()),
    "total_likes": int(master_video["likes"].sum()),
    "total_comments_metric": int(master_video["comments"].sum()),
    "avg_engagement_rate_pct": round(master_video["engagement_rate"].mean() * 100, 2),
    "median_engagement_rate_pct": round(master_video["engagement_rate"].median() * 100, 2),
    "avg_views_per_day": round(master_video["views_per_day"].mean(), 3),
    "avg_duration_minutes": round(master_video["duration_minutes"].mean(), 2),
    "corr_duration_engagement": round(float(corr_duration_engagement), 3),
    "corr_duration_views": round(float(corr_duration_views), 3),
    "corr_recency_views_per_day": round(float(corr_recency_views_per_day), 3),
    "date_range_daily": [str(daily_channel["date"].min().date()), str(daily_channel["date"].max().date())],
    "views_last_90d": int(views_last_90),
    "views_prior_90d": (int(views_prior_90) if not np.isnan(views_prior_90) else None),
    "pct_change_90d": (round(float(pct_change_90), 1) if not np.isnan(pct_change_90) else None),
    "total_subs_gained": int(total_subs_gained),
    "total_subs_lost": int(total_subs_lost),
    "net_subs": int(net_subs),
    "n_comments": int(len(comments_sentiment)),
    "sentiment_counts": {k: int(v) for k, v in sentiment_counts.items()},
    "sentiment_pct": {k: float(v) for k, v in sentiment_pct.items()},
    "top5_engagement": top5_engagement.to_dict(orient="records"),
    "top5_views": top5_views.to_dict(orient="records"),
    "bottom5_engagement": bottom5_engagement.to_dict(orient="records"),
    "top_country": geography.iloc[0]["country"],
    "top_country_pct": float(geography.iloc[0]["pct_of_total_views"]),
    "top_traffic_source": traffic_sources.iloc[0]["insightTrafficSourceType"],
    "top_traffic_source_pct": float(traffic_sources.iloc[0]["pct_of_total_views"]),
    "top_category": {
        "category_id": int(cat_perf_reliable.iloc[0]["category_id"]),
        "category_name": cat_perf_reliable.iloc[0]["category_name"],
        "avg_views": round(float(cat_perf_reliable.iloc[0]["avg_views"]), 1),
        "n_videos": int(cat_perf_reliable.iloc[0]["n_videos"]),
    },
    "category_breakdown": cat_perf.to_dict(orient="records"),
}

with open(OUT / "summary_stats.json", "w") as f:
    json.dump(summary, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# 5. Dashboard payload (compact JSON for the React artifact)
# ---------------------------------------------------------------------------

# weekly aggregation keeps the dashboard payload light and the trend readable
weekly = (
    daily_channel_sorted.set_index("date")
    .resample("W")
    .agg(views=("views", "sum"), subscribersGained=("subscribersGained", "sum"), subscribersLost=("subscribersLost", "sum"))
    .reset_index()
)
weekly["date"] = weekly["date"].dt.strftime("%Y-%m-%d")
daily_payload = weekly

video_payload = master_video[[
    "video_id", "title", "published_at", "category_id", "category_name",
    "duration_minutes", "views", "likes", "comments", "engagement_rate", "views_per_day",
]].copy()
video_payload["published_at"] = video_payload["published_at"].dt.strftime("%Y-%m-%d")
video_payload["engagement_rate_pct"] = (video_payload["engagement_rate"] * 100).round(2)
video_payload = video_payload.drop(columns=["engagement_rate"])

comments_payload = comments_sentiment[["video_id", "text", "like_count", "published_at", "compound", "label"]].copy()
comments_payload["published_at"] = comments_payload["published_at"].dt.strftime("%Y-%m-%d")
comments_payload["text"] = comments_payload["text"].astype(str).str.slice(0, 240)

dashboard_data = {
    "summary": summary,
    "daily": daily_payload.to_dict(orient="records"),
    "videos": video_payload.to_dict(orient="records"),
    "comments": comments_payload.to_dict(orient="records"),
    "geography": geography.to_dict(orient="records"),
    "traffic_sources": traffic_sources.to_dict(orient="records"),
    "category_breakdown": cat_perf.to_dict(orient="records"),
}

with open(OUT / "dashboard_data.json", "w", encoding="utf-8") as f:
    json.dump(dashboard_data, f, default=str, ensure_ascii=False)

print("Done.")
print(json.dumps(summary, indent=2, default=str))
