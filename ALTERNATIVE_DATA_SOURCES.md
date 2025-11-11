# Alternative Data Sources for ESG Sentiment

Since Twitter API has limitations (7-day history, rate limits), here are production-ready alternatives:

---

## Recommended: Free & Unlimited Options

### 1. GDELT Project (Best for ESG News)

**Global Database of Events, Language, and Tone**

```bash
pip install gdeltdoc
```

```python
from gdeltdoc import GdeltDoc, Filters

# Initialize
gd = GdeltDoc()

# Search ESG news for specific stock
f = Filters(
    keyword="Tesla AND (ESG OR sustainability OR carbon)",
    start_date="2024-01-01",
    end_date="2024-12-31",
    num_records=250
)

articles = gd.article_search(f)

# Process articles
for article in articles:
    print(f"Date: {article['seendate']}")
    print(f"Title: {article['title']}")
    print(f"URL: {article['url']}")
    print(f"Tone: {article['tone']}")  # Sentiment score
```

**Advantages**:
- ✅ **Completely free**
- ✅ **Unlimited historical access**
- ✅ Global news coverage (100+ countries)
- ✅ Real-time updates (15-minute delay)
- ✅ Built-in sentiment scores
- ✅ Perfect for ESG events

**Integration with Your System**:
```python
# Replace TwitterFetcher with GDELTFetcher
class GDELTFetcher:
    def fetch_news_for_event(self, ticker, event_date, keywords, days_before=3, days_after=7):
        from gdeltdoc import GdeltDoc, Filters
        from datetime import timedelta

        gd = GdeltDoc()

        start = (event_date - timedelta(days=days_before)).strftime('%Y-%m-%d')
        end = (event_date + timedelta(days=days_after)).strftime('%Y-%m-%d')

        # Build search query
        keyword_str = f"{ticker} AND ({' OR '.join(keywords)})"

        f = Filters(
            keyword=keyword_str,
            start_date=start,
            end_date=end,
            num_records=100
        )

        articles = gd.article_search(f)
        return self._process_articles(articles)
```

---

### 2. Reddit API (Best for Retail Sentiment)

**Reddit has generous free API access**

```bash
pip install praw
```

```python
import praw

# Free API setup (get credentials at reddit.com/prefs/apps)
reddit = praw.Reddit(
    client_id='YOUR_CLIENT_ID',
    client_secret='YOUR_SECRET',
    user_agent='ESG Research Bot 1.0'
)

# Search ESG discussions
def fetch_reddit_sentiment(ticker, keywords, limit=100):
    subreddits = ['stocks', 'investing', 'wallstreetbets', 'ESG_Investing']

    posts = []
    for sub in subreddits:
        query = f"{ticker} {' '.join(keywords)}"
        for submission in reddit.subreddit(sub).search(query, limit=limit):
            posts.append({
                'date': datetime.fromtimestamp(submission.created_utc),
                'title': submission.title,
                'text': submission.selftext,
                'score': submission.score,
                'num_comments': submission.num_comments
            })

    return pd.DataFrame(posts)
```

**Advantages**:
- ✅ **Free unlimited access**
- ✅ **No rate limits** (within reason)
- ✅ Historical data available
- ✅ Rich discussion threads
- ✅ Retail investor sentiment

---

### 3. NewsAPI.org (Quick Setup)

```bash
pip install newsapi-python
```

```python
from newsapi import NewsApiClient

newsapi = NewsApiClient(api_key='YOUR_FREE_KEY')

# Free tier: 100 requests/day, 1 month history
articles = newsapi.get_everything(
    q=f'{ticker} AND (ESG OR sustainability)',
    from_param='2024-11-01',
    to='2024-11-30',
    language='en',
    sort_by='relevancy'
)

for article in articles['articles']:
    print(article['title'])
    print(article['description'])
    print(article['publishedAt'])
```

**Advantages**:
- ✅ Free tier available
- ✅ Easy setup (5 minutes)
- ✅ Good news coverage
- ⚠️ Limited to 1 month history (free tier)

