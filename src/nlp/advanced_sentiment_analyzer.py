"""
Advanced Financial Sentiment Analysis with Linguistic Sophistication

This module implements an academically rigorous sentiment analysis system that handles:
1. Negation and syntactic negators (Taboada et al., 2011)
2. Valence shifters: intensifiers and diminishers (Polanyi & Zaenen, 2006)
3. Contextual embeddings via fine-tuned FinBERT (Araci, 2019)
4. Hybrid transformer + lexicon approach (Loughran & McDonald, 2011; Hutto & Gilbert, 2014)

References:
- Araci, D. (2019). "FinBERT: Financial Sentiment Analysis with Pre-trained Language Models"
- Loughran, T., & McDonald, B. (2011). "When is a Liability not a Liability? Textual Analysis,
  Dictionaries, and 10-Ks." Journal of Finance, 66(1), 35-65.
- Hutto, C., & Gilbert, E. (2014). "VADER: A Parsimonious Rule-based Model for Sentiment
  Analysis of Social Media Text." ICWSM.
- Taboada, M., et al. (2011). "Lexicon-Based Methods for Sentiment Analysis." Computational
  Linguistics, 37(2), 267-307.
- Polanyi, L., & Zaenen, A. (2006). "Contextual Valence Shifters." Computing Attitude and
  Affect in Text: Theory and Applications.
"""

import re
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

try:
    from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
    import torch
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False


