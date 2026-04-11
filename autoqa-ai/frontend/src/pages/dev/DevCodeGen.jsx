import React, { useState, useEffect } from 'react';
import {
  MdOutlineCode, MdCheckCircle, MdContentCopy, MdOutlineRateReview,
  MdWarning, MdError, MdInfo, MdOutlineAutoFixHigh,
} from 'react-icons/md';
import { RiLoader4Line } from 'react-icons/ri';
import { devListProjects, devGenerateCode, devReviewCode } from '../../api/client';

const LANGUAGES = [
  { key: 'python',     label: 'Python',     color: 'bg-blue-500',    emoji: '🐍' },
  { key: 'javascript', label: 'JavaScript', color: 'bg-yellow-500',  emoji: '🌐' },
  { key: 'typescript', label: 'TypeScript', color: 'bg-blue-600',    emoji: '📘' },
  { key: 'java',       label: 'Java',       color: 'bg-red-500',     emoji: '☕' },
  { key: 'sql',        label: 'SQL',        color: 'bg-emerald-600', emoji: '🗄️' },
  { key: 'bash',       label: 'Shell/Bash', color: 'bg-slate-600',   emoji: '⌨️' },
];

function CopyBtn({ text }) {
  const [ok, setOk] = useState(false);
  return (
    <button onClick={() => { navigator.clipboard.writeText(text); setOk(true); setTimeout(() => setOk(false), 1500); }}
      className="p-2 rounded-lg hover:bg-slate-700 text-slate-400 hover:text-white transition-colors flex items-center gap-1.5 text-xs font-bold">
      {ok ? <><MdCheckCircle className="text-emerald-400" /> Copied!</> : <><MdContentCopy /> Copy</>}
    </button>
  );
}

const SEV_CFG = {
  Error:   { cls: 'bg-red-50 border-red-100',    icon: MdError,   ic: 'text-red-500' },
  Warning: { cls: 'bg-yellow-50 border-yellow-100', icon: MdWarning, ic: 'text-yellow-500' },
  Info:    { cls: 'bg-blue-50 border-blue-100',   icon: MdInfo,    ic: 'text-blue-500' },
};

