import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  MdOutlineFolderOpen, MdOutlineAccountTree, MdOutlineCode,
  MdOutlineEmail, MdAdd,
} from 'react-icons/md';
import { RiLoader4Line } from 'react-icons/ri';
import { TbCode } from 'react-icons/tb';
import { devListProjects, devAllDiagrams, getMessages, getUnreadCount } from '../../api/client';
import { useAuth } from '../../context/AuthContext';

const StatCard = ({ icon: Icon, label, value, color, to }) => (
  <Link to={to || '#'}
    className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm hover:shadow-md transition-shadow flex items-center gap-4 group">
    <div className={`w-12 h-12 rounded-xl flex items-center justify-center shrink-0 ${color}`}>
      <Icon className="text-white text-2xl" />
    </div>
    <div>
      <p className="text-2xl font-black text-slate-800 group-hover:text-amber-600 transition-colors">{value}</p>
      <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mt-0.5">{label}</p>
    </div>
  </Link>
);

const QuickAction = ({ icon: Icon, label, desc, to, color }) => (
  <Link to={to}
    className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm hover:shadow-lg hover:border-amber-200 transition-all group">
    <div className={`w-10 h-10 rounded-xl flex items-center justify-center mb-3 ${color}`}>
      <Icon className="text-white text-xl" />
    </div>
    <p className="text-sm font-bold text-slate-800 group-hover:text-amber-700 transition-colors">{label}</p>
    <p className="text-xs text-slate-400 mt-1 leading-relaxed">{desc}</p>
  </Link>
);

export default function DevDashboard() {
  const { user } = useAuth();
  const [stats, setStats]     = useState({ projects: 0, diagrams: 0, unread: 0 });
  const [recent, setRecent]   = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.allSettled([
      devListProjects(), devAllDiagrams(), getUnreadCount(),
    ]).then(([proj, diag, unread]) => {
      const projects = proj.status === 'fulfilled' ? proj.value.data.projects : [];
      const diagrams = diag.status === 'fulfilled' ? diag.value.data.diagrams : [];
      const uc       = unread.status === 'fulfilled' ? unread.value.data.unread_count : 0;
      setStats({ projects: projects.length, diagrams: diagrams.length, unread: uc });
      setRecent(projects.slice(0, 5));
    }).finally(() => setLoading(false));
  }, []);

  const STATUS_COLOR = {
    Active: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    'In Progress': 'bg-blue-100 text-blue-700 border-blue-200',
    Completed: 'bg-slate-100 text-slate-600 border-slate-200',
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1400px] mx-auto space-y-8">

      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
            <TbCode className="text-amber-500" /> Developer Dashboard
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Welcome back, <strong className="text-slate-700">{user?.username}</strong> — here's your dev workspace overview.
          </p>
        </div>
        <Link to="/dev/projects"
          className="bg-amber-500 hover:bg-amber-600 text-white px-5 py-2.5 rounded-xl font-bold text-sm flex items-center gap-2 transition-all shadow-lg shadow-amber-200">
          <MdAdd /> New Project
        </Link>
      </div>

      {/* Stats */}
      {loading ? (
        <div className="flex items-center justify-center h-24">
          <RiLoader4Line className="animate-spin text-3xl text-amber-500" />
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
          <StatCard icon={MdOutlineFolderOpen} label="Total Projects" value={stats.projects}
            color="bg-gradient-to-br from-amber-400 to-orange-500" to="/dev/projects" />
          <StatCard icon={MdOutlineAccountTree} label="Diagrams Generated" value={stats.diagrams}
            color="bg-gradient-to-br from-violet-500 to-indigo-600" to="/dev/diagrams" />
          <StatCard icon={MdOutlineEmail} label="Unread Messages" value={stats.unread}
            color="bg-gradient-to-br from-emerald-400 to-teal-500" to="/dev/messages" />
        </div>
      )}

      {/* Quick Actions */}
      <div>
        <h2 className="text-sm font-black text-slate-500 uppercase tracking-widest mb-4">Quick Actions</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <QuickAction icon={MdOutlineAccountTree} label="Generate Diagrams"
            desc="Class, Activity, Sequence, Architecture, Timeline"
            to="/dev/diagrams" color="bg-gradient-to-br from-violet-500 to-indigo-600" />
          <QuickAction icon={MdOutlineCode} label="Generate Code"
            desc="AI writes Python, JS, TS, Java from your requirements"
            to="/dev/code" color="bg-gradient-to-br from-emerald-500 to-teal-500" />
          <QuickAction icon={MdOutlineEmail} label="Message QA Team"
            desc="Communicate issues directly with QA engineers"
            to="/dev/messages" color="bg-gradient-to-br from-amber-500 to-orange-500" />
        </div>
      </div>

      {/* Recent Projects */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-black text-slate-500 uppercase tracking-widest">Recent Projects</h2>
          <Link to="/dev/projects" className="text-xs font-bold text-amber-600 hover:text-amber-700 transition-colors">
            View all →
          </Link>
        </div>
        {recent.length === 0 ? (
          <div className="bg-white border-2 border-dashed border-slate-200 rounded-2xl p-12 text-center">
            <MdOutlineFolderOpen className="text-5xl text-slate-300 mx-auto mb-3" />
            <p className="text-slate-500 text-sm font-semibold">No projects yet</p>
            <p className="text-slate-400 text-xs mt-1">Create your first project to get started</p>
            <Link to="/dev/projects"
              className="mt-4 inline-flex items-center gap-2 bg-amber-500 text-white px-4 py-2 rounded-xl text-sm font-bold hover:bg-amber-600 transition-colors">
              <MdAdd /> Create Project
            </Link>
          </div>
        ) : (
          <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-100">
                  <th className="text-left text-[10px] font-black text-slate-400 uppercase px-5 py-3">Project</th>
                  <th className="text-left text-[10px] font-black text-slate-400 uppercase px-5 py-3 hidden md:table-cell">Tech Stack</th>
                  <th className="text-left text-[10px] font-black text-slate-400 uppercase px-5 py-3">Status</th>
                  <th className="text-left text-[10px] font-black text-slate-400 uppercase px-5 py-3 hidden sm:table-cell">Created</th>
                </tr>
              </thead>
              <tbody>
                {recent.map(p => (
                  <tr key={p.id} className="border-b border-slate-50 last:border-0 hover:bg-amber-50/30 transition-colors">
                    <td className="px-5 py-3.5">
                      <p className="text-sm font-bold text-slate-800">{p.title}</p>
                      {p.description && (
                        <p className="text-xs text-slate-400 mt-0.5 truncate max-w-xs">{p.description}</p>
                      )}
                    </td>
                    <td className="px-5 py-3.5 hidden md:table-cell">
                      <p className="text-xs text-slate-500 font-mono">{p.tech_stack || '—'}</p>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className={`px-2.5 py-1 rounded-full text-[10px] font-bold border ${STATUS_COLOR[p.status] || 'bg-slate-100 text-slate-600'}`}>
                        {p.status}
                      </span>
                    </td>
                    <td className="px-5 py-3.5 hidden sm:table-cell">
                      <p className="text-xs text-slate-400">{new Date(p.created_at).toLocaleDateString()}</p>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
