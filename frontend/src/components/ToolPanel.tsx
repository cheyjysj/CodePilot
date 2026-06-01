import React, { useState, useEffect } from 'react'
import { v4 as uuidv4 } from 'uuid'
import './ToolPanel.css'

interface Tool {
  name: string
  description: string
  version: string
}

interface ToolExecuteResult {
  success: boolean
  result?: any
  error?: string
}

export function ToolPanel() {
  const [tools, setTools] = useState<Tool[]>([])
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null)
  const [toolInput, setToolInput] = useState<string>('{}')
  const [result, setResult] = useState<ToolExecuteResult | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  // 加载工具列表
  useEffect(() => {
    fetchTools()
  }, [])
  
  const fetchTools = async () => {
    try {
      setError(null)
      const response = await fetch('http://localhost:8000/api/tools/list')
      const data = await response.json()
      
      if (data.success) {
        setTools(data.tools)
        if (data.tools.length > 0 && !selectedTool) {
          setSelectedTool(data.tools[0])
        }
      } else {
        setError('Failed to load tools')
      }
    } catch (err) {
      setError(`Error: ${err instanceof Error ? err.message : 'Unknown error'}`)
    }
  }
  
  const handleToolSelect = (tool: Tool) => {
    setSelectedTool(tool)
    setResult(null)
    setError(null)
    
    // 根据工具设置默认输入
    const defaultInputs: Record<string, any> = {
      'FileRead': { file_path: 'path/to/file.txt', offset: 0, limit: -1 },
      'FileEdit': { file_path: 'path/to/file.txt', old_str: 'old', new_str: 'new', replace_all: false },
      'FileWrite': { file_path: 'path/to/file.txt', content: 'content here', mode: 'w' },
      'Bash': { command: 'ls -la', timeout: 30, description: 'List files' },
      'Grep': { pattern: 'search pattern', path: '.', glob: '*.py', output_mode: 'content', case_sensitive: false },
      'Glob': { pattern: '**/*.py', path: '.', recursive: true }
    }
    
    setToolInput(JSON.stringify(defaultInputs[tool.name] || {}, null, 2))
  }
  
  const handleExecute = async () => {
    if (!selectedTool) return
    
    setIsLoading(true)
    setResult(null)
    setError(null)
    
    try {
      const input = JSON.parse(toolInput)
      
      const response = await fetch('http://localhost:8000/api/tools/execute', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          tool_name: selectedTool.name,
          tool_input: input
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
  
  const handleInputChange = (value: string) => {
    setToolInput(value)
    
    // 尝试格式化 JSON
    try {
      const parsed = JSON.parse(value)
      setToolInput(JSON.stringify(parsed, null, 2))
    } catch {
      // 如果不是有效的 JSON，保持原样
    }
  }
  
  return (
    <div className="tool-panel">
      <div className="tool-list">
        <h3>Available Tools ({tools.length})</h3>
        {error && <div className="error-message">{error}</div>}
        <div className="tools-grid">
          {tools.map(tool => (
            <div 
              key={tool.name}
              className={`tool-card ${selectedTool?.name === tool.name ? 'selected' : ''}`}
              onClick={() => handleToolSelect(tool)}
            >
              <div className="tool-name">{tool.name}</div>
              <div className="tool-description">{tool.description}</div>
              <div className="tool-version">v{tool.version}</div>
            </div>
          ))}
        </div>
      </div>
      
      {selectedTool && (
        <div className="tool-executor">
          <h3>Execute: {selectedTool.name}</h3>
          <div className="tool-info">
            <p><strong>Description:</strong> {selectedTool.description}</p>
          </div>
          
          <div className="input-section">
            <label>Tool Input (JSON):</label>
            <textarea
              value={toolInput}
              onChange={e => setToolInput(e.target.value)}
              className="json-input"
              rows={10}
            />
          </div>
          
          <button 
            onClick={handleExecute}
            disabled={isLoading}
            className="execute-button"
          >
            {isLoading ? 'Executing...' : 'Execute Tool'}
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
