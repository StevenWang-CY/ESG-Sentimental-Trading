"""
ESG-Specific Sentiment Dictionaries
Domain-specific sentiment lexicons for ESG analysis

Based on Loughran-McDonald approach but tailored for ESG language:
- Environmental sentiment words
- Social sentiment words
- Governance sentiment words
- ESG-specific positive/negative terms
"""

from typing import Dict, List, Set
import json
import os


class ESGSentimentDictionaries:
    """
    ESG-specific sentiment dictionaries
    Extends beyond general financial sentiment to capture ESG-specific language
    """

    def __init__(self):
        """Initialize ESG sentiment dictionaries"""
        self.dictionaries = {
            'environmental': self._get_environmental_sentiment(),
            'social': self._get_social_sentiment(),
            'governance': self._get_governance_sentiment(),
            'general_esg': self._get_general_esg_sentiment()
        }

    def _get_environmental_sentiment(self) -> Dict[str, Set[str]]:
        """Environmental sentiment words"""
        return {
            'positive': {
                # Climate & Carbon
                'carbon neutral', 'net zero', 'carbon negative', 'decarbonization',
                'emissions reduction', 'climate action', 'climate positive',
                'carbon offset', 'carbon capture', 'carbon reduction',

                # Renewable Energy
                'renewable energy', 'clean energy', 'solar power', 'wind power',
                'green energy', 'sustainable energy', 'energy efficiency',
                'renewable', 'clean', 'green', 'sustainable',

                # Environmental Practices
                'recycling', 'circular economy', 'zero waste', 'waste reduction',
                'biodiversity', 'conservation', 'ecosystem restoration',
                'environmental stewardship', 'sustainable practices',
                'eco-friendly', 'environmentally responsible',

                # Certifications & Recognition
                'LEED certified', 'environmental award', 'green certification',
                'sustainability certification', 'environmental leadership',
                'carbon disclosure', 'CDP score', 'climate leadership',

                # Water & Resources
                'water conservation', 'resource efficiency', 'sustainable sourcing',
                'responsible sourcing', 'sustainable supply chain',

                # Positive Actions
                'reforestation', 'habitat restoration', 'pollution prevention',
                'environmental innovation', 'green technology', 'cleantech',
                'environmental improvement', 'sustainability initiative'
            },

            'negative': {
                # Pollution & Emissions
                'pollution', 'emissions scandal', 'carbon emissions', 'toxic emissions',
                'air pollution', 'water pollution', 'soil contamination',
                'environmental contamination', 'pollutant', 'greenhouse gas',
                'methane leak', 'oil spill', 'chemical spill',

                # Violations & Penalties
                'environmental fine', 'EPA violation', 'environmental violation',
                'environmental penalty', 'environmental lawsuit', 'climate lawsuit',
                'environmental damage', 'ecological damage',
                'environmental crime', 'environmental negligence',

                # Waste & Hazards
                'toxic waste', 'hazardous waste', 'waste dumping',
                'plastic pollution', 'ocean pollution', 'deforestation',
                'habitat destruction', 'biodiversity loss', 'species extinction',

                # Climate Issues
                'climate risk', 'climate change denial', 'environmental disaster',
                'environmental catastrophe', 'ecological crisis',
                'carbon intensive', 'fossil fuel', 'coal',

                # Practices
                'greenwashing', 'environmental misrepresentation',
                'unsustainable practices', 'environmental irresponsibility',
                'overconsumption', 'resource depletion', 'overfishing',

                # Specific Issues
                'fracking', 'offshore drilling', 'arctic drilling',
                'rainforest destruction', 'wetland destruction',
                'air quality violation', 'water contamination'
            }
        }

    def _get_social_sentiment(self) -> Dict[str, Set[str]]:
        """Social sentiment words"""
        return {
            'positive': {
                # Diversity & Inclusion
                'diversity', 'inclusion', 'equity', 'diverse workforce',
                'gender diversity', 'board diversity', 'racial diversity',
                'inclusive workplace', 'equal opportunity', 'pay equity',
                'equal pay', 'wage equity', 'fair compensation',

                # Employee Wellbeing
                'employee wellbeing', 'employee wellness', 'work-life balance',
                'mental health support', 'employee benefits', 'healthcare benefits',
                'parental leave', 'paid leave', 'flexible work',
                'employee satisfaction', 'employee engagement',
                'workplace culture', 'employee retention',

                # Labor Rights
                'fair wages', 'living wage', 'labor rights', 'worker rights',
                'union recognition', 'collective bargaining', 'worker safety',
                'workplace safety', 'safe working conditions',
                'safety certification', 'safety improvement',

                # Community & Society
                'community investment', 'social impact', 'community development',
                'charitable giving', 'philanthropy', 'social responsibility',
                'community program', 'social program', 'stakeholder engagement',
                'local hiring', 'community support',

                # Human Rights
                'human rights', 'fair trade', 'ethical sourcing',
                'supply chain transparency', 'responsible supply chain',
                'anti-trafficking', 'labor standards',

                # Product & Access
                'product safety', 'consumer protection', 'accessible products',
                'affordable healthcare', 'financial inclusion',
                'digital inclusion', 'social equity'
            },

            'negative': {
                # Discrimination & Harassment
                'discrimination', 'racial discrimination', 'gender discrimination',
                'age discrimination', 'harassment', 'sexual harassment',
                'workplace harassment', 'hostile workplace', 'discrimination lawsuit',
                'bias', 'prejudice', 'inequality', 'inequity',

                # Labor Issues
                'labor dispute', 'strike', 'walkout', 'labor violation',
                'wage theft', 'unpaid overtime', 'unfair labor practice',
                'worker exploitation', 'sweatshop', 'child labor',
                'forced labor', 'modern slavery', 'labor abuse',

                # Safety Issues
                'workplace accident', 'safety violation', 'unsafe conditions',
                'worker injury', 'workplace fatality', 'OSHA violation',
                'safety hazard', 'workplace danger',

                # Employment Practices
                'layoff', 'mass layoff', 'workforce reduction',
                'union busting', 'anti-union', 'worker intimidation',
                'retaliation', 'wrongful termination',

                # Human Rights
                'human rights violation', 'human rights abuse',
                'supply chain abuse', 'supplier misconduct',
                'child labor scandal', 'forced labor',

                # Data & Privacy
                'data breach', 'privacy violation', 'data leak',
                'privacy scandal', 'surveillance', 'data misuse',
                'customer data compromise', 'security breach',

                # Product Issues
                'product recall', 'safety recall', 'defective product',
                'product liability', 'consumer harm', 'health hazard',

                # Community Impact
                'community harm', 'displacement', 'gentrification',
                'negative social impact', 'social harm'
            }
        }

    def _get_governance_sentiment(self) -> Dict[str, Set[str]]:
        """Governance sentiment words"""
        return {
            'positive': {
                # Board & Leadership
                'board independence', 'independent board', 'board diversity',
                'diverse board', 'board accountability', 'board effectiveness',
                'strong governance', 'corporate governance', 'good governance',
                'governance excellence', 'leadership transparency',

                # Transparency & Disclosure
                'transparency', 'disclosure', 'reporting transparency',
                'financial transparency', 'ESG disclosure', 'climate disclosure',
                'materiality assessment', 'stakeholder disclosure',

                # Ethics & Compliance
                'ethics program', 'code of conduct', 'ethical leadership',
                'compliance program', 'anti-corruption', 'anti-bribery',
                'whistleblower protection', 'ethics training',
                'compliance culture', 'ethical business practices',

                # Shareholder Rights
                'shareholder rights', 'shareholder engagement',
                'voting rights', 'proxy access', 'shareholder democracy',
                'shareholder value', 'investor relations',

                # Accountability
                'accountability', 'responsible leadership', 'fiduciary duty',
                'board oversight', 'risk oversight', 'internal controls',
                'audit committee', 'independent audit',

                # Executive Compensation
                'pay for performance', 'reasonable compensation',
                'compensation alignment', 'clawback provision',
                'say on pay', 'compensation disclosure'
            },

            'negative': {
                # Fraud & Corruption
                'fraud', 'accounting fraud', 'financial fraud',
                'securities fraud', 'corruption', 'bribery',
                'embezzlement', 'kickback', 'money laundering',
                'tax evasion', 'insider trading', 'market manipulation',

                # Violations & Investigations
                'SEC investigation', 'regulatory investigation',
                'DOJ investigation', 'criminal investigation',
                'accounting scandal', 'financial scandal',
                'governance scandal', 'regulatory violation',
                'compliance violation', 'legal violation',

                # Misconduct
                'executive misconduct', 'management misconduct',
                'director misconduct', 'board misconduct',
                'conflict of interest', 'self-dealing', 'related party transaction',
                'nepotism', 'cronyism',

                # Financial Issues
                'financial restatement', 'accounting irregularity',
                'audit failure', 'internal control weakness',
                'material weakness', 'financial misstatement',
                'earnings manipulation', 'revenue recognition issue',

                # Governance Failures
                'governance failure', 'board failure', 'oversight failure',
                'lack of independence', 'entrenched board',
                'staggered board', 'poison pill', 'takeover defense',

                # Compensation Issues
                'excessive compensation', 'executive excess',
                'golden parachute', 'compensation scandal',
                'pay disparity', 'CEO pay ratio',

                # Legal Issues
                'shareholder lawsuit', 'derivative lawsuit',
                'class action', 'securities litigation',
                'regulatory penalty', 'consent decree',
                'deferred prosecution', 'settlement',

                # Transparency Issues
                'lack of disclosure', 'opacity', 'hidden risks',
                'insufficient disclosure', 'misleading disclosure',
                'greenwashing', 'social washing'
            }
        }

    def _get_general_esg_sentiment(self) -> Dict[str, Set[str]]:
        """General ESG sentiment words (cross-cutting)"""
        return {
            'positive': {
                # General ESG Positive
                'sustainable', 'sustainability', 'responsible', 'ethical',
                'stakeholder', 'long-term value', 'resilient', 'resilience',
                'innovation', 'improvement', 'progress', 'advancement',
                'leadership', 'excellence', 'commitment', 'initiative',
                'achievement', 'recognition', 'award', 'certification',
                'best practices', 'industry leader', 'outperform',
                'positive impact', 'value creation', 'risk management',

                # ESG Strategy
                'ESG strategy', 'ESG goals', 'ESG commitment',
                'ESG performance', 'ESG improvement', 'ESG leadership',
                'ESG integration', 'ESG materiality', 'ESG reporting',

                # Stakeholder Focus
                'stakeholder engagement', 'stakeholder value',
                'multi-stakeholder', 'stakeholder capitalism',

                # Future Orientation
                'future-ready', 'forward-thinking', 'transformative',
                'regenerative', 'restorative'
            },

            'negative': {
                # General ESG Negative
                'controversy', 'scandal', 'violation', 'penalty',
                'lawsuit', 'litigation', 'fine', 'settlement',
                'negligence', 'misconduct', 'abuse', 'harm',
                'risk', 'material risk', 'reputational risk',
                'regulatory risk', 'legal risk', 'ESG risk',

                # Performance Issues
                'underperformance', 'failure', 'declining',
                'deterioration', 'weakness', 'shortcoming',
                'inadequate', 'insufficient', 'poor performance',

                # Controversy & Criticism
                'criticism', 'activist', 'protest', 'boycott',
                'opposition', 'resistance', 'backlash',
                'controversial', 'disputed', 'questioned',

                # ESG Issues
                'ESG controversy', 'ESG failure', 'ESG concern',
                'ESG criticism', 'ESG risk', 'ESG shortfall',
                'lack of ESG', 'ESG laggard', 'ESG underperformance'
            }
        }

    def get_all_positive_words(self, category: str = 'all') -> Set[str]:
        """
        Get all positive sentiment words for a category

        Args:
            category: 'environmental', 'social', 'governance', 'general_esg', or 'all'

        Returns:
            Set of positive sentiment words
        """
        if category == 'all':
            words = set()
            for cat_dict in self.dictionaries.values():
                words.update(cat_dict['positive'])
            return words
        elif category in self.dictionaries:
            return self.dictionaries[category]['positive']
        else:
            return set()

    def get_all_negative_words(self, category: str = 'all') -> Set[str]:
        """
        Get all negative sentiment words for a category

        Args:
            category: 'environmental', 'social', 'governance', 'general_esg', or 'all'

        Returns:
            Set of negative sentiment words
        """
        if category == 'all':
            words = set()
            for cat_dict in self.dictionaries.values():
                words.update(cat_dict['negative'])
            return words
        elif category in self.dictionaries:
            return self.dictionaries[category]['negative']
        else:
            return set()

    def score_text(self, text: str, category: str = 'all') -> Dict[str, float]:
        """
        Score text using ESG sentiment dictionaries

        Args:
            text: Input text
            category: ESG category to score

        Returns:
            Dictionary with sentiment scores
        """
        text_lower = text.lower()

        positive_words = self.get_all_positive_words(category)
        negative_words = self.get_all_negative_words(category)

        # Count positive and negative words/phrases
        n_positive = sum(1 for word in positive_words if word in text_lower)
        n_negative = sum(1 for word in negative_words if word in text_lower)

        # Calculate scores
        total_sentiment_words = n_positive + n_negative

        if total_sentiment_words == 0:
            polarity = 0.0
            subjectivity = 0.0
        else:
            polarity = (n_positive - n_negative) / total_sentiment_words
            subjectivity = total_sentiment_words / max(len(text.split()), 1)

        return {
            'polarity': polarity,  # -1 (negative) to +1 (positive)
            'subjectivity': subjectivity,  # 0 (objective) to 1 (subjective)
            'n_positive': n_positive,
            'n_negative': n_negative,
            'n_total_sentiment': total_sentiment_words
        }

    def get_matched_words(self, text: str, category: str = 'all') -> Dict[str, List[str]]:
        """
        Get actual matched sentiment words from text

        Args:
            text: Input text
            category: ESG category

        Returns:
            Dictionary with matched positive and negative words
        """
        text_lower = text.lower()

        positive_words = self.get_all_positive_words(category)
        negative_words = self.get_all_negative_words(category)

        matched_positive = [word for word in positive_words if word in text_lower]
        matched_negative = [word for word in negative_words if word in text_lower]

        return {
            'positive': matched_positive,
            'negative': matched_negative
        }

    def save_to_json(self, filepath: str):
        """Save dictionaries to JSON file"""
        # Convert sets to lists for JSON serialization
        json_dict = {}
        for category, sentiments in self.dictionaries.items():
            json_dict[category] = {
                'positive': list(sentiments['positive']),
                'negative': list(sentiments['negative'])
            }

        with open(filepath, 'w') as f:
            json.dump(json_dict, f, indent=2)

        print(f"ESG sentiment dictionaries saved to {filepath}")

    def load_from_json(self, filepath: str):
        """Load dictionaries from JSON file"""
        with open(filepath, 'r') as f:
            json_dict = json.load(f)

        # Convert lists back to sets
        self.dictionaries = {}
        for category, sentiments in json_dict.items():
            self.dictionaries[category] = {
                'positive': set(sentiments['positive']),
                'negative': set(sentiments['negative'])
            }

        print(f"ESG sentiment dictionaries loaded from {filepath}")

    def print_summary(self):
        """Print summary of dictionaries"""
        print("\n" + "="*70)
        print("ESG SENTIMENT DICTIONARIES SUMMARY")
        print("="*70)

        for category, sentiments in self.dictionaries.items():
            n_pos = len(sentiments['positive'])
            n_neg = len(sentiments['negative'])
            total = n_pos + n_neg

            print(f"\n{category.upper().replace('_', ' ')}:")
            print(f"  Positive words: {n_pos}")
            print(f"  Negative words: {n_neg}")
            print(f"  Total: {total}")

        # Overall totals
        all_pos = self.get_all_positive_words('all')
        all_neg = self.get_all_negative_words('all')

        print(f"\nTOTAL (all categories):")
        print(f"  Positive words: {len(all_pos)}")
        print(f"  Negative words: {len(all_neg)}")
        print(f"  Total: {len(all_pos) + len(all_neg)}")
        print("="*70)


def create_esg_dictionaries_json():
    """Helper function to create and save ESG dictionaries to JSON"""
    esg_dict = ESGSentimentDictionaries()

    # Create config directory if it doesn't exist
    config_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'config')
    os.makedirs(config_dir, exist_ok=True)

    # Save to JSON
    filepath = os.path.join(config_dir, 'esg_sentiment_dictionaries.json')
    esg_dict.save_to_json(filepath)
    esg_dict.print_summary()

    return filepath


if __name__ == '__main__':
    # Create and save ESG sentiment dictionaries
    filepath = create_esg_dictionaries_json()
    print(f"\nESG sentiment dictionaries created and saved to: {filepath}")
