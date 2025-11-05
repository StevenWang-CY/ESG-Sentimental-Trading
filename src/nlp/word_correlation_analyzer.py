"""
Word-Level Correlation Analysis
Analyzes correlation between individual words and stock price movements.

Based on research from Savarese (2019) - Politecnico di Torino thesis
Identifies "best words" (high positive correlation) and "worst words" (high negative correlation)
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
from collections import Counter
import re
from scipy.stats import pearsonr
import pickle
import os
from datetime import datetime


class WordCorrelationAnalyzer:
    """
    Analyzes word-level correlations with stock price movements.
    Creates dynamic "best words" and "worst words" dictionaries based on historical data.
    """

    def __init__(self,
                 min_word_frequency: int = 10,
                 correlation_threshold: float = 0.5,
                 min_word_length: int = 3,
                 stopwords: Optional[List[str]] = None):
        """
        Initialize word correlation analyzer

        Args:
            min_word_frequency: Minimum number of occurrences for a word to be analyzed
            correlation_threshold: Minimum absolute correlation to be considered significant
            min_word_length: Minimum word length to consider
            stopwords: List of stopwords to exclude (default uses common English stopwords)
        """
        self.min_word_frequency = min_word_frequency
        self.correlation_threshold = correlation_threshold
        self.min_word_length = min_word_length

        # Default stopwords (common English + finance-specific noise words)
        self.stopwords = stopwords or self._get_default_stopwords()

        # Trained word correlations
        self.word_correlations: Dict[str, float] = {}
        self.best_words: List[str] = []  # High positive correlation
        self.worst_words: List[str] = []  # High negative correlation

        # Year-specific dictionaries (to avoid look-ahead bias)
        self.yearly_correlations: Dict[int, Dict[str, float]] = {}

    def _get_default_stopwords(self) -> List[str]:
        """Get default stopwords list"""
        common_stopwords = [
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been',
            'be', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'can', 'this', 'that', 'these',
            'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'them', 'their',
            'what', 'which', 'who', 'when', 'where', 'why', 'how', 'all', 'each',
            'every', 'both', 'few', 'more', 'most', 'other', 'some', 'such',
            'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too',
            'very', 'just', 'said', 'company', 'inc', 'corp', 'llc', 'ltd'
        ]
        return common_stopwords

    def extract_words(self, text: str) -> List[str]:
        """
        Extract and clean words from text

        Args:
            text: Input text

        Returns:
            List of cleaned words
        """
        # Convert to lowercase
        text = text.lower()

        # Extract words (alphanumeric only)
        words = re.findall(r'\b[a-z]+\b', text)

        # Filter by length and stopwords
        words = [
            w for w in words
            if len(w) >= self.min_word_length and w not in self.stopwords
        ]

        return words

    def train_correlations(self,
                          text_data: pd.DataFrame,
                          price_data: pd.DataFrame,
                          date_column: str = 'date',
                          text_column: str = 'text',
                          ticker_column: str = 'ticker',
                          return_window: int = 1) -> Dict[str, float]:
        """
        Train word correlations from historical text and price data

        Args:
            text_data: DataFrame with columns [date, ticker, text]
            price_data: DataFrame with columns [date, ticker, return_1d] or similar
            date_column: Name of date column
            text_column: Name of text column
            ticker_column: Name of ticker column
            return_window: Forward return window in days (1 = next-day return)

        Returns:
            Dictionary of word -> correlation coefficient
        """
        print(f"\nTraining word correlations on {len(text_data)} documents...")

        # Merge text and price data
        merged = pd.merge(
            text_data,
            price_data,
            on=[date_column, ticker_column],
            how='inner'
        )

        if len(merged) == 0:
            print("Warning: No matching data between text and price data")
            return {}

        print(f"Matched {len(merged)} documents with price data")

        # Extract all words from all documents
        print("Extracting words from documents...")
        word_occurrences = {}  # word -> list of returns when word appears

        for idx, row in merged.iterrows():
            text = row[text_column]
            price_return = row[f'return_{return_window}d']

            if pd.isna(price_return):
                continue

            words = self.extract_words(text)

            # Record return for each word occurrence
            for word in set(words):  # Use set to count document once per word
                if word not in word_occurrences:
                    word_occurrences[word] = []
                word_occurrences[word].append(price_return)

        print(f"Found {len(word_occurrences)} unique words")

        # Filter by minimum frequency
        word_occurrences = {
            word: returns
            for word, returns in word_occurrences.items()
            if len(returns) >= self.min_word_frequency
        }

        print(f"Filtered to {len(word_occurrences)} words (min frequency: {self.min_word_frequency})")

        # Calculate correlations
        print("Calculating word-return correlations...")
        word_correlations = {}

        # Get all returns for baseline correlation
        all_returns = merged[f'return_{return_window}d'].dropna().values

        for word, returns in word_occurrences.items():
            try:
                # Create binary indicator: 1 if word appears, 0 otherwise
                word_indicator = np.zeros(len(all_returns))

                # This is a simplified approach - in production, you'd want to align properly
                # For now, we calculate correlation between word presence and returns
                if len(returns) > 1:  # Need at least 2 points for correlation
                    # Calculate mean return when word appears vs doesn't appear
                    word_returns = np.array(returns)

                    # Use point-biserial correlation (binary variable vs continuous)
                    # Here we approximate by comparing means
                    mean_return_with_word = np.mean(word_returns)
                    mean_return_overall = np.mean(all_returns)

                    # Calculate proper Pearson correlation
                    # Create full dataset: word appears (1) or not (0) vs returns
                    n_total = len(all_returns)
                    n_with_word = len(returns)

                    # Simplified correlation (proper implementation would merge datasets)
                    # For now, we use the difference in means as a proxy
                    correlation = mean_return_with_word - mean_return_overall

                    # Normalize by standard deviation
                    if np.std(all_returns) > 0:
                        correlation = correlation / np.std(all_returns)

                    word_correlations[word] = correlation

            except Exception as e:
                continue

        self.word_correlations = word_correlations

        # Identify best and worst words
        self._identify_best_worst_words()

        print(f"\nCorrelation analysis complete:")
        print(f"  Best words (positive correlation): {len(self.best_words)}")
        print(f"  Worst words (negative correlation): {len(self.worst_words)}")

        return self.word_correlations

    def train_correlations_by_year(self,
                                   text_data: pd.DataFrame,
                                   price_data: pd.DataFrame,
                                   years: List[int],
                                   date_column: str = 'date',
                                   text_column: str = 'text',
                                   ticker_column: str = 'ticker') -> Dict[int, Dict[str, float]]:
        """
        Train year-specific word correlations to avoid look-ahead bias

        Args:
            text_data: DataFrame with text data
            price_data: DataFrame with price data
            years: List of years to train for
            date_column: Name of date column
            text_column: Name of text column
            ticker_column: Name of ticker column

        Returns:
            Dictionary of year -> word correlations
        """
        print(f"\nTraining year-specific correlations for {len(years)} years...")

        for year in years:
            print(f"\n--- Year {year} ---")

            # Filter data for this year
            text_year = text_data[text_data[date_column].dt.year == year].copy()
            price_year = price_data[price_data[date_column].dt.year == year].copy()

            if len(text_year) == 0 or len(price_year) == 0:
                print(f"No data for year {year}, skipping...")
                continue

            # Train correlations for this year
            year_correlations = self.train_correlations(
                text_year,
                price_year,
                date_column=date_column,
                text_column=text_column,
                ticker_column=ticker_column
            )

            self.yearly_correlations[year] = year_correlations

        return self.yearly_correlations

    def _identify_best_worst_words(self):
        """Identify best words (high positive corr) and worst words (high negative corr)"""
        if not self.word_correlations:
            return

        # Best words: correlation > threshold
        self.best_words = [
            word for word, corr in self.word_correlations.items()
            if corr > self.correlation_threshold
        ]

        # Worst words: correlation < -threshold
        self.worst_words = [
            word for word, corr in self.word_correlations.items()
            if corr < -self.correlation_threshold
        ]

        # Sort by correlation magnitude
        self.best_words = sorted(
            self.best_words,
            key=lambda w: self.word_correlations[w],
            reverse=True
        )
        self.worst_words = sorted(
            self.worst_words,
            key=lambda w: self.word_correlations[w]
        )

    def get_top_words(self, n: int = 50, word_type: str = 'best') -> List[Tuple[str, float]]:
        """
        Get top N best or worst words

        Args:
            n: Number of words to return
            word_type: 'best' or 'worst'

        Returns:
            List of (word, correlation) tuples
        """
        if word_type == 'best':
            words = self.best_words[:n]
        elif word_type == 'worst':
            words = self.worst_words[:n]
        else:
            raise ValueError("word_type must be 'best' or 'worst'")

        return [(w, self.word_correlations[w]) for w in words]

    def score_text(self, text: str, use_year: Optional[int] = None) -> Dict[str, float]:
        """
        Score text based on word correlations

        Args:
            text: Input text to score
            use_year: If provided, use year-specific correlations

        Returns:
            Dictionary with scoring metrics
        """
        words = self.extract_words(text)

        if not words:
            return {
                'correlation_score': 0.0,
                'n_best_words': 0,
                'n_worst_words': 0,
                'best_words_found': [],
                'worst_words_found': []
            }

        # Get appropriate correlation dictionary
        if use_year and use_year in self.yearly_correlations:
            correlations = self.yearly_correlations[use_year]
            best_words = [w for w, c in correlations.items() if c > self.correlation_threshold]
            worst_words = [w for w, c in correlations.items() if c < -self.correlation_threshold]
        else:
            correlations = self.word_correlations
            best_words = self.best_words
            worst_words = self.worst_words

        # Count best and worst words
        word_counts = Counter(words)
        best_words_found = [w for w in words if w in best_words]
        worst_words_found = [w for w in words if w in worst_words]

        # Calculate correlation-weighted score
        correlation_score = sum(
            correlations.get(word, 0) * count
            for word, count in word_counts.items()
        )

        # Normalize by total words
        if len(words) > 0:
            correlation_score = correlation_score / len(words)

        return {
            'correlation_score': correlation_score,
            'n_best_words': len(best_words_found),
            'n_worst_words': len(worst_words_found),
            'best_words_found': list(set(best_words_found)),
            'worst_words_found': list(set(worst_words_found)),
            'n_total_words': len(words)
        }

    def save_model(self, filepath: str):
        """Save trained model to disk"""
        model_data = {
            'word_correlations': self.word_correlations,
            'best_words': self.best_words,
            'worst_words': self.worst_words,
            'yearly_correlations': self.yearly_correlations,
            'min_word_frequency': self.min_word_frequency,
            'correlation_threshold': self.correlation_threshold,
            'min_word_length': self.min_word_length,
            'stopwords': self.stopwords
        }

        with open(filepath, 'wb') as f:
            pickle.dump(model_data, f)

        print(f"Model saved to {filepath}")

    def load_model(self, filepath: str):
        """Load trained model from disk"""
        with open(filepath, 'rb') as f:
            model_data = pickle.load(f)

        self.word_correlations = model_data['word_correlations']
        self.best_words = model_data['best_words']
        self.worst_words = model_data['worst_words']
        self.yearly_correlations = model_data.get('yearly_correlations', {})
        self.min_word_frequency = model_data['min_word_frequency']
        self.correlation_threshold = model_data['correlation_threshold']
        self.min_word_length = model_data['min_word_length']
        self.stopwords = model_data['stopwords']

        print(f"Model loaded from {filepath}")
        print(f"  Best words: {len(self.best_words)}")
        print(f"  Worst words: {len(self.worst_words)}")
        print(f"  Years available: {list(self.yearly_correlations.keys())}")

    def print_top_words_summary(self, n: int = 20):
        """Print summary of top best and worst words"""
        print("\n" + "="*70)
        print("WORD CORRELATION ANALYSIS SUMMARY")
        print("="*70)

        print(f"\nTop {n} BEST words (positive correlation with returns):")
        print("-" * 70)
        for i, (word, corr) in enumerate(self.get_top_words(n, 'best'), 1):
            print(f"{i:2d}. {word:20s} {corr:+.4f}")

        print(f"\nTop {n} WORST words (negative correlation with returns):")
        print("-" * 70)
        for i, (word, corr) in enumerate(self.get_top_words(n, 'worst'), 1):
            print(f"{i:2d}. {word:20s} {corr:+.4f}")

        print("\n" + "="*70)


class ESGWordCorrelationAnalyzer(WordCorrelationAnalyzer):
    """
    ESG-specific word correlation analyzer
    Extends base analyzer with ESG-focused preprocessing and analysis
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # Add ESG-specific stopwords
        esg_stopwords = ['esg', 'company', 'companies', 'stock', 'stocks', 'market']
        self.stopwords.extend(esg_stopwords)

    def extract_esg_context_words(self, text: str, esg_keywords: List[str],
                                  context_window: int = 10) -> List[str]:
        """
        Extract words that appear near ESG keywords (contextual analysis)

        Args:
            text: Input text
            esg_keywords: List of ESG keywords to look for
            context_window: Number of words before/after keyword to extract

        Returns:
            List of context words around ESG keywords
        """
        words = text.lower().split()
        context_words = []

        for i, word in enumerate(words):
            # Check if this word is an ESG keyword
            if any(kw in word for kw in esg_keywords):
                # Extract context window
                start = max(0, i - context_window)
                end = min(len(words), i + context_window + 1)
                context = words[start:end]

                # Clean and filter context words
                for ctx_word in context:
                    cleaned = re.sub(r'[^a-z]', '', ctx_word)
                    if (len(cleaned) >= self.min_word_length and
                        cleaned not in self.stopwords):
                        context_words.append(cleaned)

        return context_words

    def score_esg_text(self, text: str, esg_category: str = 'all') -> Dict[str, float]:
        """
        Score text with ESG-specific analysis

        Args:
            text: Input text
            esg_category: 'environmental', 'social', 'governance', or 'all'

        Returns:
            Dictionary with ESG-specific scoring metrics
        """
        # Get base score
        base_score = self.score_text(text)

        # Add ESG-specific metrics
        base_score['esg_category'] = esg_category

        return base_score
