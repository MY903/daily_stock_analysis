# -*- coding: utf-8 -*-
"""
===================================
Watchlist Service
===================================

Service for managing the stock watchlist in .env file.
Supports add/remove/list operations with hot-reload capability.
"""

import os
import re
import logging
import threading
from pathlib import Path
from typing import List, Tuple, Optional

from dotenv import dotenv_values, set_key

logger = logging.getLogger(__name__)

# Thread lock for file operations
_file_lock = threading.Lock()


def _get_env_path() -> Path:
    """Get the path to the .env file."""
    # Try project root first
    project_root = Path(__file__).parent.parent.parent
    env_path = project_root / '.env'
    if env_path.exists():
        return env_path
    # Fallback to current directory
    return Path('.env')


def _normalize_code(code: str) -> str:
    """
    Normalize stock code to standard format.
    
    Args:
        code: Raw stock code input
        
    Returns:
        Normalized code (lowercase for consistency)
    """
    code = code.strip().upper()
    # HK stocks: remove HK prefix for storage, keep 5 digits
    if code.startswith('HK') and len(code) == 7:
        code = code[2:]  # Store as 5 digits
    return code.lower()


def _validate_code(code: str) -> Tuple[bool, str]:
    """
    Validate stock code format.
    
    Args:
        code: Stock code to validate
        
    Returns:
        (is_valid, error_message)
    """
    code = code.strip().upper()
    
    # A-share: 6 digits
    if re.match(r'^\d{6}$', code):
        return True, ""
    
    # HK stock: HK + 5 digits or just 5 digits
    if re.match(r'^(HK)?\d{5}$', code):
        return True, ""
    
    # US stock: 1-5 uppercase letters
    if re.match(r'^[A-Z]{1,5}(\.[A-Z]{1,2})?$', code):
        return True, ""
    
    return False, f"Invalid code format: {code}"


def get_stock_list() -> List[str]:
    """
    Get current stock list from .env file.
    
    Returns:
        List of stock codes
    """
    env_path = _get_env_path()
    if not env_path.exists():
        logger.warning(f".env file not found at {env_path}")
        return []
    
    with _file_lock:
        values = dotenv_values(env_path)
        stock_list_str = values.get('STOCK_LIST', '')
    
    if not stock_list_str:
        return []
    
    # Parse comma-separated list
    codes = [c.strip() for c in stock_list_str.split(',') if c.strip()]
    return codes


def add_stock(code: str) -> Tuple[bool, str]:
    """
    Add a stock to the watchlist.
    
    Args:
        code: Stock code to add
        
    Returns:
        (success, message)
    """
    # Validate code
    is_valid, error = _validate_code(code)
    if not is_valid:
        return False, error
    
    normalized = _normalize_code(code)
    
    # Get current list
    current_list = get_stock_list()
    
    # Check for duplicates (case-insensitive)
    lower_list = [c.lower() for c in current_list]
    if normalized in lower_list:
        return False, f"Stock {code} is already in the watchlist"
    
    # Add to list
    current_list.append(normalized)
    
    # Write back
    success = _write_stock_list(current_list)
    if success:
        _refresh_config()
        return True, f"Added {code} to watchlist"
    return False, "Failed to write to .env file"


def remove_stock(code: str) -> Tuple[bool, str]:
    """
    Remove a stock from the watchlist.
    
    Args:
        code: Stock code to remove
        
    Returns:
        (success, message)
    """
    normalized = _normalize_code(code)
    
    # Get current list
    current_list = get_stock_list()
    
    # Find and remove (case-insensitive)
    lower_list = [c.lower() for c in current_list]
    if normalized not in lower_list:
        return False, f"Stock {code} is not in the watchlist"
    
    # Remove the matching item
    idx = lower_list.index(normalized)
    removed = current_list.pop(idx)
    
    # Write back
    success = _write_stock_list(current_list)
    if success:
        _refresh_config()
        return True, f"Removed {removed} from watchlist"
    return False, "Failed to write to .env file"


def _write_stock_list(stock_list: List[str]) -> bool:
    """
    Write stock list to .env file.
    
    Args:
        stock_list: List of stock codes
        
    Returns:
        True if successful
    """
    env_path = _get_env_path()
    stock_str = ','.join(stock_list)
    
    try:
        with _file_lock:
            set_key(str(env_path), 'STOCK_LIST', stock_str)
        logger.info(f"Updated STOCK_LIST in .env: {stock_str}")
        return True
    except Exception as e:
        logger.error(f"Failed to write STOCK_LIST to .env: {e}")
        return False


def _refresh_config():
    """Refresh the Config singleton to pick up new stock list."""
    try:
        from src.config import Config
        config = Config.get_instance()
        if hasattr(config, 'refresh_stock_list'):
            config.refresh_stock_list()
            logger.info("Config stock list refreshed")
    except Exception as e:
        logger.warning(f"Failed to refresh config: {e}")


def resolve_stock_name(name: str) -> Optional[str]:
    """
    Resolve Chinese stock name to code.
    
    Args:
        name: Chinese stock name (e.g., "茅台", "腾讯")
        
    Returns:
        Stock code if found, None otherwise
    """
    try:
        from src.analyzer import STOCK_NAME_MAP
        
        # Build reverse mapping (name -> code)
        name_to_code = {}
        for code, stock_name in STOCK_NAME_MAP.items():
            # Add both full name and partial matches
            name_to_code[stock_name] = code
            # Also add without common suffixes
            for suffix in ['控股', '集团', '银行', '证券', '汽车']:
                if stock_name.endswith(suffix):
                    name_to_code[stock_name[:-len(suffix)]] = code
        
        # Exact match
        if name in name_to_code:
            return name_to_code[name]
        
        # Partial match
        for stock_name, code in name_to_code.items():
            if name in stock_name or stock_name in name:
                return code
        
        return None
    except Exception as e:
        logger.warning(f"Failed to resolve stock name: {e}")
        return None
