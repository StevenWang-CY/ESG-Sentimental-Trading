"""
ESG-Sensitive Universe
Identifies companies most sensitive to ESG events and sentiment
"""

import pandas as pd
from typing import List, Dict, Optional


class ESGSensitiveUniverse:
    """
    Manages ESG-sensitive stock universes
    Focuses on companies where ESG events have material impact
    """

    # ESG-SENSITIVE SECTORS (High impact from ESG events)
    ESG_SENSITIVE_SECTORS = {
        'Energy': {
            'sensitivity': 'VERY HIGH',
            'reasons': ['Carbon emissions', 'Climate regulation', 'Renewable transition'],
            'subsectors': ['Oil & Gas', 'Coal', 'Renewable Energy', 'Utilities']
        },
        'Materials': {
            'sensitivity': 'VERY HIGH',
            'reasons': ['Environmental impact', 'Resource extraction', 'Pollution'],
            'subsectors': ['Mining', 'Chemicals', 'Metals', 'Paper & Forest']
        },
        'Consumer Discretionary': {
            'sensitivity': 'HIGH',
            'reasons': ['Labor practices', 'Supply chain ethics', 'Brand reputation'],
            'subsectors': ['Retail', 'Apparel', 'Automotive', 'Restaurants']
        },
        'Industrials': {
            'sensitivity': 'HIGH',
            'reasons': ['Emissions', 'Workplace safety', 'Defense ethics'],
            'subsectors': ['Aerospace', 'Construction', 'Transportation', 'Defense']
        },
        'Financials': {
            'sensitivity': 'MEDIUM-HIGH',
            'reasons': ['ESG investing', 'Fossil fuel financing', 'Diversity'],
            'subsectors': ['Banks', 'Insurance', 'Asset Management']
        },
        'Healthcare': {
            'sensitivity': 'MEDIUM',
            'reasons': ['Drug pricing', 'Access to medicine', 'Clinical ethics'],
            'subsectors': ['Pharma', 'Biotech', 'Healthcare Services']
        },
        'Technology': {
            'sensitivity': 'MEDIUM',
            'reasons': ['Data privacy', 'Labor practices', 'E-waste'],
            'subsectors': ['Software', 'Hardware', 'Semiconductors']
        }
    }

    # ESG-FOCUSED NASDAQ-100 COMPANIES (Most likely to be affected by ESG events)
    ESG_SENSITIVE_NASDAQ100 = {
        # Energy & Utilities (VERY HIGH sensitivity)
        'energy': ['XEL', 'CEG', 'EXC', 'AEP'],  # Utilities with climate exposure

        # Materials & Chemicals (VERY HIGH sensitivity)
        'materials': ['LIN', 'HON'],  # Industrial chemicals, emissions

        # Consumer Discretionary (HIGH sensitivity)
        'consumer': [
            'TSLA',   # EV leader, labor issues, environmental claims
            'AMZN',   # Labor practices, carbon footprint, packaging
            'SBUX',   # Supply chain ethics, labor relations
            'NKE',    # Supply chain labor, environmental footprint
            'LULU',   # Supply chain, labor practices
            'ROST',   # Retail labor, sustainability
            'ABNB',   # Community impact, regulation
            'BKNG',   # Carbon footprint, travel sustainability
            'COST',   # Labor practices, supplier ethics
            'MAR',    # Environmental impact, labor
            'WBD',    # Content ethics, diversity
        ],

        # Industrials (HIGH sensitivity)
        'industrials': [
            'BA',     # Aerospace emissions, safety
            'HON',    # Industrial emissions
            'ADP',    # Employment practices
            'PCAR',   # Commercial vehicle emissions
            'ODFL',   # Transportation emissions
            'CTAS',   # Workplace safety
        ],

        # Technology (MEDIUM-HIGH for select companies)
        'tech_esg': [
            'AAPL',   # Supply chain labor, e-waste, privacy
            'MSFT',   # Carbon neutral goals, AI ethics
            'GOOGL',  # Privacy, content moderation, AI ethics
            'META',   # Privacy, content ethics, mental health
            'AMZN',   # Labor, carbon footprint
            'TSLA',   # Environmental claims, labor
            'INTC',   # Manufacturing emissions
            'AMD',    # Manufacturing practices
            'NVDA',   # Energy consumption (AI chips)
            'QCOM',   # Supply chain
        ],

        # Financials (MEDIUM-HIGH)
        'financials': [
            'PYPL',   # Financial inclusion
            'COIN',   # Crypto environmental impact
        ],

        # Healthcare & Pharma (MEDIUM-HIGH)
        'healthcare': [
            'GILD',   # Drug pricing, access to medicine
            'AMGN',   # Drug pricing
            'VRTX',   # Drug pricing, rare disease access
            'REGN',   # Drug pricing
            'BIIB',   # Drug pricing
            'MRNA',   # Vaccine equity
            'ILMN',   # Genetic testing ethics
        ],

        # Food & Beverage (HIGH - supply chain)
        'food': [
            'SBUX',   # Coffee sourcing, labor
            'MNST',   # Health impact, marketing ethics
            'KDP',    # Water usage, packaging
            'MDLZ',   # Supply chain, health
        ],

        # Semiconductors (MEDIUM - water/energy intensive)
        'semis': [
            'NVDA',   # AI chip energy consumption
            'AMD',    # Manufacturing impact
            'INTC',   # Water usage, emissions
            'QCOM',   # Supply chain
            'AVGO',   # Manufacturing
            'MRVL',   # Supply chain
            'NXPI',   # Automotive safety
        ]
    }

    # LOW ESG SENSITIVITY (Exclude or deprioritize)
    LOW_ESG_SECTORS = ['Real Estate', 'Communication Services (some)']

    def __init__(self):
        """Initialize ESG-sensitive universe manager"""
        self.cache = {}

    def get_esg_sensitive_nasdaq100(self, sensitivity_threshold: str = 'MEDIUM') -> List[str]:
        """
        Get NASDAQ-100 stocks most sensitive to ESG events

        Args:
            sensitivity_threshold: 'VERY HIGH', 'HIGH', 'MEDIUM', 'ALL'

        Returns:
            List of ticker symbols
        """
        all_tickers = []

        if sensitivity_threshold in ['VERY HIGH', 'HIGH', 'MEDIUM', 'ALL']:
            # Energy & Materials (VERY HIGH)
            all_tickers.extend(self.ESG_SENSITIVE_NASDAQ100['energy'])
            all_tickers.extend(self.ESG_SENSITIVE_NASDAQ100['materials'])

        if sensitivity_threshold in ['HIGH', 'MEDIUM', 'ALL']:
            # Consumer & Industrials (HIGH)
            all_tickers.extend(self.ESG_SENSITIVE_NASDAQ100['consumer'])
            all_tickers.extend(self.ESG_SENSITIVE_NASDAQ100['industrials'])
            all_tickers.extend(self.ESG_SENSITIVE_NASDAQ100['food'])

        if sensitivity_threshold in ['MEDIUM', 'ALL']:
            # Tech, Healthcare, Financials (MEDIUM-HIGH)
            all_tickers.extend(self.ESG_SENSITIVE_NASDAQ100['tech_esg'])
            all_tickers.extend(self.ESG_SENSITIVE_NASDAQ100['healthcare'])
            all_tickers.extend(self.ESG_SENSITIVE_NASDAQ100['financials'])
            all_tickers.extend(self.ESG_SENSITIVE_NASDAQ100['semis'])

        # Remove duplicates and sort
        tickers = sorted(list(set(all_tickers)))

        print(f"\nESG-Sensitive NASDAQ-100 (threshold: {sensitivity_threshold})")
        print(f"Total tickers: {len(tickers)}")

        return tickers

    def get_sector_breakdown(self, tickers: List[str]) -> Dict:
        """
        Get sector breakdown of ticker list

        Returns:
            Dictionary with sector counts
        """
        breakdown = {
            'Energy & Utilities': [],
            'Materials': [],
            'Consumer': [],
            'Industrials': [],
            'Technology': [],
            'Healthcare': [],
            'Financials': [],
            'Food & Beverage': [],
            'Semiconductors': []
        }

        for ticker in tickers:
            for category, category_tickers in self.ESG_SENSITIVE_NASDAQ100.items():
                if ticker in category_tickers:
                    if category == 'energy':
                        breakdown['Energy & Utilities'].append(ticker)
                    elif category == 'materials':
                        breakdown['Materials'].append(ticker)
                    elif category == 'consumer':
                        breakdown['Consumer'].append(ticker)
                    elif category == 'industrials':
                        breakdown['Industrials'].append(ticker)
                    elif category == 'tech_esg':
                        breakdown['Technology'].append(ticker)
                    elif category == 'healthcare':
                        breakdown['Healthcare'].append(ticker)
                    elif category == 'financials':
                        breakdown['Financials'].append(ticker)
                    elif category == 'food':
                        breakdown['Food & Beverage'].append(ticker)
                    elif category == 'semis':
                        breakdown['Semiconductors'].append(ticker)

        return breakdown

    def print_universe_summary(self, tickers: List[str]):
        """
        Print summary of ESG-sensitive universe

        Args:
            tickers: List of ticker symbols
        """
        print("\n" + "="*60)
        print("ESG-SENSITIVE UNIVERSE SUMMARY")
        print("="*60)

        breakdown = self.get_sector_breakdown(tickers)

        for sector, sector_tickers in breakdown.items():
            if sector_tickers:
                print(f"\n{sector} ({len(sector_tickers)} stocks):")
                print(f"  {', '.join(sorted(sector_tickers))}")

        print("\n" + "="*60)
        print(f"TOTAL: {len(tickers)} ESG-sensitive stocks")
        print("="*60)

    def get_esg_keywords_by_sector(self, sector: str) -> List[str]:
        """
        Get relevant ESG keywords for a specific sector

        Args:
            sector: Sector name

        Returns:
            List of relevant ESG keywords
        """
        keyword_map = {
            'Energy & Utilities': [
                'climate', 'carbon emissions', 'fossil fuel', 'renewable energy',
                'net zero', 'greenhouse gas', 'coal', 'oil spill', 'fracking'
            ],
            'Materials': [
                'pollution', 'toxic waste', 'mining', 'deforestation',
                'water usage', 'recycling', 'circular economy'
            ],
            'Consumer': [
                'labor practices', 'supply chain', 'fair trade', 'sweatshop',
                'child labor', 'working conditions', 'union', 'wages'
            ],
            'Industrials': [
                'workplace safety', 'emissions', 'industrial accident',
                'labor union', 'manufacturing practices'
            ],
            'Technology': [
                'data privacy', 'surveillance', 'AI ethics', 'e-waste',
                'conflict minerals', 'labor practices', 'diversity'
            ],
            'Healthcare': [
                'drug pricing', 'access to medicine', 'clinical trial ethics',
                'patient safety', 'vaccine equity'
            ],
            'Financials': [
                'fossil fuel financing', 'ESG investing', 'predatory lending',
                'diversity', 'executive compensation'
            ],
            'Food & Beverage': [
                'sustainable sourcing', 'fair trade', 'water usage',
                'packaging waste', 'health impact', 'supply chain'
            ]
        }

        return keyword_map.get(sector, [])

    def get_high_impact_tickers(self, min_market_cap: float = 10e9) -> List[str]:
        """
        Get high-impact ESG-sensitive tickers
        (Large enough to have material ESG events + high sensitivity)

        Args:
            min_market_cap: Minimum market cap in USD (default $10B)

        Returns:
            List of ticker symbols
        """
        # These are the "core" ESG-sensitive stocks with:
        # 1. High ESG sensitivity
        # 2. Large market cap (gets media/Twitter attention)
        # 3. Frequent ESG events

        core_tickers = [
            # Mega-cap with high ESG visibility
            'TSLA',   # EV, labor, Musk tweets, environmental claims
            'AAPL',   # Supply chain labor, privacy, e-waste
            'AMZN',   # Labor practices, carbon footprint
            'META',   # Privacy, content moderation, mental health
            'GOOGL',  # Privacy, AI ethics, antitrust
            'MSFT',   # AI ethics, carbon goals

            # Energy & Climate (VERY HIGH)
            'XEL', 'CEG', 'EXC',  # Utilities facing climate pressure

            # Consumer brands (HIGH - brand reputation matters)
            'SBUX',   # Labor, supply chain
            'NKE',    # Supply chain labor
            'COST',   # Labor practices

            # Healthcare (Drug pricing = major ESG issue)
            'GILD', 'AMGN', 'VRTX', 'MRNA',

            # Semis (Energy intensive, supply chain)
            'NVDA', 'INTC', 'AMD',

            # Industrials
            'HON', 'PCAR',
        ]

        return core_tickers

    def get_esg_risk_profile(self, ticker: str) -> Dict:
        """
        Get ESG risk profile for a ticker

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dictionary with ESG risk assessment
        """
        # Map tickers to risk profiles
        high_risk_profile = {
            'primary_risks': [],
            'sensitivity': 'HIGH',
            'event_frequency': 'HIGH',
            'twitter_volume': 'HIGH'
        }

        profiles = {
            'TSLA': {
                'primary_risks': ['Labor practices', 'Environmental claims', 'CEO controversy'],
                'sensitivity': 'VERY HIGH',
                'event_frequency': 'VERY HIGH',
                'twitter_volume': 'EXTREMELY HIGH'
            },
            'AAPL': {
                'primary_risks': ['Supply chain labor', 'Privacy', 'E-waste', 'Tax avoidance'],
                'sensitivity': 'HIGH',
                'event_frequency': 'MEDIUM',
                'twitter_volume': 'VERY HIGH'
            },
            'AMZN': {
                'primary_risks': ['Labor practices', 'Carbon footprint', 'Market power'],
                'sensitivity': 'VERY HIGH',
                'event_frequency': 'HIGH',
                'twitter_volume': 'VERY HIGH'
            },
            'META': {
                'primary_risks': ['Privacy', 'Content moderation', 'Mental health', 'Misinformation'],
                'sensitivity': 'VERY HIGH',
                'event_frequency': 'VERY HIGH',
                'twitter_volume': 'VERY HIGH'
            },
            'SBUX': {
                'primary_risks': ['Labor relations', 'Supply chain ethics', 'Tax practices'],
                'sensitivity': 'HIGH',
                'event_frequency': 'HIGH',
                'twitter_volume': 'HIGH'
            },
            'GILD': {
                'primary_risks': ['Drug pricing', 'Access to medicine', 'R&D ethics'],
                'sensitivity': 'HIGH',
                'event_frequency': 'MEDIUM',
                'twitter_volume': 'MEDIUM'
            }
        }

        return profiles.get(ticker, high_risk_profile)
