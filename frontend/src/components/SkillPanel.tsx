import React, { useState, useEffect } from 'react'
import { v4 as uuidv4 } from 'uuid'
import './SkillPanel.css'

interface Skill {
  name: string
  source: string
  description: string
  context: string
  paths?: string[]
  allowed_tools?: string[]
}

interface SkillExecuteResult {
  success: boolean
  result?: any
  error?: string
}

export function SkillPanel() {
  const [skills, setSkills] = useState<Skill[]>([])
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null)
  const [skillArgs, setSkillArgs] = useState<string>('{}')
  const [result, setResult] = useState<SkillExecuteResult | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  // 加载技能列表
  useEffect(() => {
    fetchSkills()
  }, [])
  
  const fetchSkills = async () => {
    try {
      setError(null)
      const response = await fetch('http://localhost:8000/api/skills/list')
      const data = await response.json()
      
      if (data.success) {
        setSkills(data.skills)
        if (data.skills.length > 0 && !selectedSkill) {
          setSelectedSkill(data.skills[0])
        }
      } else {
        setError('Failed to load skills')
      }
    } catch (err) {
      setError(`Error: ${err instanceof Error ? err.message : 'Unknown error'}`)
    }
  }
  
  const handleSkillSelect = (skill: Skill) => {
    setSelectedSkill(skill)
    setResult(null)
    setError(null)
    
    // 根据技能设置默认参数
    const defaultArgs: Record<string, any> = {}
    
    if (skill.name === '代码审查') {
      defaultArgs['file_path'] = 'path/to/file.py'
    } else if (skill.name === '文档生成') {
      defaultArgs['output_path'] = 'docs/README.md'
    } else if (skill.name === '测试用例生成') {
      defaultArgs['test_framework'] = 'pytest'
    }
    
    setSkillArgs(JSON.stringify(defaultArgs, null, 2))
  }
  
  const handleExecute = async () => {
    if (!selectedSkill) return
    
    setIsLoading(true)
    setResult(null)
    setError(null)
    
    try {
      const args = JSON.parse(skillArgs)
      
      const response = await fetch('http://localhost:8000/api/skills/execute', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          skill_name: selectedSkill.name,
          args: args
        })
      })
      
      const data = await response.json()
      setResult(data)
    } catch (err) {
      setError(`Error: ${err instanceof Error ? err.message : 'Unknown error'}`)
    } finally {
      setIsLoading(false)
    }
  }
  
  const handleArgsChange = (value: string) => {
    setSkillArgs(value)
    
    // 尝试格式化 JSON
    try {
      const parsed = JSON.parse(value)
      setSkillArgs(JSON.stringify(parsed, null, 2))
    } catch {
      // 如果不是有效的 JSON，保持原样
    }
  }
  
  const getSourceLabel = (source: string) => {
    const labels: Record<string, string> = {
      'bundled': 'Bundled',
      'disk': 'Disk',
      'mcp': 'MCP'
    }
    return labels[source] || source
  }
  
  const getSourceColor = (source: string) => {
    const colors: Record<string, string> = {
      'bundled': '#16a34a',
      'disk': '#3b82f6',
      'mcp': '#f59e0b'
    }
    return colors[source] || '#6b7280'
  }
  
  return (
    <div className="skill-panel">
      <div className="skill-list">
        <h3>Available Skills ({skills.length})</h3>
        {error && <div className="error-message">{error}</div>}
        <div className="skills-grid">
          {skills.map(skill => (
            <div 
              key={skill.name}
              className={`skill-card ${selectedSkill?.name === skill.name ? 'selected' : ''}`}
              onClick={() => handleSkillSelect(skill)}
            >
              <div className="skill-header">
                <div className="skill-name">{skill.name}</div>
                <div 
                  className="skill-source"
                  style={{ backgroundColor: getSourceColor(skill.source) }}
                >
                  {getSourceLabel(skill.source)}
                </div>
              </div>
              <div className="skill-description">{skill.description}</div>
              <div className="skill-meta">
                <span>Context: {skill.context}</span>
                {skill.paths && <span>Paths: {skill.paths.length}</span>}
                {skill.allowed_tools && <span>Tools: {skill.allowed_tools.length}</span>}
              </div>
            </div>
          ))}
        </div>
      </div>
      
      {selectedSkill && (
        <div className="skill-executor">
          <h3>Execute: {selectedSkill.name}</h3>
          <div className="skill-info">
            <p><strong>Description:</strong> {selectedSkill.description}</p>
            <p><strong>Source:</strong> {getSourceLabel(selectedSkill.source)}</p>
            <p><strong>Context:</strong> {selectedSkill.context}</p>
            {selectedSkill.paths && (
              <p><strong>Paths:</strong> {selectedSkill.paths.join(', ')}</p>
            )}
            {selectedSkill.allowed_tools && (
              <p><strong>Allowed Tools:</strong> {selectedSkill.allowed_tools.join(', ')}</p>
            )}
          </div>
          
          <div className="input-section">
            <label>Skill Arguments (JSON):</label>
            <textarea
              value={skillArgs}
              onChange={e => setSkillArgs(e.target.value)}
              className="json-input"
              rows={10}
            />
          </div>
          
          <button 
            onClick={handleExecute}
            disabled={isLoading}
            className="execute-button"
          >
            {isLoading ? 'Executing...' : 'Execute Skill'}
          </button>
          
          {result && (
            <div className={`result-section ${result.success ? 'success' : 'error'}`}>
              <h4>Result:</h4>
              <pre>{JSON.stringify(result, null, 2)}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