export default function DevCodeGen() {
  const [projects, setProjects]   = useState([]);
  const [pid, setPid]             = useState('');
  const [lang, setLang]           = useState('python');
  const [requirement, setReq]     = useState('');
  const [genLoading, setGenLoad]  = useState(false);
  const [genResult, setGenResult] = useState(null);
  const [tab, setTab]             = useState('code'); // code | review
  const [reviewCode, setRevCode]  = useState('');
  const [revLang, setRevLang]     = useState('python');
  const [revCtx, setRevCtx]       = useState('');
  const [revLoad, setRevLoad]     = useState(false);
  const [review, setReview]       = useState(null);

  useEffect(() => {
    devListProjects().then(r => setProjects(r.data.projects || [])).catch(() => []);
  }, []);

  const handleGenerate = async (e) => {
    e.preventDefault();
    if (!pid) { alert('Select a project'); return; }
    setGenLoad(true); setGenResult(null);
    try {
      const r = await devGenerateCode(pid, { requirements: requirement, language: lang });
      setGenResult(r.data.code);
      setRevCode(r.data.code.code_content || '');
      setRevLang(lang);
    } catch (err) {
      alert(err.response?.data?.error || 'Code generation failed');
    } finally { setGenLoad(false); }
  };

  const handleReview = async (e) => {
    e.preventDefault();
    if (!reviewCode.trim()) { alert('Paste code to review'); return; }
    setRevLoad(true); setReview(null);
    try {
      const r = await devReviewCode({ code: reviewCode, language: revLang, context: revCtx });
      setReview(r.data.review);
    } catch (err) {
      alert(err.response?.data?.error || 'Review failed');
    } finally { setRevLoad(false); }
  };

  const SCORE_COLOR = (s) => s >= 80 ? 'text-emerald-600' : s >= 60 ? 'text-yellow-600' : 'text-red-600';

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-[1600px] mx-auto space-y-6">

      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
          <MdOutlineCode className="text-emerald-500" /> Code Generator & Review
        </h1>
        <p className="text-slate-500 text-sm mt-1">AI generates production-ready code from requirements, then reviews it</p>
      </div>

      {/* Tab switcher */}
      <div className="flex gap-2 bg-slate-100 p-1 rounded-xl w-fit">
        {[
          { key: 'code',   label: '⚡ Generate Code' },
          { key: 'review', label: '🔍 Code Review' },
        ].map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-5 py-2 rounded-lg text-sm font-bold transition-all ${
              tab === t.key ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-700'
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {/* ── Code Generator ──────────────────────────────────────────────────── */}
      {tab === 'code' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-4 space-y-5">
            <form onSubmit={handleGenerate} className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-4">
              <h2 className="text-xs font-black text-slate-500 uppercase tracking-widest">Code Generation</h2>

              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase ml-1">Select Project</label>
                <select required value={pid} onChange={e => setPid(e.target.value)}
                  className="mt-1 w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-400/30">
                  <option value="">— Choose a project —</option>
                  {projects.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}
                </select>
              </div>

              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase ml-1">Language</label>
                <div className="mt-2 grid grid-cols-3 gap-2">
                  {LANGUAGES.map(l => (
                    <button key={l.key} type="button" onClick={() => setLang(l.key)}
                      className={`p-2.5 rounded-xl border-2 transition-all text-center ${
                        lang === l.key ? 'border-emerald-500 bg-emerald-50' : 'border-slate-200 bg-slate-50 hover:border-slate-300'
                      }`}>
                      <p className="text-lg">{l.emoji}</p>
                      <p className={`text-[10px] font-bold mt-0.5 ${lang === l.key ? 'text-emerald-700' : 'text-slate-600'}`}>{l.label}</p>
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase ml-1">Requirements / Feature Description *</label>
                <textarea required value={requirement} onChange={e => setReq(e.target.value)}
                  placeholder="Describe exactly what you need. e.g.: Create a REST API endpoint that handles user login with JWT token generation and bcrypt password validation…"
                  rows={6}
                  className="mt-1 w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-emerald-400/30"
                />
              </div>

              <button type="submit" disabled={genLoading}
                className="w-full bg-emerald-600 hover:bg-emerald-700 disabled:bg-emerald-400 text-white py-3 rounded-xl font-bold text-sm flex items-center justify-center gap-2 transition-all shadow-md shadow-emerald-200">
                {genLoading
                  ? <><RiLoader4Line className="animate-spin text-lg" /> Generating {LANGUAGES.find(l => l.key === lang)?.label} code…</>
                  : <><MdOutlineCode className="text-lg" /> Generate Code</>}
              </button>
            </form>
          </div>

          {/* Right: Code output */}
          <div className="lg:col-span-8">
            {!genResult ? (
              <div className="bg-slate-900 rounded-3xl h-full min-h-[500px] flex items-center justify-center text-center p-10">
                <div>
                  <MdOutlineCode className="text-6xl text-slate-600 mx-auto mb-4" />
                  <p className="text-slate-400 text-sm font-semibold">Your generated code will appear here</p>
                  <p className="text-slate-600 text-xs mt-2">Select a project and describe what you need</p>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Metrics */}
                <div className="grid grid-cols-3 gap-4">
                  {[
                    { label: 'Total Lines', value: genResult.metrics?.total_lines || 0 },
                    { label: 'Code Lines', value: genResult.metrics?.code_lines || 0 },
                    { label: 'File', value: genResult.filename_suggestion || 'output.py' },
                  ].map(({ label, value }) => (
                    <div key={label} className="bg-white border border-slate-200 rounded-xl p-3 text-center shadow-sm">
                      <p className="text-sm font-black text-emerald-600">{value}</p>
                      <p className="text-[10px] font-bold text-slate-400 uppercase mt-0.5">{label}</p>
                    </div>
                  ))}
                </div>

                {/* Code block */}
                <div className="bg-slate-900 rounded-2xl overflow-hidden shadow-xl border border-slate-700">
                  <div className="flex items-center justify-between px-5 py-3 bg-slate-800 border-b border-slate-700">
                    <div className="flex gap-1.5">
                      <div className="w-3 h-3 rounded-full bg-red-400" />
                      <div className="w-3 h-3 rounded-full bg-yellow-400" />
                      <div className="w-3 h-3 rounded-full bg-emerald-400" />
                    </div>
                    <span className="text-[11px] text-slate-400 font-mono">{genResult.filename_suggestion}</span>
                    <div className="flex gap-2">
                      <CopyBtn text={genResult.code_content || ''} />
                      <button onClick={() => { setRevCode(genResult.code_content || ''); setRevLang(lang); setTab('review'); }}
                        className="text-xs font-bold text-violet-400 hover:text-violet-300 px-2 py-1 rounded-lg hover:bg-slate-700 transition-colors flex items-center gap-1">
                        <MdOutlineRateReview /> Review
                      </button>
                    </div>
                  </div>
                  <pre className="text-sm text-emerald-300 p-6 overflow-auto font-mono leading-relaxed max-h-[600px]">
                    {genResult.code_content}
                  </pre>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Code Review ──────────────────────────────────────────────────────── */}
      {tab === 'review' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-5 space-y-5">
            <form onSubmit={handleReview} className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-4">
              <h2 className="text-xs font-black text-slate-500 uppercase tracking-widest">Code Review</h2>

              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase ml-1">Language</label>
                <select value={revLang} onChange={e => setRevLang(e.target.value)}
                  className="mt-1 w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none">
                  {LANGUAGES.map(l => <option key={l.key} value={l.key}>{l.label}</option>)}
                </select>
              </div>

              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase ml-1">Context (optional)</label>
                <input value={revCtx} onChange={e => setRevCtx(e.target.value)}
                  placeholder="e.g. Authentication service, handles JWT tokens"
                  className="mt-1 w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-violet-400/30"
                />
              </div>

              <div>
                <label className="text-[10px] font-bold text-slate-400 uppercase ml-1">Paste Your Code *</label>
                <textarea required value={reviewCode} onChange={e => setRevCode(e.target.value)}
                  placeholder="Paste your code here for AI review…"
                  rows={14} className="mt-1 w-full bg-slate-900 text-emerald-300 border border-slate-700 rounded-xl px-4 py-3 text-xs font-mono resize-none focus:outline-none focus:ring-2 focus:ring-violet-400/30 leading-relaxed"
                />
              </div>

              <button type="submit" disabled={revLoad}
                className="w-full bg-violet-600 hover:bg-violet-700 disabled:bg-violet-400 text-white py-3 rounded-xl font-bold text-sm flex items-center justify-center gap-2 transition-all shadow-md shadow-violet-200">
                {revLoad
                  ? <><RiLoader4Line className="animate-spin text-lg" /> Reviewing code…</>
                  : <><MdOutlineRateReview className="text-lg" /> Review Code</>}
              </button>
            </form>
          </div>

          {/* Review result */}
          <div className="lg:col-span-7">
            {!review ? (
              <div className="bg-slate-100/50 border-2 border-dashed border-slate-200 rounded-3xl min-h-[500px] flex items-center justify-center text-center p-10">
                <div>
                  <MdOutlineRateReview className="text-6xl text-slate-300 mx-auto mb-4" />
                  <p className="text-slate-500 text-sm font-semibold">Code review results will appear here</p>
                  <p className="text-slate-400 text-xs mt-1">Paste your code on the left and click Review</p>
                </div>
              </div>
            ) : (
              <div className="space-y-5">
                {/* Score banner */}
                <div className={`rounded-2xl p-5 flex items-center gap-5 shadow-sm ${
                  (review.overall_score||70) >= 80 ? 'bg-emerald-50 border border-emerald-200' :
                  (review.overall_score||70) >= 60 ? 'bg-yellow-50 border border-yellow-200' :
                  'bg-red-50 border border-red-200'
                }`}>
                  <div className="text-center shrink-0">
                    <p className={`text-4xl font-black ${SCORE_COLOR(review.overall_score||70)}`}>{review.overall_score || 70}</p>
                    <p className="text-xs font-black text-slate-500 uppercase mt-1">Score</p>
                  </div>
                  <div className="text-center shrink-0">
                    <p className={`text-3xl font-black ${SCORE_COLOR(review.overall_score||70)}`}>{review.grade || 'B'}</p>
                    <p className="text-xs font-black text-slate-500 uppercase mt-1">Grade</p>
                  </div>
                  <div className="flex-1">
                    <p className="text-sm text-slate-700 leading-relaxed">{review.summary}</p>
                    <div className="flex gap-3 mt-2">
                      <span className="text-[10px] font-bold text-slate-500">Health: <strong>{review.overall_code_health}</strong></span>
                      <span className="text-[10px] font-bold text-slate-500">Tech Debt: <strong>{review.technical_debt_level}</strong></span>
                    </div>
                  </div>
                </div>

                {/* Issues */}
                {review.issues?.length > 0 && (
                  <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-3">
                    <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest">Issues Found ({review.issues.length})</h3>
                    {review.issues.map((issue, i) => {
                      const cfg = SEV_CFG[issue.severity] || SEV_CFG.Info;
                      const Icon = cfg.icon;
                      return (
                        <div key={i} className={`flex items-start gap-3 p-3.5 rounded-xl border ${cfg.cls}`}>
                          <Icon className={`shrink-0 mt-0.5 ${cfg.ic}`} />
                          <div className="flex-1">
                            <p className="text-sm text-slate-700">{issue.description}</p>
                            {issue.suggestion && (
                              <p className="text-xs text-slate-500 mt-1 italic flex items-start gap-1">
                                <MdOutlineAutoFixHigh className="shrink-0 mt-0.5 text-violet-500" /> {issue.suggestion}
                              </p>
                            )}
                            {issue.line_hint && <p className="text-[10px] font-mono text-slate-400 mt-1">{issue.line_hint}</p>}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}

                {/* Improvements */}
                {review.improvements?.length > 0 && (
                  <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm space-y-3">
                    <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest">Improvements ({review.improvements.length})</h3>
                    {review.improvements.map((imp, i) => (
                      <div key={i} className="flex items-start gap-3 p-3.5 rounded-xl bg-emerald-50 border border-emerald-100">
                        <MdCheckCircle className="text-emerald-500 shrink-0 mt-0.5" />
                        <div>
                          <p className="text-sm text-slate-700">{imp.improvement}</p>
                          {imp.benefit && <p className="text-xs text-emerald-600 mt-1 italic">→ {imp.benefit}</p>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Test suggestion */}
                {review.test_coverage_suggestion && (
                  <div className="bg-blue-50 border border-blue-100 rounded-2xl p-4">
                    <p className="text-[10px] font-black text-blue-500 uppercase mb-1">Testing Suggestion</p>
                    <p className="text-sm text-blue-800">{review.test_coverage_suggestion}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
