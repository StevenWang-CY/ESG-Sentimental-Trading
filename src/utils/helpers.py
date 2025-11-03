"""
Helper Utilities
General utility functions for the project
"""

import json
import pickle
from pathlib import Path
from typing import Any, Dict
import pandas as pd


def ensure_dir(directory: str) -> Path:
    """
    Ensure directory exists, create if it doesn't

    Args:
        directory: Directory path

    Returns:
        Path object
    """
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_results(data: Any, filepath: str, format: str = 'pickle'):
    """
    Save results to file

    Args:
        data: Data to save
        filepath: Output file path
        format: Format ('pickle', 'json', 'csv')
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    if format == 'pickle':
        with open(filepath, 'wb') as f:
            pickle.dump(data, f)

    elif format == 'json':
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    elif format == 'csv' and isinstance(data, pd.DataFrame):
        data.to_csv(filepath, index=True)

    else:
        raise ValueError(f"Unsupported format: {format}")

    print(f"Results saved to {filepath}")


def load_results(filepath: str, format: str = 'pickle') -> Any:
    """
    Load results from file

    Args:
        filepath: Input file path
        format: Format ('pickle', 'json', 'csv')

    Returns:
        Loaded data
    """
    if format == 'pickle':
        with open(filepath, 'rb') as f:
            return pickle.load(f)

    elif format == 'json':
        with open(filepath, 'r') as f:
            return json.load(f)

    elif format == 'csv':
        return pd.read_csv(filepath, index_col=0)

    else:
        raise ValueError(f"Unsupported format: {format}")


def format_percentage(value: float, decimals: int = 2) -> str:
    """Format value as percentage string"""
    return f"{value * 100:.{decimals}f}%"


def format_currency(value: float, decimals: int = 2) -> str:
    """Format value as currency string"""
    return f"${value:,.{decimals}f}"
