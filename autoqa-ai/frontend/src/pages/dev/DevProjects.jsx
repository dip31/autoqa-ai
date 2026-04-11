import React, { useState, useEffect } from 'react';
import {
  MdAdd, MdDelete, MdEdit, MdOutlineFolderOpen, MdCheckCircle,
  MdOutlineAccountTree, MdOutlineCode, MdOutlineRadar, MdExpandMore,
  MdExpandLess, MdClose, MdOutlineBugReport,
} from 'react-icons/md';
import { RiLoader4Line } from 'react-icons/ri';
import {
  devListProjects, devCreateProject, devUpdateProject,
  devDeleteProject, devGetProject, devProjectRisk,
} from '../../api/client';

const STATUS_OPTS = ['Active', 'In Progress', 'Completed', 'On Hold'];
const STATUS_COLOR = {
  Active:       'bg-emerald-100 text-emerald-700 border-emerald-200',
  'In Progress':'bg-blue-100 text-blue-700 border-blue-200',
  Completed:    'bg-slate-100 text-slate-600 border-slate-200',
  'On Hold':    'bg-yellow-100 text-yellow-700 border-yellow-200',
};
const RISK_COLOR = {
  Low: 'text-emerald-600', Medium: 'text-yellow-600',
  High: 'text-orange-600', Critical: 'text-red-600',
};

const defaultForm = { title: '', description: '', requirements_text: '', tech_stack: '', status: 'Active' };

