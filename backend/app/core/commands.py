"""
斜杠命令系统
处理 /compact, /memory, /help, /model 等命令行命令
"""

import sys
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from app.core.agent_loop import AgentLoop


class CommandHandler:
    """处理用户输入中以 / 开头的命令"""

    def __init__(self, agent: "AgentLoop"):
        self.agent = agent
        self._commands = {
            "/compact": self._compact,
            "/memory": self._show_memory,
            "/stats": self._show_stats,
            "/cache": self._show_cache,
            "/help": self._help,
            "/clear": self._clear,
            "/model": self._switch_model,
            "/tools": self._list_tools,
            "/skills": self._list_skills,
            "/reset": self._reset,
            "/exit": self._exit,
            "/quit": self._exit,
        }

    async def handle(self, user_input: str) -> bool:
        """
        处理斜杠命令。返回 True 表示是命令（需要继续循环），False 表示退出。
        """
        parts = user_input.strip().split()
        command = parts[0].lower()
        args = parts[1:]

        handler = self._commands.get(command)
        if handler is None:
            self.agent.output.error(f"未知命令: {command}. 输入 /help 查看可用命令。")
            return True

        try:
            return await handler(args)
        except Exception as e:
            self.agent.output.error(f"命令执行失败: {e}")
            return True

    async def _compact(self, args: List[str]) -> bool:
        """手动触发上下文压缩"""
        target_tokens = None
        if args:
            try:
                target_tokens = int(args[0])
            except ValueError:
                self.agent.output.error(f"无效的 token 数: {args[0]}")
                return True

        if not self.agent.messages:
            self.agent.output.info("当前没有对话内容可压缩。")
            return True

        before = len(
            "\n".join(m.get("content", "") for m in self.agent.messages)
        ) // 4

        try:
            if target_tokens:
                self.agent.messages = await self.agent.context.manual_compact_async(
                    self.agent.messages, target_tokens
                )
            else:
                self.agent.messages = await self.agent.context.process_messages_async(
                    self.agent.messages
                )
        except Exception:
            # 降级到同步压缩
            if target_tokens:
                self.agent.messages = self.agent.context.manual_compact(
                    self.agent.messages, target_tokens
                )
            else:
                self.agent.messages = self.agent.context.process_messages(
                    self.agent.messages
                )

        after = len(
            "\n".join(m.get("content", "") for m in self.agent.messages)
        ) // 4
        self.agent.output.compact_notice(before, after)
        return True

    async def _show_memory(self, args: List[str]) -> bool:
        """显示记忆统计"""
        try:
            stats = self.agent.memory.get_stats()
            self.agent.output.console.print(
                Panel(
                    f"[bold]会话记忆数:[/] {stats.get('session_memory_count', 0)}\n"
                    f"[bold]项目记忆数:[/] {stats.get('project_memory_count', 0)}\n"
                    f"[bold]长期记忆数:[/] {stats.get('long_term_memory_count', 0)}\n"
                    f"[bold]会话摘要:[/] {stats.get('session_summary') or '暂无'}",
                    title="🧠 记忆统计",
                    border_style="cyan",
                )
            )
        except Exception as e:
            self.agent.output.error(f"无法获取记忆统计: {e}")
        return True

    async def _show_stats(self, args: List[str]) -> bool:
        """显示压缩统计"""
        try:
            stats = self.agent.context.get_compact_stats()
            msg_count = len(self.agent.messages)
            total_tokens = len(
                "\n".join(m.get("content", "") for m in self.agent.messages)
            ) // 4

            self.agent.output.console.print(
                Panel(
                    f"[bold]消息总数:[/] {msg_count}\n"
                    f"[bold]估算 tokens:[/] {total_tokens:,}\n"
                    f"[bold]压缩次数:[/] {stats['total_compactions']}\n"
                    f"[bold]LLM 压缩次数:[/] {stats['llm_compactions']}",
                    title="📊 会话统计",
                    border_style="cyan",
                )
            )
        except Exception as e:
            self.agent.output.error(f"无法获取统计: {e}")
        return True

    async def _show_cache(self, args: List[str]) -> bool:
        """显示缓存统计"""
        try:
            stats = self.agent.cache.get_cache_stats()
            self.agent.output.console.print(
                Panel(
                    f"[bold]总体命中率:[/] {stats['overall_hit_rate']}\n"
                    f"[bold]Prompt 缓存:[/] {stats['prompt_cache_hit_rate']}\n"
                    f"[bold]文件读取缓存:[/] {stats['file_read_cache_hit_rate']}\n"
                    f"[bold]文件状态缓存:[/] {stats['file_state_cache_hit_rate']}\n"
                    f"[bold]磁盘缓存:[/] {stats['disk_cache_hit_rate']}",
                    title="💾 缓存统计",
                    border_style="cyan",
                )
            )
        except Exception as e:
            self.agent.output.error(f"无法获取缓存统计: {e}")
        return True

    async def _help(self, args: List[str]) -> bool:
        """显示帮助信息"""
        help_text = """
[bold cyan]CodePilot CLI - 可用命令[/]

[bold]会话管理:[/]
  [green]/compact [tokens][/]   - 手动压缩上下文
  [green]/memory[/]            - 查看记忆统计
  [green]/stats[/]             - 查看会话统计
  [green]/cache[/]             - 查看缓存统计
  [green]/clear[/]             - 清空当前对话
  [green]/reset[/]             - 完全重置（清空所有）

[bold]模型与工具:[/]
  [green]/model <name>[/]      - 切换模型
  [green]/tools[/]             - 列出可用工具
  [green]/skills[/]            - 列出可用技能

[bold]系统:[/]
  [green]/help[/]              - 显示此帮助
  [green]/exit[/] 或 [green]/quit[/] - 退出

[bold]交互提示:[/]
  直接输入问题即可与 AI 对话。
  AI 会自动调用工具（读写文件、执行命令、搜索代码等）。
  Ctrl+C 可中断当前操作。
"""
        self.agent.output.console.print(Markdown(help_text))
        return True

    async def _clear(self, args: List[str]) -> bool:
        """清空当前对话（保留系统提示词）"""
        self.agent.messages.clear()
        self.agent.output.success("对话已清空。")
        return True

    async def _reset(self, args: List[str]) -> bool:
        """完全重置（清空对话、记忆、缓存）"""
        self.agent.messages.clear()
        self.agent.memory.session_memory.clear()
        self.agent.cache.clear_all_caches()
        self.agent.output.success("已完全重置（对话、记忆、缓存均已清空）。")
        return True

    async def _switch_model(self, args: List[str]) -> bool:
        """切换模型"""
        if not args:
            self.agent.output.info(f"当前模型: {self.agent.llm.model}")
            return True

        model_name = args[0]
        old_model = self.agent.llm.model
        self.agent.llm.model = model_name
        self.agent.llm._current_model = model_name
        self.agent.output.success(f"模型已切换: {old_model} → {model_name}")
        return True

    async def _list_tools(self, args: List[str]) -> bool:
        """列出可用工具"""
        tools = self.agent.tools.list_tools()
        lines = []
        for t in tools:
            lines.append(f"  [bold]{t['name']}[/] - {t.get('description', '')}")
            if t.get('version'):
                lines[-1] += f" [dim](v{t['version']})[/]"

        self.agent.output.console.print(
            Panel("\n".join(lines), title=f"🔧 可用工具 ({len(tools)})", border_style="cyan")
        )
        return True

    async def _list_skills(self, args: List[str]) -> bool:
        """列出可用技能"""
        try:
            skills = self.agent.skill_loader.list_skills()
            lines = []
            for s in skills:
                source_icon = {"bundled": "📦", "disk": "💾", "mcp": "🔌"}.get(s['source'], "❓")
                lines.append(
                    f"  {source_icon} [bold]{s['name']}[/] - {s.get('description', '')}"
                )

            self.agent.output.console.print(
                Panel("\n".join(lines), title=f"🎯 可用技能 ({len(skills)})", border_style="cyan")
            )
        except Exception as e:
            self.agent.output.error(f"无法列出技能: {e}")
        return True

    async def _exit(self, args: List[str]) -> bool:
        """退出程序"""
        self.agent.output.info("再见！")
        return False
