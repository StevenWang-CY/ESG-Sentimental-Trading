"""
Feature Selection Module
Implements feature selection to avoid curse of dimensionality

Key insight from Savarese (2019) thesis:
- Temporal indicators (10 features) outperformed technical indicators (22 features)
- Combined approach (37 features) performed WORSE than temporal alone
- Feature quality > feature quantity

Implements multiple feature selection strategies:
1. Correlation-based selection
2. Mutual information
3. Random Forest importance
4. Sequential feature selection
5. Variance threshold
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional, Set
from sklearn.feature_selection import (
    mutual_info_regression,
    SelectKBest,
    VarianceThreshold,
    RFE
)
from sklearn.ensemble import RandomForestRegressor
from scipy.stats import spearmanr
import warnings
warnings.filterwarnings('ignore')


class FeatureSelector:
    """
    Feature selection for trading signal models
    Prevents curse of dimensionality by selecting most informative features
    """

    def __init__(self, max_features: int = 15):
        """
        Initialize feature selector

        Args:
            max_features: Maximum number of features to select (default 15, close to thesis optimal of 10-11)
        """
        self.max_features = max_features
        self.selected_features: List[str] = []
        self.feature_scores: Dict[str, float] = {}
        self.selection_method = None

    def select_by_correlation(self,
                             X: pd.DataFrame,
                             y: pd.Series,
                             method: str = 'spearman') -> List[str]:
        """
        Select features by correlation with target

        Args:
            X: Feature matrix
            y: Target variable
            method: 'pearson' or 'spearman'

        Returns:
            List of selected feature names
        """
        print(f"\nFeature selection by {method} correlation...")

        correlations = {}

        for col in X.columns:
            try:
                if method == 'pearson':
                    corr = np.corrcoef(X[col].fillna(0), y)[0, 1]
                else:  # spearman
                    corr, _ = spearmanr(X[col].fillna(0), y)

                correlations[col] = abs(corr)  # Use absolute correlation
            except:
                correlations[col] = 0.0

        # Sort by correlation
        sorted_features = sorted(correlations.items(), key=lambda x: x[1], reverse=True)

        # Select top features
        self.selected_features = [f for f, _ in sorted_features[:self.max_features]]
        self.feature_scores = dict(sorted_features)
        self.selection_method = f'{method}_correlation'

        print(f"Selected {len(self.selected_features)} features")
        self._print_top_features()

        return self.selected_features

    def select_by_mutual_information(self,
                                     X: pd.DataFrame,
                                     y: pd.Series) -> List[str]:
        """
        Select features by mutual information with target

        Args:
            X: Feature matrix
            y: Target variable

        Returns:
            List of selected feature names
        """
        print("\nFeature selection by mutual information...")

        # Fill NaN values
        X_filled = X.fillna(0)

        # Calculate mutual information
        mi_scores = mutual_info_regression(X_filled, y, random_state=42)

        # Create feature scores dictionary
        self.feature_scores = dict(zip(X.columns, mi_scores))

        # Sort by MI score
        sorted_features = sorted(self.feature_scores.items(), key=lambda x: x[1], reverse=True)

        # Select top features
        self.selected_features = [f for f, _ in sorted_features[:self.max_features]]
        self.selection_method = 'mutual_information'

        print(f"Selected {len(self.selected_features)} features")
        self._print_top_features()

        return self.selected_features

    def select_by_random_forest(self,
                                X: pd.DataFrame,
                                y: pd.Series,
                                n_estimators: int = 100) -> List[str]:
        """
        Select features by Random Forest importance

        Args:
            X: Feature matrix
            y: Target variable
            n_estimators: Number of trees in forest

        Returns:
            List of selected feature names
        """
        print("\nFeature selection by Random Forest importance...")

        # Fill NaN values
        X_filled = X.fillna(0)

        # Train Random Forest
        rf = RandomForestRegressor(
            n_estimators=n_estimators,
            max_depth=10,
            random_state=42,
            n_jobs=-1
        )
        rf.fit(X_filled, y)

        # Get feature importances
        self.feature_scores = dict(zip(X.columns, rf.feature_importances_))

        # Sort by importance
        sorted_features = sorted(self.feature_scores.items(), key=lambda x: x[1], reverse=True)

        # Select top features
        self.selected_features = [f for f, _ in sorted_features[:self.max_features]]
        self.selection_method = 'random_forest_importance'

        print(f"Selected {len(self.selected_features)} features")
        self._print_top_features()

        return self.selected_features

    def select_by_rfe(self,
                     X: pd.DataFrame,
                     y: pd.Series,
                     n_features: Optional[int] = None) -> List[str]:
        """
        Select features by Recursive Feature Elimination

        Args:
            X: Feature matrix
            y: Target variable
            n_features: Number of features to select (default: self.max_features)

        Returns:
            List of selected feature names
        """
        print("\nFeature selection by Recursive Feature Elimination...")

        n_features = n_features or self.max_features

        # Fill NaN values
        X_filled = X.fillna(0)

        # Use Random Forest as base estimator
        estimator = RandomForestRegressor(
            n_estimators=50,
            max_depth=5,
            random_state=42,
            n_jobs=-1
        )

        # RFE
        rfe = RFE(estimator, n_features_to_select=n_features, step=1)
        rfe.fit(X_filled, y)

        # Get selected features
        self.selected_features = [col for col, selected in zip(X.columns, rfe.support_) if selected]

        # Get feature rankings
        self.feature_scores = dict(zip(X.columns, 1.0 / rfe.ranking_))  # Inverse rank as score
        self.selection_method = 'recursive_feature_elimination'

        print(f"Selected {len(self.selected_features)} features")
        self._print_top_features()

        return self.selected_features

    def select_by_variance_threshold(self,
                                     X: pd.DataFrame,
                                     threshold: float = 0.01) -> List[str]:
        """
        Remove features with low variance

        Args:
            X: Feature matrix
            threshold: Variance threshold

        Returns:
            List of selected feature names
        """
        print(f"\nFeature selection by variance threshold ({threshold})...")

        # Fill NaN values
        X_filled = X.fillna(0)

        # Calculate variances
        variances = X_filled.var()

        # Select features above threshold
        selected = variances[variances > threshold].index.tolist()

        # If too many features, select top by variance
        if len(selected) > self.max_features:
            sorted_features = variances.sort_values(ascending=False)
            selected = sorted_features.head(self.max_features).index.tolist()

        self.selected_features = selected
        self.feature_scores = variances.to_dict()
        self.selection_method = 'variance_threshold'

        print(f"Selected {len(self.selected_features)} features")

        return self.selected_features

    def select_by_collinearity_removal(self,
                                       X: pd.DataFrame,
                                       y: pd.Series,
                                       threshold: float = 0.8) -> List[str]:
        """
        Remove highly correlated features (keep most predictive)

        Args:
            X: Feature matrix
            y: Target variable
            threshold: Correlation threshold for removal

        Returns:
            List of selected feature names
        """
        print(f"\nRemoving collinear features (threshold: {threshold})...")

        # Calculate feature correlations
        X_filled = X.fillna(0)
        corr_matrix = X_filled.corr().abs()

        # Calculate target correlations
        target_corrs = {}
        for col in X.columns:
            target_corrs[col] = abs(np.corrcoef(X_filled[col], y)[0, 1])

        # Find collinear pairs
        upper = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))

        # For each pair of collinear features, keep the one more correlated with target
        to_drop = set()

        for col in upper.columns:
            correlated = upper[col][upper[col] > threshold].index.tolist()

            for corr_col in correlated:
                # Keep the feature with higher target correlation
                if target_corrs[col] > target_corrs[corr_col]:
                    to_drop.add(corr_col)
                else:
                    to_drop.add(col)

        # Selected features
        selected = [col for col in X.columns if col not in to_drop]

        # If still too many, select by target correlation
        if len(selected) > self.max_features:
            selected_corrs = {col: target_corrs[col] for col in selected}
            sorted_features = sorted(selected_corrs.items(), key=lambda x: x[1], reverse=True)
            selected = [f for f, _ in sorted_features[:self.max_features]]

        self.selected_features = selected
        self.feature_scores = target_corrs
        self.selection_method = 'collinearity_removal'

        print(f"Removed {len(to_drop)} collinear features")
        print(f"Selected {len(self.selected_features)} features")
        self._print_top_features()

        return self.selected_features

    def select_ensemble(self,
                       X: pd.DataFrame,
                       y: pd.Series,
                       min_votes: int = 2) -> List[str]:
        """
        Ensemble feature selection: select features chosen by multiple methods

        Args:
            X: Feature matrix
            y: Target variable
            min_votes: Minimum number of methods that must select a feature

        Returns:
            List of selected feature names
        """
        print("\nEnsemble feature selection (voting across methods)...")

        # Run multiple selection methods
        methods = {
            'correlation': self.select_by_correlation,
            'mutual_info': self.select_by_mutual_information,
            'random_forest': self.select_by_random_forest,
            'collinearity': self.select_by_collinearity_removal
        }

        feature_votes = {}

        for method_name, method_func in methods.items():
            print(f"\n  Running {method_name}...")
            selected = method_func(X, y)

            for feature in selected:
                feature_votes[feature] = feature_votes.get(feature, 0) + 1

        # Select features with at least min_votes
        selected = [f for f, votes in feature_votes.items() if votes >= min_votes]

        # If too many, select by votes then by correlation
        if len(selected) > self.max_features:
            # Calculate correlations
            target_corrs = {}
            for col in selected:
                target_corrs[col] = abs(np.corrcoef(X[col].fillna(0), y)[0, 1])

            # Sort by votes, then by correlation
            sorted_features = sorted(
                selected,
                key=lambda f: (feature_votes[f], target_corrs[f]),
                reverse=True
            )
            selected = sorted_features[:self.max_features]

        self.selected_features = selected
        self.feature_scores = {f: float(v) for f, v in feature_votes.items()}
        self.selection_method = 'ensemble_voting'

        print(f"\nFinal ensemble selection: {len(self.selected_features)} features")
        print("\nFeatures by number of votes:")
        for feature in sorted(selected, key=lambda f: feature_votes[f], reverse=True):
            print(f"  {feature}: {feature_votes[feature]} votes")

        return self.selected_features

    def select_thesis_features(self) -> List[str]:
        """
        Select the 11 temporal indicator features from the thesis
        (I_1 through I_11)

        Returns:
            List of thesis feature names
        """
        thesis_features = [
            'TPW',      # I_1: Total Positive Words
            'TNW',      # I_2: Total Negative Words
            'TSPN',     # I_3: Total Single Positive News
            'TSNN',     # I_4: Total Single Negative News
            'TNN',      # I_5: Total Number of News
            'TWN',      # I_6: Total Words in News
            'TNWS',     # I_7: Total News With Sentiment
            'TNPWWHC',  # I_8: Total Neg/Pos Words With Highest Correlation
            'TNNWWHC',  # I_9: Total Neg News Words With Highest Correlation
            'TNPWWLC',  # I_10: Total Neg/Pos Words With Lowest Correlation
            'TNNWWLC'   # I_11: Total Neg News Words With Lowest Correlation
        ]

        self.selected_features = thesis_features
        self.selection_method = 'thesis_temporal_indicators'

        print("\nUsing 11 temporal indicator features from thesis:")
        for i, feature in enumerate(thesis_features, 1):
            print(f"  I_{i}: {feature}")

        return self.selected_features

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Transform feature matrix to keep only selected features

        Args:
            X: Feature matrix

        Returns:
            Transformed feature matrix with selected features
        """
        if not self.selected_features:
            raise ValueError("No features selected. Run a selection method first.")

        # Filter to selected features that exist in X
        available_features = [f for f in self.selected_features if f in X.columns]

        if len(available_features) < len(self.selected_features):
            missing = set(self.selected_features) - set(available_features)
            print(f"Warning: {len(missing)} selected features not found in input: {missing}")

        return X[available_features]

    def _print_top_features(self, n: int = 10):
        """Print top N selected features with scores"""
        if not self.feature_scores:
            return

        sorted_features = sorted(
            [(f, self.feature_scores[f]) for f in self.selected_features],
            key=lambda x: x[1],
            reverse=True
        )

        print(f"\nTop {min(n, len(sorted_features))} selected features:")
        for i, (feature, score) in enumerate(sorted_features[:n], 1):
            print(f"  {i:2d}. {feature:30s} {score:.4f}")

    def get_feature_summary(self) -> pd.DataFrame:
        """
        Get summary of selected features with scores

        Returns:
            DataFrame with feature names and scores
        """
        if not self.selected_features:
            return pd.DataFrame()

        summary = pd.DataFrame({
            'feature': self.selected_features,
            'score': [self.feature_scores.get(f, 0) for f in self.selected_features]
        }).sort_values('score', ascending=False)

        summary['rank'] = range(1, len(summary) + 1)
        summary['selection_method'] = self.selection_method

        return summary

    def compare_methods(self,
                       X: pd.DataFrame,
                       y: pd.Series,
                       methods: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Compare different feature selection methods

        Args:
            X: Feature matrix
            y: Target variable
            methods: List of methods to compare (default: all)

        Returns:
            DataFrame comparing methods
        """
        if methods is None:
            methods = [
                'correlation', 'mutual_info', 'random_forest',
                'collinearity', 'ensemble'
            ]

        results = []

        for method in methods:
            print(f"\n{'='*70}")
            print(f"METHOD: {method.upper()}")
            print('='*70)

            if method == 'correlation':
                selected = self.select_by_correlation(X, y)
            elif method == 'mutual_info':
                selected = self.select_by_mutual_information(X, y)
            elif method == 'random_forest':
                selected = self.select_by_random_forest(X, y)
            elif method == 'collinearity':
                selected = self.select_by_collinearity_removal(X, y)
            elif method == 'ensemble':
                selected = self.select_ensemble(X, y)
            else:
                continue

            results.append({
                'method': method,
                'n_features': len(selected),
                'features': ', '.join(selected[:10]) + ('...' if len(selected) > 10 else '')
            })

        return pd.DataFrame(results)


def create_optimal_feature_set(X: pd.DataFrame,
                                y: pd.Series,
                                max_features: int = 15) -> Tuple[List[str], FeatureSelector]:
    """
    Create optimal feature set using ensemble selection

    Args:
        X: Feature matrix
        y: Target variable
        max_features: Maximum number of features

    Returns:
        Tuple of (selected features, feature selector object)
    """
    selector = FeatureSelector(max_features=max_features)

    # Use ensemble selection for robustness
    selected_features = selector.select_ensemble(X, y, min_votes=2)

    print("\n" + "="*70)
    print("OPTIMAL FEATURE SET SELECTED")
    print("="*70)
    print(f"Original features: {len(X.columns)}")
    print(f"Selected features: {len(selected_features)}")
    print(f"Reduction: {(1 - len(selected_features)/len(X.columns))*100:.1f}%")
    print("="*70)

    return selected_features, selector
