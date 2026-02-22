"""
ESG Event Detection
Detects material ESG events from SEC filings and news
"""

import re
from typing import Dict, List, Optional
import numpy as np

try:
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    import torch
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    print("Warning: transformers not available. Only rule-based detection will work.")
    print("Install with: pip install transformers torch")


class ESGEventDetector:
    """
    Rule-based ESG event detection using curated keyword dictionaries
    """

    ESG_KEYWORDS = {
        'environmental': {
            'positive': [
                # Original keywords
                'renewable energy', 'carbon neutral', 'emissions reduction',
                'clean energy investment', 'environmental certification',
                'sustainability initiative', 'green energy', 'solar power',
                'wind power', 'carbon offset', 'environmental award',
                # EXPANDED: additional environmental keywords
                'net zero commitment', 'science-based targets', 'LEED certification', 'circular economy',
                'biodiversity protection', 'water conservation', 'waste reduction', 'sustainable packaging',
                'carbon capture', 'electric vehicle', 'energy efficiency', 'renewable portfolio',
                'ESG rating upgrade', 'CDP disclosure', 'climate pledge', 'carbon disclosure',
                'zero waste', 'recycled materials', 'sustainable sourcing', 'green building',
                'climate action', 'sustainable practices', 'environmental stewardship', 'green bond',
                'renewable investment', 'clean technology', 'environmental leadership',
                'sustainability report', 'carbon footprint reduction', 'green initiative',
                # Modern ESG frameworks & regulatory terms
                'TCFD disclosure', 'SASB reporting', 'GRI standards', 'CSRD compliance',
                'decarbonization', 'green hydrogen', 'sustainable finance',
                'climate transition plan', 'net zero target',
                'scope 1 emissions reduction', 'scope 2 emissions reduction',
                'environmental impact assessment', 'water stewardship',
                'climate resilience', 'nature-based solutions'
            ],
            'negative': [
                # Original keywords
                'environmental fine', 'EPA violation', 'pollution incident',
                'oil spill', 'emissions scandal', 'hazardous waste',
                'environmental lawsuit', 'toxic waste', 'air pollution',
                'water pollution', 'environmental damage', 'climate lawsuit',
                # EXPANDED: additional negative keywords
                'environmental penalty', 'carbon emissions increase', 'deforestation', 'greenwashing',
                'ecological damage', 'wetland destruction', 'wildlife harm', 'pesticide contamination',
                'air quality violation', 'wastewater discharge', 'landfill', 'methane leak',
                'fossil fuel expansion', 'coal plant', 'fracking', 'pipeline spill', 'refinery accident',
                'climate risk', 'scope 3 emissions', 'environmental liability',
                'emissions scandal', 'toxic discharge', 'environmental non-compliance',
                'greenhouse gas increase', 'carbon intensity', 'environmental remediation',
                # Regulatory & litigation terms
                'climate litigation', 'stranded assets', 'physical climate risk',
                'transition risk', 'environmental protest', 'superfund site',
                'toxic release', 'water scarcity risk', 'biodiversity loss',
                'habitat destruction', 'emissions restatement', 'environmental injunction',
                'carbon tax exposure', 'scope 3 emissions increase', 'environmental enforcement'
            ]
        },
        'social': {
            'positive': [
                # Original keywords
                'diversity initiative', 'employee benefit expansion',
                'community investment', 'fair wage increase', 'workplace safety',
                'employee wellness', 'diversity and inclusion', 'equal pay',
                'labor rights', 'community program', 'charitable donation',
                # EXPANDED: additional social keywords
                'living wage', 'paid family leave', 'mental health benefits', 'employee stock ownership',
                'diversity hiring target', 'gender pay equity', 'LGBTQ inclusion', 'accessibility program',
                'supplier code of conduct', 'fair trade certification', 'community development',
                'affordable housing', 'healthcare access', 'education partnership', 'skills training',
                'stakeholder engagement', 'indigenous rights', 'racial equity', 'veterans hiring',
                'employee satisfaction', 'work-life balance', 'diversity award', 'social impact',
                'community support', 'philanthropic initiative', 'employee engagement',
                'workforce development', 'human capital', 'social responsibility',
                # Supply chain & modern workforce terms
                'supply chain transparency', 'responsible AI', 'digital inclusion',
                'employee retention program', 'talent development', 'worker safety investment',
                'human rights due diligence', 'DE&I program', 'social equity',
                'health and safety certification', 'responsible sourcing',
                'consumer protection', 'product safety certification',
                'community resilience', 'social license'
            ],
            'negative': [
                # Original keywords
                'discrimination lawsuit', 'labor dispute', 'worker safety violation',
                'data breach', 'privacy violation', 'product recall',
                'sexual harassment', 'wage theft', 'child labor',
                'human rights violation', 'unsafe working conditions',
                'customer data leak', 'privacy breach', 'security breach',
                # EXPANDED: additional negative keywords
                'forced labor', 'sweatshop', 'union busting', 'gig worker exploitation',
                'age discrimination', 'disability discrimination', 'pregnancy discrimination',
                'toxic workplace', 'burnout', 'high turnover', 'whistleblower retaliation',
                'supply chain violation', 'conflict minerals', 'modern slavery', 'trafficking',
                'consumer fraud', 'predatory lending', 'misleading advertising', 'antitrust',
                'algorithmic bias', 'surveillance', 'facial recognition controversy',
                'workplace harassment', 'hostile work environment', 'labor violation',
                'worker exploitation', 'safety incident', 'data privacy breach',
                # Litigation & regulatory terms
                'class action lawsuit', 'OSHA violation', 'food safety recall',
                'privacy class action', 'mass layoff', 'consumer complaint',
                'accessibility violation', 'workplace fatality', 'cybersecurity incident',
                'social media backlash', 'employee walkout', 'workplace injury',
                'product liability', 'labor arbitration', 'wrongful termination'
            ]
        },
        'governance': {
            'positive': [
                # Original keywords
                'board diversity', 'anti-corruption policy',
                'executive compensation reform', 'corporate governance',
                'transparency initiative', 'ethics program', 'compliance program',
                'shareholder rights', 'board independence',
                # EXPANDED: Additional governance keywords
                'governance best practices', 'stakeholder governance', 'ESG committee',
                'independent directors', 'board oversight', 'audit committee',
                'governance structure', 'shareholder engagement', 'corporate accountability',
                'governance rating', 'governance improvement', 'board effectiveness',
                # Modern governance terms
                'clawback policy', 'say on pay', 'board refreshment',
                'cybersecurity governance', 'risk committee', 'succession planning',
                'proxy access', 'integrated reporting',
                'governance code compliance', 'ESG oversight',
                # BALANCE FIX: 8 keywords to match 39 negative keywords (was 31:39)
                'executive accountability', 'board diversity target',
                'whistleblower protection', 'anti-bribery compliance',
                'governance transparency', 'shareholder democracy',
                'independent audit', 'ethical leadership'
            ],
            'negative': [
                # Original keywords
                'insider trading', 'accounting scandal', 'bribery charges',
                'shareholder lawsuit', 'SEC investigation', 'fraud',
                'corruption', 'embezzlement', 'money laundering',
                'financial restatement', 'audit failure', 'conflict of interest',
                'executive misconduct', 'accounting irregularities',
                # EXPANDED: Additional negative keywords
                'regulatory violation', 'corporate scandal', 'governance failure',
                'board misconduct', 'executive departure', 'CEO resignation',
                'CFO investigation', 'audit deficiency', 'compliance failure',
                'governance controversy', 'shareholder dispute', 'proxy fight',
                'governance risk', 'regulatory fine', 'legal settlement',
                # Financial reporting & enforcement terms
                'material weakness', 'going concern', 'delisting risk',
                'poison pill', 'golden parachute', 'related party transaction',
                'whistleblower complaint', 'SEC enforcement',
                'DOJ investigation', 'restatement of earnings'
            ]
        }
    }

    def __init__(self):
        """Initialize event detector"""
        self.keywords = self.ESG_KEYWORDS

        # Pre-compile word boundary regex for single-word keywords
        # to prevent false positives ("fine" matching "define", etc.)
        self._single_word_patterns = {}
        for category, sentiments in self.keywords.items():
            for sentiment, kws in sentiments.items():
                for kw in kws:
                    if ' ' not in kw:
                        self._single_word_patterns[kw] = re.compile(
                            r'\b' + re.escape(kw) + r'\b', re.IGNORECASE
                        )

    def detect_event(self, text: str, threshold: float = 0.3) -> Dict:
        """
        Detect ESG events in text

        Args:
            text: Text to analyze
            threshold: Minimum confidence threshold

        Returns:
            Dictionary with detection results
        """
        if not text:
            return {'has_event': False}

        text_lower = text.lower()
        results = []

        # Search for keywords
        for category, sentiments in self.keywords.items():
            for sentiment, keywords in sentiments.items():
                for keyword in keywords:
                    if self._match_keyword(keyword, text_lower):
                        results.append({
                            'category': category[0].upper(),  # E, S, or G
                            'sentiment': sentiment,
                            'keyword': keyword,
                            'category_full': category
                        })

        if not results:
            return {'has_event': False}

        # Calculate confidence based on number of matches
        confidence = min(len(results) / 10.0, 1.0)

        if confidence < threshold:
            return {'has_event': False}

        # Determine primary category (most matches)
        category_counts = {}
        for r in results:
            cat = r['category']
            category_counts[cat] = category_counts.get(cat, 0) + 1

        primary_category = max(category_counts, key=category_counts.get)

        # Determine overall sentiment
        sentiment_counts = {'positive': 0, 'negative': 0}
        for r in results:
            sentiment_counts[r['sentiment']] += 1

        overall_sentiment = 'positive' if sentiment_counts['positive'] > sentiment_counts['negative'] else 'negative'

        return {
            'has_event': True,
            'category': primary_category,
            'category_full': self._get_category_name(primary_category),
            'sentiment': overall_sentiment,
            'confidence': confidence,
            'matched_keywords': [r['keyword'] for r in results],
            'num_matches': len(results)
        }

    def _match_keyword(self, keyword: str, text_lower: str) -> bool:
        """
        Match keyword in text with word boundary awareness.

        Single-word keywords use regex word boundaries to prevent false
        positives (e.g., "fine" matching "define"). Multi-word phrases
        use substring matching (safe because spaces act as boundaries).
        """
        if keyword in self._single_word_patterns:
            return bool(self._single_word_patterns[keyword].search(text_lower))
        return keyword in text_lower

    def _get_category_name(self, category_code: str) -> str:
        """Get full category name from code"""
        mapping = {'E': 'environmental', 'S': 'social', 'G': 'governance'}
        return mapping.get(category_code, 'unknown')

    def add_custom_keywords(self, category: str, sentiment: str, keywords: List[str]):
        """
        Add custom keywords to detector

        Args:
            category: 'environmental', 'social', or 'governance'
            sentiment: 'positive' or 'negative'
            keywords: List of keywords to add
        """
        if category in self.keywords and sentiment in self.keywords[category]:
            self.keywords[category][sentiment].extend(keywords)


