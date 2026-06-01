import React, { useState, useEffect } from 'react'
import { ChatWindow } from './components/ChatWindow'
import { ToolPanel } from './components/ToolPanel'
import { SkillPanel } from './components/SkillPanel'
import { WebSocketProvider } from './services/WebSocketProvider'
import './App.css'

function App() {
  const [activeTab, setActiveTab] = useState<'chat' | 'tools' | 'skills'>('chat')
  const [isConnected, setIsConnected] = useState(false)

  return (
    <WebSocketProvider url="ws://localhost:8000/api/chat/ws">
      <div className="app">
        <header className="app-header">
          <h1>CodePilot</h1>
          <div className={`connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
            {isConnected ? '🟢 Connected' : '🔴 Disconnected'}
          </div>
        </header>
        
        <nav className="app-nav">
          <button 
            className={activeTab === 'chat' ? 'active' : ''}
            onClick={() => setActiveTab('chat')}
          >
            Chat
          </button>
          <button 
            className={activeTab === 'tools' ? 'active' : ''}
            onClick={() => setActiveTab('tools')}
          >
            Tools
          </button>
          <button 
            className={activeTab === 'skills' ? 'active' : ''}
            onClick={() => setActiveTab('skills')}
          >
            Skills
          </button>
        </nav>
        
        <main className="app-main">
          {activeTab === 'chat' && <ChatWindow />}
          {activeTab === 'tools' && <ToolPanel />}
          {activeTab === 'skills' && <SkillPanel />}
        </main>
      </div>
    </WebSocketProvider>
  )
}

export default App