class AdvancedSentimentAnalyzer:
    """
    Hybrid sentiment analyzer combining:
    1. FinBERT transformer for contextual understanding
    2. Lexicon-based valence shifter detection (VADER-inspired)
    3. Financial domain-specific adjustments (Loughran-McDonald)

    Architecture Justification:
    - FinBERT's BERT-based architecture uses self-attention mechanisms to capture
      contextual relationships between words, automatically learning negation patterns
      through training on financial text (Araci, 2019)
    - However, transformers can miss explicit linguistic rules, so we augment with
      rule-based valence shifter detection (Hutto & Gilbert, 2014)
    - Loughran-McDonald lexicon provides domain-specific financial sentiment that
      outperforms general sentiment dictionaries on financial text
    """

    def __init__(self,
                 use_transformer: bool = True,
                 model_name: str = "ProsusAI/finbert",
                 use_valence_shifters: bool = True,
                 use_negation_rules: bool = True):
        """
        Initialize advanced sentiment analyzer

        Args:
            use_transformer: Use FinBERT transformer model
            model_name: Transformer model to use
            use_valence_shifters: Apply explicit valence shifter rules
            use_negation_rules: Apply explicit negation handling rules
        """
        self.use_transformer = use_transformer and TRANSFORMERS_AVAILABLE
        self.use_valence_shifters = use_valence_shifters
        self.use_negation_rules = use_negation_rules

        # Initialize transformer model
        if self.use_transformer:
            try:
                print(f"Loading FinBERT model: {model_name}")
                self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
                self.tokenizer = AutoTokenizer.from_pretrained(model_name)
                self.sentiment_pipeline = pipeline(
                    "sentiment-analysis",
                    model=self.model,
                    tokenizer=self.tokenizer,
                    device=-1  # CPU
                )
                print("✓ FinBERT loaded successfully")
            except Exception as e:
                print(f"Failed to load FinBERT: {e}")
                print("Falling back to lexicon-only mode")
                self.use_transformer = False
                self.sentiment_pipeline = None
        else:
            self.sentiment_pipeline = None

        # Initialize lexicons and linguistic rules
        self._init_lexicons()
        self._init_valence_shifters()
        self._init_negation_patterns()

    def _init_lexicons(self):
        """
        Initialize financial sentiment lexicons

        Based on:
        - Loughran-McDonald Financial Sentiment Dictionary (2011)
        - Domain-specific ESG terms
        """
        # Loughran-McDonald inspired lexicon (subset)
        self.positive_lexicon = {
            # Strong positive (weight: 2.0)
            'excellent': 2.0, 'outstanding': 2.0, 'exceptional': 2.0,
            'revolutionary': 2.0, 'breakthrough': 2.0, 'superior': 2.0,
            'spectacular': 2.0, 'remarkable': 2.0, 'impressive': 2.0,

            # Moderate positive (weight: 1.5)
            'strong': 1.5, 'positive': 1.5, 'growth': 1.5, 'improved': 1.5,
            'gain': 1.5, 'profitable': 1.5, 'success': 1.5, 'benefit': 1.5,

            # Weak positive (weight: 1.0)
            'good': 1.0, 'better': 1.0, 'favorable': 1.0, 'progress': 1.0,
            'increase': 1.0, 'recovery': 1.0, 'stable': 1.0
        }

        self.negative_lexicon = {
            # Strong negative (weight: -2.0)
            'catastrophic': -2.0, 'disastrous': -2.0, 'devastating': -2.0,
            'collapse': -2.0, 'crisis': -2.0, 'scandal': -2.0, 'fraud': -2.0,
            'bankruptcy': -2.0, 'failure': -2.0,

            # Moderate negative (weight: -1.5)
            'loss': -1.5, 'decline': -1.5, 'weak': -1.5, 'concern': -1.5,
            'risk': -1.5, 'penalty': -1.5, 'warning': -1.5, 'lawsuit': -1.5,

            # Weak negative (weight: -1.0)
            'bad': -1.0, 'poor': -1.0, 'lower': -1.0, 'negative': -1.0,
            'decrease': -1.0, 'below': -1.0, 'miss': -1.0
        }

    def _init_valence_shifters(self):
        """
        Initialize valence shifters (Polanyi & Zaenen, 2006)

        Valence shifters modify the intensity of sentiment-bearing words:
        - Intensifiers amplify sentiment (very, extremely, highly)
        - Diminishers reduce sentiment (somewhat, slightly, barely)
        """
        # Intensifiers (multiply sentiment by factor)
        self.intensifiers = {
            'very': 1.5, 'extremely': 1.8, 'highly': 1.6, 'particularly': 1.4,
            'especially': 1.5, 'remarkably': 1.7, 'exceptionally': 1.8,
            'incredibly': 1.7, 'significantly': 1.6, 'substantially': 1.6,
            'greatly': 1.5, 'strongly': 1.5, 'deeply': 1.4
        }

        # Diminishers (multiply sentiment by factor)
        self.diminishers = {
            'somewhat': 0.7, 'slightly': 0.6, 'barely': 0.5, 'hardly': 0.5,
            'scarcely': 0.5, 'relatively': 0.7, 'moderately': 0.75,
            'partially': 0.7, 'marginally': 0.6, 'a little': 0.6,
            'kind of': 0.7, 'sort of': 0.7
        }

        # Negators (reverse polarity and reduce intensity)
        self.negators = {
            'not', 'no', 'never', "n't", 'neither', 'nor', 'none',
            'nobody', 'nothing', 'nowhere', 'cannot', 'cant', "can't"
        }

    def _init_negation_patterns(self):
        """
        Initialize negation detection patterns (Taboada et al., 2011)

        Negation scope: typically extends from negator to punctuation or
        clause boundary (average: 4-5 words)
        """
        self.negation_window = 5  # Words affected after negation

        # Punctuation marks that end negation scope
        self.negation_terminators = {'.', ',', ';', ':', '!', '?', 'but', 'however', 'although'}

    def analyze_with_features(self, text: str) -> Dict:
        """
        Comprehensive sentiment analysis with linguistic features

        Returns:
            Dictionary with:
            - raw_score: Base sentiment score
            - adjusted_score: Score after negation and valence shifters
            - intensity: Final weighted sentiment magnitude
            - confidence: Model confidence (if using transformer)
            - negation_detected: Whether negation patterns found
            - shifter_count: Number of valence shifters applied
            - polarization: Internal contradiction measure
        """
        if not text or len(text.strip()) == 0:
            return self._empty_result()

        # Step 1: Get base sentiment from transformer (if available)
        if self.use_transformer and self.sentiment_pipeline:
            try:
                transformer_result = self.sentiment_pipeline(text, truncation=True, max_length=512)[0]
                base_score = self._convert_transformer_score(transformer_result)
                confidence = transformer_result['score']
            except Exception as e:
                print(f"Transformer analysis failed: {e}")
                base_score = 0.0
                confidence = 0.0
        else:
            base_score = 0.0
            confidence = 0.0

        # Step 2: Apply lexicon-based analysis with linguistic rules
        lexicon_result = self._lexicon_analysis_with_rules(text)

        # Step 3: Combine transformer and lexicon scores (weighted average)
        # Transformer: 70%, Lexicon: 30% (transformer better at context, lexicon better at domain terms)
        if self.use_transformer and confidence > 0.5:
            combined_score = 0.7 * base_score + 0.3 * lexicon_result['adjusted_score']
            final_confidence = confidence
        else:
            combined_score = lexicon_result['adjusted_score']
            final_confidence = lexicon_result['confidence']

        return {
            'raw_score': base_score,
            'adjusted_score': combined_score,
            'intensity': abs(combined_score),  # Magnitude of sentiment
            'confidence': final_confidence,
            'negation_detected': lexicon_result['negation_detected'],
            'shifter_count': lexicon_result['shifter_count'],
            'polarization': lexicon_result['polarization'],
            'label': 'positive' if combined_score > 0.1 else ('negative' if combined_score < -0.1 else 'neutral')
        }

    def _lexicon_analysis_with_rules(self, text: str) -> Dict:
        """
        Lexicon-based analysis with explicit linguistic rules

        Implements:
        1. Valence shifter detection and application
        2. Negation scope handling
        3. Sentiment aggregation with weights
        """
        words = text.lower().split()
        sentiment_scores = []
        negation_detected = False
        shifter_count = 0

        i = 0
        negation_active = False
        negation_countdown = 0
        current_modifier = 1.0

        while i < len(words):
            word = words[i].strip('.,!?;:')

            # Check if negation ends
            if negation_countdown == 0:
                negation_active = False

            # Detect negation
            if self.use_negation_rules and word in self.negators:
                negation_active = True
                negation_countdown = self.negation_window
                negation_detected = True
                i += 1
                continue

            # Detect intensifiers
            if word in self.intensifiers:
                current_modifier *= self.intensifiers[word]
                shifter_count += 1
                i += 1
                continue

            # Detect diminishers
            if word in self.diminishers:
                current_modifier *= self.diminishers[word]
                shifter_count += 1
                i += 1
                continue

            # Check for sentiment-bearing word
            sentiment_score = 0.0
            if word in self.positive_lexicon:
                sentiment_score = self.positive_lexicon[word]
            elif word in self.negative_lexicon:
                sentiment_score = self.negative_lexicon[word]

            # Apply modifiers
            if sentiment_score != 0.0:
                # Apply valence shifters
                sentiment_score *= current_modifier

                # Apply negation (flip polarity and reduce intensity)
                if negation_active:
                    sentiment_score = -sentiment_score * 0.8  # Negation reduces intensity

                sentiment_scores.append(sentiment_score)

                # Reset modifier after applying
                current_modifier = 1.0

            # Decrement negation countdown
            if negation_active:
                negation_countdown -= 1

            # Check for negation terminators
            if any(term in word for term in self.negation_terminators):
                negation_active = False
                negation_countdown = 0

            i += 1

        # Aggregate sentiment scores
        if len(sentiment_scores) == 0:
            adjusted_score = 0.0
            polarization = 0.0
            confidence = 0.0
        else:
            adjusted_score = np.mean(sentiment_scores)
            polarization = np.std(sentiment_scores)  # High std = high disagreement
            confidence = min(len(sentiment_scores) / 10.0, 1.0)  # More words = higher confidence

        # Normalize to [-1, 1]
        adjusted_score = np.clip(adjusted_score, -1.0, 1.0)

        return {
            'adjusted_score': adjusted_score,
            'negation_detected': negation_detected,
            'shifter_count': shifter_count,
            'polarization': polarization,
            'confidence': confidence
        }

    def _convert_transformer_score(self, result: Dict) -> float:
        """Convert transformer output to [-1, 1] scale"""
        label = result['label'].lower()
        score = result['score']

        if 'positive' in label:
            return score
        elif 'negative' in label:
            return -score
        else:  # neutral
            return 0.0

    def _empty_result(self) -> Dict:
        """Return empty result structure"""
        return {
            'raw_score': 0.0,
            'adjusted_score': 0.0,
            'intensity': 0.0,
            'confidence': 0.0,
            'negation_detected': False,
            'shifter_count': 0,
            'polarization': 0.0,
            'label': 'neutral'
        }

    def analyze_batch(self, texts: List[str]) -> List[Dict]:
        """Analyze multiple texts"""
        return [self.analyze_with_features(text) for text in texts]

    def compute_aggregate_features(self,
                                   sentiment_results: List[Dict],
                                   timestamps: Optional[List[pd.Timestamp]] = None) -> Dict:
        """
        Compute aggregate features for ESG signal generation

        Features (as specified):
        1. Intensity: Weighted average sentiment magnitude
        2. Volume: Total number of posts/articles
        3. Duration: Number of days sentiment stays above threshold
        4. Polarization: Standard deviation of sentiment scores (disagreement measure)

        Args:
            sentiment_results: List of sentiment analysis results
            timestamps: Optional timestamps for duration calculation

        Returns:
            Dictionary with aggregate features
        """
        if not sentiment_results:
            return {
                'intensity': 0.0,
                'volume': 0,
                'duration': 0,
                'polarization': 0.0,
                'mean_sentiment': 0.0,
                'sentiment_trend': 0.0
            }

        # Extract sentiment scores
        scores = [r['adjusted_score'] for r in sentiment_results]
        intensities = [r['intensity'] for r in sentiment_results]
        confidences = [r['confidence'] for r in sentiment_results]

        # Feature 1: Intensity (confidence-weighted average magnitude)
        weights = np.array(confidences) + 0.1  # Add small epsilon to avoid zero weights
        weighted_intensity = np.average(intensities, weights=weights)

        # Feature 2: Volume
        volume = len(sentiment_results)

        # Feature 3: Duration (if timestamps provided)
        duration = 0
        threshold = 0.3  # Sentiment threshold for "elevated" sentiment
        if timestamps and len(timestamps) > 0:
            # Convert to DataFrame for time-based analysis
            df = pd.DataFrame({
                'timestamp': timestamps,
                'sentiment': scores
            })
            df = df.sort_values('timestamp')

            # Count consecutive days above threshold
            df['above_threshold'] = df['sentiment'].abs() > threshold
            df['date'] = df['timestamp'].dt.date
            daily_elevated = df.groupby('date')['above_threshold'].any()

            # Count consecutive days
            duration = daily_elevated.astype(int).sum()

        # Feature 4: Polarization (std dev of sentiment)
        polarization = np.std(scores)

        # Additional features
        mean_sentiment = np.mean(scores)

        # NEW: Max sentiment magnitude (research shows max is predictive - MDPI 2025)
        max_sentiment = max(scores, key=abs) if scores else 0.0

        # Sentiment trend (if timestamps available)
        sentiment_trend = 0.0
        if timestamps and len(timestamps) > 1:
            # Simple linear trend: correlation between time and sentiment
            time_index = np.arange(len(scores))
            if len(scores) > 2:
                sentiment_trend = np.corrcoef(time_index, scores)[0, 1]

        return {
            'intensity': weighted_intensity,
            'volume': volume,
            'duration': duration,
            'polarization': polarization,  # Sentiment std (disagreement measure)
            'mean_sentiment': mean_sentiment,
            'max_sentiment': max_sentiment,  # NEW: Maximum sentiment for signal enhancement
            'sentiment_trend': sentiment_trend
        }

    def get_model_info(self) -> Dict:
        """Return information about the sentiment analysis configuration"""
        return {
            'transformer_enabled': self.use_transformer,
            'valence_shifters_enabled': self.use_valence_shifters,
            'negation_rules_enabled': self.use_negation_rules,
            'model_architecture': 'Hybrid FinBERT + Lexicon-based',
            'references': [
                'Araci (2019) - FinBERT',
                'Loughran & McDonald (2011) - Financial Lexicon',
                'Hutto & Gilbert (2014) - VADER Valence Shifters',
                'Taboada et al. (2011) - Negation Handling'
            ]
        }


# Example usage and testing
if __name__ == "__main__":
    analyzer = AdvancedSentimentAnalyzer()

    # Test cases for negation
    test_texts = [
        "The company's performance is excellent",
        "The company's performance is not bad",  # Negation test
        "This is very good news",  # Intensifier test
        "This is somewhat disappointing",  # Diminisher test
        "The results are extremely catastrophic",  # Strong negative with intensifier
    ]

    print("Testing Advanced Sentiment Analyzer:")
    print("=" * 60)
    for text in test_texts:
        result = analyzer.analyze_with_features(text)
        print(f"\nText: {text}")
        print(f"Score: {result['adjusted_score']:.3f}")
        print(f"Intensity: {result['intensity']:.3f}")
        print(f"Label: {result['label']}")
        print(f"Negation: {result['negation_detected']}")
        print(f"Shifters: {result['shifter_count']}")