export default function DevProjects() {
  const [projects, setProjects]   = useState([]);
  const [loading, setLoading]     = useState(true);
  const [showForm, setShowForm]   = useState(false);
  const [form, setForm]           = useState(defaultForm);
  const [editId, setEditId]       = useState(null);
  const [saving, setSaving]       = useState(false);
  const [expanded, setExpanded]   = useState(null);
  const [detail, setDetail]       = useState(null);
  const [riskData, setRiskData]   = useState({});
  const [riskLoading, setRiskLoading] = useState(null);

  const load = () => {
    setLoading(true);
    devListProjects().then(r => setProjects(r.data.projects))
      .catch(() => {}).finally(() => setLoading(false));
  };
  useEffect(load, []);

  const openCreate = () => { setForm(defaultForm); setEditId(null); setShowForm(true); };
  const openEdit   = (p) => { setForm({ title: p.title, description: p.description||'', requirements_text: p.requirements_text||'', tech_stack: p.tech_stack||'', status: p.status }); setEditId(p.id); setShowForm(true); };

  const handleSave = async (e) => {
    e.preventDefault(); setSaving(true);
    try {
      if (editId) await devUpdateProject(editId, form);
      else        await devCreateProject(form);
      setShowForm(false); load();
    } catch { } finally { setSaving(false); }
  };

  const handleDelete = async (id) => {
    if (!confirm('Delete this project?')) return;
    await devDeleteProject(id); load();
  };

  const toggleExpand = async (id) => {
    if (expanded === id) { setExpanded(null); setDetail(null); return; }
    setExpanded(id);
    const r = await devGetProject(id); setDetail(r.data.project);
  };

  const runRisk = async (pid) => {
    setRiskLoading(pid);
    try {
      const r = await devProjectRisk(pid, {});
      setRiskData(d => ({ ...d, [pid]: r.data.risk }));
    } catch {} finally { setRiskLoading(null); }
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1400px] mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
            <MdOutlineFolderOpen className="text-amber-500" /> My Projects
          </h1>
          <p className="text-slate-500 text-sm mt-1">Manage requirements, track progress, generate assets</p>
        </div>
        <button onClick={openCreate}
          className="bg-amber-500 hover:bg-amber-600 text-white px-5 py-2.5 rounded-xl font-bold text-sm flex items-center gap-2 transition-all shadow-lg shadow-amber-200">
          <MdAdd /> New Project
        </button>
      </div>

      {/* Create/Edit Modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl shadow-2xl w-full max-w-lg">
            <div className="p-6 border-b border-slate-100 flex items-center justify-between">
              <h2 className="text-lg font-black text-slate-800">
                {editId ? 'Edit Project' : 'New Project'}
              </h2>
              <button onClick={() => setShowForm(false)} className="p-2 hover:bg-slate-100 rounded-xl transition-colors">
                <MdClose />
              </button>
            </div>
            <form onSubmit={handleSave} className="p-6 space-y-4">
              {[
                { key: 'title',     label: 'Project Title *',       ph: 'e.g. User Auth Service', req: true },
                { key: 'description', label: 'Short Description',   ph: 'What this project does' },
                { key: 'tech_stack',label: 'Tech Stack',            ph: 'e.g. React, Flask, SQLite' },
              ].map(({ key, label, ph, req }) => (
                <div key={key}>
                  <label className="text-[10px] font-bold text-slate-400 uppercase ml-1">{label}</label>
                  <input required={req} value={form[key]}
                    onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                    placeholder={ph}
                    className="mt-1 w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400/30 transition-all"
                  />
                </div>
              ))}
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase ml-1">Requirements</label>
                <textarea value={form.requirements_text}
                  onChange={e => setForm(f => ({ ...f, requirements_text: e.target.value }))}
                  placeholder="Detail the project requirements here…"
                  rows={5}
                  className="mt-1 w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400/30 resize-none transition-all"
                />
              </div>
              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase ml-1">Status</label>
                <select value={form.status} onChange={e => setForm(f => ({ ...f, status: e.target.value }))}
                  className="mt-1 w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none">
                  {STATUS_OPTS.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowForm(false)}
                  className="flex-1 py-2.5 border border-slate-200 rounded-xl text-sm font-bold text-slate-600 hover:bg-slate-50 transition-colors">
                  Cancel
                </button>
                <button type="submit" disabled={saving}
                  className="flex-1 py-2.5 bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white rounded-xl text-sm font-bold transition-colors flex items-center justify-center gap-2">
                  {saving ? <RiLoader4Line className="animate-spin" /> : <MdCheckCircle />}
                  {editId ? 'Save Changes' : 'Create Project'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Project List */}
      {loading ? (
        <div className="flex items-center justify-center h-40">
          <RiLoader4Line className="animate-spin text-3xl text-amber-500" />
        </div>
      ) : projects.length === 0 ? (
        <div className="bg-white border-2 border-dashed border-slate-200 rounded-3xl p-16 text-center">
          <MdOutlineFolderOpen className="text-6xl text-slate-300 mx-auto mb-4" />
          <p className="text-lg font-bold text-slate-700">No projects yet</p>
          <p className="text-slate-400 text-sm mt-1">Create your first project to generate diagrams and code</p>
          <button onClick={openCreate}
            className="mt-5 bg-amber-500 text-white px-6 py-2.5 rounded-xl font-bold text-sm hover:bg-amber-600 transition-colors inline-flex items-center gap-2">
            <MdAdd /> Create Project
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {projects.map(p => (
            <div key={p.id} className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
              {/* Row */}
              <div className="p-5 flex items-center gap-4">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-400 to-orange-500 flex items-center justify-center shrink-0">
                  <MdOutlineFolderOpen className="text-white text-xl" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 flex-wrap">
                    <p className="text-sm font-bold text-slate-800">{p.title}</p>
                    <span className={`px-2 py-0.5 rounded-full text-[9px] font-black border uppercase ${STATUS_COLOR[p.status] || 'bg-slate-100 text-slate-500'}`}>
                      {p.status}
                    </span>
                  </div>
                  {p.description && <p className="text-xs text-slate-400 mt-0.5 truncate">{p.description}</p>}
                  {p.tech_stack && <p className="text-[10px] text-slate-400 font-mono mt-1">{p.tech_stack}</p>}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button onClick={() => openEdit(p)}
                    className="p-2 hover:bg-amber-50 hover:text-amber-600 text-slate-400 rounded-xl transition-colors">
                    <MdEdit />
                  </button>
                  <button onClick={() => handleDelete(p.id)}
                    className="p-2 hover:bg-red-50 hover:text-red-500 text-slate-400 rounded-xl transition-colors">
                    <MdDelete />
                  </button>
                  <button onClick={() => toggleExpand(p.id)}
                    className="p-2 hover:bg-slate-100 text-slate-400 rounded-xl transition-colors">
                    {expanded === p.id ? <MdExpandLess /> : <MdExpandMore />}
                  </button>
                </div>
              </div>

              {/* Expanded Detail */}
              {expanded === p.id && (
                <div className="border-t border-slate-100 p-5 space-y-5 bg-slate-50/50">
                  {/* Requirements */}
                  {p.requirements_text && (
                    <div>
                      <p className="text-[10px] font-black text-slate-400 uppercase mb-2">Requirements</p>
                      <p className="text-sm text-slate-600 leading-relaxed whitespace-pre-line bg-white border border-slate-100 rounded-xl p-4">
                        {p.requirements_text}
                      </p>
                    </div>
                  )}

                  {/* Risk Analysis */}
                  <div>
                    <div className="flex items-center justify-between mb-3">
                      <p className="text-[10px] font-black text-slate-400 uppercase">Risk Analysis</p>
                      <button onClick={() => runRisk(p.id)} disabled={riskLoading === p.id}
                        className="flex items-center gap-1.5 text-xs font-bold text-amber-600 bg-amber-50 border border-amber-100 px-3 py-1.5 rounded-lg hover:bg-amber-100 transition-colors disabled:opacity-50">
                        {riskLoading === p.id ? <RiLoader4Line className="animate-spin" /> : <MdOutlineRadar />}
                        Run Risk Assessment
                      </button>
                    </div>
                    {riskData[p.id] ? (
                      <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
                        <div className="flex items-center gap-4 flex-wrap">
                          <div className="text-center">
                            <p className="text-2xl font-black text-orange-600">{riskData[p.id].overall_risk_score}</p>
                            <p className="text-[9px] text-slate-400 font-bold uppercase">Risk Score</p>
                          </div>
                          <div className="text-center">
                            <p className={`text-lg font-black ${RISK_COLOR[riskData[p.id].risk_level]}`}>{riskData[p.id].risk_level}</p>
                            <p className="text-[9px] text-slate-400 font-bold uppercase">Level</p>
                          </div>
                          <div className="text-center">
                            <p className="text-lg font-black text-slate-700">{riskData[p.id].estimated_complexity}</p>
                            <p className="text-[9px] text-slate-400 font-bold uppercase">Complexity</p>
                          </div>
                        </div>
                        {riskData[p.id].recommendations?.slice(0,3).map((r, i) => (
                          <div key={i} className="flex items-start gap-2 text-xs text-slate-600 bg-blue-50 border border-blue-100 rounded-lg px-3 py-2">
                            <span className="text-blue-500 shrink-0 mt-0.5">→</span> {r}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-slate-400 italic">Click "Run Risk Assessment" to analyze this project.</p>
                    )}
                  </div>

                  {/* Diagrams + Code summary */}
                  {detail && detail.id === p.id && (
                    <div className="grid grid-cols-2 gap-4">
                      <div className="bg-white border border-slate-200 rounded-xl p-4">
                        <p className="text-[10px] font-black text-slate-400 uppercase mb-2">
                          <MdOutlineAccountTree className="inline mr-1" /> Diagrams ({detail.diagrams?.length || 0})
                        </p>
                        {detail.diagrams?.slice(0,3).map(d => (
                          <p key={d.id} className="text-xs text-slate-600 py-1 border-b border-slate-50 last:border-0 truncate">
                            • {d.diagram_type} — {d.title?.slice(0,40)}
                          </p>
                        ))}
                        {!detail.diagrams?.length && <p className="text-xs text-slate-400 italic">No diagrams yet</p>}
                      </div>
                      <div className="bg-white border border-slate-200 rounded-xl p-4">
                        <p className="text-[10px] font-black text-slate-400 uppercase mb-2">
                          <MdOutlineCode className="inline mr-1" /> Code Files ({detail.code?.length || 0})
                        </p>
                        {detail.code?.slice(0,3).map(c => (
                          <p key={c.id} className="text-xs text-slate-600 py-1 border-b border-slate-50 last:border-0 truncate">
                            • {c.language} — {c.title?.slice(0,40)}
                          </p>
                        ))}
                        {!detail.code?.length && <p className="text-xs text-slate-400 italic">No code generated yet</p>}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
