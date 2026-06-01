"""
工具注册表
管理所有工具的注册和调用
"""

from typing import Any, Dict, List, Optional
from app.tools.base_tool import BaseTool, PermissionCheck
from app.tools.file_tools import FileReadTool, FileEditTool, FileWriteTool
from app.tools.bash_tool import BashTool
from app.tools.search_tools import GrepTool, GlobTool


class ToolRegistry:
    """工具注册表"""
    
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
        self._initialize_tools()
    
    def _initialize_tools(self) -> None:
        """初始化所有工具"""
        # 注册文件工具
        self.register(FileReadTool())
        self.register(FileEditTool())
        self.register(FileWriteTool())
        
        # 注册终端工具
        self.register(BashTool())
        
        # 注册搜索工具
        self.register(GrepTool())
        self.register(GlobTool())
    
    def register(self, tool: BaseTool) -> None:
        """
        注册工具
        
        Args:
            tool: 工具实例
        """
        if tool.name in self.tools:
            raise ValueError(f"Tool {tool.name} already registered")
        
        self.tools[tool.name] = tool
    
    def unregister(self, tool_name: str) -> None:
        """
        注销工具
        
        Args:
            tool_name: 工具名称
        """
        if tool_name in self.tools:
            del self.tools[tool_name]
    
    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """
        获取工具
        
        Args:
            tool_name: 工具名称
            
        Returns:
            工具实例，如果没有则返回 None
        """
        return self.tools.get(tool_name)
    
    def execute_tool(self, tool_name: str, tool_input: Dict[str, Any], 
                    context: Optional[Dict[str, Any]] = None) -> Any:
        """
        执行工具
        
        Args:
            tool_name: 工具名称
            tool_input: 工具输入
            context: 执行上下文（用于权限检查）
            
        Returns:
            工具输出
        """
        # 获取工具
        tool = self.get_tool(tool_name)
        if not tool:
            raise ValueError(f"Tool {tool_name} not found")
        
        # 权限检查
        permission = tool.can_use_tool(**tool_input)
        if not permission.allowed:
            raise PermissionError(f"Tool {tool_name} not allowed: {permission.reason}")
        
        # 执行工具
        return tool.execute(**tool_input)
    
    def list_tools(self) -> List[Dict[str, Any]]:
        """
        列出所有工具
        
        Returns:
            工具列表
        """
        return [tool.get_schema() for tool in self.tools.values()]
    
    def get_tool_descriptions(self) -> str:
        """
        获取所有工具的描述（用于 LLM prompt）
        
        Returns:
            工具描述字符串
        """
        descriptions = []
        for tool in self.tools.values():
            descriptions.append(f"- {tool.name}: {tool.description}")
        
        return "\n".join(descriptions)
