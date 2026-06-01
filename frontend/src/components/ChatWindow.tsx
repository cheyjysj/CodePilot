import React, { useState, useEffect, useRef } from 'react'
import { useWebSocket } from '../services/WebSocketProvider'
import { v4 as uuidv4 } from 'uuid'
import './ChatWindow.css'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
}

export function ChatWindow() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  
  const { sendMessage, lastMessage, readyState } = useWebSocket()
  
  // 自动滚动到底部
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }
  
  useEffect(() => {
    scrollToBottom()
  }, [messages])
  
  // 处理收到的消息
  useEffect(() => {
    if (lastMessage && lastMessage.role === 'assistant') {
      setMessages(prev => [
        ...prev,
        {
          id: uuidv4(),
          role: 'assistant',
          content: lastMessage.content,
          timestamp: lastMessage.timestamp || Date.now()
        }
      ])
      setIsLoading(false)
    }
  }, [lastMessage])
  
  const handleSend = () => {
    if (!input.trim() || isLoading) return
    
    // 添加用户消息
    const userMessage: Message = {
      id: uuidv4(),
      role: 'user',
      content: input,
      timestamp: Date.now()
    }
    
    setMessages(prev => [...prev, userMessage])
    setInput('')
    setIsLoading(true)
    
    // 发送消息
    sendMessage({
      messages: [...messages, userMessage].map(msg => ({
        role: msg.role,
        content: msg.content
      }))
    })
  }
  
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }
  
  return (
    <div className="chat-window">
      <div className="messages-container">
        {messages.length === 0 ? (
          <div className="empty-state">
            <h2>Welcome to CodePilot</h2>
            <p>Start a conversation with your AI coding assistant.</p>
          </div>
        ) : (
          messages.map(msg => (
            <div key={msg.id} className={`message ${msg.role}`}>
              <div className="message-role">
                {msg.role === 'user' ? 'You' : 'CodePilot'}
              </div>
              <div className="message-content">
                {msg.content}
              </div>
              <div className="message-timestamp">
                {new Date(msg.timestamp).toLocaleTimeString()}
              </div>
            </div>
          ))
        )}
        
        {isLoading && (
          <div className="message assistant">
            <div className="message-role">CodePilot</div>
            <div className="message-content loading">
              <div className="loading-dots">
                <span>.</span><span>.</span><span>.</span>
              </div>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>
      
      <div className="input-container">
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type your message... (Shift+Enter for new line)"
          disabled={isLoading || readyState !== WebSocket.OPEN}
          rows={1}
        />
        <button 
          onClick={handleSend}
          disabled={!input.trim() || isLoading || readyState !== WebSocket.OPEN}
        >
          Send
        </button>
      </div>
    </div>
  )
}
