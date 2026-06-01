"""
技能 API 路由
提供技能列表和技能调用接口
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

from app.skills.loader import SkillLoader
from app.skills.executor import SkillExecutor


router = APIRouter()

# 初始化技能加载器和执行器
skill_loader = SkillLoader()
skill_executor = SkillExecutor()


class SkillExecuteRequest(BaseModel):
    """技能执行请求"""
    skill_name: str
    args: Dict[str, Any]
    context: Optional[Dict[str, Any]] = None


@router.get("/list")
async def list_skills() -> Dict[str, Any]:
    """
    列出所有技能
    
    Returns:
        技能列表
    """
    skills = skill_loader.list_skills()
    
    return {
        'success': True,
        'skills': skills,
        'count': len(skills)
    }


@router.get("/{skill_name}")
async def get_skill_info(skill_name: str) -> Dict[str, Any]:
    """
    获取技能信息
    
    Args:
        skill_name: 技能名称
        
    Returns:
        技能信息
    """
    skill = skill_loader.get_skill(skill_name)
    
    if not skill:
        return {
            'success': False,
            'error': f"Skill {skill_name} not found"
        }
    
    return {
        'success': True,
        'skill': skill
    }


@router.post("/execute")
async def execute_skill(request: SkillExecuteRequest) -> Dict[str, Any]:
    """
    执行技能
    
    Args:
        request: 技能执行请求
        
    Returns:
        执行结果
    """
    try:
        result = await skill_executor.execute(
            skill_name=request.skill_name,
            args=request.args,
            context=request.context
        )
        
        return {
            'success': True,
            'result': result
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


@router.get("/sources")
async def get_skill_sources() -> Dict[str, Any]:
    """
    获取技能来源
    
    Returns:
        技能来源列表
    """
    sources = [
        {
            'name': 'bundled',
            'description': 'Bundled skills (built-in)',
            'security_level': 'high'
        },
        {
            'name': 'disk',
            'description': 'Disk-based skills (user-defined)',
            'security_level': 'medium'
        },
        {
            'name': 'mcp',
            'description': 'MCP skills (remote)',
            'security_level': 'low'
        }
    ]
    
    return {
        'success': True,
        'sources': sources
    }
