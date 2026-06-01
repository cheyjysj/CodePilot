"""
上下文压缩管理器
实现三级渐进式压缩策略：MicroCompact、AutoCompact、Manual/Partial
借鉴 Claude Code 的压缩架构：

  MicroCompact   — 纯内容替换，无 LLM 成本（对齐 Claude Code 的 Time-based MC）
  AutoCompact    — Forked-agent 全局摘要 + boundary marker（对齐 Claude Code 的 compactConversation）
  Manual Compact — 手动触发，走 AutoCompact 同路径
"""
from __future__ import annotations

import os
import time
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from enum import Enum

logger = logging.getLogger(__name__)


class CompactLevel(Enum):
    """压缩级别"""
    MICRO = "micro"      # 工具结果时间基裁剪
    AUTO = "auto"        # Token 阈值触发压缩
    MANUAL = "manual"    # 用户手动触发


# ──────────────────────────────────────────────────────────────
# 数据模型
# ──────────────────────────────────────────────────────────────

class CompactResult(BaseModel):
    """Forked-agent 压缩结果（对齐 Claude Code 的 compactConversation 输出）"""
    boundary: Dict[str, Any]         # 边界标记消息（is_boundary=True）
    summary: Dict[str, Any]          # 全局摘要消息
    messages_to_keep: List[Dict[str, Any]]  # 保留的最近消息
    pre_token_count: int = 0
    post_token_count: int = 0
    model: Optional[str] = None

    def build_messages(self) -> List[Dict[str, Any]]:
        """构建压缩后的完整消息列表"""
        return [self.boundary, self.summary] + self.messages_to_keep


# ──────────────────────────────────────────────────────────────
# MicroCompact — 纯内容替换，零 LLM 成本
# ──────────────────────────────────────────────────────────────

