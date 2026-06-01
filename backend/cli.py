#!/usr/bin/env python3
"""
CodePilot CLI - 交互式 AI 编程助手

使用方式:
  python cli.py                        交互模式
  python cli.py -p "修复 bug"          单次模式
  python cli.py --model deepseek       指定模型
  python cli.py --cwd /path/to/project 指定工作目录
"""

import os
import sys
import asyncio
import argparse

# 确保 backend 目录在 path 中
sys.path.insert(0, os.path.dirname(__file__))

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.styles import Style
from prompt_toolkit.key_binding import KeyBindings

from app.core.agent_loop import AgentLoop
from app.core.commands import CommandHandler
from app.core.output import Output


# ──── 常量 ────
HISTORY_FILE = os.path.expanduser("~/.codepilot/history")

COMMANDS = [
    "/compact", "/memory", "/stats", "/cache",
    "/help", "/clear", "/reset",
    "/model", "/tools", "/skills",
    "/exit", "/quit",
]

# prompt_toolkit 样式
CLI_STYLE = Style.from_dict({
    "prompt": "#00ff00 bold",
    "separator": "#666666",
})


# ──── 键盘绑定 ────
def create_key_bindings() -> KeyBindings:
    kb = KeyBindings()

    @kb.add("c-c")
    def _(event):
        """Ctrl+C 清除当前输入，不退出程序"""
        event.app.current_buffer.reset()
        print("  (按 Ctrl+D 或输入 /exit 退出)")

    @kb.add("c-d")
    def _(event):
        """Ctrl+D 退出（仅在空行时）"""
        if event.app.current_buffer.text == "":
            event.app.exit()

    return kb


# ──── 交互循环 ────
class CodePilotCLI:
    """CLI 主控制器"""

    def __init__(self, cwd: str = ".", model: str = None):
        self.cwd = os.path.abspath(cwd)
        os.chdir(self.cwd)

        # 初始化核心组件
        self.agent = AgentLoop(cwd=self.cwd)
        self.commands = CommandHandler(self.agent)
        self.output = self.agent.output  # alias

        # 如果指定了模型，覆盖默认
        if model:
            self.agent.llm.model = model
            self.agent.llm._current_model = model

        # 设置 prompt_toolkit session
        self.session = PromptSession(
            history=FileHistory(HISTORY_FILE),
            auto_suggest=AutoSuggestFromHistory(),
            completer=WordCompleter(COMMANDS, ignore_case=True, sentence=True),
            style=CLI_STYLE,
            key_bindings=create_key_bindings(),
        )

    async def run_interactive(self) -> None:
        """交互式 REPL 循环"""
        self.output.print_banner()

        while True:
            try:
                user_input = await self.session.prompt_async(
                    [("class:prompt", "❯ ")],  # 绿色提示符
                )
                user_input = user_input.strip()
                if not user_input:
                    continue

                # 斜杠命令
                if user_input.startswith("/"):
                    should_continue = await self.commands.handle(user_input)
                    if not should_continue:
                        break
                else:
                    await self.agent.process(user_input)

            except KeyboardInterrupt:
                continue
            except EOFError:
                break

    async def run_single(self, prompt: str) -> None:
        """单次模式：执行一个 prompt 后退出"""
        self.output.console.print(
            f"[dim]CodePilot CLI · Model: {self.agent.llm.model} · CWD: {self.cwd}[/]"
        )
        self.output.console.print(f"[bold]❯ {prompt}[/]\n")
        await self.agent.process(prompt)
        self.output.console.print("[dim]Done.[/]")


# ──── main ────
async def main():
    parser = argparse.ArgumentParser(
        description="CodePilot CLI - 交互式 AI 编程助手",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python cli.py                          交互模式
  python cli.py -p "修复 utils.py 的 bug"  单次模式
  python cli.py --model gpt-4            指定模型
  python cli.py --cwd ../my-project      指定工作目录
        """,
    )
    parser.add_argument(
        "-p", "--prompt",
        type=str,
        default=None,
        help="单次模式：直接执行一个 prompt 后退出",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="指定 LLM 模型（覆盖 .env 中的配置）",
    )
    parser.add_argument(
        "--cwd",
        type=str,
        default=".",
        help="工作目录（默认当前目录）",
    )
    args = parser.parse_args()

    cli = CodePilotCLI(cwd=args.cwd, model=args.model)

    if args.prompt:
        await cli.run_single(args.prompt)
    else:
        await cli.run_interactive()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n再见！")
    except ImportError as e:
        print(f"""
╔══════════════════════════════════════════════════════════════╗
║  缺少依赖！请先安装:                                           ║
║                                                              ║
║  pip install prompt_toolkit rich                             ║
║                                                              ║
║  完整安装:                                                     ║
║  pip install -r requirements-cli.txt                          ║
║                                                              ║
║  错误详情: {e}                                         
╚══════════════════════════════════════════════════════════════╝
        """)
        sys.exit(1)
