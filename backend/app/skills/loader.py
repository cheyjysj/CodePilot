
"""
技能加载器
负责从三种来源加载技能：Bundled、Disk-based、MCP
"""

import os
import json
import yaml
from typing import Any, Dict, List, Optional


class SkillDefinition:
    """技能定义"""
    def __init__(self, name: str, source: str, definition: Dict[str, Any]):
        self.name = name
        self.source = source  # bundled, disk, mcp
        self.definition = definition
        self.description = definition.get('description', '')
        self.context = definition.get('context', 'none')  # none, fork
        self.paths = definition.get('paths', None)
        self.allowed_tools = definition.get('allowedTools', None)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'name': self.name,
            'source': self.source,
            'description': self.description,
            'context': self.context,
            'paths': self.paths,
            'allowed_tools': self.allowed_tools
        }


class SkillLoader:
    """技能加载器"""
    
    def __init__(self):
        self.skills: Dict[str, SkillDefinition] = {}
        self.skills_dir = os.path.expanduser('~/.codepilot/skills')
        os.makedirs(self.skills_dir, exist_ok=True)
        
        # 加载所有技能
        self.load_skills()
    
    def load_skills(self) -> None:
        """加载所有技能"""
        # 1. 加载 Bundled Skills
        self._load_bundled_skills()
        
        # 2. 加载 Disk-based Skills
        self._load_disk_skills()
        
        # 3. 加载 MCP Skills
        self._load_mcp_skills()
    
    def _load_bundled_skills(self) -> None:
        """加载内置技能"""
        # 内置技能定义
        bundled_skills = [
            {
                'name': '代码审查',
                'description': '对代码进行深度审查，提供改进建议',
                'context': 'none',
                'paths': None,
                'allowedTools': ['FileRead', 'Grep']
            },
            {
                'name': '文档生成',
                'description': '为代码生成文档',
                'context': 'fork',
                'paths': ['**/*.py', '**/*.js', '**/*.ts'],
                'allowedTools': ['FileRead', 'FileWrite']
            },
            {
                'name': '测试用例生成',
                'description': '为代码生成测试用例',
                'context': 'fork',
                'paths': ['**/*.py'],
                'allowedTools': ['FileRead', 'FileWrite', 'Bash']
            }
        ]
        
        for skill_def in bundled_skills:
            skill = SkillDefinition(
                name=skill_def['name'],
                source='bundled',
                definition=skill_def
            )
            self.skills[skill.name] = skill
    
    def _load_disk_skills(self) -> None:
        """从磁盘加载技能"""
        # 搜索 .md 文件
        for root, dirs, files in os.walk(self.skills_dir):
            for file in files:
                if file.endswith('.md'):
                    file_path = os.path.join(root, file)
                    self._load_skill_from_file(file_path)
    
    def _load_skill_from_file(self, file_path: str) -> None:
        """
        从文件加载技能
        
        Args:
            file_path: 文件路径
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 解析 YAML front matter
            if content.startswith('---'):
                _, front_matter, skill_content = content.split('---', 2)
                metadata = yaml.safe_load(front_matter)
                
                skill = SkillDefinition(
                    name=metadata.get('name', os.path.basename(file_path)),
                    source='disk',
                    definition={
                        **metadata,
                        'content': skill_content
                    }
                )
                
                self.skills[skill.name] = skill
        except Exception as e:
            print(f"Error loading skill from {file_path}: {e}")
    
    def _load_mcp_skills(self) -> None:
        """从 MCP Server 加载技能"""
        # TODO: 实现 MCP 技能加载
        pass
    
    def get_skill(self, skill_name: str) -> Optional[SkillDefinition]:
        """
        获取技能
        
        Args:
            skill_name: 技能名称
            
        Returns:
            技能定义，如果没有则返回 None
        """
        return self.skills.get(skill_name)
    
    def list_skills(self) -> List[Dict[str, Any]]:
        """
        列出所有技能
        
        Returns:
            技能列表
        """
        return [skill.to_dict() for skill in self.skills.values()]
    
    def register_skill(self, skill: SkillDefinition) -> None:
        """
        注册技能
        
        Args:
            skill: 技能定义
        """
        self.skills[skill.name] = skill
    
    def unregister_skill(self, skill_name: str) -> None:
        """
        注销技能
        
        Args:
            skill_name: 技能名称
        """
        if skill_name in self.skills:
            del self.skills[skill_name]
