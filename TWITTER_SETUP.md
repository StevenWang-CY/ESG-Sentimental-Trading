# Twitter/X Integration Guide

This guide explains how to set up and use Twitter/X data for sentiment analysis in the ESG Event-Driven Alpha Strategy.

## Overview

The strategy now exclusively uses **Twitter/X** as the source for sentiment analysis. When ESG events are detected from SEC filings, the system fetches related tweets to analyze market reaction sentiment.

## Features

- **Real-time Twitter data** fetching using Twitter API v2
- **Mock data mode** for testing without API keys
- **ESG-focused** keyword filtering
- **Engagement metrics** analysis (retweets, likes, follower counts)
- **Temporal analysis** (pre-event vs post-event sentiment)

## Setup Instructions

### 1. Get Twitter API Access

To use real Twitter data, you need a Twitter Developer account and API v2 Bearer Token:

1. **Apply for Twitter Developer Access**
   - Go to: https://developer.twitter.com/
   - Create a developer account
   - Create a new project and app

2. **Get Your Bearer Token**
   - Navigate to your app's "Keys and tokens" section
   - Copy the "Bearer Token"
   - **Keep this secure - never commit it to git!**

3. **API Access Levels**
   - **Free Tier**: 500,000 tweets/month, search recent tweets (last 7 days)
   - **Basic Tier** ($100/month): 10M tweets/month, full archive search
   - **Academic Research**: Free for researchers, full archive access

### 2. Configure the Strategy

Edit `config/config.yaml`:

```yaml
data:
  twitter:
    bearer_token: "YOUR_TWITTER_BEARER_TOKEN_HERE"  # Paste your token here
    use_mock: false  # Set to false to use real API
    max_tweets_per_ticker: 100
    days_before_event: 3  # Days before event to collect tweets
    days_after_event: 7   # Days after event to collect tweets
    esg_keywords:
      - "ESG"
      - "climate"
      - "sustainability"
      - "carbon emissions"
      - "diversity"
      - "governance"
```

### 3. Install Dependencies

```bash
# Install tweepy for Twitter API
pip install tweepy

# Or install all requirements
pip install -r requirements.txt
```

## Usage

### Running with Real Twitter Data

Once configured with your Bearer Token:

```bash
# Run full pipeline with real Twitter data
python main.py --mode full --tickers AAPL TSLA XOM

# Specify custom date range
python main.py --mode full \
    --tickers AAPL MSFT GOOGL \
    --start-date 2023-01-01 \
    --end-date 2023-12-31
```

### Running with Mock Data (No API Key Required)

For testing without API access:

```bash
# Demo mode with mock Twitter data
python main.py --mode demo

# Full mode with mock data (set use_mock: true in config)
python main.py --mode full --tickers AAPL TSLA
```

## How It Works

### 1. Event Detection
```
SEC Filing → Event Detection → ESG Event Identified
```

### 2. Twitter Data Collection
```
For each detected event:
├── Search Twitter for: $TICKER + ESG Keywords
├── Time window: 3 days before → 7 days after event
├── Filter: Original tweets only (no retweets)
└── Collect: Tweet text, engagement metrics, timestamps
```

### 3. Sentiment Analysis
```
Tweets → FinBERT Analysis → Sentiment Features:
├── Intensity: Weighted average sentiment (-1 to +1)
├── Volume: Pre-event vs post-event tweet volume
├── Duration: Days sentiment stays elevated
├── Amplification: Virality score (retweets × followers)
└── Baseline Deviation: How unusual is the reaction?
```

### 4. Signal Generation
```
Event Features + Twitter Sentiment → ESG Event Shock Score → Trading Signal
```

## Twitter Data Structure

The system collects the following data for each tweet:

| Field | Description |
|-------|-------------|
| `timestamp` | When the tweet was posted |
| `text` | Tweet content |
| `user_followers` | Number of followers the user has |
| `retweets` | Number of retweets |
| `likes` | Number of likes |
| `ticker` | Stock ticker symbol |

## Example Output

```
2025-11-03 16:40:21 - INFO - Fetching Twitter data for AAPL around 2023-03-15...
2025-11-03 16:40:23 - INFO - Fetched 87 tweets for AAPL
2025-11-03 16:40:23 - INFO - Tweets analyzed: 87
2025-11-03 16:40:23 - INFO - Reaction intensity: -0.456
2025-11-03 16:40:23 - INFO - Volume ratio: 3.24
```

## Sentiment Features Explained

### Intensity
**Formula**: Weighted average of tweet sentiments
- Weight = (retweets + likes/10) × log(followers)
- Range: -1 (very negative) to +1 (very positive)
- **Use**: Measures the overall tone of the reaction

