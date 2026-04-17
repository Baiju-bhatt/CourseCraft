import { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, AuthError } from '../api'

function ChatIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  )
}

function CloseIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}

function SendIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  )
}

function TrashIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14H6L5 6" />
      <path d="M10 11v6M14 11v6" />
      <path d="M9 6V4h6v2" />
    </svg>
  )
}

function LoginIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
      <polyline points="10 17 15 12 10 7" />
      <line x1="15" y1="12" x2="3" y2="12" />
    </svg>
  )
}

function TypingIndicator() {
  return (
    <div className="chatbot-typing-indicator" aria-label="AI is thinking">
      <span className="chatbot-typing-dot" style={{ animationDelay: '0ms' }} />
      <span className="chatbot-typing-dot" style={{ animationDelay: '160ms' }} />
      <span className="chatbot-typing-dot" style={{ animationDelay: '320ms' }} />
    </div>
  )
}

function MessageBubble({ role, content }) {
  const isUser = role === 'user'

  return (
    <div className={`chatbot-message-row ${isUser ? 'chatbot-message-row--user' : 'chatbot-message-row--ai'}`}>
      {!isUser && (
        <div className="chatbot-avatar chatbot-avatar--ai" aria-hidden="true">AI</div>
      )}
      <div className={`chatbot-bubble ${isUser ? 'chatbot-bubble--user' : 'chatbot-bubble--ai'}`}>
        {isUser ? (
          <p className="chatbot-bubble-text">{content}</p>
        ) : (
          <div className="chatbot-markdown">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {content}
            </ReactMarkdown>
          </div>
        )}
      </div>
      {isUser && (
        <div className="chatbot-avatar chatbot-avatar--user" aria-hidden="true">You</div>
      )}
    </div>
  )
}

function SessionExpiredBanner({ onLoginClick }) {
  return (
    <div className="chatbot-session-expired">
      <div className="chatbot-session-expired-icon">🔒</div>
      <p className="chatbot-session-expired-title">Session Expired</p>
      <p className="chatbot-session-expired-text">
        Your login session has expired. Please log in again to continue using the AI assistant.
      </p>
      <button className="chatbot-session-login-btn" onClick={onLoginClick}>
        <LoginIcon />
        <span>Go to Login</span>
      </button>
    </div>
  )
}

