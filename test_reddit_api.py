#!/usr/bin/env python3
"""Test Reddit API authentication"""
import praw
from dotenv import load_dotenv
import os

load_dotenv()

client_id = os.getenv('REDDIT_CLIENT_ID')
client_secret = os.getenv('REDDIT_CLIENT_SECRET')

print(f"Client ID: {client_id[:10]}..." if client_id else "NOT FOUND")
print(f"Client Secret: {client_secret[:10]}..." if client_secret else "NOT FOUND")

try:
    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent="ESG Test Bot 1.0"
    )
    
    # Test basic read-only access
    print("\nTesting Reddit API connection...")
    subreddit = reddit.subreddit('stocks')
    print(f"✓ Successfully connected to r/stocks")
    print(f"✓ Subreddit has {subreddit.subscribers} subscribers")
    
    # Test search
    print("\nTesting search functionality...")
    results = list(subreddit.search('AAPL', time_filter='week', limit=1))
    print(f"✓ Search returned {len(results)} result(s)")
    
    print("\n✅ Reddit API is working correctly!")
    
except Exception as e:
    print(f"\n❌ Reddit API Error: {e}")
    print(f"Error type: {type(e).__name__}")