---

## Pre-Collected Datasets

### HuggingFace Financial Datasets

```python
from datasets import load_dataset

# Load pre-labeled financial sentiment
dataset = load_dataset("zeroshot/twitter-financial-news-sentiment")

# Load Financial PhraseBank (4,840 sentences)
dataset = load_dataset("financial_phrasebank", "sentences_allagree")

# Use for training/validation
for example in dataset['train']:
    print(example['sentence'])
    print(example['label'])  # positive/negative/neutral
```

---

## Hybrid Strategy (Recommended)

**Combine multiple free sources for robust ESG sentiment**:

```python
class HybridSentimentFetcher:
    def __init__(self):
        self.gdelt = GdeltDoc()
        self.reddit = praw.Reddit(...)
        # Keep Twitter for live data (last 7 days)
        self.twitter = TwitterFetcher(use_mock=False) if has_twitter else None

    def fetch_esg_sentiment(self, ticker, event_date, keywords):
        """
        Fetch from multiple sources and aggregate
        """
        sentiment_data = []

        # 1. GDELT for news (best for ESG events)
        news_articles = self._fetch_gdelt_news(ticker, event_date, keywords)
        sentiment_data.extend(news_articles)

        # 2. Reddit for retail sentiment
        reddit_posts = self._fetch_reddit_posts(ticker, event_date, keywords)
        sentiment_data.extend(reddit_posts)

        # 3. Twitter for very recent events (optional)
        if self.twitter and (datetime.now() - event_date).days <= 7:
            tweets = self.twitter.fetch_tweets_for_event(...)
            sentiment_data.extend(tweets)

        # Aggregate and return
        return self._aggregate_sentiment(sentiment_data)
```

---

## Cost Comparison

| Source | Cost | Historical Access | Rate Limits | Best For |
|--------|------|-------------------|-------------|----------|
| **GDELT** | Free | ✅ Unlimited | Generous | ESG news |
| **Reddit** | Free | ✅ Years | Generous | Retail sentiment |
| **NewsAPI** | Free | ⚠️ 1 month | 100/day | Quick setup |
| **Twitter Free** | Free | ❌ 7 days | Very strict | Live only |
| **Twitter Basic** | $100/mo | ⚠️ 30 days | 10K/mo | Recent backtests |
| **Alpha Vantage** | $50/mo | ✅ Years | Varies | News sentiment |

---

## Implementation Priority

**Phase 1: Replace Twitter with GDELT** (1-2 hours)
```bash
pip install gdeltdoc
# Create src/data/gdelt_fetcher.py
# Update run_production.py to use GDELT
```

**Phase 2: Add Reddit** (1-2 hours)
```bash
pip install praw
# Create src/data/reddit_fetcher.py
# Aggregate with GDELT data
```

**Phase 3: Keep Twitter for Live Trading** (optional)
```bash
# Use Twitter only for events < 7 days old
# Use GDELT/Reddit for backtesting
```

---

## Quick Start: GDELT Integration

```bash
# Install
pip install gdeltdoc

# Test
python << 'EOF'
from gdeltdoc import GdeltDoc, Filters

gd = GdeltDoc()

# Test ESG news search for Tesla
f = Filters(
    keyword="Tesla AND ESG",
    start_date="2024-10-01",
    end_date="2024-10-31",
    num_records=10
)

articles = gd.article_search(f)
print(f"Found {len(articles)} ESG news articles for Tesla")

for article in articles[:3]:
    print(f"\nTitle: {article['title']}")
    print(f"Date: {article['seendate']}")
    print(f"Tone: {article['tone']}")
EOF
```

---

**Recommendation**: Start with **GDELT** (free, unlimited, perfect for ESG) and add **Reddit** for additional retail sentiment. Keep your Twitter API for live trading (< 7 days) if you want real-time data.

This gives you the best of all worlds:
- ✅ Free historical data for backtesting
- ✅ Multiple sentiment sources
- ✅ No rate limit concerns
- ✅ Production-ready

---

**Last Updated**: November 10, 2025
