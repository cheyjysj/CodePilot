"""
文件工具
实现 FileRead、FileEdit、FileWrite 工具
"""

import os
import re
from typing import Any, Dict, List, Optional
from app.tools.base_tool import BaseTool, ToolInput, ToolOutput, PermissionCheck


class FileReadInput(ToolInput):
    """FileRead 工具输入"""
    file_path: str
    offset: int = 0
    limit: int = -1


class FileReadTool(BaseTool):
    """文件读取工具"""
    
    def __init__(self):
        super().__init__(
            name='FileRead',
            description='Read file content with optional offset and limit'
        )
    
    def execute(self, file_path: str, offset: int = 0, limit: int = -1) -> ToolOutput:
        """
        读取文件
        
        Args:
            file_path: 文件路径
            offset: 起始行（0-based）
            limit: 读取行数（-1 表示读取全部）
            
        Returns:
            工具输出
        """
        try:
            # 检查文件是否存在
            if not os.path.exists(file_path):
                return ToolOutput(
                    success=False,
                    error=f"File not found: {file_path}"
                )
            
            # 检查是否是文件
            if not os.path.isfile(file_path):
                return ToolOutput(
                    success=False,
                    error=f"Not a file: {file_path}"
                )
            
            # 读取文件
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 应用 offset 和 limit
            if limit == -1:
                content = ''.join(lines[offset:])
            else:
                content = ''.join(lines[offset:offset + limit])
            
            return ToolOutput(
                success=True,
                output=content
            )
        except Exception as e:
            return ToolOutput(
                success=False,
                error=str(e)
            )
    
    def can_use_tool(self, file_path: str, **kwargs) -> PermissionCheck:
        """
        检查文件读取权限
        
        Args:
            file_path: 文件路径
            
        Returns:
            权限检查结果
        """
        # 禁止读取敏感文件
        sensitive_patterns = [
            '/etc/passwd',
            '/etc/shadow',
            'id_rsa',
            'id_ed25519',
            '.env'
        ]
        
        # 敏感文件走 ask 确认路径，而非直接 deny
        if any(pattern in file_path for pattern in sensitive_patterns):
            return PermissionCheck(
                allowed=True,
                reason=f'Sensitive file detected: {file_path}',
                requires_user_confirmation=True
            )
        
        return PermissionCheck(allowed=True)


class FileEditInput(ToolInput):
    """FileEdit 工具输入"""
    file_path: str
    old_str: str
    new_str: str
    replace_all: bool = False


class FileEditTool(BaseTool):
    """文件编辑工具"""
    
    def __init__(self):
        super().__init__(
            name='FileEdit',
            description='Edit file by replacing old string with new string'
        )
    
    def execute(self, file_path: str, old_str: str, new_str: str, replace_all: bool = False) -> ToolOutput:
        """
        编辑文件
        
        Args:
            file_path: 文件路径
            old_str: 要替换的字符串
            new_str: 新字符串
            replace_all: 是否替换所有匹配
            
        Returns:
            工具输出
        """
        try:
            # 检查文件是否存在
            if not os.path.exists(file_path):
                return ToolOutput(
                    success=False,
                    error=f"File not found: {file_path}"
                )
            
            # 读取文件
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 检查 old_str 是否存在
            if old_str not in content:
                return ToolOutput(
                    success=False,
                    error=f"String not found: {old_str}"
                )
            
            # 替换
            if replace_all:
                new_content = content.replace(old_str, new_str)
            else:
                new_content = content.replace(old_str, new_str, 1)
            
            # 写回文件
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            # 返回替换次数
            count = content.count(old_str) if replace_all else 1
            
            return ToolOutput(
                success=True,
                output=f"Replaced {count} occurrence(s)"
            )
        except Exception as e:
            return ToolOutput(
                success=False,
                error=str(e)
            )
    
    def can_use_tool(self, file_path: str, **kwargs) -> PermissionCheck:
        """
        检查文件编辑权限
        
        Args:
            file_path: 文件路径
            
        Returns:
            权限检查结果
        """
        # 文件不可写 → 直接 deny
        if os.path.exists(file_path) and not os.access(file_path, os.W_OK):
            return PermissionCheck(
                allowed=False,
                reason=f"File is not writable: {file_path}"
            )
        
        # 编辑已存在的文件 → ask 确认
        if os.path.exists(file_path):
            return PermissionCheck(
                allowed=True,
                reason=f"Editing existing file: {file_path}",
                requires_user_confirmation=True
            )
        
        return PermissionCheck(allowed=True)


class FileWriteInput(ToolInput):
    """FileWrite 工具输入"""
    file_path: str
    content: str
    mode: str = 'w'  # 'w' 覆盖，'a' 追加


class FileWriteTool(BaseTool):
    """文件写入工具"""
    
    def __init__(self):
        super().__init__(
            name='FileWrite',
            description='Write content to file'
        )
    
    def execute(self, file_path: str, content: str, mode: str = 'w') -> ToolOutput:
        """
        写入文件
        
        Args:
            file_path: 文件路径
            content: 文件内容
            mode: 写入模式（'w' 覆盖，'a' 追加）
            
        Returns:
            工具输出
        """
        try:
            # 创建目录
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # 写入文件
            with open(file_path, mode, encoding='utf-8') as f:
                f.write(content)
            
            return ToolOutput(
                success=True,
                output=f"File written: {file_path}"
            )
        except Exception as e:
            return ToolOutput(
                success=False,
                error=str(e)
            )
    
    def can_use_tool(self, file_path: str, **kwargs) -> PermissionCheck:
        """
        检查文件写入权限
        
        Args:
            file_path: 文件路径
            
        Returns:
            权限检查结果
        """
        # 目录不可写 → 直接 deny
        dir_path = os.path.dirname(file_path)
        if dir_path and not os.access(dir_path, os.W_OK):
            return PermissionCheck(
                allowed=False,
                reason=f"Directory is not writable: {dir_path}"
            )
        
        # 覆盖已存在的文件 → ask 确认
        if os.path.exists(file_path):
            return PermissionCheck(
                allowed=True,
                reason=f"Overwriting existing file: {file_path}",
                requires_user_confirmation=True
            )
        
        return PermissionCheck(allowed=True)
