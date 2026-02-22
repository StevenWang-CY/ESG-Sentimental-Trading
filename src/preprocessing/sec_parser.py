"""
SEC Filing Parser
Extracts and cleans text from SEC EDGAR filings
"""

import re
from typing import Dict, List, Optional
from pathlib import Path

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    print("Warning: BeautifulSoup not available. Install with: pip install beautifulsoup4 lxml")


class SECFilingParser:
    """
    Parses and extracts text from SEC EDGAR filings
    """

    def __init__(self):
        """Initialize SEC filing parser"""
        self.item_patterns = {
            '8-K': r'Item\s+(\d+\.\d+)[:\s]+([^\n]+)',
            '10-K': r'Item\s+(\d+[A-Z]?)[:\.\s]+([^\n]+)',
            '10-Q': r'Item\s+(\d+[A-Z]?)[:\.\s]+([^\n]+)'
        }

        # Key 8-K items for ESG events
        self.esg_relevant_items = {
            '1.01': 'Entry into Material Agreement',
            '2.05': 'Costs Associated with Exit Activities',
            '8.01': 'Other Events',  # Most ESG events reported here
            '2.02': 'Results of Operations'
        }

        # 10-K items containing ESG disclosures (Business, Risk Factors, MD&A)
        self.esg_relevant_items_10k = {
            '1': 'Business Description',
            '1A': 'Risk Factors',
            '7': "Management's Discussion and Analysis",
        }

        # 10-Q items containing ESG disclosures (Risk Factors, MD&A)
        self.esg_relevant_items_10q = {
            '1A': 'Risk Factors',
            '2': "Management's Discussion and Analysis",
        }

    def extract_text(self, filing_path: str) -> str:
        """
        Extract clean text from SEC filing

        Args:
            filing_path: Path to filing file

        Returns:
            Cleaned text content
        """
        try:
            with open(filing_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            if BS4_AVAILABLE:
                return self._extract_with_beautifulsoup(content)
            else:
                return self._extract_simple(content)

        except Exception as e:
            print(f"Error extracting text from {filing_path}: {e}")
            return ""

    def _extract_with_beautifulsoup(self, content: str) -> str:
        """Extract text using BeautifulSoup"""
        soup = BeautifulSoup(content, 'lxml')

        # Remove script, style, and table elements
        for tag in soup(['script', 'style', 'table']):
            tag.decompose()

        # Get text
        text = soup.get_text(separator=' ', strip=True)

        # Clean whitespace
        text = re.sub(r'\s+', ' ', text)

        return text

    def _extract_simple(self, content: str) -> str:
        """Simple text extraction without BeautifulSoup"""
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', content)

        # Clean whitespace
        text = re.sub(r'\s+', ' ', text)

        return text.strip()

    def extract_item_sections(self, text: str, filing_type: str = '8-K') -> Dict[str, str]:
        """
        Extract specific Item sections from filing

        Args:
            text: Filing text
            filing_type: Type of filing (8-K, 10-K, 10-Q)

        Returns:
            Dictionary mapping item numbers to their content
        """
        if filing_type not in self.item_patterns:
            return {'full_text': text}

        pattern = self.item_patterns[filing_type]
        items = {}

        # Find all item headers
        matches = list(re.finditer(pattern, text, re.IGNORECASE))

        for i, match in enumerate(matches):
            item_number = match.group(1)
            item_title = match.group(2).strip()

            # Extract content until next item or end
            start = match.end()
            if i < len(matches) - 1:
                end = matches[i + 1].start()
            else:
                end = len(text)

            content = text[start:end].strip()

            items[item_number] = {
                'title': item_title,
                'content': content
            }

        return items

    def extract_esg_relevant_sections(self, text: str, filing_type: str = '8-K') -> str:
        """
        Extract only ESG-relevant sections from filing

        For 8-K: Material event items (1.01, 2.05, 8.01, 2.02)
        For 10-K: Business, Risk Factors, MD&A sections
        For 10-Q: Risk Factors, MD&A sections

        Args:
            text: Filing text
            filing_type: Type of filing

        Returns:
            Combined text from ESG-relevant sections
        """
        # Select the relevant items mapping based on filing type
        if filing_type == '8-K':
            relevant_items = self.esg_relevant_items
        elif filing_type == '10-K':
            relevant_items = self.esg_relevant_items_10k
        elif filing_type == '10-Q':
            relevant_items = self.esg_relevant_items_10q
        else:
            return text

        items = self.extract_item_sections(text, filing_type)

        relevant_text = []
        for item_num, content in items.items():
            if item_num in relevant_items:
                if isinstance(content, dict):
                    relevant_text.append(content['content'])
                else:
                    relevant_text.append(content)

        return ' '.join(relevant_text) if relevant_text else text

    def parse_filing_metadata(self, filing_path: str) -> Dict:
        """
        Extract metadata from filing

        Args:
            filing_path: Path to filing

        Returns:
            Dictionary with metadata
        """
        path = Path(filing_path)

        metadata = {
            'file_name': path.name,
            'file_size': path.stat().st_size if path.exists() else 0,
            'file_path': str(path)
        }

        # Try to extract accession number from path
        parts = str(path).split('/')
        if len(parts) > 2:
            metadata['ticker'] = parts[-3] if 'sec-edgar-filings' in str(path) else 'UNKNOWN'
            metadata['filing_type'] = parts[-2] if 'sec-edgar-filings' in str(path) else 'UNKNOWN'

        return metadata