class MLESGEventDetector:
    """
    Transformer-based ESG event classifier using FinBERT or ESG-BERT
    """

    def __init__(self, model_name: str = 'yiyanghkust/finbert-esg'):
        """
        Initialize ML-based event detector

        Args:
            model_name: HuggingFace model name
                       Options: 'yiyanghkust/finbert-esg', 'ProsusAI/finbert'
        """
        if not TRANSFORMERS_AVAILABLE:
            raise ImportError("transformers package required for ML event detection")

        self.model_name = model_name
        self.device = 'cuda' if torch.cuda.is_available() else 'cpu'

        print(f"Loading model {model_name} on {self.device}...")

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
            self.model.to(self.device)
            self.model.eval()
            print("Model loaded successfully!")
        except Exception as e:
            print(f"Error loading model: {e}")
            print("Falling back to rule-based detection")
            self.model = None
            self.tokenizer = None

    def predict(self, text: str, max_length: int = 512) -> Dict[str, float]:
        """
        Classify text into ESG categories

        Args:
            text: Text to classify
            max_length: Maximum token length

        Returns:
            Dictionary with probabilities for each category
        """
        if self.model is None or self.tokenizer is None:
            # Fallback to rule-based
            detector = ESGEventDetector()
            result = detector.detect_event(text)
            if result['has_event']:
                category = result['category_full']
                return {
                    'environmental': 1.0 if category == 'environmental' else 0.0,
                    'social': 1.0 if category == 'social' else 0.0,
                    'governance': 1.0 if category == 'governance' else 0.0,
                    'none': 0.0
                }
            else:
                return {'environmental': 0.0, 'social': 0.0, 'governance': 0.0, 'none': 1.0}

        try:
            inputs = self.tokenizer(
                text,
                return_tensors='pt',
                truncation=True,
                max_length=max_length,
                padding=True
            )

            # Move inputs to device
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self.model(**inputs)
                probs = torch.softmax(outputs.logits, dim=1)

            # Get probabilities
            probs = probs.cpu().numpy()[0]

            # Map to category names
            # Note: Actual label mapping depends on the specific model
            if len(probs) == 4:
                return {
                    'environmental': float(probs[0]),
                    'social': float(probs[1]),
                    'governance': float(probs[2]),
                    'none': float(probs[3])
                }
            elif len(probs) == 3:
                return {
                    'environmental': float(probs[0]),
                    'social': float(probs[1]),
                    'governance': float(probs[2]),
                    'none': 0.0
                }
            else:
                # Fallback
                return {'environmental': 0.33, 'social': 0.33, 'governance': 0.34, 'none': 0.0}

        except Exception as e:
            print(f"Error in prediction: {e}")
            return {'environmental': 0.0, 'social': 0.0, 'governance': 0.0, 'none': 1.0}

    def detect_event(self, text: str, threshold: float = 0.6) -> Dict:
        """
        Detect ESG event using ML model

        Args:
            text: Text to analyze
            threshold: Confidence threshold

        Returns:
            Detection result dictionary
        """
        probs = self.predict(text)

        # Find max category
        max_category = max(probs, key=probs.get)
        max_prob = probs[max_category]

        if max_prob < threshold or max_category == 'none':
            return {'has_event': False}

        return {
            'has_event': True,
            'category': max_category[0].upper(),
            'category_full': max_category,
            'confidence': max_prob,
            'probabilities': probs
        }
