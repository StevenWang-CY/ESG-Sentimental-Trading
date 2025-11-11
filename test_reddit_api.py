"""
Quick test script to verify Reddit API credentials
Run after setting up your REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in .env
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_reddit_connection():
    """Test Reddit API connection"""
    client_id = os.getenv('REDDIT_CLIENT_ID')
    client_secret = os.getenv('REDDIT_CLIENT_SECRET')
    user_agent = os.getenv('REDDIT_USER_AGENT', 'ESG Sentiment Trading Bot 1.0')

    print("=" * 60)
    print("Reddit API Connection Test")
    print("=" * 60)

    # Check if credentials are set
    if not client_id or client_id == 'your_client_id_here':
        print("❌ REDDIT_CLIENT_ID not set in .env file")
        print("   Please update .env with your Reddit app credentials")
        return False

    if not client_secret or client_secret == 'your_client_secret_here':
        print("❌ REDDIT_CLIENT_SECRET not set in .env file")
        print("   Please update .env with your Reddit app credentials")
        return False

    print(f"✓ Client ID: {client_id[:8]}...")
    print(f"✓ User Agent: {user_agent}")
    print()

    # Test connection
    try:
        import praw

        print("Connecting to Reddit API...")
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )

        # Test API call
        print("Testing API access...")
        subreddit = reddit.subreddit('stocks')

        # Fetch a few posts to verify access
        posts = list(subreddit.hot(limit=3))

        print()
        print("✅ SUCCESS! Reddit API is working")
        print("=" * 60)
        print(f"Connected to Reddit")
        print(f"Test: Retrieved {len(posts)} posts from r/stocks")
        print()
        print("Sample posts:")
        for i, post in enumerate(posts, 1):
            print(f"  {i}. {post.title[:60]}...")
        print()
        print("=" * 60)
        print("Your Reddit API is ready to use!")
        print("The bot will monitor these subreddits:")
        print("  • r/stocks, r/investing, r/StockMarket")
        print("  • r/wallstreetbets, r/ESG_Investing")
        print("  • r/sustainableinvesting, r/finance, r/SecurityAnalysis")
        print("=" * 60)

        return True

    except ImportError:
        print("❌ ERROR: praw library not installed")
        print("   Install with: pip install praw")
        return False

    except Exception as e:
        print(f"❌ ERROR: {e}")
        print()
        print("Common issues:")
        print("  • Check that CLIENT_ID and CLIENT_SECRET are correct")
        print("  • Make sure you selected 'script' as app type")
        print("  • Verify your Reddit app is active at reddit.com/prefs/apps")
        return False

if __name__ == "__main__":
    success = test_reddit_connection()
    exit(0 if success else 1)