class MicroCompactor:
    """
    MicroCompact — 工具结果时间基裁剪

    对齐 Claude Code 的 Time-based MicroCompact：
      - 无 LLM 参与（LLM 摘要是 AutoCompact 层的职责）
      - 用简单占位文本替换过期工具结果
      - Claude Code 的 Cached MC（cache_edits API）因 DeepSeek/OpenAI 无等价 API，本期不做
    """

    def __init__(self):
        self.COMPACTABLE_TOOLS = {
            'FileRead', 'Bash', 'Grep',
            'Glob', 'WebSearch', 'WebFetch',
            'FileEdit', 'FileWrite', 'LS'
        }
        self.MAX_AGE = 5 * 60       # 5 分钟（秒）
        self.MAX_TOKENS = 1000      # 超过此 token 数也触发压缩
        self.REPLACEMENT = '[Old tool result content cleared by MicroCompact]'

    # ── 公共接口 ──

    def compact(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """纯时间基 + Token 基内容替换（同步），无 LLM 参与"""
        now = time.time()

        for msg in messages:
            if msg.get('role') != 'user':
                continue

            content = msg.get('content', '')
            if not isinstance(content, str):
                continue

            tool_name = msg.get('tool_name', '')
            if not tool_name and 'tool_result' in msg:
                tool_name = msg.get('tool_result', {}).get('tool_name', '')

            if tool_name not in self.COMPACTABLE_TOOLS:
                continue

            timestamp = msg.get('timestamp', 0)
            if timestamp == 0 and 'tool_result' in msg:
                timestamp = msg.get('tool_result', {}).get('timestamp', 0)

            age = now - timestamp
            should_compact = age > self.MAX_AGE

            if self._estimate_tokens(content) > self.MAX_TOKENS:
                should_compact = True

            if should_compact:
                msg['compacted'] = True
                msg['compact_level'] = CompactLevel.MICRO.value
                msg['original_length'] = len(content)
                msg['content'] = self.REPLACEMENT

        return messages

    def compact_async(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """MicroCompact 层不使用 LLM，直接委托给同步版本"""
        return self.compact(messages)

    # ── 内部 ──

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """字符数 / 4 粗估 token"""
        if not text:
            return 0
        return len(text) // 4


# ──────────────────────────────────────────────────────────────
# AutoCompact — Forked-agent 全局摘要（对齐 Claude Code）
# ──────────────────────────────────────────────────────────────

class AutoCompactor:
    """
    AutoCompact — Token 阈值触发的全局对话压缩

    对齐 Claude Code 的 compactConversation()：
      - 启动一个 LLM 调用（"forked-agent"），生成全局摘要
      - 插入 boundary marker 标记压缩边界
      - 保留最近 N 条消息避免上下文完全断裂
      - Circuit breaker：连续失败 3 次后暂停
      - 动态阈值：基于模型上下文窗口计算
    """

    # 模型上下文窗口（默认值，vendor 侧可能有变化）
    MODEL_CONTEXT_WINDOWS: Dict[str, int] = {
        "deepseek-chat":     64_000,
        "deepseek-reasoner": 64_000,
        "deepseek-v3":      128_000,
        "gpt-4":            128_000,
        "gpt-4-turbo":      128_000,
        "gpt-4o":           128_000,
        "gpt-3.5-turbo":     16_000,
    }
    DEFAULT_CONTEXT_WINDOW = 128_000

    # 为 LLM 输出预留的 token（对齐 Claude Code: window - MAX_OUTPUT_TOKENS）
    MAX_OUTPUT_TOKENS_FOR_MODEL = 20_000

    # 压缩缓冲（对齐 Claude Code 的 AUTOCOMPACT_BUFFER_TOKENS）
    AUTOCOMPACT_BUFFER = 13_000

    # Circuit breaker
    MAX_CONSECUTIVE_FAILURES = 3

    # 摘要目标长度
    SUMMARY_MAX_TOKENS = 4000

    # 保留最近消息占目标窗口的比例
    KEEP_RATIO = 0.35

    def __init__(self):
        self._llm_client = None
        self.consecutive_failures = 0
        self.compaction_count = 0

    # ── 窗口 / 阈值 ──

    def get_effective_window(self, model: Optional[str] = None) -> int:
        """有效上下文窗口 = 模型窗口 - LLM 输出预留"""
        model = model or os.getenv("LLM_MODEL", "deepseek-chat")
        context_window = self.MODEL_CONTEXT_WINDOWS.get(model, self.DEFAULT_CONTEXT_WINDOW)
        return context_window - self.MAX_OUTPUT_TOKENS_FOR_MODEL

    def get_auto_compact_threshold(self, model: Optional[str] = None) -> int:
        """自动压缩触发阈值 = 有效窗口 - 压缩缓冲"""
        return self.get_effective_window(model) - self.AUTOCOMPACT_BUFFER

    # ── 判断 ──

    def should_compact(self, messages: List[Dict[str, Any]],
                       model: Optional[str] = None) -> bool:
        """是否应触发 AutoCompact"""
        if self.consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
            logger.debug("AutoCompact circuit breaker 已触发，跳过")
            return False
        total = self._count_total_tokens(messages)
        threshold = self.get_auto_compact_threshold(model)
        return total > threshold

    # ── Forked-agent 全局摘要（核心路径） ──

    async def compact_async(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
    ) -> CompactResult | Dict[str, Any]:
        """
        Forked-agent 全局摘要压缩

        流程（对齐 Claude Code compactConversation）:
          1. 计算 pre-compact token 数
          2. 构建压缩 prompt（告知 LLM 需要总结什么）
          3. 调用 LLM 生成全局对话摘要
          4. 保留最近 N 条消息避免上下文断裂
          5. 插入 boundary marker + summary
          6. 成功则重置 circuit breaker，失败则累加

        Returns:
            CompactResult（成功）或 {"messages": messages, "compacted": False, ...}
        """
        if self.consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
            return {"messages": messages, "compacted": False,
                    "reason": "circuit breaker open"}

        llm = self._get_llm_client()
        if not llm:
            return {"messages": messages, "compacted": False,
                    "reason": "LLM client unavailable"}

        pre_tokens = self._count_total_tokens(messages)

        try:
            # 1. 构建压缩 prompt
            compact_prompt = self._build_compact_prompt(messages, pre_tokens)

            # 2. 调用 LLM 生成全局摘要
            summary = await llm.chat(
                messages=[
                    {"role": "system",
                     "content": "You are a helpful AI assistant tasked with summarizing conversations."},
                    {"role": "user", "content": compact_prompt},
                ],
                temperature=0.3,
                max_tokens=self.SUMMARY_MAX_TOKENS,
                model=model,
            )

            # 3. 保留最近消息
            kept = self._keep_recent(messages, model)

            # 4. 构建 boundary marker + summary
            boundary = self._create_boundary_marker(pre_tokens)
            summary_msg = {
                "role": "user",
                "content": f"[Previous conversation summary]\n{summary.strip()}",
                "is_summary": True,
                "compact_level": CompactLevel.AUTO.value,
            }

            new_messages = [boundary, summary_msg] + kept
            post_tokens = self._count_total_tokens(new_messages)

            # 重置 circuit breaker
            self.consecutive_failures = 0
            self.compaction_count += 1

            logger.info(
                "AutoCompact #%d: %d → %d tokens (model=%s, kept %d messages)",
                self.compaction_count, pre_tokens, post_tokens,
                model or "default", len(kept),
            )

            return CompactResult(
                boundary=boundary,
                summary=summary_msg,
                messages_to_keep=kept,
                pre_token_count=pre_tokens,
                post_token_count=post_tokens,
                model=model,
            )

        except Exception as e:
            self.consecutive_failures += 1
            logger.error(
                "AutoCompact forked-agent 失败 (fail %d/%d): %s",
                self.consecutive_failures, self.MAX_CONSECUTIVE_FAILURES, e,
            )
            return {"messages": messages, "compacted": False,
                    "error": str(e), "consecutive_failures": self.consecutive_failures}

    # ── 构建 prompt ──

    def _build_compact_prompt(self, _messages: List[Dict[str, Any]],
                              total_tokens: int) -> str:
        """构建发送给 forked-agent 的压缩指令"""
        return (
            f"The conversation below has grown too large ({total_tokens:,} tokens) "
            f"and needs to be compressed. Please summarize the key information:\n\n"
            f"1. User's original requests and goals\n"
            f"2. Key decisions and technical choices made\n"
            f"3. Important code changes and their rationale\n"
            f"4. Current state of the project / files being worked on\n"
            f"5. Any errors encountered and how they were resolved\n"
            f"6. Remaining tasks or open questions\n\n"
            f"Be concise but comprehensive. The summary will replace the original "
            f"conversation, so preserve ALL critical context the assistant needs "
            f"to continue working effectively."
        )

    def _create_boundary_marker(self, pre_tokens: int) -> Dict[str, Any]:
        """创建压缩边界标记（对齐 Claude Code CompactBoundaryMessage）"""
        return {
            "role": "system",
            "content": (
                f"[CONTEXT COMPACTED at {time.strftime('%Y-%m-%d %H:%M:%S')} — "
                f"previous {pre_tokens:,} tokens summarized below]"
            ),
            "is_boundary": True,
            "compaction_metadata": {
                "level": CompactLevel.AUTO.value,
                "timestamp": time.time(),
                "pre_compact_tokens": pre_tokens,
                "compaction_index": self.compaction_count + 1,
            },
        }

    # ── 保留最近消息 ──

    def _keep_recent(self, messages: List[Dict[str, Any]],
                     model: Optional[str] = None) -> List[Dict[str, Any]]:
        """倒序遍历消息，保留不超过 KEEP_RATIO * effective_window 的最近消息"""
        target = int(self.get_effective_window(model) * self.KEEP_RATIO)
        kept: List[Dict[str, Any]] = []
        kept_tokens = 0

        for msg in reversed(messages):
            t = self._estimate_tokens(msg.get("content", ""))
            if kept_tokens + t > target:
                break
            kept.insert(0, msg)
            kept_tokens += t

        # 最少保留 1 条消息避免上下文完全丢失
        if not kept and messages:
            kept.append(messages[-1])

        return kept

    # ── 内部工具方法 ──

    def _get_llm_client(self):
        if self._llm_client is None:
            try:
                from app.core.llm_client import LLMClient
                self._llm_client = LLMClient()
            except Exception as e:
                logger.warning("LLM 客户端初始化失败: %s", e)
                self._llm_client = None
        return self._llm_client

    def _count_total_tokens(self, messages: List[Dict[str, Any]]) -> int:
        return sum(self._estimate_tokens(msg.get("content", "")) for msg in messages)

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        if not text:
            return 0
        return len(text) // 4


# ──────────────────────────────────────────────────────────────
# ContextManager — 统一入口
# ──────────────────────────────────────────────────────────────

class ContextManager:
    """上下文管理器 — 统一入口"""

    def __init__(self):
        self.micro_compactor = MicroCompactor()
        self.auto_compactor = AutoCompactor()
        self.compact_history: List[Dict[str, Any]] = []

    # ── 同步版本 ──

    def process_messages(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """处理消息列表：MicroCompact 纯替换 → AutoCompact 降级（同步版无 LLM）"""
        messages = self.micro_compactor.compact(messages)

        if self.auto_compactor.should_compact(messages, model=model):
            # 同步版无法做 forked-agent LLM 调用，标记但不执行
            logger.warning(
                "AutoCompact 需要 LLM 但当前在同步路径，跳过。"
                "请使用 process_messages_async。"
            )

        return messages

    # ── 异步版本（主路径） ──

    async def process_messages_async(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        异步处理：MicroCompact 纯替换 → AutoCompact forked-agent 全局摘要
        """
        # 1. MicroCompact（无 LLM）
        messages = self.micro_compactor.compact_async(messages)

        # 2. AutoCompact（forked-agent 全局摘要）
        if self.auto_compactor.should_compact(messages, model=model):
            result = await self.auto_compactor.compact_async(messages, model=model)
            if isinstance(result, CompactResult):
                self.compact_history.append({
                    'level': CompactLevel.AUTO.value,
                    'timestamp': time.time(),
                    'tokens_before': result.pre_token_count,
                    'tokens_after': result.post_token_count,
                    'model': result.model,
                    'llm_forked_agent': True,
                })
                return result.build_messages()
            else:
                # LLM 不可用 / circuit breaker，使用原始消息继续
                logger.debug("AutoCompact 未执行: %s", result.get("reason", "unknown"))
                return result.get("messages", messages)

        return messages

    # ── 手动压缩 ──

    def manual_compact(
        self,
        messages: List[Dict[str, Any]],
        target_tokens: Optional[int] = None,
        model: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        手动触发压缩（同步版，无 LLM）
        如果 target_tokens 未指定，保留最近 20K 的消息
        """
        if not messages:
            return messages

        target = target_tokens or 20_000
        kept: List[Dict[str, Any]] = []
        kept_tokens = 0

        for msg in reversed(messages):
            t = len(str(msg.get("content", ""))) // 4
            if kept_tokens + t > target:
                break
            kept.insert(0, msg)
            kept_tokens += t

        if not kept and messages:
            kept = [messages[-1]]

        self.compact_history.append({
            'level': CompactLevel.MANUAL.value,
            'timestamp': time.time(),
            'tokens_after': kept_tokens,
            'target_tokens': target,
            'model': model,
        })

        return kept

    async def manual_compact_async(
        self,
        messages: List[Dict[str, Any]],
        target_tokens: Optional[int] = None,
        model: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        手动触发异步压缩 — 走 AutoCompact 的 forked-agent 路径
        """
        if not messages:
            return messages

        if target_tokens:
            # 覆盖保留比例以适应目标
            original_keep = self.auto_compactor.KEEP_RATIO
            effective = self.auto_compactor.get_effective_window(model)
            self.auto_compactor.KEEP_RATIO = target_tokens / effective if effective > 0 else 0.3

        try:
            result = await self.auto_compactor.compact_async(messages, model=model)
        finally:
            if target_tokens:
                self.auto_compactor.KEEP_RATIO = original_keep

        if isinstance(result, CompactResult):
            self.compact_history.append({
                'level': CompactLevel.MANUAL.value,
                'timestamp': time.time(),
                'tokens_before': result.pre_token_count,
                'tokens_after': result.post_token_count,
                'model': result.model,
                'llm_forked_agent': True,
            })
            return result.build_messages()

        return messages

    # ── 统计 ──

    def get_compact_stats(self) -> Dict[str, Any]:
        llm_compactions = sum(
            1 for h in self.compact_history if h.get('llm_forked_agent')
        )
        return {
            'total_compactions': len(self.compact_history),
            'forked_agent_compactions': llm_compactions,
            'auto_compactor_failures': self.auto_compactor.consecutive_failures,
            'auto_compactor_total': self.auto_compactor.compaction_count,
            'models_used': list({h.get('model') for h in self.compact_history if h.get('model')}),
            'history': self.compact_history[-10:],
            'thresholds': {
                'current_model': os.getenv("LLM_MODEL", "deepseek-chat"),
                'effective_window': self.auto_compactor.get_effective_window(),
                'compact_threshold': self.auto_compactor.get_auto_compact_threshold(),
            },
            'micro_compactable_tools': list(self.micro_compactor.COMPACTABLE_TOOLS),
        }
