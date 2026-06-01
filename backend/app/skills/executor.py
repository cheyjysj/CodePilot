"""
技能执行器
负责执行技能
"""

import os
import subprocess
from typing import Any, Dict, List, Optional
from app.skills.loader import SkillDefinition, SkillLoader
from app.tools.tool_registry import ToolRegistry


class SkillExecutor:
    """技能执行器"""
    
    def __init__(self):
        self.skill_loader = SkillLoader()
        self.tool_registry = ToolRegistry()
    
    async def execute(self, skill_name: str, args: Dict[str, Any], 
                     context: Optional[Dict[str, Any]] = None) -> Any:
        """
        执行技能
        
        Args:
            skill_name: 技能名称
            args: 技能参数
            context: 执行上下文
            
        Returns:
            执行结果
        """
        # 获取技能
        skill = self.skill_loader.get_skill(skill_name)
        if not skill:
            raise ValueError(f"Skill {skill_name} not found")
        
        # 检查条件激活
        if skill.paths and context:
            if not self._match_paths(skill.paths, context.get('cwd', '')):
                raise ValueError(f"Skill {skill_name} not applicable to current context")
        
        # 检查工具隔离
        if skill.allowed_tools:
            self._check_allowed_tools(skill.allowed_tools, context)
        
        # 执行技能
        if skill.context == 'fork':
            return await self._execute_in_fork(skill, args)
        else:
            return self._render_prompt(skill, args)
    
    def _match_paths(self, patterns: List[str], cwd: str) -> bool:
        """
        检查路径是否匹配
        
        Args:
            patterns: 路径模式列表
            cwd: 当前工作目录
            
        Returns:
            是否匹配
        """
        import fnmatch
        
        for pattern in patterns:
            if fnmatch.fnmatch(cwd, pattern):
                return True
        
        return False
    
    def _check_allowed_tools(self, allowed_tools: List[str], context: Optional[Dict[str, Any]]) -> None:
        """
        检查工具隔离
        
        Args:
            allowed_tools: 允许的工具列表
            context: 执行上下文
            
        Raises:
            ValueError: 如果使用了不允许的工具
        """
        if not context:
            return
        
        # 检查要使用的工具是否在允许列表中
        tool_name = context.get('tool_name')
        if tool_name and tool_name not in allowed_tools:
            raise ValueError(f"Tool {tool_name} not allowed by skill")
    
    async def _execute_in_fork(self, skill: SkillDefinition, args: Dict[str, Any]) -> Any:
        """
        在 fork 中执行技能
        
        Args:
            skill: 技能定义
            args: 技能参数
            
        Returns:
            执行结果
        """
        # TODO: 实现 fork 执行
        # 这里应该创建一个新的上下文来执行技能
        
        # 暂时返回模拟结果
        return f"[Skill {skill.name}] Executed in fork with args: {args}"
    
    def _render_prompt(self, skill: SkillDefinition, args: Dict[str, Any]) -> str:
        """
        渲染 Prompt
        
        Args:
            skill: 技能定义
            args: 技能参数
            
        Returns:
            渲染后的 Prompt
        """
        # 获取技能内容
        content = skill.definition.get('content', '')
        
        # 替换参数
        for key, value in args.items():
            placeholder = f"{{{key}}}"
            content = content.replace(placeholder, str(value))
        
        return content
