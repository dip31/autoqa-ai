import React, { useState, useEffect, useCallback } from 'react';
import {
  MdOutlineEmail, MdSend, MdInbox, MdOutbound, MdCheckCircle,
  MdCircle, MdAdd, MdClose, MdReply, MdExpandMore, MdExpandLess,
} from 'react-icons/md';
import { RiLoader4Line } from 'react-icons/ri';
import {
  getMessages, sendMessage, replyMessage, markRead,
  getTeamUsers, devListProjects,
} from '../api/client';
import { useAuth } from '../context/AuthContext';

const BOX_TABS = [
  { key: 'inbox', label: 'Inbox',  icon: MdInbox },
  { key: 'sent',  label: 'Sent',   icon: MdOutbound },
];

const timeAgo = (ts) => {
  if (!ts) return '';
  const d = (new Date() - new Date(ts)) / 1000;
  if (d < 60)    return 'just now';
  if (d < 3600)  return `${Math.round(d/60)}m ago`;
  if (d < 86400) return `${Math.round(d/3600)}h ago`;
  return new Date(ts).toLocaleDateString();
};

export default function QAMessages() {
  const { user }                    = useAuth();
  const [box, setBox]               = useState('inbox');
  const [messages, setMessages]     = useState([]);
  const [loading, setLoading]       = useState(true);
  const [expanded, setExpanded]     = useState(null);
  const [replyText, setReplyText]   = useState({});
  const [replySending, setReplySend]= useState(null);
  const [showCompose, setShowCompose] = useState(false);
  const [teamUsers, setTeamUsers]   = useState([]);
  const [projects, setProjects]     = useState([]);
  const [compose, setCompose]       = useState({ receiver_id: '', subject: '', body: '', project_id: '' });
  const [composeSending, setCompSend] = useState(false);
  const [composeError, setCompErr]  = useState('');

  const loadMessages = useCallback(() => {
    setLoading(true);
    getMessages(box).then(r => setMessages(r.data.messages || [])).catch(() => {}).finally(() => setLoading(false));
  }, [box]);

  useEffect(() => { loadMessages(); }, [loadMessages]);

  useEffect(() => {
    const id = setInterval(loadMessages, 8000);
    return () => clearInterval(id);
  }, [loadMessages]);

  const openCompose = async () => {
    setShowCompose(true); setCompErr('');
    setCompose({ receiver_id: '', subject: '', body: '', project_id: '' });
    const [tu, tp] = await Promise.allSettled([getTeamUsers(), devListProjects()]);
    setTeamUsers(tu.status === 'fulfilled' ? tu.value.data.users || [] : []);
    setProjects(tp.status === 'fulfilled' ? tp.value.data.projects || [] : []);
  };

  const handleSend = async (e) => {
    e.preventDefault();
    if (!compose.receiver_id || !compose.body.trim()) { setCompErr('Select recipient and write a message'); return; }
    setCompSend(true); setCompErr('');
    try {
      await sendMessage({ ...compose, receiver_id: parseInt(compose.receiver_id), project_id: compose.project_id ? parseInt(compose.project_id) : null });
      setShowCompose(false); setBox('sent'); loadMessages();
    } catch (err) { setCompErr(err.response?.data?.error || 'Failed to send'); }
    finally { setCompSend(false); }
  };

  const handleReply = async (mid) => {
    const body = (replyText[mid] || '').trim();
    if (!body) return;
    setReplySend(mid);
    try {
      await replyMessage(mid, body);
      setReplyText(t => ({ ...t, [mid]: '' }));
      loadMessages();
    } catch {} finally { setReplySend(null); }
  };

  const openMsg = async (msg) => {
    if (expanded === msg.id) { setExpanded(null); return; }
    setExpanded(msg.id);
    if (!msg.is_read && msg.receiver_id === user?.id) {
      await markRead(msg.id).catch(() => {});
      setMessages(prev => prev.map(m => m.id === msg.id ? { ...m, is_read: 1 } : m));
    }
  };

  const inboxCount = messages.filter(m => !m.is_read && box === 'inbox').length;

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1200px] mx-auto space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
            <MdOutlineEmail className="text-blue-600" /> QA-Dev Messages
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Collaborate directly with the development team on bugs and requirements
          </p>
        </div>
        <button onClick={openCompose}
          className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-2.5 rounded-xl font-bold text-sm flex items-center gap-2 transition-all shadow-lg shadow-blue-200">
          <MdAdd /> Compose Message
        </button>
      </div>

      {/* Compose Modal */}
      {showCompose && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl shadow-2xl w-full max-w-lg">
            <div className="p-6 border-b border-slate-100 flex items-center justify-between">
              <h2 className="text-lg font-black text-slate-800">New Message to Dev</h2>
              <button onClick={() => setShowCompose(false)} className="p-2 hover:bg-slate-100 rounded-xl"><MdClose /></button>
            </div>
            <form onSubmit={handleSend} className="p-6 space-y-4">
              {composeError && (
                <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3">{composeError}</div>
              )}
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase ml-1">
                  Recipient (Developer) *
                </label>
                <select required value={compose.receiver_id} onChange={e => setCompose(c => ({ ...c, receiver_id: e.target.value }))}
                  className="mt-1 w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400/30">
                  <option value="">— Select Developer —</option>
                  {teamUsers.map(u => (
                    <option key={u.id} value={u.id}>{u.username} ({u.email})</option>
                  ))}
                  {teamUsers.length === 0 && <option disabled>No Developers found</option>}
                </select>
              </div>
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase ml-1">Subject</label>
                <input value={compose.subject} onChange={e => setCompose(c => ({ ...c, subject: e.target.value }))}
                  placeholder="e.g. Critical Bug on Login Page"
                  className="mt-1 w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400/30"
                />
              </div>
              {projects.length > 0 && (
                <div>
                  <label className="text-[10px] font-bold text-slate-400 uppercase ml-1">Relate to Project (optional)</label>
                  <select value={compose.project_id} onChange={e => setCompose(c => ({ ...c, project_id: e.target.value }))}
                    className="mt-1 w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none">
                    <option value="">— No project —</option>
                    {projects.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}
                  </select>
                </div>
              )}
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase ml-1">Description *</label>
                <textarea required value={compose.body} onChange={e => setCompose(c => ({ ...c, body: e.target.value }))}
                  placeholder="Describe the bug or request for the developer…"
                  rows={5}
                  className="mt-1 w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-400/30"
                />
              </div>
              <div className="flex gap-3">
                <button type="button" onClick={() => setShowCompose(false)}
                  className="flex-1 py-2.5 border border-slate-200 rounded-xl text-sm font-bold text-slate-600 hover:bg-slate-50">Cancel</button>
                <button type="submit" disabled={composeSending}
                  className="flex-1 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-xl text-sm font-bold flex items-center justify-center gap-2">
                  {composeSending ? <RiLoader4Line className="animate-spin" /> : <MdSend />}
                  Send Message
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Box tabs */}
      <div className="flex gap-2 bg-slate-100 p-1 rounded-xl w-fit">
        {BOX_TABS.map(({ key, label, icon: Icon }) => (
          <button key={key} onClick={() => setBox(key)}
            className={`px-5 py-2 rounded-lg text-sm font-bold flex items-center gap-2 transition-all ${
              box === key ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-700'
            }`}>
            <Icon className="text-base" /> {label}
            {key === 'inbox' && inboxCount > 0 && (
              <span className="bg-red-500 text-white text-[9px] font-black rounded-full min-w-[16px] h-4 flex items-center justify-center px-1">
                {inboxCount}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Message list */}
      {loading ? (
        <div className="flex items-center justify-center h-40">
          <RiLoader4Line className="animate-spin text-3xl text-blue-600" />
        </div>
      ) : messages.length === 0 ? (
        <div className="bg-white border-2 border-dashed border-slate-200 rounded-3xl p-16 text-center">
          <MdOutlineEmail className="text-6xl text-slate-300 mx-auto mb-4" />
          <p className="text-lg font-bold text-slate-700">{box === 'inbox' ? 'No messages received' : 'No messages sent'}</p>
          <p className="text-slate-400 text-sm mt-1">
            {box === 'inbox'
              ? 'Your inbox is clear. Developers can reply to your messages here.'
              : 'Communicate findings directly to developers by composing a message.'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {messages.map(msg => (
            <div key={msg.id}
              className={`bg-white border rounded-2xl shadow-sm overflow-hidden transition-all ${
                !msg.is_read && box === 'inbox' ? 'border-blue-300 shadow-blue-100' : 'border-slate-200'
              }`}>
              {/* Message row */}
              <div
                className="p-5 cursor-pointer flex items-start gap-4"
                onClick={() => openMsg(msg)}
              >
                {!msg.is_read && box === 'inbox' ? (
                  <MdCircle className="text-blue-600 text-xs shrink-0 mt-1.5" />
                ) : (
                  <MdCheckCircle className="text-slate-200 text-sm shrink-0 mt-1" />
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-4">
                    <p className={`text-sm font-bold ${!msg.is_read && box === 'inbox' ? 'text-slate-900' : 'text-slate-700'}`}>
                      {msg.subject || '(No subject)'}
                    </p>
                    <p className="text-xs text-slate-400 shrink-0">{timeAgo(msg.created_at)}</p>
                  </div>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {box === 'inbox' ? `From: ${msg.sender_name}` : `To: ${msg.receiver_name}`}
                    {msg.replies?.length > 0 && <span className="ml-2 text-blue-500 font-bold">• {msg.replies.length} {msg.replies.length === 1 ? 'reply' : 'replies'}</span>}
                  </p>
                  <p className="text-xs text-slate-500 mt-1 truncate">{msg.body}</p>
                </div>
                {expanded === msg.id ? <MdExpandLess className="text-slate-400 shrink-0 mt-1" /> : <MdExpandMore className="text-slate-400 shrink-0 mt-1" />}
              </div>

              {/* Expanded thread */}
              {expanded === msg.id && (
                <div className="border-t border-slate-100 bg-slate-50/50">
                  {/* Original */}
                  <div className="px-6 py-4">
                    <div className="flex items-center gap-2 mb-3">
                      <div className="w-7 h-7 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white text-[10px] font-black">
                        {(msg.sender_name || 'U').slice(0, 1).toUpperCase()}
                      </div>
                      <div>
                        <p className="text-xs font-bold text-slate-700">{msg.sender_name}</p>
                        <p className="text-[10px] text-slate-400">{new Date(msg.created_at).toLocaleString()}</p>
                      </div>
                    </div>
                    <div className="bg-white rounded-xl border border-slate-100 p-4 shadow-sm">
                      <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-line">{msg.body}</p>
                    </div>
                  </div>

                  {/* Replies */}
                  {msg.replies?.map((r, i) => (
                    <div key={i} className="px-6 py-3 border-t border-slate-100">
                      <div className="flex items-center gap-2 mb-2">
                        <div className="w-6 h-6 rounded-full bg-gradient-to-br from-slate-400 to-slate-500 flex items-center justify-center text-white text-[9px] font-black">
                          {(r.sender_name || 'U').slice(0, 1).toUpperCase()}
                        </div>
                        <div>
                          <p className="text-xs font-bold text-slate-700 flex items-center gap-1">
                            <MdReply className="text-slate-400" /> {r.sender_name}
                          </p>
                          <p className="text-[10px] text-slate-400">{new Date(r.created_at).toLocaleString()}</p>
                        </div>
                      </div>
                      <div className="ml-8 bg-blue-50 border border-blue-100 rounded-xl p-3">
                        <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-line">{r.body}</p>
                      </div>
                    </div>
                  ))}

                  {/* Reply box */}
                  <div className="px-6 py-4 border-t border-slate-100">
                    <div className="flex gap-3">
                      <textarea
                        value={replyText[msg.id] || ''}
                        onChange={e => setReplyText(t => ({ ...t, [msg.id]: e.target.value }))}
                        placeholder="Write a reply to the developer…"
                        rows={2}
                        className="flex-1 bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-400/30 transition-all"
                      />
                      <button
                        onClick={() => handleReply(msg.id)}
                        disabled={replySending === msg.id || !(replyText[msg.id] || '').trim()}
                        className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-4 rounded-xl flex items-center gap-2 transition-colors text-sm font-bold shrink-0">
                        {replySending === msg.id ? <RiLoader4Line className="animate-spin" /> : <MdSend />}
                        Reply
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
