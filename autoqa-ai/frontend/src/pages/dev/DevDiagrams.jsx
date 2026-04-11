import React, { useState, useEffect, useRef } from 'react';
import {
  MdOutlineAccountTree, MdAdd, MdContentCopy, MdCheckCircle,
  MdDownload, MdDelete, MdRefresh,
} from 'react-icons/md';
import { RiLoader4Line } from 'react-icons/ri';
import { devListProjects, devGenerateDiagram, devAllDiagrams } from '../../api/client';
import mermaid from 'mermaid';

mermaid.initialize({
  startOnLoad: false,
  theme: 'neutral',
  securityLevel: 'loose',
});

const DIAGRAM_TYPES = [
  { key: 'class',        label: 'Class Diagram',       emoji: '📦', desc: 'Classes, attributes, relationships' },
  { key: 'activity',     label: 'Activity Diagram',     emoji: '🔄', desc: 'Process flow and decision points' },
  { key: 'sequence',     label: 'Sequence Diagram',     emoji: '📡', desc: 'Component interactions over time' },
  { key: 'architecture', label: 'Architecture Diagram', emoji: '🏗️', desc: 'System layers and components' },
  { key: 'timeline',     label: 'Timeline / Gantt',     emoji: '📅', desc: 'Project phases and task schedule' },
];

/* ── Mermaid renderer ──────────────────────────────────────────────────── */
function MermaidView({ id, code }) {
  const ref = useRef(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    if (!code || !ref.current) return;
    const render = async () => {
      setErr(false);
      try {
        const { svg } = await mermaid.render(`m-${id}-${Date.now()}`, code);
        if (ref.current) ref.current.innerHTML = svg;
      } catch (e) {
        setErr(true);
      }
    };
    render();
  }, [id, code]);

  if (err) return (
    <pre className="text-[11px] text-slate-600 bg-slate-50 rounded-xl p-4 overflow-auto border border-slate-100 leading-relaxed max-h-64 font-mono">
      {code}
    </pre>
  );
  return <div ref={ref} className="bg-slate-50 rounded-xl p-4 flex justify-center items-center min-h-24 overflow-auto" />;
}

function CopyBtn({ text }) {
  const [ok, setOk] = useState(false);
  return (
    <button onClick={() => { navigator.clipboard.writeText(text); setOk(true); setTimeout(() => setOk(false), 1500); }}
      className="p-1.5 rounded-lg hover:bg-slate-100 transition-colors">
      {ok ? <MdCheckCircle className="text-emerald-500" /> : <MdContentCopy className="text-xs text-slate-400" />}
    </button>
  );
}

