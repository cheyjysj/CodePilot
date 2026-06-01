"""
工具基类
所有工具的抽象基类
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ToolInput(BaseModel):
    """工具输入基类"""
    pass


class ToolOutput(BaseModel):
    """工具输出基类"""
    success: bool = True
    output: Any = None
    error: Optional[str] = None


class PermissionCheck(BaseModel):
    """权限检查结果"""
    allowed: bool = True
    reason: Optional[str] = None
    requires_user_confirmation: bool = False


class BaseTool(ABC):
    """工具基类"""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.version = "1.0.0"
    
    @abstractmethod
    def execute(self, **kwargs) -> ToolOutput:
        """
        执行工具
        
        Args:
            **kwargs: 工具参数
            
        Returns:
            工具输出
        """
        pass
    
    def can_use_tool(self, **kwargs) -> PermissionCheck:
        """
        权限检查
        
        Args:
            **kwargs: 工具参数
            
        Returns:
            权限检查结果
        """
        return PermissionCheck(allowed=True)
    
    def get_schema(self) -> Dict[str, Any]:
        """
        获取工具 Schema
        
        Returns:
            工具 Schema 字典
        """
        return {
            'name': self.name,
            'description': self.description,
            'version': self.version
        }
    
    def __str__(self) -> str:
        return f"{self.name}: {self.description}"
    
    def __repr__(self) -> str:
        return f"BaseTool(name='{self.name}', description='{self.description}')"
