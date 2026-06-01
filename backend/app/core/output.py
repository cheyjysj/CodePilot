"""
终端输出美化模块
利用 rich 库实现 Markdown 渲染、代码高亮、工具调用横幅等功能
"""

from rich.console import Console
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner
from typing import Optional


class Output:
    """终端输出美化器"""

    def __init__(self):
        self.console = Console()

    def print_banner(self) -> None:
        """打印启动横幅"""
        import os
        try:
            from app.core.llm_client import LLMClient
            llm = LLMClient()
            model_name = llm.model
        except Exception:
            model_name = "unknown"

        try:
            from app.tools.tool_registry import ToolRegistry
            tools = ToolRegistry()
            tool_count = len(tools.tools)
        except Exception:
            tool_count = 0

        banner = f"""
  ██████╗  ██████╗ ██████╗ ███████╗██████╗ ██╗██╗      ██████╗ ████████╗
 ██╔════╝ ██╔═══██╗██╔══██╗██╔════╝██╔══██╗██║██║     ██╔═══██╗╚══██╔══╝
 ██║      ██║   ██║██║  ██║█████╗  ██████╔╝██║██║     ██║   ██║   ██║
 ██║      ██║   ██║██║  ██║██╔══╝  ██╔═══╝ ██║██║     ██║   ██║   ██║
 ╚██████╗╚██████╔╝██████╔╝███████╗██║     ██║███████╗╚██████╔╝   ██║
  ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝     ╚═╝╚══════╝ ╚═════╝   ╚═╝

  [bold cyan]CodePilot CLI[/] · LLM: [green]{model_name}[/] · Tools: [yellow]{tool_count}[/]
  Type [bold]/help[/] for commands, [bold]/exit[/] to quit
"""
        self.console.print(banner)

    def stream_token(self, token: str) -> None:
        """逐 token 流式输出（非 rich，直接用 print 保证即时性）"""
        print(token, end="", flush=True)

    def render_markdown(self, text: str) -> None:
        """渲染 Markdown 文本"""
        self.console.print(Markdown(text))

    def render_code(self, code: str, language: str = "python", line_numbers: bool = True) -> None:
        """渲染代码块（带语法高亮）"""
        self.console.print(
            Syntax(code, language, theme="monokai", line_numbers=line_numbers)
        )

    def tool_call_banner(self, tool_name: str, description: str = "") -> None:
        """工具调用横幅"""
        content = f"[bold yellow]🔧 {tool_name}[/]"
        if description:
            content += f"\n[dim]{description}[/]"
        self.console.print(Panel(content, border_style="yellow"))

    def tool_result_banner(self, tool_name: str, success: bool, summary: str = "") -> None:
        """工具执行结果横幅"""
        icon = "✅" if success else "❌"
        content = f"[bold]{icon} {tool_name}[/]"
        if summary:
            content += f"\n{summary}"
        style = "green" if success else "red"
        self.console.print(Panel(content, border_style=style))

    def info(self, message: str) -> None:
        """信息提示"""
        self.console.print(f"[bold blue]ℹ[/] {message}")

    def warn(self, message: str) -> None:
        """警告提示"""
        self.console.print(f"[bold yellow]⚠[/] {message}")

    def error(self, message: str) -> None:
        """错误提示"""
        self.console.print(f"[bold red]✗[/] {message}")

    def success(self, message: str) -> None:
        """成功提示"""
        self.console.print(f"[bold green]✓[/] {message}")

    def compact_notice(self, before: int, after: int) -> None:
        """压缩通知"""
        saved_pct = int((1 - after / before) * 100) if before > 0 else 0
        self.console.print(
            f"[bold green]⚡ AutoCompact[/] · {before:,} → {after:,} tokens · "
            f"节省 {saved_pct}%"
        )

    def spinner(self, message: str = "Thinking...") -> Spinner:
        """获取一个旋转动画（用于上下文管理器）"""
        return Spinner("dots", text=f"[dim]{message}[/]")

    def ask_confirmation(self, tool_name: str, details: str) -> bool:
        """询问用户确认"""
        self.console.print(
            Panel(f"[bold yellow]🔧 {tool_name}[/]\n[dim]{details}[/]",
                  title="需要确认", border_style="yellow")
        )
        response = input("  确认执行? [Y/n] ").strip().lower()
        return response in ("", "y", "yes")

    def hr(self) -> None:
        """水平分割线"""
        self.console.rule(style="dim")
