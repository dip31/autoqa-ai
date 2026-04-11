import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import {
  MdDashboard, MdOutlineFactCheck,
  MdOutlineLanguage, MdOutlineAutoAwesome,
  MdOutlineAssessment, MdClose,
  MdLogout, MdPersonOutline, MdOutlineHubOutlined, MdOutlineEmail,
} from 'react-icons/md';
import { TbBrandReact } from 'react-icons/tb';
import { RiGithubFill } from 'react-icons/ri';
import { useAuth } from '../context/AuthContext';

const navItems = [
  { path: '/',                label: 'Dashboard',        icon: MdDashboard },
  { path: '/github-intelligence', label: 'GitHub Intelligence', icon: RiGithubFill },
  { path: '/test-review',     label: 'Test Case Review', icon: MdOutlineFactCheck },
  { path: '/website-testing', label: 'Website Testing',  icon: MdOutlineLanguage },
  { path: '/autonomous-qa',   label: 'Autonomous QA',    icon: MdOutlineAutoAwesome },
  { path: '/test-generator',  label: 'Test Generator',   icon: MdOutlineAutoAwesome },
  { path: '/smart-report',    label: 'Smart Report',     icon: MdOutlineAssessment },
  { path: '/messages',        label: 'Messages',          icon: MdOutlineEmail },
];

export default function Sidebar({ onClose }) {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    signOut();
    navigate('/login');
  };

  const initials = user?.username
    ? user.username.slice(0, 2).toUpperCase()
    : 'U';

  return (
    <aside className="w-60 h-full bg-white border-r border-slate-200 flex flex-col shadow-sm">
      {/* Logo */}
      <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-3 shrink-0">
        <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center shrink-0">
          <TbBrandReact className="text-white text-lg" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-slate-800 leading-tight truncate">AutoQA AI</p>
          <p className="text-xs text-slate-400 truncate">QA Automation Platform</p>
        </div>
        {onClose && (
          <button onClick={onClose} className="lg:hidden p-1 rounded-lg hover:bg-slate-100 transition-colors shrink-0">
            <MdClose className="text-slate-500 text-lg" />
          </button>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider px-3 mb-2">Menu</p>
        {navItems.map(({ path, label, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            end={path === '/'}
            onClick={onClose}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all ${
                isActive ? 'bg-blue-50 text-blue-700' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <Icon className={`text-lg shrink-0 ${isActive ? 'text-blue-600' : 'text-slate-400'}`} />
                <span className="truncate">{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* User profile */}
      {user && (
        <div className="px-3 py-3 border-t border-slate-100 shrink-0">
          <div className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-slate-50 border border-slate-200">
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center shrink-0">
              <span className="text-white text-xs font-bold">{initials}</span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-slate-800 truncate">{user.username}</p>
              <p className="text-xs text-slate-400 truncate">{user.email}</p>
            </div>
            <button
              onClick={handleLogout}
              title="Sign out"
              className="p-1.5 hover:bg-red-50 hover:text-red-500 text-slate-400 rounded-lg transition-colors shrink-0"
            >
              <MdLogout className="text-base" />
            </button>
          </div>
        </div>
      )}
    </aside>
  );
}