### Volume Ratio
**Formula**: Post-event tweets / Pre-event tweets
- Example: 3.0 means 3x more tweets after the event
- **Use**: Measures how much attention the event generated

### Duration
**Formula**: Number of days sentiment stays above threshold
- Threshold: |sentiment| > 0.2
- **Use**: Measures how long the reaction persists

### Amplification
**Formula**: Log-normalized virality score
- Virality = (retweets + likes/10) × log(followers)
- **Use**: Measures how widely the reaction spread

## Mock Data Mode

When `use_mock: true` or no API token is provided, the system generates realistic mock Twitter data:

- **Distribution**: 30% pre-event, 70% post-event tweets
- **Content**: ESG-themed templates (environmental, social, governance)
- **Engagement**: Log-normal follower distribution (realistic influencer mix)
- **Sentiment**: Varies by ticker to create diverse signals

This is perfect for:
- Testing the strategy without API costs
- Development and debugging
- Demonstrations

## Best Practices

### 1. Rate Limiting
```python
# The TwitterFetcher automatically handles rate limits
# Free tier: ~450 requests per 15 minutes
# System includes 1-second delays between requests
```

### 2. Keyword Strategy
```yaml
# Use specific ESG keywords to filter noise
esg_keywords:
  - "ESG"              # General ESG discussion
  - "climate change"   # Environmental focus
  - "carbon footprint" # Specific metrics
  - "diversity"        # Social focus
  - "board"            # Governance focus
```

### 3. Time Windows
```yaml
# Adjust based on your strategy
days_before_event: 3   # Baseline period
days_after_event: 7    # Reaction period

# For faster-moving events, reduce windows:
days_before_event: 1
days_after_event: 3
```

## Troubleshooting

### Issue: "No tweets found"
**Solutions**:
- Check if the ticker is popular on Twitter (small caps may have few tweets)
- Expand the time window (`days_before_event`, `days_after_event`)
- Remove some ESG keywords to broaden search
- Verify the event date is within the last 7 days (Free tier limitation)

### Issue: "Rate limit exceeded"
**Solutions**:
- Enable `wait_on_rate_limit=True` (already enabled by default)
- Reduce `max_tweets_per_ticker`
- Add delays between batch processing
- Consider upgrading to Basic tier

### Issue: "Authentication failed"
**Solutions**:
- Verify Bearer Token is correct (copy-paste carefully)
- Check token has not expired
- Ensure token has Read permissions
- Test token at: https://developer.twitter.com/en/portal/dashboard

## API Costs

### Free Tier
- **Cost**: $0
- **Limits**: 500K tweets/month, 7-day search window
- **Good for**: Testing, small-scale strategies, demo

### Basic Tier
- **Cost**: $100/month
- **Limits**: 10M tweets/month, full archive search
- **Good for**: Production strategies, backtesting

### Comparison

| Feature | Free | Basic |
|---------|------|-------|
| Monthly tweets | 500K | 10M |
| Search window | 7 days | Full archive |
| Rate limit | 450/15min | 450/15min |
| Cost | $0 | $100 |

## Advanced Configuration

### Custom Search Query

Modify `src/data/twitter_fetcher.py` to customize search logic:

```python
def _build_search_query(self, ticker: str, keywords: Optional[List[str]] = None) -> str:
    # Example: Add language filter, exclude specific terms
    query = f"(${ticker} OR #{ticker})"

    if keywords:
        keyword_str = " OR ".join(keywords)
        query += f" ({keyword_str})"

    # Exclude retweets, require English
    query += " -is:retweet lang:en"

    # Optional: Add more filters
    # query += " has:links"  # Only tweets with links
    # query += " -is:reply"  # Exclude replies

    return query
```

## Security Best Practices

1. **Never commit API keys to git**
   ```bash
   # Add to .gitignore
   echo "config/config.yaml" >> .gitignore
   ```

2. **Use environment variables (recommended)**
   ```bash
   export TWITTER_BEARER_TOKEN="your_token_here"
   ```

   Then in code:
   ```python
   import os
   bearer_token = os.getenv('TWITTER_BEARER_TOKEN')
   ```

3. **Rotate tokens regularly**
   - Regenerate Bearer Token every 90 days
   - Revoke old tokens after rotation

## Further Reading

- [Twitter API v2 Documentation](https://developer.twitter.com/en/docs/twitter-api)
- [Tweepy Documentation](https://docs.tweepy.org/en/stable/)
- [FinBERT Sentiment Analysis](https://arxiv.org/abs/1908.10063)

## Support

For issues or questions:
- Check the [main README](README.md)
- Review the [troubleshooting guide](QUICK_REFERENCE.md)
- Open an issue on GitHub
