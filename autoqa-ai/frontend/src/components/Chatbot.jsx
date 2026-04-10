import React, { useState, useRef, useEffect, useCallback } from 'react';
import { sendChatMessage, getChatSessions, createChatSession, deleteChatSession, getSessionMessages } from '../api/client';
import { useAuth } from '../context/AuthContext';
import {
  MdClose, MdSend, MdPerson, MdOutlineRefresh,
  MdOutlineChat, MdOutlineMinimize, MdOutlineHistory,
  MdAdd, MdDeleteOutline,
} from 'react-icons/md';
import { RiRobot2Line } from 'react-icons/ri';

const QUICK_PROMPTS = [
  { label: 'Write a test case', text: 'How do I write a good test case?' },
  { label: 'Boundary testing',  text: 'What is boundary value testing?' },
  { label: 'Reduce risk',       text: 'How can I reduce high risk in my modules?' },
  { label: 'Code quality',      text: 'What makes code high quality?' },
];

const WELCOME = "Hi! I'm **AutoQA Assistant** — your AI-powered QA expert.\n\nI can help you with test cases, code reviews, risk analysis, and QA best practices. What would you like to know?";

function TypingDots() {
  return (
    <div className="flex items-end gap-1 px-1 py-1 h-5">
      {[0,1,2].map(i => (
        <span key={i} className="w-1.5 h-1.5 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: `${i*0.18}s` }} />
      ))}
    </div>
  );
}

function renderText(text) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\n)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={i}>{part.slice(2,-2)}</strong>;
    if (part.startsWith('`') && part.endsWith('`')) return <code key={i} className="bg-black/10 px-1 rounded text-xs font-mono">{part.slice(1,-1)}</code>;
    if (part === '\n') return <br key={i} />;
    return part;
  });
}

function Message({ msg }) {
  const isUser = msg.role === 'user';
  return (
    <div className={`flex gap-2.5 items-end ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
      <div className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 ${isUser ? 'bg-blue-600' : 'bg-gradient-to-br from-blue-500 to-violet-600'} shadow-sm`}>
        {isUser ? <MdPerson className="text-white text-sm" /> : <RiRobot2Line className="text-white text-sm" />}
      </div>
      <div className={`max-w-[75%] text-sm leading-relaxed ${isUser ? 'bg-blue-600 text-white rounded-2xl rounded-br-sm px-4 py-2.5 shadow-sm' : 'bg-white border border-slate-200 text-slate-800 rounded-2xl rounded-bl-sm px-4 py-2.5 shadow-sm'}`}>
        {renderText(msg.content)}
      </div>
    </div>
  );
}

