"""
终端工具
实现 Bash 工具
"""

import subprocess
import shlex
from typing import Any, Dict, List, Optional
from app.tools.base_tool import BaseTool, ToolInput, ToolOutput, PermissionCheck


class BashInput(ToolInput):
    """Bash 工具输入"""
    command: str
    timeout: int = 30
    description: Optional[str] = None


class BashTool(BaseTool):
    """Bash 命令执行工具"""
    
    def __init__(self):
        super().__init__(
            name='Bash',
            description='Execute bash command'
        )
        # 危险命令列表
        self.dangerous_patterns = [
            'rm -rf',
            'mkfs',
            'dd if=',
            'format',
            'del /f',
            'rmdir /s',
            ':(){ :|:& };:'  # fork bomb
        ]
    
    def execute(self, command: str, timeout: int = 30, description: Optional[str] = None) -> ToolOutput:
        """
        执行 Bash 命令
        
        Args:
            command: 要执行的命令
            timeout: 超时时间（秒）
            description: 命令描述（可选）
            
        Returns:
            工具输出
        """
        try:
            # 执行命令
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=timeout
            )
            
            output = {
                'stdout': result.stdout,
                'stderr': result.stderr,
                'exit_code': result.returncode
            }
            
            return ToolOutput(
                success=True,
                output=output
            )
        except subprocess.TimeoutExpired:
            return ToolOutput(
                success=False,
                error=f"Command timeout ({timeout}s)"
            )
        except Exception as e:
            return ToolOutput(
                success=False,
                error=str(e)
            )
    
    def can_use_tool(self, command: str, **kwargs) -> PermissionCheck:
        """
        检查命令执行权限
        
        Args:
            command: 要执行的命令
            
        Returns:
            权限检查结果
        """
        # 检查危险命令：触发 ask，走用户确认路径
        for pattern in self.dangerous_patterns:
            if pattern in command:
                return PermissionCheck(
                    allowed=True,
                    reason=f'Dangerous command detected: {pattern}',
                    requires_user_confirmation=True
                )
        
        return PermissionCheck(allowed=True)
