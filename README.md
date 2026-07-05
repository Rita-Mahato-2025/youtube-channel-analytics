# YouTube Channel Performance Analytics

An end-to-end analysis of a YouTube channel's video performance, audience engagement,
and comment sentiment — built on the YouTube Data API and YouTube Analytics API.

## 📊 What this project does

- Pulls video-level metrics (views, likes, comments, duration, category) via the
  YouTube Data API
- Pulls channel-level metrics (daily views, geography, traffic source, subscriber
  gain/loss) via the YouTube Analytics API
- Computes engagement rate, duration/engagement correlation, and recency effects
- Scores comment sentiment using VADER (lexicon-based sentiment analysis)
- Generates an executive summary report and an interactive dashboard

## 🔑 Key findings (88 videos analyzed)

- **14,739** total views, **12.06%** average engagement rate
- **+82.8%** view growth in the last 90 days vs. the prior 90
- **92.72%** of views come from a single country (India) — audience is concentrated
- **54.64%** of views come from YouTube Shorts — distribution depends on one surface
- **96.2%** of comments are positive (VADER sentiment, 106 comments scored)

See the full [Executive Summary](reports/executive_summary.pdf) for details.

## 🛠️ Tech stack

- Python (pandas, matplotlib, VADER/`vaderSentiment`)
- YouTube Data API v3
- YouTube Analytics API
- [Interactive dashboard link]

## 🚀 Getting started

\`\`\`bash
git clone https://github.com/<your-username>/youtube-channel-analytics.git
cd youtube-channel-analytics
pip install -r requirements.txt
\`\`\`

You'll need your own YouTube Data API key and OAuth credentials for the Analytics API.
Create a `.env` file:

\`\`\`
YOUTUBE_API_KEY=your_key_here
\`\`\`

Then run:

\`\`\`bash
python src/fetch_data.py
python src/analyze.py
\`\`\`

## 📁 Project structure

\`\`\`
├── src/            # data collection & analysis scripts
├── reports/        # generated executive summary
├── assets/charts/  # exported chart images
└── data/           # data notes (raw data not committed)
\`\`\`

## 📈 Live dashboard

[Interactive dashboard →](your-dashboard-link-here)

## 📄 License

MIT (or your choice)