export default function Chatbot() {
  const { user } = useAuth();
  const [open, setOpen]         = useState(false);
  const [minimized, setMin]     = useState(false);
  const [activeTab, setActiveTab] = useState('chat'); // 'chat' | 'history'
  const [input, setInput]       = useState('');
  const [messages, setMessages] = useState([{ role: 'assistant', content: WELCOME }]);
  const [loading, setLoading]   = useState(false);
  const [unread, setUnread]     = useState(0);
  const [sessions, setSessions] = useState([]);
  const [sessionId, setSessionId] = useState(null);
  const [sessLoading, setSessLoading] = useState(false);
  const bottomRef = useRef(null);
  const inputRef  = useRef(null);

  // Load sessions when history tab opens
  const loadSessions = useCallback(async () => {
    if (!user) return;
    setSessLoading(true);
    try {
      const res = await getChatSessions();
      setSessions(res.data.sessions || []);
    } catch {}
    finally { setSessLoading(false); }
  }, [user]);

  useEffect(() => {
    if (open && !minimized && activeTab === 'history') loadSessions();
  }, [open, minimized, activeTab, loadSessions]);

  useEffect(() => {
    if (open && !minimized) { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }); setUnread(0); }
  }, [messages, loading, open, minimized]);

  useEffect(() => {
    if (open && !minimized) { setTimeout(() => inputRef.current?.focus(), 150); setUnread(0); }
  }, [open, minimized]);

  // Start a new session
  const startNewSession = async () => {
    if (!user) return;
    try {
      const res = await createChatSession('New Chat');
      setSessionId(res.data.session_id);
      setMessages([{ role: 'assistant', content: WELCOME }]);
      setActiveTab('chat');
    } catch {}
  };

  // Load a session's messages
  const loadSession = async (sess) => {
    try {
      const res = await getSessionMessages(sess.id);
      const msgs = res.data.messages || [];
      setMessages(msgs.length > 0
        ? msgs.map(m => ({ role: m.role, content: m.content }))
        : [{ role: 'assistant', content: WELCOME }]
      );
      setSessionId(sess.id);
      setActiveTab('chat');
    } catch {}
  };

  // Delete a session
  const removeSession = async (e, id) => {
    e.stopPropagation();
    try {
      await deleteChatSession(id);
      setSessions(s => s.filter(x => x.id !== id));
      if (sessionId === id) { setSessionId(null); setMessages([{ role: 'assistant', content: WELCOME }]); }
    } catch {}
  };

  const send = async (text) => {
    const userText = (text || input).trim();
    if (!userText || loading) return;
    setInput('');

    // Auto-create session if none
    let sid = sessionId;
    if (!sid && user) {
      try {
        const res = await createChatSession(userText.slice(0, 50));
        sid = res.data.session_id;
        setSessionId(sid);
      } catch {}
    }

    const newMessages = [...messages, { role: 'user', content: userText }];
    setMessages(newMessages);
    setLoading(true);

    try {
      const res = await sendChatMessage(newMessages, sid);
      setMessages(prev => [...prev, { role: 'assistant', content: res.data.reply }]);
      if (!open || minimized) setUnread(u => u + 1);
    } catch (e) {
      const errMsg = e.response?.data?.error || '';
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: errMsg.includes('rate limit') || errMsg.includes('429')
          ? "I'm getting too many requests. Please wait a moment and try again."
          : 'Something went wrong. Please try again.'
      }]);
    } finally { setLoading(false); }
  };

  const toggleOpen = () => { setOpen(o => !o); setMin(false); setUnread(0); };

  const formatDate = (str) => {
    if (!str) return '';
    const d = new Date(str);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  return (
    <>
      {/* Chat Window */}
      <div className={`fixed z-50 transition-all duration-300 origin-bottom-right bottom-0 right-0 w-full sm:bottom-20 sm:right-5 sm:w-[390px] ${open ? 'scale-100 opacity-100 pointer-events-auto' : 'scale-90 opacity-0 pointer-events-none'}`}>
        <div className={`bg-white shadow-2xl border border-slate-200 flex flex-col overflow-hidden transition-all duration-300 rounded-t-2xl sm:rounded-2xl ${minimized ? 'h-14' : 'h-[88vh] sm:h-[580px]'}`}>

          {/* Header */}
          <div className="flex items-center gap-3 px-4 py-3 bg-gradient-to-r from-blue-600 to-violet-600 shrink-0">
            <div className="w-9 h-9 bg-white/20 rounded-full flex items-center justify-center ring-2 ring-white/30">
              <RiRobot2Line className="text-white text-lg" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-white leading-tight">AutoQA Assistant</p>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse" />
                <p className="text-xs text-blue-100">
                  {user ? `Hi, ${user.username} · Gemini AI` : 'Online · Gemini AI'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-1">
              {user && (
                <button onClick={startNewSession} title="New chat" className="p-1.5 hover:bg-white/20 rounded-lg transition-colors">
                  <MdAdd className="text-white text-base" />
                </button>
              )}
              <button onClick={() => setMin(m => !m)} title="Minimize" className="p-1.5 hover:bg-white/20 rounded-lg transition-colors">
                <MdOutlineMinimize className="text-white text-base" />
              </button>
              <button onClick={toggleOpen} title="Close" className="p-1.5 hover:bg-white/20 rounded-lg transition-colors">
                <MdClose className="text-white text-base" />
              </button>
            </div>
          </div>

          {!minimized && (
            <>
              {/* Tabs */}
              {user && (
                <div className="flex border-b border-slate-200 shrink-0 bg-white">
                  <button
                    onClick={() => setActiveTab('chat')}
                    className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 text-xs font-semibold border-b-2 transition-colors ${activeTab === 'chat' ? 'border-blue-600 text-blue-600' : 'border-transparent text-slate-500 hover:text-slate-700'}`}
                  >
                    <MdOutlineChat className="text-sm" /> Chat
                  </button>
                  <button
                    onClick={() => setActiveTab('history')}
                    className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 text-xs font-semibold border-b-2 transition-colors ${activeTab === 'history' ? 'border-blue-600 text-blue-600' : 'border-transparent text-slate-500 hover:text-slate-700'}`}
                  >
                    <MdOutlineHistory className="text-sm" /> History
                  </button>
                </div>
              )}

              {/* Chat tab */}
              {activeTab === 'chat' && (
                <>
                  <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 bg-slate-50">
                    {messages.map((msg, i) => <Message key={i} msg={msg} />)}
                    {loading && (
                      <div className="flex gap-2.5 items-end">
                        <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center shrink-0 shadow-sm">
                          <RiRobot2Line className="text-white text-sm" />
                        </div>
                        <div className="bg-white border border-slate-200 rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm">
                          <TypingDots />
                        </div>
                      </div>
                    )}
                    <div ref={bottomRef} />
                  </div>

                  {messages.length === 1 && !loading && (
                    <div className="px-4 py-3 bg-white border-t border-slate-100 shrink-0">
                      <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">Quick questions</p>
                      <div className="grid grid-cols-2 gap-2">
                        {QUICK_PROMPTS.map(({ label, text }) => (
                          <button key={label} onClick={() => send(text)}
                            className="text-xs text-left bg-slate-50 hover:bg-blue-50 hover:text-blue-700 border border-slate-200 hover:border-blue-200 text-slate-600 px-3 py-2 rounded-xl transition-colors leading-tight">
                            {label}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="px-3 py-3 bg-white border-t border-slate-100 shrink-0">
                    <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-100 transition-all">
                      <input
                        ref={inputRef} type="text"
                        className="flex-1 bg-transparent text-sm text-slate-800 placeholder-slate-400 focus:outline-none"
                        placeholder="Ask me anything about QA..."
                        value={input}
                        onChange={e => setInput(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
                        disabled={loading}
                      />
                      <button onClick={() => send()} disabled={loading || !input.trim()}
                        className="w-8 h-8 bg-gradient-to-br from-blue-600 to-violet-600 hover:from-blue-700 hover:to-violet-700 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg flex items-center justify-center transition-all shrink-0 shadow-sm">
                        <MdSend className="text-white text-sm" />
                      </button>
                    </div>
                    <p className="text-center text-xs text-slate-300 mt-2">AutoQA AI · Gemini Powered</p>
                  </div>
                </>
              )}

              {/* History tab */}
              {activeTab === 'history' && (
                <div className="flex-1 overflow-y-auto bg-slate-50">
                  <div className="px-4 py-3 border-b border-slate-200 bg-white flex items-center justify-between">
                    <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Chat History</p>
                    <button onClick={startNewSession}
                      className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 font-medium">
                      <MdAdd className="text-sm" /> New Chat
                    </button>
                  </div>

                  {sessLoading ? (
                    <div className="flex items-center justify-center py-10">
                      <div className="w-6 h-6 border-2 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
                    </div>
                  ) : sessions.length === 0 ? (
                    <div className="text-center py-10 px-4">
                      <MdOutlineHistory className="text-slate-300 text-4xl mx-auto mb-2" />
                      <p className="text-slate-400 text-sm">No chat history yet</p>
                      <p className="text-slate-300 text-xs mt-1">Start a conversation to see it here</p>
                    </div>
                  ) : (
                    <div className="divide-y divide-slate-100">
                      {sessions.map(sess => (
                        <div key={sess.id} onClick={() => loadSession(sess)}
                          className={`flex items-start gap-3 px-4 py-3 cursor-pointer hover:bg-white transition-colors ${sessionId === sess.id ? 'bg-blue-50 border-l-2 border-blue-500' : ''}`}>
                          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center shrink-0 mt-0.5">
                            <MdOutlineChat className="text-white text-sm" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-slate-800 truncate">{sess.title || 'New Chat'}</p>
                            <p className="text-xs text-slate-400 mt-0.5">{formatDate(sess.updated_at)}</p>
                          </div>
                          <button onClick={e => removeSession(e, sess.id)}
                            className="p-1 hover:bg-red-50 hover:text-red-500 text-slate-300 rounded-lg transition-colors shrink-0 mt-0.5">
                            <MdDeleteOutline className="text-base" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* FAB */}
      <button onClick={toggleOpen} className="fixed bottom-5 right-5 z-50 group" title="AutoQA Assistant">
        <div className={`relative w-14 h-14 rounded-full shadow-lg flex items-center justify-center transition-all duration-300 hover:scale-110 ${open ? 'bg-slate-700 hover:bg-slate-800' : 'bg-gradient-to-br from-blue-600 to-violet-600 hover:from-blue-700 hover:to-violet-700'}`}>
          {!open && <span className="absolute inset-0 rounded-full bg-blue-500 animate-ping opacity-20" />}
          {open ? <MdClose className="text-white text-2xl" /> : <MdOutlineChat className="text-white text-2xl" />}
          {!open && unread > 0 && (
            <span className="absolute -top-1 -right-1 w-5 h-5 bg-red-500 text-white text-xs font-bold rounded-full flex items-center justify-center shadow">
              {unread}
            </span>
          )}
        </div>
        {!open && (
          <span className="absolute right-16 top-1/2 -translate-y-1/2 bg-slate-800 text-white text-xs px-3 py-1.5 rounded-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none shadow-lg">
            Chat with AutoQA AI
          </span>
        )}
      </button>
    </>
  );
}
