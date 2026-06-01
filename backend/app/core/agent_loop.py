"""
Agent 执行循环 - LLM ↔ Tool 多轮交互核心

这是 Claude Code 的灵魂：LLM 调用工具 → 执行工具 → 结果还给 LLM → 继续直到 LLM 不再调用工具。
"""

import json
import time
import re
import asyncio
from typing import Any, Dict, List, Optional, Tuple

from app.core.llm_client import LLMClient, LLMClientError
from app.core.context_manager import ContextManager
from app.core.memory_manager import MemoryManager
from app.core.cache_manager import CacheManager
from app.tools.tool_registry import ToolRegistry
from app.skills.loader import SkillLoader
from app.core.output import Output


class AgentLoopError(Exception):
    """Agent 循环异常"""
    pass


class AgentLoop:
    """Agent 执行循环

    核心流程:
    1. 接收用户输入
    2. 构建含工具列表的系统提示词
    3. 调用 LLM（流式输出）
    4. 解析 LLM 响应中的 <tool_call> 标签
    5. 执行工具调用（带权限确认）
    6. 将工具结果反馈给 LLM
    7. 重复步骤 3-6，直到 LLM 不再调用工具
    8. 自动压缩上下文
    """

    MAX_TOOL_ROUNDS = 25          # 每次对话最多工具调用轮数

    def __init__(self, cwd: str = "."):
        self.cwd = cwd
        self.llm = LLMClient()
        self.context = ContextManager()
        self.memory = MemoryManager(cwd)
        self.cache = CacheManager()
        self.tools = ToolRegistry()
        self.skill_loader = SkillLoader()
        self.output = Output()

        # 对话消息历史（不含系统提示词）
        self.messages: List[Dict[str, Any]] = []

        # 项目级临时文件（CLAUDE.md / AGENTS.md 等）
        self._project_files: Dict[str, str] = {}

        # 持久的工具执行上下文
        self._tool_context: Dict[str, Any] = {}

    # ──────────────────── 公共接口 ────────────────────

    async def process(self, user_input: str) -> None:
        """处理用户输入，进入 Agent 循环"""
        import os

        # 添加用户消息
        self.messages.append({
            "role": "user",
            "content": user_input,
            "timestamp": time.time(),
        })

        # 从磁盘加载项目级指令文件
        self._load_project_files()

        # Agent 循环
        try:
            for round_num in range(1, self.MAX_TOOL_ROUNDS + 1):
                # 构建系统提示词 + 完整消息
                system_prompt = self._build_system_prompt()
                full_messages = [{"role": "system", "content": system_prompt}] + self.messages

                # 上下文压缩（传入模型名以支持动态阈值）
                full_messages = await self.context.process_messages_async(
                    full_messages, model=self.llm.model
                )

                # 检查是否需要自动压缩（显示通知）—— 使用动态阈值
                total_tokens = self._count_tokens(full_messages)
                threshold = self.context.auto_compactor.get_auto_compact_threshold(
                    self.llm.model
                )
                if total_tokens > threshold:
                    self.output.info(
                        f"当前上下文 {total_tokens:,} tokens，超过 {threshold:,} 阈值..."
                    )

                # 调用 LLM（流式）
                response_text = await self._call_llm_streaming(full_messages)

                # 解析工具调用
                structured_response, tool_calls = self._parse_response(response_text)

                # 如果没有工具调用，完成本轮
                if not tool_calls:
                    self.messages.append({
                        "role": "assistant",
                        "content": response_text,
                        "timestamp": time.time(),
                    })
                    break

                # 先显示助手文本部分（如果有）
                if structured_response.strip():
                    print()  # 换行

                # 添加助手消息（原始内容，包含 tool_call 标签）
                self.messages.append({
                    "role": "assistant",
                    "content": response_text,
                    "timestamp": time.time(),
                })

                # 执行工具调用
                for tc in tool_calls:
                    result_content = await self._execute_tool_safe(tc)

                    # 将工具结果作为 user 消息插入
                    self.messages.append({
                        "role": "user",
                        "content": f"<tool_result name=\"{tc['name']}\">\n{result_content}\n</tool_result>",
                        "tool_name": tc["name"],
                        "timestamp": time.time(),
                    })

            else:
                # 达到 MAX_TOOL_ROUNDS，强制停止
                self.output.warn(f"已达到最大工具调用轮数 ({self.MAX_TOOL_ROUNDS})，强制停止。")

        except LLMClientError as e:
            self.output.error(f"LLM 调用失败: {e}")
            # 移除最后一条 user 消息（因为对话没有完成）
            self.messages.pop()
        except AgentLoopError as e:
            self.output.error(f"Agent 循环错误: {e}")
        except asyncio.CancelledError:
            self.output.warn("操作已取消。")
        except Exception as e:
            self.output.error(f"未预期的错误: {e}")
            import traceback
            traceback.print_exc()

        # 输出空行分隔不同轮对话
        print()

    # ──────────────────── 提示词构建 ────────────────────

    def _build_system_prompt(self) -> str:
        """构建包含工具列表、项目上下文和交互规则的完整系统提示词"""
        cwd_abs = __import__('os').path.abspath(self.cwd)

        prompt_parts = [
            "You are CodePilot, an AI coding assistant running interactively in the terminal.",
            "",
            f"You are working in directory: {cwd_abs}",
            "",
            "## Tools",
            "",
            "You have access to the following tools. To call a tool, output a <tool_call> block:",
            "",
            self.tools.get_tool_descriptions(),
            "",
            "### Tool call format (MUST follow exactly):",
            "",
            "<tool_call>",
            '{"name": "ToolName", "args": {"arg1": "value1", "arg2": "value2"}}',
            "</tool_call>",
            "",
            "### Important rules:",
            "- You may call multiple tools in sequence, one <tool_call> block per tool.",
            "- After each tool call, the result will be automatically provided to you.",
            "- Continue calling tools until the user's request is fully satisfied.",
            "- You may mix regular text and tool calls. Text outside <tool_call> is shown to the user.",
            "- **Do NOT** output multiple <tool_call> blocks in a single response. Use one at a time.",
            "- When you are done, respond with text only (no more <tool_call> blocks).",
            "",
            "## Files and editing",
            "- Use FileRead to read file contents.",
            "- Use FileEdit to modify files (provide exact old_str to replace).",
            "- Use FileWrite to create or overwrite files.",
            "- Use Grep to search file contents with regex.",
            "- Use Glob to find files by pattern.",
            "- Use Bash to run shell commands (tests, builds, git, etc.).",
            "",
            "## Best practices",
            "- **Always** read a file before editing it.",
            "- Work iteratively: read → understand → edit → verify.",
            "- When editing, ensure old_str matches the file content exactly.",
            "- Run tests after making changes to verify correctness.",
            "- Keep changes minimal and focused.",
        ]

        # 注入项目级文件内容（CLAUDE.md 等）
        if self._project_files:
            prompt_parts.append("")
            prompt_parts.append("## Project context")
            for filename, content in self._project_files.items():
                if content.strip():
                    prompt_parts.append(f"\n### {filename}\n{content}")

        return "\n".join(prompt_parts)

    def _load_project_files(self) -> None:
        """加载项目级上下文文件（CLAUDE.md, AGENTS.md 等）"""
        import os
        patterns = ["CLAUDE.md", "AGENTS.md", "CODEPILOT.md", ".codepilot/instructions.md"]
        for pattern in patterns:
            path = os.path.join(self.cwd, pattern)
            if os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        self._project_files[pattern] = f.read()
                except Exception:
                    pass

    # ──────────────────── LLM 调用 ────────────────────

    async def _call_llm_streaming(self, messages: List[Dict[str, Any]]) -> str:
        """调用 LLM（流式输出），返回完整响应文本"""
        full_response = ""
        thinking = False

        # 使用 spinner 显示等待状态
        with self.output.console.status("[dim]Thinking...[/]", spinner="dots"):
            minimal_messages = _strip_message_metadata(messages)
            try:
                async for token in self._llm_chat_stream(minimal_messages):
                    if not thinking:
                        thinking = True
                        # 清除 spinner，开始真实输出
                        self.output.console.print("")  # 换行
                    full_response += token
                    self.output.stream_token(token)
            except LLMClientError:
                raise
            except Exception as e:
                raise LLMClientError(f"流式调用失败: {e}") from e

        # 流式输出完成后换行
        if thinking:
            print()
        return full_response

    async def _llm_chat_stream(self, messages: List[Dict[str, Any]]):
        """逐 token 产出的 LLM 流式调用"""
        async for token in self.llm.chat_stream(messages=messages, temperature=0.7):
            yield token

    # ──────────────────── 响应解析 ────────────────────

    def _parse_response(self, response_text: str) -> Tuple[str, List[Dict[str, Any]]]:
        """解析 LLM 响应，分离普通文本和工具调用

        Returns:
            (plain_text, tool_calls_list)
        """
        tool_calls = []

        # 使用正则提取所有 <tool_call>...</tool_call> 块
        pattern = r"<tool_call>\s*(.*?)\s*</tool_call>"
        matches = list(re.finditer(pattern, response_text, re.DOTALL))

        for match in matches:
            json_str = match.group(1).strip()
            try:
                tool_call = json.loads(json_str)
                if "name" in tool_call and "args" in tool_call:
                    tool_calls.append({
                        "name": tool_call["name"],
                        "args": tool_call["args"],
                    })
                else:
                    self.output.warn(f"工具调用格式无效，缺少 'name' 或 'args': {json_str[:200]}")
            except json.JSONDecodeError as e:
                self.output.warn(f"工具调用 JSON 解析失败: {e}\n内容: {json_str[:300]}")

        # 提取纯文本（去掉 tool_call 块）
        plain_text = re.sub(pattern, "", response_text, flags=re.DOTALL).strip()

        return plain_text, tool_calls

    # ──────────────────── 工具执行 ────────────────────

    async def _execute_tool_safe(self, tool_call: Dict[str, Any]) -> str:
        """安全执行工具，带权限检查、错误处理和用户确认"""
        name = tool_call["name"]
        args = tool_call["args"]
        args_repr = self._format_tool_args(args)

        # 显示工具调用
        self.output.tool_call_banner(name, args_repr)

        # 获取工具
        tool = self.tools.get_tool(name)
        if tool is None:
            self.output.error(f"工具 '{name}' 不存在")
            return f"ERROR: Tool '{name}' not found. Available tools: {', '.join(self.tools.tools.keys())}"

        # 权限检查
        try:
            permission = tool.can_use_tool(**args)
        except TypeError:
            permission = tool.can_use_tool()

        if not permission.allowed:
            self.output.error(f"工具 '{name}' 被阻止: {permission.reason}")
            return f"ERROR: Tool '{name}' is not allowed: {permission.reason}"

        # 危险工具需要用户确认
        if permission.requires_user_confirmation:
            if not self.output.ask_confirmation(name, args_repr):
                self.output.info("用户取消了工具执行。")
                return f"User cancelled tool execution: {name}"

        # 执行工具
        try:
            result = tool.execute(**args)
        except TypeError as e:
            self.output.error(f"工具参数错误: {e}")
            return f"ERROR: Invalid tool arguments for '{name}': {e}"
        except Exception as e:
            self.output.error(f"工具执行失败: {e}")
            return f"ERROR: Tool '{name}' execution failed: {e}"

        # 格式化结果
        if hasattr(result, "success") and hasattr(result, "output"):
            # ToolOutput 对象
            if result.success:
                output_str = self._format_tool_output(result.output)
                self.output.tool_result_banner(name, True, self._truncate(output_str, 200))
                return output_str
            else:
                error_str = result.error or "Unknown error"
                self.output.tool_result_banner(name, False, error_str)
                return f"ERROR: {error_str}"
        else:
            output_str = str(result)
            self.output.tool_result_banner(name, True, self._truncate(output_str, 200))
            return output_str

    def _format_tool_args(self, args: Dict[str, Any]) -> str:
        """格式化工具参数为可读字符串"""
        parts = []
        for k, v in args.items():
            v_str = str(v)
            if len(v_str) > 80:
                v_str = v_str[:77] + "..."
            # 对于多行内容，只显示行数
            if "\n" in v_str:
                line_count = v_str.count("\n") + 1
                parts.append(f"{k}: [{line_count} lines]")
            else:
                parts.append(f"{k}: {v_str}")
        return ", ".join(parts)

    def _format_tool_output(self, output: Any) -> str:
        """格式化工具输出为字符串"""
        if output is None:
            return "(no output)"
        if isinstance(output, str):
            return output
        if isinstance(output, (dict, list)):
            try:
                return json.dumps(output, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                return str(output)
        return str(output)

    def _truncate(self, text: str, max_len: int) -> str:
        """截断文本"""
        if len(text) <= max_len:
            return text
        return text[:max_len - 3] + "..."

    def _count_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """估算 token 数"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += len(content) // 4
        return total


def _strip_message_metadata(messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """去除消息的元数据字段，只保留 role 和 content"""
    clean = []
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            clean.append({"role": msg.get("role", "user"), "content": content})
        elif isinstance(content, list):
            clean.append({"role": msg.get("role", "user"), "content": str(content)})
        else:
            clean.append({"role": msg.get("role", "user"), "content": str(content)})
    return clean
