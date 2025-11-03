"""
Text Cleaning Utilities
Cleans and preprocesses text data for NLP analysis
"""

import re
from typing import List, Optional


class TextCleaner:
    """
    Cleans and preprocesses text for NLP
    """

    def __init__(self):
        """Initialize text cleaner"""
        self.url_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
        self.email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
        self.number_pattern = re.compile(r'\d+')

    def clean_text(self, text: str, remove_urls: bool = True,
                   remove_emails: bool = True, remove_numbers: bool = False,
                   lowercase: bool = False, remove_extra_whitespace: bool = True) -> str:
        """
        Clean text with various options

        Args:
            text: Text to clean
            remove_urls: Remove URLs
            remove_emails: Remove email addresses
            remove_numbers: Remove numbers
            lowercase: Convert to lowercase
            remove_extra_whitespace: Remove extra whitespace

        Returns:
            Cleaned text
        """
        if not text:
            return ""

        # Remove URLs
        if remove_urls:
            text = self.url_pattern.sub(' ', text)

        # Remove emails
        if remove_emails:
            text = self.email_pattern.sub(' ', text)

        # Remove numbers
        if remove_numbers:
            text = self.number_pattern.sub(' ', text)

        # Convert to lowercase
        if lowercase:
            text = text.lower()

        # Remove extra whitespace
        if remove_extra_whitespace:
            text = re.sub(r'\s+', ' ', text)
            text = text.strip()

        return text

    def remove_boilerplate(self, text: str) -> str:
        """
        Remove common boilerplate text from SEC filings

        Args:
            text: Filing text

        Returns:
            Text with boilerplate removed
        """
        boilerplate_patterns = [
            r'UNITED STATES\s+SECURITIES AND EXCHANGE COMMISSION.*?Washington, D\.C\. 20549',
            r'FORM \d+-[A-Z]+',
            r'Commission File Number:.*?\n',
            r'Indicate by check mark.*?\n',
            r'Table of Contents',
            r'Page \d+ of \d+'
        ]

        for pattern in boilerplate_patterns:
            text = re.sub(pattern, ' ', text, flags=re.IGNORECASE | re.DOTALL)

        return text

    def extract_sentences(self, text: str, min_length: int = 10) -> List[str]:
        """
        Extract sentences from text

        Args:
            text: Input text
            min_length: Minimum sentence length

        Returns:
            List of sentences
        """
        # Simple sentence splitting
        sentences = re.split(r'[.!?]+', text)

        # Filter short sentences
        sentences = [s.strip() for s in sentences if len(s.strip()) >= min_length]

        return sentences

    def truncate_text(self, text: str, max_length: int = 5000) -> str:
        """
        Truncate text to maximum length

        Args:
            text: Input text
            max_length: Maximum length

        Returns:
            Truncated text
        """
        if len(text) <= max_length:
            return text

        # Truncate at sentence boundary if possible
        truncated = text[:max_length]
        last_period = truncated.rfind('.')

        if last_period > max_length * 0.8:  # If we can find a period in last 20%
            return truncated[:last_period + 1]

        return truncated

    def clean_for_sentiment_analysis(self, text: str) -> str:
        """
        Clean text specifically for sentiment analysis

        Args:
            text: Input text

        Returns:
            Cleaned text
        """
        # Keep case for sentiment (important for BERT models)
        # Remove URLs and emails
        text = self.clean_text(text, remove_urls=True, remove_emails=True,
                              remove_numbers=False, lowercase=False,
                              remove_extra_whitespace=True)

        # Remove special characters but keep punctuation
        text = re.sub(r'[^\w\s.,!?;:\-\'\"()]', ' ', text)

        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        return text