export default function ChatbotWidget() {
  const [isOpen, setIsOpen] = useState(false)
  const [messages, setMessages] = useState([])
  const [inputValue, setInputValue] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [sessionExpired, setSessionExpired] = useState(false)

  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)
  const panelRef = useRef(null)
  const navigate = useNavigate()

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, isLoading])

  useEffect(() => {
    if (isOpen && !sessionExpired && inputRef.current) {
      setTimeout(() => inputRef.current?.focus(), 120)
    }
  }, [isOpen, sessionExpired])

  const toggleOpen = useCallback(() => {
    setIsOpen((prev) => !prev)
    setError('')
  }, [])

  const clearChat = useCallback(() => {
    setMessages([])
    setError('')
    setInputValue('')
    setSessionExpired(false)
  }, [])

  const handleSessionExpiredLogin = useCallback(() => {
    setIsOpen(false)
    navigate('/login')
  }, [navigate])

  const sendMessage = useCallback(async () => {
    const trimmed = inputValue.trim()
    if (!trimmed || isLoading || sessionExpired) return

    const userMessage = { role: 'user', content: trimmed }
    const currentHistory = [...messages]

    setMessages((prev) => [...prev, userMessage])
    setInputValue('')
    setError('')
    setIsLoading(true)

    try {
      const data = await api.chat(trimmed, currentHistory, '')
      const assistantMessage = {
        role: 'assistant',
        content: data.reply || 'No response received.',
      }
      setMessages((prev) => [...prev, assistantMessage])
    } catch (err) {
      if (err instanceof AuthError) {
        setSessionExpired(true)
        setError('')
      } else {
        setError(err.message || 'Failed to get a response. Please try again.')
      }
    } finally {
      setIsLoading(false)
    }
  }, [inputValue, isLoading, messages, sessionExpired])

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const hasMessages = messages.length > 0

  return (
    <>
      <button
        className={`chatbot-fab ${isOpen ? 'chatbot-fab--open' : ''}`}
        onClick={toggleOpen}
        aria-label={isOpen ? 'Close AI Assistant' : 'Open AI Assistant'}
        title={isOpen ? 'Close AI Assistant' : 'Ask AI Assistant'}
      >
        {isOpen ? <CloseIcon /> : <ChatIcon />}
        {!isOpen && <span className="chatbot-fab-label">Ask AI</span>}
      </button>

      {isOpen && (
        <div className="chatbot-panel" ref={panelRef} role="dialog" aria-label="AI Learning Assistant">
          <div className="chatbot-header">
            <div className="chatbot-header-identity">
              <div className="chatbot-header-avatar">AI</div>
              <div>
                <p className="chatbot-header-title">AI Learning Assistant</p>
                <p className="chatbot-header-subtitle">Ask anything about any topic or concept</p>
              </div>
            </div>
            <div className="chatbot-header-actions">
              {hasMessages && !sessionExpired && (
                <button
                  className="chatbot-icon-btn"
                  onClick={clearChat}
                  aria-label="Clear conversation"
                  title="Clear conversation"
                >
                  <TrashIcon />
                </button>
              )}
              <button
                className="chatbot-icon-btn"
                onClick={toggleOpen}
                aria-label="Close chat"
                title="Close"
              >
                <CloseIcon />
              </button>
            </div>
          </div>

          <div className="chatbot-messages" aria-live="polite" aria-atomic="false">
            {sessionExpired ? (
              <SessionExpiredBanner onLoginClick={handleSessionExpiredLogin} />
            ) : (
              <>
                {!hasMessages && !isLoading && (
                  <div className="chatbot-empty-state">
                    <div className="chatbot-empty-icon">🎓</div>
                    <p className="chatbot-empty-title">How can I help you learn?</p>
                    <p className="chatbot-empty-subtitle">
                      Ask me anything, including concepts, tools, workflows, examples, best practices, or
                      explanations for any topic in your course.
                    </p>
                    <div className="chatbot-suggestion-list">
                      {[
                        'What is a data pipeline and how does it work?',
                        'Explain SQL JOINs with examples',
                        'What are the key differences between supervised and unsupervised learning?',
                        'How does REST API authentication work?',
                      ].map((suggestion) => (
                        <button
                          key={suggestion}
                          className="chatbot-suggestion-chip"
                          onClick={() => {
                            setInputValue(suggestion)
                            inputRef.current?.focus()
                          }}
                        >
                          {suggestion}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {messages.map((msg, idx) => (
                  <MessageBubble key={idx} role={msg.role} content={msg.content} />
                ))}

                {isLoading && (
                  <div className="chatbot-message-row chatbot-message-row--ai">
                    <div className="chatbot-avatar chatbot-avatar--ai" aria-hidden="true">AI</div>
                    <div className="chatbot-bubble chatbot-bubble--ai chatbot-bubble--loading">
                      <TypingIndicator />
                    </div>
                  </div>
                )}

                {error && (
                  <div className="chatbot-error-banner">
                    <span>⚠ {error}</span>
                    <button className="chatbot-error-dismiss" onClick={() => setError('')}>✕</button>
                  </div>
                )}
              </>
            )}

            <div ref={messagesEndRef} />
          </div>

          {!sessionExpired && (
            <>
              <div className="chatbot-input-area">
                <textarea
                  ref={inputRef}
                  className="chatbot-input"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Ask a question about any topic..."
                  rows={1}
                  disabled={isLoading}
                  aria-label="Chat message input"
                />
                <button
                  className="chatbot-send-btn"
                  onClick={sendMessage}
                  disabled={isLoading || !inputValue.trim()}
                  aria-label="Send message"
                  title="Send (Enter)"
                >
                  <SendIcon />
                </button>
              </div>
              <p className="chatbot-input-hint">Enter to send · Shift+Enter for new line</p>
            </>
          )}
        </div>
      )}
    </>
  )
}
