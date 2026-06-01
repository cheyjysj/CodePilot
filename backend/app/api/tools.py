"""
工具 API 路由
提供工具列表和工具调用接口
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

from app.tools.tool_registry import ToolRegistry


router = APIRouter()

# 初始化工具注册表
tool_registry = ToolRegistry()


class ToolExecuteRequest(BaseModel):
    """工具执行请求"""
    tool_name: str
    tool_input: Dict[str, Any]
    context: Optional[Dict[str, Any]] = None


@router.get("/list")
async def list_tools() -> Dict[str, Any]:
    """
    列出所有工具
    
    Returns:
        工具列表
    """
    tools = tool_registry.list_tools()
    
    return {
        'success': True,
        'tools': tools,
        'count': len(tools)
    }


@router.get("/descriptions")
async def get_tool_descriptions() -> Dict[str, Any]:
    """
    获取所有工具的描述
    
    Returns:
        工具描述字符串
    """
    descriptions = tool_registry.get_tool_descriptions()
    
    return {
        'success': True,
        'descriptions': descriptions
    }


@router.post("/execute")
async def execute_tool(request: ToolExecuteRequest) -> Dict[str, Any]:
    """
    执行工具
    
    Args:
        request: 工具执行请求
        
    Returns:
        执行结果
    """
    try:
        result = tool_registry.execute_tool(
            tool_name=request.tool_name,
            tool_input=request.tool_input,
            context=request.context
        )
        
        return {
            'success': True,
            'result': result.dict() if hasattr(result, 'dict') else str(result)
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


@router.get("/{tool_name}")
async def get_tool_info(tool_name: str) -> Dict[str, Any]:
    """
    获取工具信息
    
    Args:
        tool_name: 工具名称
        
    Returns:
        工具信息
    """
    tool = tool_registry.get_tool(tool_name)
    
    if not tool:
        return {
            'success': False,
            'error': f"Tool {tool_name} not found"
        }
    
    return {
        'success': True,
        'tool': tool.get_schema()
    }
