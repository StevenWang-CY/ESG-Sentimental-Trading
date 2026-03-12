"""
Canonical financial sentiment interface.

Supports a strict hybrid production mode while keeping a lightweight
rule-based fallback available for demos and tests.
"""

from __future__ import annotations

from typing import Dict, List

try:
    from transformers import pipeline
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    print("Warning: transformers not available. Falling back to non-transformer sentiment.")

try:
    from .advanced_sentiment_analyzer import AdvancedSentimentAnalyzer
    ADVANCED_AVAILABLE = True
except ImportError:
    ADVANCED_AVAILABLE = False
    AdvancedSentimentAnalyzer = None  # type: ignore[assignment]


class FinancialSentimentAnalyzer:
    """
    Shared sentiment analyzer used across the pipeline.

    Modes:
    - hybrid: AdvancedSentimentAnalyzer (FinBERT + lexicon)
    - finbert: plain transformer sentiment
    - simple: lightweight rule-based fallback
    """

    def __init__(
        self,
        model_name: str = "ProsusAI/finbert",
        mode: str = "hybrid",
        batch_size: int = 32,
        strict: bool = False,
    ):
        self.model_name = model_name
        self.requested_mode = mode.lower()
        self.batch_size = batch_size
        self.strict = strict
        self.sentiment_pipeline = None
        self.advanced_analyzer = None
        self.active_mode = 'simple'

        if self.requested_mode == 'hybrid':
            self._init_hybrid()
        elif self.requested_mode == 'finbert':
            self._init_transformer()
        else:
            self.active_mode = 'simple'

    def _init_hybrid(self) -> None:
        if not ADVANCED_AVAILABLE:
            if self.strict:
                raise RuntimeError("Hybrid sentiment mode requested but advanced analyzer is unavailable")
            self.active_mode = 'simple'
            return

        try:
            self.advanced_analyzer = AdvancedSentimentAnalyzer(
                use_transformer=True,
                model_name=self.model_name,
                use_valence_shifters=True,
                use_negation_rules=True,
            )
            if self.strict and not self.advanced_analyzer.use_transformer:
                raise RuntimeError(
                    "Hybrid sentiment mode requires transformer-backed FinBERT but it could not be loaded"
                )
            self.active_mode = 'hybrid' if self.advanced_analyzer.use_transformer else 'lexicon'
        except Exception:
            if self.strict:
                raise
            self.advanced_analyzer = None
            self.active_mode = 'simple'

    def _init_transformer(self) -> None:
        if not TRANSFORMERS_AVAILABLE:
            if self.strict:
                raise RuntimeError("Transformer sentiment mode requested but transformers is unavailable")
            self.active_mode = 'simple'
            return

        try:
            print(f"Loading sentiment model {self.model_name}...")
            self.sentiment_pipeline = pipeline(
                "sentiment-analysis",
                model=self.model_name,
                tokenizer=self.model_name,
                device=-1,
            )
            self.active_mode = 'finbert'
            print("Sentiment model loaded successfully!")
        except Exception:
            if self.strict:
                raise
            self.sentiment_pipeline = None
            self.active_mode = 'simple'

    def analyze_batch(self, texts: List[str], batch_size: int | None = None) -> List[Dict]:
        if not texts:
            return []

        if self.advanced_analyzer is not None:
            return self.advanced_analyzer.analyze_batch(texts)

        if self.sentiment_pipeline is None:
            return self._simple_sentiment_batch(texts)

        effective_batch_size = batch_size or self.batch_size
        results: List[Dict] = []
        try:
            for i in range(0, len(texts), effective_batch_size):
                batch = texts[i:i + effective_batch_size]
                batch_results = self.sentiment_pipeline(
                    batch,
                    truncation=True,
                    max_length=512,
                )
                results.extend(batch_results)
        except Exception:
            results = self._simple_sentiment_batch(texts)

        return results

    def analyze_single(self, text: str) -> Dict:
        if not text:
            return {'label': 'neutral', 'score': 0.0, 'mode': self.active_mode}

        if self.advanced_analyzer is not None:
            result = self.advanced_analyzer.analyze_with_features(text)
            result['mode'] = self.active_mode
            result['score'] = abs(result.get('adjusted_score', 0.0))
            return result

        if self.sentiment_pipeline is None:
            result = self._simple_sentiment(text)
            result['mode'] = self.active_mode
            return result

        try:
            result = self.sentiment_pipeline(text, truncation=True, max_length=512)[0]
            result['mode'] = self.active_mode
            return result
        except Exception:
            result = self._simple_sentiment(text)
            result['mode'] = self.active_mode
            return result

    def score_to_numeric(self, sentiment_result: Dict) -> float:
        if sentiment_result is None:
            return 0.0

        if 'adjusted_score' in sentiment_result:
            return float(sentiment_result.get('adjusted_score', 0.0))
        if 'raw_score' in sentiment_result and 'label' in sentiment_result:
            return float(sentiment_result.get('raw_score', 0.0))

        label = str(sentiment_result.get('label', 'neutral')).lower()
        score = float(sentiment_result.get('score', 0.5))

        if 'positive' in label:
            return score
        if 'negative' in label:
            return -score
        return 0.0

    def get_model_info(self) -> Dict:
        if self.advanced_analyzer is not None:
            info = self.advanced_analyzer.get_model_info()
            info.update({
                'requested_mode': self.requested_mode,
                'active_mode': self.active_mode,
                'strict': self.strict,
            })
            return info

        return {
            'requested_mode': self.requested_mode,
            'active_mode': self.active_mode,
            'model_name': self.model_name,
            'strict': self.strict,
            'transformer_enabled': self.sentiment_pipeline is not None,
        }

    def _simple_sentiment_batch(self, texts: List[str]) -> List[Dict]:
        return [self._simple_sentiment(text) for text in texts]

    def _simple_sentiment(self, text: str) -> Dict:
        positive_words = {
            'good', 'great', 'excellent', 'positive', 'growth', 'increase',
            'profit', 'success', 'gain', 'strong', 'up', 'beat', 'exceed',
            'outperform', 'improvement', 'recovery', 'bullish',
        }

        negative_words = {
            'bad', 'poor', 'negative', 'decline', 'decrease', 'loss',
            'failure', 'weak', 'down', 'miss', 'below', 'underperform',
            'concern', 'risk', 'warning', 'bearish', 'lawsuit', 'fine',
        }

        words = text.lower().split()
        pos_count = sum(1 for word in words if word in positive_words)
        neg_count = sum(1 for word in words if word in negative_words)
        total = pos_count + neg_count

        if total == 0:
            return {'label': 'neutral', 'score': 0.5}
        if pos_count > neg_count:
            return {'label': 'positive', 'score': pos_count / total}
        if neg_count > pos_count:
            return {'label': 'negative', 'score': neg_count / total}
        return {'label': 'neutral', 'score': 0.5}

    def get_sentiment_distribution(self, sentiments: List[Dict]) -> Dict:
        labels = [str(s.get('label', 'neutral')).lower() for s in sentiments]
        distribution = {
            'positive': labels.count('positive'),
            'negative': labels.count('negative'),
            'neutral': labels.count('neutral'),
            'total': len(labels),
            'mode': self.active_mode,
        }
        if distribution['total'] > 0:
            distribution['positive_pct'] = distribution['positive'] / distribution['total']
            distribution['negative_pct'] = distribution['negative'] / distribution['total']
            distribution['neutral_pct'] = distribution['neutral'] / distribution['total']
        return distribution
