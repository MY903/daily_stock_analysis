# -*- coding: utf-8 -*-
"""
===================================
Watchlist Command
===================================

Manage stock watchlist via natural language commands.
Supports add/remove/list operations through chat bot.
"""

import re
import logging
from typing import List, Optional

from bot.commands.base import BotCommand
from bot.models import BotMessage, BotResponse

logger = logging.getLogger(__name__)


class WatchlistCommand(BotCommand):
    """
    Watchlist management command
    
    Allows users to manage their stock watchlist through natural language.
    
    Usage:
        /watchlist                    - Show current watchlist
        /watchlist add 600519         - Add stock by code
        /watchlist remove 600519      - Remove stock by code
        /wl 添加 茅台                  - Add stock by Chinese name
        显示我的自选股                 - Show watchlist (natural language)
        帮我把茅台加入分析列表          - Add stock (natural language)
    """
    
    @property
    def name(self) -> str:
        return "watchlist"
    
    @property
    def aliases(self) -> List[str]:
        return ["wl", "自选股", "股票列表", "我的自选"]
    
    @property
    def description(self) -> str:
        return "管理自选股列表（添加/删除/查看）"
    
    @property
    def usage(self) -> str:
        return "/watchlist [add|remove|list] [股票代码/名称]"
    
    def execute(self, message: BotMessage, args: List[str]) -> BotResponse:
        """Execute watchlist command with intent detection."""
        from src.services.watchlist_service import (
            get_stock_list, add_stock, remove_stock, resolve_stock_name
        )
        
        # Get full message text for natural language parsing
        full_text = message.content.strip()
        
        # Detect intent from args or full text
        intent, stock_input = self._parse_intent(args, full_text)
        
        logger.info(f"[WatchlistCommand] Intent: {intent}, Stock: {stock_input}")
        
        if intent == "list":
            return self._handle_list(get_stock_list())
        
        elif intent == "add":
            if not stock_input:
                return BotResponse.error_response("请指定要添加的股票代码或名称")
            
            # Try to resolve name to code
            code = self._resolve_to_code(stock_input, resolve_stock_name)
            if not code:
                return BotResponse.error_response(
                    f"无法识别股票: {stock_input}\n"
                    "请使用标准代码格式：A股6位数字 / 港股HK+5位数字 / 美股1-5个字母"
                )
            
            success, msg = add_stock(code)
            if success:
                return BotResponse.markdown_response(f"✅ {msg}\n\n当前自选股: {', '.join(get_stock_list())}")
            return BotResponse.error_response(msg)
        
        elif intent == "remove":
            if not stock_input:
                return BotResponse.error_response("请指定要删除的股票代码或名称")
            
            # Try to resolve name to code
            code = self._resolve_to_code(stock_input, resolve_stock_name)
            if not code:
                code = stock_input  # Try raw input as code
            
            success, msg = remove_stock(code)
            if success:
                current = get_stock_list()
                list_str = ', '.join(current) if current else "(空)"
                return BotResponse.markdown_response(f"✅ {msg}\n\n当前自选股: {list_str}")
            return BotResponse.error_response(msg)
        
        else:
            # Default to list
            return self._handle_list(get_stock_list())
    
    def _parse_intent(self, args: List[str], full_text: str) -> tuple:
        """
        Parse user intent from args and full text.
        
        Returns:
            (intent, stock_input) where intent is 'list', 'add', or 'remove'
        """
        # Check explicit command args first
        if args:
            first_arg = args[0].lower()
            
            # Explicit add/remove/list
            if first_arg in ('add', 'a', '添加', '加入', '增加'):
                stock = args[1] if len(args) > 1 else None
                return "add", stock
            
            if first_arg in ('remove', 'rm', 'del', 'delete', '删除', '移除', '去掉'):
                stock = args[1] if len(args) > 1 else None
                return "remove", stock
            
            if first_arg in ('list', 'ls', '列表', '显示', '查看'):
                return "list", None
            
            # If first arg looks like a stock code, assume add
            if self._looks_like_stock_code(first_arg):
                return "add", first_arg
        
        # Natural language intent detection from full text
        add_keywords = ['添加', '加入', '增加', '新增', '把', '帮我加']
        remove_keywords = ['删除', '移除', '去掉', '删掉', '移走']
        list_keywords = ['显示', '查看', '列表', '我的自选', '有哪些', '当前']
        
        # Check for list intent
        for kw in list_keywords:
            if kw in full_text:
                # Make sure it's not also an add/remove
                has_add = any(k in full_text for k in add_keywords)
                has_remove = any(k in full_text for k in remove_keywords)
                if not has_add and not has_remove:
                    return "list", None
        
        # Check for add intent
        for kw in add_keywords:
            if kw in full_text:
                stock = self._extract_stock_from_text(full_text)
                return "add", stock
        
        # Check for remove intent
        for kw in remove_keywords:
            if kw in full_text:
                stock = self._extract_stock_from_text(full_text)
                return "remove", stock
        
        # Default to list
        return "list", None
    
    def _extract_stock_from_text(self, text: str) -> Optional[str]:
        """Extract stock code or name from natural language text."""
        # Try to find stock code patterns
        
        # A-share: 6 digits
        match = re.search(r'\b(\d{6})\b', text)
        if match:
            return match.group(1)
        
        # HK stock: HK + 5 digits
        match = re.search(r'\b(HK\d{5})\b', text, re.IGNORECASE)
        if match:
            return match.group(1).upper()
        
        # US stock: 1-5 uppercase letters
        match = re.search(r'\b([A-Z]{1,5})\b', text)
        if match and match.group(1) not in ('HK', 'ETF', 'A股'):
            return match.group(1)
        
        # Try to extract Chinese stock name
        # Common patterns: "把XX加入", "添加XX", "XX加入"
        chinese_patterns = [
            r'把(.{2,6}?)(?:加入|添加|删除|移除)',
            r'(?:加入|添加|删除|移除)(.{2,6})',
            r'分析(.{2,6})',
        ]
        for pattern in chinese_patterns:
            match = re.search(pattern, text)
            if match:
                name = match.group(1).strip()
                # Filter out common non-stock words
                if name and name not in ('我', '到', '从', '列表', '自选股', '分析', '股票'):
                    return name
        
        return None
    
    def _looks_like_stock_code(self, text: str) -> bool:
        """Check if text looks like a stock code."""
        text = text.upper()
        # A-share
        if re.match(r'^\d{6}$', text):
            return True
        # HK
        if re.match(r'^(HK)?\d{5}$', text):
            return True
        # US
        if re.match(r'^[A-Z]{1,5}$', text):
            return True
        return False
    
    def _resolve_to_code(self, stock_input: str, resolver) -> Optional[str]:
        """Resolve stock input to code."""
        # If already looks like a code, return it
        if self._looks_like_stock_code(stock_input):
            return stock_input.upper()
        
        # Try to resolve Chinese name
        code = resolver(stock_input)
        if code:
            return code
        
        return None
    
    def _handle_list(self, stock_list: List[str]) -> BotResponse:
        """Format and return the watchlist."""
        if not stock_list:
            return BotResponse.markdown_response(
                "📋 **自选股列表**\n\n"
                "(空)\n\n"
                "*使用 `/wl add 股票代码` 添加股票*"
            )
        
        # Format list with market identification
        lines = ["📋 **自选股列表**", ""]
        for code in stock_list:
            market = self._get_market_tag(code)
            lines.append(f"• `{code}` {market}")
        
        lines.extend([
            "",
            f"共 **{len(stock_list)}** 只股票",
            "",
            "*添加: `/wl add 代码`  删除: `/wl rm 代码`*"
        ])
        
        return BotResponse.markdown_response("\n".join(lines))
    
    def _get_market_tag(self, code: str) -> str:
        """Get market tag for stock code."""
        code = code.upper()
        if re.match(r'^\d{6}$', code):
            if code.startswith(('51', '52', '56', '58', '15', '16', '18')):
                return "[ETF]"
            if code.startswith(('6', '9')):
                return "[沪]"
            if code.startswith(('0', '3')):
                return "[深]"
            return "[A股]"
        if re.match(r'^(HK)?\d{5}$', code):
            return "[港股]"
        if re.match(r'^[A-Z]{1,5}$', code):
            return "[美股]"
        return ""