export default function DevDiagrams() {
  const [projects, setProjects]   = useState([]);
  const [diagrams, setDiagrams]   = useState([]);
  const [pid, setPid]             = useState('');
  const [types, setTypes]         = useState(['architecture']);
  const [requirement, setReq]     = useState('');
  const [loading, setLoading]     = useState(false);
  const [histLoading, setHistLoading] = useState(true);

  useEffect(() => {
    devListProjects().then(r => setProjects(r.data.projects || [])).catch(() => []);
    devAllDiagrams().then(r => setDiagrams(r.data.diagrams || [])).catch(() => {}).finally(() => setHistLoading(false));
  }, []);

  const toggleType = (k) => setTypes(prev => prev.includes(k) ? prev.filter(x => x !== k) : [...prev, k]);

  const handleGenerate = async (e) => {
    e.preventDefault();
    if (!pid) { alert('Please select a project first'); return; }
    if (!types.length) { alert('Select at least one diagram type'); return; }
    setLoading(true);
    try {
      const res = await devGenerateDiagram(pid, { requirements: requirement, types });
      const newDiags = res.data.diagrams || (res.data.diagram ? [res.data.diagram] : []);
      setDiagrams(prev => [...newDiags, ...prev]);
    } catch (err) {
      alert(err.response?.data?.error || 'Generation failed');
    } finally { setLoading(false); }
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1400px] mx-auto space-y-6">

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
          <MdOutlineAccountTree className="text-violet-500" /> Diagram Generator
        </h1>
        <p className="text-slate-500 text-sm mt-1">
          Generate professional Mermaid diagrams from your project requirements using AI
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

        {/* Left: Generator form */}
        <div className="lg:col-span-4 space-y-5">
          <form onSubmit={handleGenerate} className="space-y-5">

            <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-4">
              <h2 className="text-xs font-black text-slate-500 uppercase tracking-widest">Generate Diagrams</h2>

              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase ml-1">Select Project</label>
                <select required value={pid} onChange={e => setPid(e.target.value)}
                  className="mt-1 w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400/30">
                  <option value="">— Choose a project —</option>
                  {projects.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}
                </select>
              </div>

              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase ml-1">Diagram Types</label>
                <div className="mt-2 grid grid-cols-1 gap-2">
                  {DIAGRAM_TYPES.map(t => (
                    <button key={t.key} type="button" onClick={() => toggleType(t.key)}
                      className={`flex items-center gap-3 p-3 rounded-xl border-2 text-left transition-all ${
                        types.includes(t.key)
                          ? 'border-violet-500 bg-violet-50'
                          : 'border-slate-200 bg-slate-50 hover:border-slate-300'
                      }`}>
                      <span className="text-xl">{t.emoji}</span>
                      <div>
                        <p className={`text-xs font-bold ${types.includes(t.key) ? 'text-violet-700' : 'text-slate-700'}`}>{t.label}</p>
                        <p className="text-[10px] text-slate-400">{t.desc}</p>
                      </div>
                      {types.includes(t.key) && <MdCheckCircle className="ml-auto text-violet-500 shrink-0" />}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase ml-1">
                  Additional Requirements (optional)
                </label>
                <textarea value={requirement} onChange={e => setReq(e.target.value)}
                  placeholder="Describe specific details, components, or focus areas for the diagrams…"
                  rows={4}
                  className="mt-1 w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-violet-400/30"
                />
              </div>

              <button type="submit" disabled={loading || !types.length}
                className="w-full bg-violet-600 hover:bg-violet-700 disabled:bg-violet-400 text-white py-3 rounded-xl font-bold text-sm flex items-center justify-center gap-2 transition-all shadow-md shadow-violet-200">
                {loading
                  ? <><RiLoader4Line className="animate-spin text-lg" /> Generating {types.length} diagram{types.length > 1 ? 's' : ''}…</>
                  : <><MdAdd className="text-lg" /> Generate {types.length} Diagram{types.length > 1 ? 's' : ''}</>}
              </button>

              {loading && (
                <div className="space-y-1.5">
                  {types.map((t, i) => (
                    <div key={t} className="flex items-center gap-2 text-xs text-violet-600">
                      <div className="w-1.5 h-1.5 bg-violet-400 rounded-full animate-pulse" style={{ animationDelay: `${i * 0.3}s` }} />
                      Generating {DIAGRAM_TYPES.find(d => d.key === t)?.label}…
                    </div>
                  ))}
                </div>
              )}
            </div>
          </form>
        </div>

        {/* Right: Diagram gallery */}
        <div className="lg:col-span-8 space-y-5">
          {histLoading ? (
            <div className="flex items-center justify-center h-40">
              <RiLoader4Line className="animate-spin text-3xl text-violet-500" />
            </div>
          ) : diagrams.length === 0 ? (
            <div className="bg-slate-100/50 border-2 border-dashed border-slate-200 rounded-3xl h-[500px] flex flex-col items-center justify-center text-center px-10">
              <MdOutlineAccountTree className="text-6xl text-slate-300 mb-4" />
              <p className="text-lg font-bold text-slate-700 mb-2">No Diagrams Yet</p>
              <p className="text-sm text-slate-400 max-w-sm">
                Select a project, choose diagram types, and click Generate to create your first AI-powered Mermaid diagrams.
              </p>
            </div>
          ) : (
            <div className="space-y-5">
              {diagrams.map((d, i) => (
                <div key={d.id || i} className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
                  <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-100 bg-slate-50/50">
                    <div>
                      <p className="text-sm font-bold text-slate-800">
                        {DIAGRAM_TYPES.find(t => t.key === d.diagram_type)?.emoji || '📊'} {d.title || d.diagram_type}
                      </p>
                      {d.description && <p className="text-xs text-slate-400 mt-0.5">{d.description}</p>}
                    </div>
                    <div className="flex items-center gap-1">
                      <CopyBtn text={d.mermaid_code || ''} />
                    </div>
                  </div>
                  <div className="p-5">
                    <MermaidView id={d.id || i} code={d.mermaid_code || ''} />
                    <details className="mt-3">
                      <summary className="text-[10px] font-bold text-slate-400 uppercase cursor-pointer hover:text-slate-600 transition-colors">
                        View Mermaid Source
                      </summary>
                      <pre className="mt-2 text-[10px] bg-slate-900 text-emerald-300 p-4 rounded-xl overflow-auto font-mono leading-relaxed max-h-48">
                        {d.mermaid_code}
                      </pre>
                    </details>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
