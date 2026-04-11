import React, { useEffect, useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import {
  MdDashboard, MdOutlineFolderOpen, MdOutlineAccountTree,
  MdOutlineCode, MdOutlineEmail, MdClose, MdLogout,
  MdOutlineRadar,
} from 'react-icons/md';
import { TbCode } from 'react-icons/tb';
import { useAuth } from '../context/AuthContext';
import { getUnreadCount } from '../api/client';

const navItems = [
  { path: '/dev',           label: 'Dashboard',     icon: MdDashboard,            end: true },
  { path: '/dev/projects',  label: 'My Projects',   icon: MdOutlineFolderOpen },
  { path: '/dev/diagrams',  label: 'Diagrams',      icon: MdOutlineAccountTree },
  { path: '/dev/code',      label: 'Code Generator',icon: MdOutlineCode },
  { path: '/dev/messages',  label: 'Messages',      icon: MdOutlineEmail, badge: true },
];

export default function DevSidebar({ onClose }) {
  const { user, signOut } = useAuth();
  const navigate          = useNavigate();
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    const fetch = () => getUnreadCount().then(r => setUnread(r.data.unread_count || 0)).catch(() => {});
    fetch();
    const id = setInterval(fetch, 8000);
    return () => clearInterval(id);
  }, []);

  const handleLogout = () => { signOut(); navigate('/login'); };
  const initials = user?.username ? user.username.slice(0, 2).toUpperCase() : 'D';

  return (
    <aside className="w-60 h-full bg-white border-r border-slate-200 flex flex-col shadow-sm">
      {/* Logo */}
      <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-3 shrink-0">
        <div className="w-8 h-8 bg-gradient-to-br from-amber-500 to-orange-500 rounded-lg flex items-center justify-center shrink-0 shadow-md shadow-amber-200">
          <TbCode className="text-white text-lg" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-slate-800 leading-tight truncate">DevPortal</p>
          <p className="text-xs text-slate-400 truncate">Developer Dashboard</p>
        </div>
        {onClose && (
          <button onClick={onClose} className="lg:hidden p-1 rounded-lg hover:bg-slate-100 shrink-0">
            <MdClose className="text-slate-500 text-lg" />
          </button>
        )}
      </div>

      {/* Role badge */}
      <div className="px-4 pt-3 pb-1">
        <div className="flex items-center gap-2 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
          <span className="text-xs">💻</span>
          <p className="text-[10px] font-bold text-amber-700 uppercase tracking-wide">Developer Account</p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-3 space-y-0.5 overflow-y-auto">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider px-3 mb-2">Menu</p>
        {navItems.map(({ path, label, icon: Icon, end, badge }) => (
          <NavLink
            key={path} to={path} end={end} onClick={onClose}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                isActive
                  ? 'bg-amber-50 text-amber-700'
                  : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <Icon className={`text-lg shrink-0 ${isActive ? 'text-amber-600' : 'text-slate-400'}`} />
                <span className="truncate flex-1">{label}</span>
                {badge && unread > 0 && (
                  <span className="bg-red-500 text-white text-[9px] font-black rounded-full min-w-[18px] h-[18px] flex items-center justify-center px-1">
                    {unread > 99 ? '99+' : unread}
                  </span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* User */}
      {user && (
        <div className="px-3 py-3 border-t border-slate-100 shrink-0">
          <div className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-slate-50 border border-slate-200">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center shrink-0">
              <span className="text-white text-xs font-bold">{initials}</span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-slate-800 truncate">{user.username}</p>
              <p className="text-xs text-slate-400 truncate">{user.email}</p>
            </div>
            <button onClick={handleLogout} title="Sign out"
              className="p-1.5 hover:bg-red-50 hover:text-red-500 text-slate-400 rounded-lg transition-colors shrink-0">
              <MdLogout className="text-base" />
            </button>
          </div>
        </div>
      )}
    </aside>
  );
}
