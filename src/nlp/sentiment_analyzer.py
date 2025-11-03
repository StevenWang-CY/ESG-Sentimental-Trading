"""
Financial Sentiment Analysis
Analyzes sentiment of financial text using FinBERT or similar models
"""

from typing import List, Dict
import numpy as np

try:
    from transformers import pipeline
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    print("Warning: transformers not available. Falling back to simple sentiment.")
    print("Install with: pip install transformers torch")


class FinancialSentimentAnalyzer:
    """
    Production-grade sentiment analysis for financial text
    """

    def __init__(self, model_name: str = "ProsusAI/finbert"):
        """
        Initialize sentiment analyzer

        Args:
            model_name: HuggingFace model name
                       Options: 'ProsusAI/finbert', 'yiyanghkust/finbert-tone'
        """
        self.model_name = model_name

        if TRANSFORMERS_AVAILABLE:
            try:
                print(f"Loading sentiment model {model_name}...")
                self.sentiment_pipeline = pipeline(
                    "sentiment-analysis",
                    model=model_name,
                    tokenizer=model_name,
                    device=-1  # CPU, change to 0 for GPU
                )
                print("Sentiment model loaded successfully!")
            except Exception as e:
                print(f"Error loading model: {e}")
                print("Falling back to simple sentiment analysis")
                self.sentiment_pipeline = None
        else:
            self.sentiment_pipeline = None

    def analyze_batch(self, texts: List[str], batch_size: int = 32) -> List[Dict]:
        """
        Analyze sentiment for a batch of texts

        Args:
            texts: List of texts to analyze
            batch_size: Batch size for processing

        Returns:
            List of dictionaries with 'label' and 'score'
        """
        if not texts:
            return []

        if self.sentiment_pipeline is None:
            return self._simple_sentiment_batch(texts)

        results = []
        try:
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i+batch_size]
                batch_results = self.sentiment_pipeline(
                    batch,
                    truncation=True,
                    max_length=512
                )
                results.extend(batch_results)
        except Exception as e:
            print(f"Error in batch sentiment analysis: {e}")
            results = self._simple_sentiment_batch(texts)

        return results

    def analyze_single(self, text: str) -> Dict:
        """
        Analyze sentiment for a single text

        Args:
            text: Text to analyze

        Returns:
            Dictionary with 'label' and 'score'
        """
        if not text:
            return {'label': 'neutral', 'score': 0.0}

        if self.sentiment_pipeline is None:
            return self._simple_sentiment(text)

        try:
            result = self.sentiment_pipeline(text, truncation=True, max_length=512)[0]
            return result
        except Exception as e:
            print(f"Error in sentiment analysis: {e}")
            return self._simple_sentiment(text)

    def score_to_numeric(self, sentiment_result: Dict) -> float:
        """
        Convert sentiment to numeric score: [-1, 1]

        Args:
            sentiment_result: Result from analyze_single or analyze_batch

        Returns:
            Numeric sentiment score
        """
        label = sentiment_result['label'].lower()
        score = sentiment_result.get('score', 0.5)

        if 'positive' in label:
            return score
        elif 'negative' in label:
            return -score
        else:  # neutral
            return 0.0

    def _simple_sentiment_batch(self, texts: List[str]) -> List[Dict]:
        """Simple rule-based sentiment (fallback)"""
        return [self._simple_sentiment(text) for text in texts]

    def _simple_sentiment(self, text: str) -> Dict:
        """Simple rule-based sentiment analysis (fallback)"""
        positive_words = {
            'good', 'great', 'excellent', 'positive', 'growth', 'increase',
            'profit', 'success', 'gain', 'strong', 'up', 'beat', 'exceed',
            'outperform', 'improvement', 'recovery', 'bullish'
        }

        negative_words = {
            'bad', 'poor', 'negative', 'decline', 'decrease', 'loss',
            'failure', 'weak', 'down', 'miss', 'below', 'underperform',
            'concern', 'risk', 'warning', 'bearish', 'lawsuit', 'fine'
        }

        text_lower = text.lower()
        words = text_lower.split()

        pos_count = sum(1 for word in words if word in positive_words)
        neg_count = sum(1 for word in words if word in negative_words)

        total = pos_count + neg_count

        if total == 0:
            return {'label': 'neutral', 'score': 0.5}

        if pos_count > neg_count:
            return {'label': 'positive', 'score': pos_count / total}
        elif neg_count > pos_count:
            return {'label': 'negative', 'score': neg_count / total}
        else:
            return {'label': 'neutral', 'score': 0.5}

    def get_sentiment_distribution(self, sentiments: List[Dict]) -> Dict:
        """
        Get distribution of sentiments

        Args:
            sentiments: List of sentiment results

        Returns:
            Dictionary with sentiment counts and percentages
        """
        labels = [s['label'].lower() for s in sentiments]

        distribution = {
            'positive': labels.count('positive'),
            'negative': labels.count('negative'),
            'neutral': labels.count('neutral'),
            'total': len(labels)
        }

        # Add percentages
        if distribution['total'] > 0:
            distribution['positive_pct'] = distribution['positive'] / distribution['total']
            distribution['negative_pct'] = distribution['negative'] / distribution['total']
            distribution['neutral_pct'] = distribution['neutral'] / distribution['total']

        return distribution
