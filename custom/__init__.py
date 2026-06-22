# -*- coding: utf-8 -*-
"""
Custom 模块 — 非 upstream 的定制化功能集合

本目录下的所有代码都是 fork 专属的定制功能，不应出现在 upstream 中。
通过 custom/loader.py 统一加载，不会修改 upstream 的任何文件。

定制功能包括：
- trading/     : QuantWeasel 量化交易系统
- crypto/      : 加密货币数据源扩展
- mcp/         : MCP Server（AI 助手接入）
- agents/      : 专家委员会（多 AI 角色分析）
- bot/         : 飞书交互卡片、自选股命令
- api_endpoints/ : 交易、专家战绩等定制 API 端点
- strategies/  : 交易策略 YAML 文件
"""
