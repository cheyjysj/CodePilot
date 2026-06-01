"""
搜索工具
实现 Grep 和 Glob 工具
"""

import os
import re
import subprocess
from typing import Any, Dict, List, Optional
from app.tools.base_tool import BaseTool, ToolInput, ToolOutput, PermissionCheck


class GrepInput(ToolInput):
    """Grep 工具输入"""
    pattern: str
    path: str = '.'
    glob: Optional[str] = None
    output_mode: str = 'content'  # content, files_with_matches, count
    case_sensitive: bool = False
    context_before: int = 0
    context_after: int = 0


class GrepTool(BaseTool):
    """Grep 搜索工具"""
    
    def __init__(self):
        super().__init__(
            name='Grep',
            description='Search for pattern in files'
        )
    
    def execute(self, pattern: str, path: str = '.', glob: Optional[str] = None, 
                output_mode: str = 'content', case_sensitive: bool = False,
                context_before: int = 0, context_after: int = 0) -> ToolOutput:
        """
        搜索文件内容
        
        Args:
            pattern: 搜索模式（正则表达式）
            path: 搜索路径
            glob: 文件模式（如 *.py）
            output_mode: 输出模式
            case_sensitive: 是否区分大小写
            context_before: 匹配前显示行数
            context_after: 匹配后显示行数
            
        Returns:
            工具输出
        """
        try:
            results = []
            
            # 编译正则表达式
            flags = 0 if case_sensitive else re.IGNORECASE
            regex = re.compile(pattern, flags)
            
            # 遍历文件
            for root, dirs, files in os.walk(path):
                # 跳过隐藏目录和 __pycache__
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
                
                for file in files:
                    # 检查文件模式
                    if glob and not self._match_glob(file, glob):
                        continue
                    
                    file_path = os.path.join(root, file)
                    
                    # 读取文件
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                    except Exception:
                        continue
                    
                    # 搜索
                    matches = []
                    for i, line in enumerate(lines):
                        if regex.search(line):
                            matches.append({
                                'line_num': i + 1,
                                'line': line.rstrip(),
                                'context_before': lines[max(0, i-context_before):i],
                                'context_after': lines[i+1:i+1+context_after]
                            })
                    
                    if matches:
                        if output_mode == 'files_with_matches':
                            results.append(file_path)
                        elif output_mode == 'count':
                            results.append({
                                'file': file_path,
                                'count': len(matches)
                            })
                        else:  # content
                            results.append({
                                'file': file_path,
                                'matches': matches
                            })
            
            return ToolOutput(
                success=True,
                output=results
            )
        except Exception as e:
            return ToolOutput(
                success=False,
                error=str(e)
            )
    
    def _match_glob(self, filename: str, pattern: str) -> bool:
        """
        简单的 glob 匹配
        
        Args:
            filename: 文件名
            pattern: glob 模式
            
        Returns:
            是否匹配
        """
        # 转换 glob 为 regex
        regex_pattern = pattern.replace('.', '\\.')
        regex_pattern = regex_pattern.replace('*', '.*')
        regex_pattern = regex_pattern.replace('?', '.')
        regex_pattern = f"^{regex_pattern}$"
        
        return bool(re.match(regex_pattern, filename))
    
    def can_use_tool(self, pattern: str, path: str = '.', **kwargs) -> PermissionCheck:
        """
        检查搜索权限
        
        Args:
            pattern: 搜索模式
            path: 搜索路径
            
        Returns:
            权限检查结果
        """
        # 检查路径是否可访问
        if not os.path.exists(path):
            return PermissionCheck(
                allowed=False,
                reason=f"Path does not exist: {path}"
            )
        
        return PermissionCheck(allowed=True)


class GlobInput(ToolInput):
    """Glob 工具输入"""
    pattern: str
    path: str = '.'
    recursive: bool = True


class GlobTool(BaseTool):
    """Glob 文件搜索工具"""
    
    def __init__(self):
        super().__init__(
            name='Glob',
            description='Find files matching pattern'
        )
    
    def execute(self, pattern: str, path: str = '.', recursive: bool = True) -> ToolOutput:
        """
        搜索匹配模式的文件
        
        Args:
            pattern: 文件模式（如 **/*.py）
            path: 搜索路径
            recursive: 是否递归搜索
            
        Returns:
            工具输出
        """
        try:
            results = []
            
            # 处理 ** 递归模式
            if '**' in pattern and recursive:
                # 递归搜索
                for root, dirs, files in os.walk(path):
                    # 跳过隐藏目录
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                    
                    for file in files:
                        if self._match_glob(file, pattern.replace('**/', '')):
                            results.append(os.path.join(root, file))
            else:
                # 非递归搜索
                if os.path.exists(path):
                    for file in os.listdir(path):
                        full_path = os.path.join(path, file)
                        if os.path.isfile(full_path) and self._match_glob(file, pattern):
                            results.append(full_path)
            
            return ToolOutput(
                success=True,
                output=results
            )
        except Exception as e:
            return ToolOutput(
                success=False,
                error=str(e)
            )
    
    def _match_glob(self, filename: str, pattern: str) -> bool:
        """
        简单的 glob 匹配
        
        Args:
            filename: 文件名
            pattern: glob 模式
            
        Returns:
            是否匹配
        """
        # 转换 glob 为 regex
        regex_pattern = pattern.replace('.', '\\.')
        regex_pattern = regex_pattern.replace('*', '.*')
        regex_pattern = regex_pattern.replace('?', '.')
        regex_pattern = f"^{regex_pattern}$"
        
        return bool(re.match(regex_pattern, filename))
    
    def can_use_tool(self, pattern: str, path: str = '.', **kwargs) -> PermissionCheck:
        """
        检查搜索权限
        
        Args:
            pattern: 文件模式
            path: 搜索路径
            
        Returns:
            权限检查结果
        """
        # 检查路径是否可访问
        if not os.path.exists(path):
            return PermissionCheck(
                allowed=False,
                reason=f"Path does not exist: {path}"
            )
        
        return PermissionCheck(allowed=True)
