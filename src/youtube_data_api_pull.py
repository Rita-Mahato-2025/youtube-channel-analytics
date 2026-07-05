"""
YouTube Data API v3 pull — video metadata, stats, tags, thumbnails, comments.

Fills the gap left after the YouTube Analytics API pull (daily_metrics,
geography, traffic_sources, videos-from-analytics). This script gets the
per-video CONTENT data that only the Data API v3 exposes:
    - snippet: title, description, publishedAt, tags, thumbnails
    - statistics: viewCount, likeCount, commentCount
    - contentDetails: duration
    - commentThreads: actual comment text (for later NLP/sentiment)

Auth: uses a simple API key (Create Credentials > API key in the same GCP
project). OAuth is NOT required here because you're only reading public
data on your own public videos/comments. If you ever need private/unlisted
video data or comment moderation actions, switch to OAuth like you did for
Analytics.

Install:
    pip install google-api-python-client --break-system-packages

Fill in API_KEY and CHANNEL_ID below, then run:
    python youtube_data_api_pull.py
"""

import json
import csv
import time
import os
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ---------------------------------------------------------------------------
# CONFIG — fill these in
# ---------------------------------------------------------------------------
API_KEY = "AIzaSyB78n7Yd-v94AAQwDMSxC9I2HuX5f89jsM"
CHANNEL_ID = "UC_rKMuZRt8abUeuAid5SPmA"  # starts with "UC..."

RAW_DIR = "raw"
OUT_DIR = "processed"
os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

youtube = build("youtube", "v3", developerKey=API_KEY)


# ---------------------------------------------------------------------------
# 1. Get the channel's uploads playlist ID
# ---------------------------------------------------------------------------
def get_uploads_playlist_id(channel_id):
    resp = youtube.channels().list(
        part="contentDetails,snippet,statistics",
        id=channel_id
    ).execute()

    with open(f"{RAW_DIR}/channel_raw.json", "w") as f:
        json.dump(resp, f, indent=2)

    return resp["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]


# ---------------------------------------------------------------------------
# 2. Get all video IDs from the uploads playlist (paginated)
# ---------------------------------------------------------------------------
def get_all_video_ids(uploads_playlist_id):
    video_ids = []
    raw_pages = []
    page_token = None

    while True:
        resp = youtube.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_playlist_id,
            maxResults=50,
            pageToken=page_token
        ).execute()

        raw_pages.append(resp)
        video_ids.extend(
            item["contentDetails"]["videoId"] for item in resp["items"]
        )

        page_token = resp.get("nextPageToken")
        if not page_token:
            break
        time.sleep(0.1)  # be polite to the quota

    with open(f"{RAW_DIR}/playlist_items_raw.json", "w") as f:
        json.dump(raw_pages, f, indent=2)

    return video_ids


# ---------------------------------------------------------------------------
# 3. Fetch full video details in batches of 50
# ---------------------------------------------------------------------------
def get_video_details(video_ids):
    all_items = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        resp = youtube.videos().list(
            part="snippet,statistics,contentDetails,status",
            id=",".join(batch)
        ).execute()
        all_items.extend(resp["items"])
        time.sleep(0.1)

    with open(f"{RAW_DIR}/videos_raw.json", "w") as f:
        json.dump(all_items, f, indent=2)

    return all_items


def flatten_video_details(items):
    rows = []
    for v in items:
        snippet = v.get("snippet", {})
        stats = v.get("statistics", {})
        content = v.get("contentDetails", {})
        thumbnails = snippet.get("thumbnails", {})
        best_thumb = (
            thumbnails.get("maxres")
            or thumbnails.get("standard")
            or thumbnails.get("high")
            or thumbnails.get("medium")
            or thumbnails.get("default")
            or {}
        )

        rows.append({
            "video_id": v["id"],
            "title": snippet.get("title"),
            "description": snippet.get("description"),
            "published_at": snippet.get("publishedAt"),
            "tags": "|".join(snippet.get("tags", [])),
            "category_id": snippet.get("categoryId"),
            "duration_iso8601": content.get("duration"),
            "view_count": stats.get("viewCount"),
            "like_count": stats.get("likeCount"),
            "comment_count": stats.get("commentCount"),
            "thumbnail_url": best_thumb.get("url"),
            "privacy_status": v.get("status", {}).get("privacyStatus"),
        })
    return rows


def save_csv(rows, filename):
    if not rows:
        print(f"No rows to write for {filename}")
        return
    path = f"{OUT_DIR}/{filename}"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} rows -> {path}")


# ---------------------------------------------------------------------------
# 4. Fetch comments for each video
# ---------------------------------------------------------------------------
def get_comments_for_video(video_id):
    comments = []
    page_token = None

    while True:
        try:
            resp = youtube.commentThreads().list(
                part="snippet,replies",
                videoId=video_id,
                maxResults=100,
                pageToken=page_token,
                textFormat="plainText"
            ).execute()
        except HttpError as e:
            # comments disabled, video not found, etc.
            print(f"  skipping comments for {video_id}: {e.reason if hasattr(e, 'reason') else e}")
            break

        for item in resp.get("items", []):
            top = item["snippet"]["topLevelComment"]["snippet"]
            comments.append({
                "video_id": video_id,
                "comment_id": item["snippet"]["topLevelComment"]["id"],
                "parent_id": None,
                "author": top.get("authorDisplayName"),
                "text": top.get("textDisplay"),
                "like_count": top.get("likeCount"),
                "published_at": top.get("publishedAt"),
                "reply_count": item["snippet"].get("totalReplyCount", 0),
            })

            for reply in item.get("replies", {}).get("comments", []):
                rsnip = reply["snippet"]
                comments.append({
                    "video_id": video_id,
                    "comment_id": reply["id"],
                    "parent_id": item["snippet"]["topLevelComment"]["id"],
                    "author": rsnip.get("authorDisplayName"),
                    "text": rsnip.get("textDisplay"),
                    "like_count": rsnip.get("likeCount"),
                    "published_at": rsnip.get("publishedAt"),
                    "reply_count": 0,
                })

        page_token = resp.get("nextPageToken")
        if not page_token:
            break
        time.sleep(0.1)

    return comments


def get_all_comments(video_ids):
    all_comments = []
    raw_dump = {}
    for vid in video_ids:
        print(f"Fetching comments for {vid} ...")
        c = get_comments_for_video(vid)
        all_comments.extend(c)
        raw_dump[vid] = c

    with open(f"{RAW_DIR}/comments_raw.json", "w") as f:
        json.dump(raw_dump, f, indent=2)

    return all_comments


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("1. Getting uploads playlist ID...")
    uploads_id = get_uploads_playlist_id(CHANNEL_ID)

    print("2. Getting all video IDs...")
    video_ids = get_all_video_ids(uploads_id)
    print(f"   Found {len(video_ids)} videos.")

    print("3. Fetching video details (metadata, stats, tags, thumbnails)...")
    video_items = get_video_details(video_ids)
    video_rows = flatten_video_details(video_items)
    save_csv(video_rows, "video_metadata.csv")

    print("4. Fetching comments (this can take a while for large channels)...")
    comment_rows = get_all_comments(video_ids)
    save_csv(comment_rows, "comments.csv")

    print("Done. Raw JSON is in ./raw, processed CSVs are in ./processed.")
