import React, { createContext, useContext, useRef, useState, useEffect, useCallback } from 'react'

interface WebSocketContextType {
  sendMessage: (message: any) => void
  lastMessage: any
  readyState: number
  messages: any[]
  connect: () => void
  disconnect: () => void
}

const WebSocketContext = createContext<WebSocketContextType | null>(null)

interface WebSocketProviderProps {
  url: string
  children: React.ReactNode
  reconnectInterval?: number
  maxRetries?: number
}

export function WebSocketProvider({ 
  url, 
  children, 
  reconnectInterval = 3000, 
  maxRetries = 5 
}: WebSocketProviderProps) {
  const ws = useRef<WebSocket | null>(null)
  const [lastMessage, setLastMessage] = useState<any>(null)
  const [readyState, setReadyState] = useState<number>(WebSocket.CONNECTING)
  const [messages, setMessages] = useState<any[]>([])
  const retryCount = useRef(0)
  const reconnectTimer = useRef<number | null>(null)
  
  const connect = useCallback(() => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      return
    }
    
    const socket = new WebSocket(url)
    ws.current = socket
    
    socket.onopen = () => {
      setReadyState(WebSocket.OPEN)
      retryCount.current = 0
      console.log('WebSocket connected')
    }
    
    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        setLastMessage(data)
        setMessages(prev => [...prev, data])
      } catch (error) {
        console.error('Error parsing WebSocket message:', error)
      }
    }
    
    socket.onclose = (event) => {
      setReadyState(WebSocket.CLOSED)
      console.log('WebSocket disconnected:', event.reason)
      
      // 尝试重连
      if (retryCount.current < maxRetries) {
        retryCount.current += 1
        console.log(`Reconnecting... Attempt ${retryCount.current}/${maxRetries}`)
        
        reconnectTimer.current = window.setTimeout(() => {
          connect()
        }, reconnectInterval)
      }
    }
    
    socket.onerror = (error) => {
      console.error('WebSocket error:', error)
    }
  }, [url, reconnectInterval, maxRetries])
  
  const disconnect = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current)
    }
    
    if (ws.current) {
      ws.current.close()
      ws.current = null
    }
  }, [])
  
  const sendMessage = useCallback((message: any) => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(message))
    } else {
      console.error('WebSocket is not connected')
    }
  }, [])
  
  useEffect(() => {
    connect()
    
    return () => {
      disconnect()
    }
  }, [connect, disconnect])
  
  const contextValue: WebSocketContextType = {
    sendMessage,
    lastMessage,
    readyState,
    messages,
    connect,
    disconnect
  }
  
  return (
    <WebSocketContext.Provider value={contextValue}>
      {children}
    </WebSocketContext.Provider>
  )
}

export function useWebSocket() {
  const context = useContext(WebSocketContext)
  
  if (!context) {
    throw new Error('useWebSocket must be used within a WebSocketProvider')
  }
  
  return context
}
