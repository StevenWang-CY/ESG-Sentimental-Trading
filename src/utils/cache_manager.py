"""
Cache Manager for ESG Trading Strategy

Provides intelligent caching to avoid redundant data fetching across backtests.
Implements 3-tier caching strategy:
1. Immutable data: SEC filings, historical prices (never invalidate)
2. Config-dependent: Events, signals (invalidate on config change)
3. Time-fresh: Universe, recent data (invalidate by age)
"""

import hashlib
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional


def compute_config_hash(config_dict: Dict, keys: List[str]) -> str:
    """
    Compute 8-character hash of specific config keys.

    This allows cache invalidation when relevant parameters change
    (e.g., confidence_threshold changes) while preserving cache for
    unchanged parameters (e.g., SEC filings don't depend on NLP config).

    Args:
        config_dict: Full configuration dictionary
        keys: List of config keys to include in hash
              Example: ['nlp.event_detector.confidence_threshold']

    Returns:
        8-character hex hash (e.g., 'a3f2d8e1')

    Example:
        >>> config = {'nlp': {'event_detector': {'confidence_threshold': 0.30}}}
        >>> compute_config_hash(config, ['nlp.event_detector.confidence_threshold'])
        'a3f2d8e1'
    """
    relevant_config = {}

    for key in keys:
        # Support nested keys like 'nlp.event_detector.confidence_threshold'
        parts = key.split('.')
        value = config_dict

        try:
            for part in parts:
                value = value[part]
            relevant_config[key] = value
        except (KeyError, TypeError):
            # Key doesn't exist in config, skip it
            continue

    # Create stable JSON representation for hashing
    config_json = json.dumps(relevant_config, sort_keys=True)
    full_hash = hashlib.sha256(config_json.encode()).hexdigest()

    # Return first 8 characters for compact filenames
    return full_hash[:8]


def is_cache_fresh(cache_file: Path, end_date: str, max_age_days: int = 60) -> bool:
    """
    Check if cached data is still fresh based on end date and file age.

    Strategy:
    - Historical data (>60 days old): Always fresh (immutable)
    - Recent data (<60 days old): Fresh if file modified <24 hours ago

    Args:
        cache_file: Path to cache file
        end_date: End date of data range (YYYY-MM-DD)
        max_age_days: Days before data is considered historical (default: 60)

    Returns:
        True if cache is fresh and should be used, False if stale

    Example:
        >>> # Historical data (end_date 2024-06-01, today 2025-11-18)
        >>> is_cache_fresh(Path('data/prices_2024-06-01.pkl'), '2024-06-01')
        True  # >60 days old, always fresh

        >>> # Recent data (end_date 2025-11-15, today 2025-11-18)
        >>> is_cache_fresh(Path('data/prices_2025-11-15.pkl'), '2025-11-15')
        False  # <60 days old, file >24 hours old
    """
    if not cache_file.exists():
        return False

    # Parse end date
    try:
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    except ValueError:
        # Invalid date format, consider cache stale
        return False

    # For historical data (>max_age_days old), always use cache
    days_since_end = (datetime.now() - end_dt).days
    if days_since_end > max_age_days:
        return True

    # For recent data, check file modification time
    file_mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
    file_age_hours = (datetime.now() - file_mtime).total_seconds() / 3600

    # Cache is fresh if modified within last 24 hours
    return file_age_hours < 24


def build_cache_key(
    data_type: str,
    universe: str,
    start_date: str,
    end_date: str,
    config_hash: Optional[str] = None,
    ticker_count: Optional[int] = None
) -> str:
    """
    Build standardized cache filename with metadata.

    Format: {data_type}_{universe}_{start_date}_to_{end_date}[_{config_hash}][_n{count}].pkl

    Args:
        data_type: Type of data (e.g., 'filings', 'prices', 'events', 'signals')
        universe: Universe name (e.g., 'russell_midcap', 'sp500')
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        config_hash: Optional 8-char config hash (for config-dependent data)
        ticker_count: Optional number of tickers (for validation)

    Returns:
        Cache filename (without directory path)

    Examples:
        >>> build_cache_key('filings', 'russell_midcap', '2024-06-01', '2025-06-01', ticker_count=172)
        'filings_russell_midcap_2024-06-01_to_2025-06-01_n172.pkl'

        >>> build_cache_key('events', 'sp500', '2024-01-01', '2024-12-31', config_hash='a3f2d8e1')
        'events_sp500_2024-01-01_to_2024-12-31_a3f2d8e1.pkl'
    """
    parts = [
        data_type,
        universe,
        f"{start_date}_to_{end_date}"
    ]

    if config_hash:
        parts.append(config_hash)

    if ticker_count is not None:
        parts.append(f"n{ticker_count}")

    filename = "_".join(parts) + ".pkl"
    return filename


def clear_cache(data_dir: Path, data_type: Optional[str] = None) -> int:
    """
    Delete cached data files.

    Args:
        data_dir: Directory containing cache files
        data_type: Optional filter for specific data type (e.g., 'events')
                   If None, clears all .pkl cache files

    Returns:
        Number of files deleted

    Example:
        >>> clear_cache(Path('data'), data_type='events')
        2  # Deleted 2 event cache files
    """
    if not data_dir.exists():
        return 0

    pattern = f"{data_type}_*.pkl" if data_type else "*.pkl"
    cache_files = list(data_dir.glob(pattern))

    for cache_file in cache_files:
        try:
            cache_file.unlink()
        except OSError:
            # File already deleted or permission error
            pass

    return len(cache_files)


def get_cache_info(cache_file: Path) -> Dict[str, any]:
    """
    Extract metadata from cache filename.

    Args:
        cache_file: Path to cache file

    Returns:
        Dictionary with extracted metadata

    Example:
        >>> get_cache_info(Path('data/filings_russell_midcap_2024-06-01_to_2025-06-01_n172.pkl'))
        {
            'data_type': 'filings',
            'universe': 'russell_midcap',
            'start_date': '2024-06-01',
            'end_date': '2025-06-01',
            'ticker_count': 172,
            'file_size_mb': 15.2,
            'modified': '2025-11-18 10:30:00'
        }
    """
    metadata = {
        'filename': cache_file.name,
        'exists': cache_file.exists()
    }

    if not cache_file.exists():
        return metadata

    # Extract info from filename
    name = cache_file.stem  # Remove .pkl extension
    parts = name.split('_')

    if len(parts) >= 5:
        metadata['data_type'] = parts[0]
        # Handle multi-word universe names (e.g., russell_midcap)
        # Find the date pattern to split
        for i, part in enumerate(parts):
            if len(part) == 10 and part.count('-') == 2:  # YYYY-MM-DD format
                metadata['universe'] = '_'.join(parts[1:i])
                metadata['start_date'] = part
                if i+2 < len(parts):  # 'to' separator
                    metadata['end_date'] = parts[i+2]
                break

    # Extract ticker count if present (e.g., n172)
    for part in parts:
        if part.startswith('n') and part[1:].isdigit():
            metadata['ticker_count'] = int(part[1:])

    # File metadata
    stat = cache_file.stat()
    metadata['file_size_mb'] = round(stat.st_size / (1024 * 1024), 2)
    metadata['modified'] = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')

    return metadata
