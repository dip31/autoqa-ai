import React, { useState } from 'react';
import { reviewCode } from '../api/client';
import Loader from '../components/Loader';
import ScoreBadge from '../components/ScoreBadge';
import ErrorAlert from '../components/ErrorAlert';
import {
  MdOutlineUploadFile, MdOutlineBugReport, MdOutlineLightbulb,
  MdFileDownload, MdOutlineAutoFixHigh, MdContentCopy, MdCheck,
  MdOutlineCode,
} from 'react-icons/md';
import { exportToExcel } from '../api/exportExcel';

const LANGUAGES = ['Python', 'JavaScript', 'Java', 'C++', 'HTML/CSS', 'React', 'NodeJS', 'TypeScript'];

const SEVERITY = {
  high:   'bg-red-50 text-red-700 border-red-200',
  medium: 'bg-amber-50 text-amber-700 border-amber-200',
  low:    'bg-emerald-50 text-emerald-700 border-emerald-200',
};

// Map language to file extension for download
const EXT_MAP = {
  Python: 'py', JavaScript: 'js', Java: 'java', 'C++': 'cpp',
  'HTML/CSS': 'html', React: 'jsx', NodeJS: 'js', TypeScript: 'ts',
};

export default function CodeReview() {
  const [code, setCode]         = useState('');
  const [language, setLanguage] = useState('Python');
  const [result, setResult]     = useState(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState('');
  const [copied, setCopied]     = useState(false);
  const [activeTab, setActiveTab] = useState('issues'); // 'issues' | 'optimized'

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => setCode(ev.target.result);
    reader.onerror = () => setError('Failed to read file. Please try again.');
    reader.readAsText(file);
  };

  const handleSubmit = async () => {
    if (!code.trim()) return;
    setLoading(true); setError(''); setResult(null); setActiveTab('issues');
    try {
      const res = await reviewCode(code, language);
      setResult(res.data.data);
    } catch (e) {
      setError(e.response?.data?.error || e.message || 'Failed to review code. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    if (!result?.optimized_code) return;
    navigator.clipboard.writeText(result.optimized_code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const handleDownloadCode = () => {
    if (!result?.optimized_code) return;
    const ext = EXT_MAP[language] || 'txt';
    const blob = new Blob([result.optimized_code], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `optimized_code.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleExport = () => {
    exportToExcel([
      {
        sheetName: 'Issues',
        rows: (result.issues || []).map((issue, i) => ({
          '#': i + 1,
          'Line':        issue.line || '—',
          'Severity':    issue.severity || '—',
          'Type':        issue.type || '—',
          'Description': issue.description || '',
        }))
      },
      {
        sheetName: 'Suggestions',
        rows: (result.suggestions || []).map((s, i) => ({ '#': i + 1, Suggestion: s }))
      },
      {
        sheetName: 'Optimized Code',
        rows: [{ 'Optimized Code': result.optimized_code || '' }]
      }
    ], 'code-review.xlsx');
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 w-full">
      <h2 className="text-xl font-semibold text-slate-800 mb-1">Code Review</h2>
      <p className="text-slate-500 text-sm mb-6">Upload or paste code for AI-powered quality, security, and performance analysis — with an optimized version.</p>

      {/* Input panel */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm mb-5 space-y-4">
        <div className="flex gap-4 items-end">
          <div className="flex-1">
            <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">Language</label>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="w-full bg-slate-50 text-slate-800 rounded-lg px-4 py-2.5 border border-slate-200 focus:border-blue-400 focus:ring-2 focus:ring-blue-100 focus:outline-none text-sm transition"
            >
              {LANGUAGES.map(l => <option key={l}>{l}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">Upload File</label>
            <label className="flex items-center gap-2 px-4 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-lg text-sm cursor-pointer transition-colors border border-slate-200">
              <MdOutlineUploadFile className="text-base" /> Choose File
              <input type="file" className="hidden" accept=".py,.js,.java,.cpp,.html,.css,.ts,.jsx,.tsx" onChange={handleFileUpload} />
            </label>
          </div>
        </div>

        <div>
          <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">Code Editor</label>
          <textarea
            className="w-full h-60 bg-slate-50 text-slate-800 rounded-lg p-4 text-sm border border-slate-200 focus:border-blue-400 focus:ring-2 focus:ring-blue-100 focus:outline-none resize-none font-mono transition"
            placeholder="Paste your code here..."
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        </div>

        <button
          onClick={handleSubmit}
          disabled={loading || !code.trim()}
          className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors"
        >
          Review Code
        </button>
      </div>

      <ErrorAlert message={error} onClose={() => setError('')} />
      {loading && <Loader message="Reviewing and optimizing your code..." />}

      {result && (
        <div className="space-y-4">
          {/* Result header */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-slate-700">Review Complete</p>
              <p className="text-xs text-slate-400 mt-0.5">{result.summary}</p>
            </div>
            <div className="flex items-center gap-3">
              <ScoreBadge score={result.score} />
              <button
                onClick={handleExport}
                className="flex items-center gap-1.5 px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium rounded-lg transition-colors"
              >
                <MdFileDownload className="text-base" /> Export Excel
              </button>
            </div>
          </div>

          {/* Tab switcher */}
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
            <div className="flex border-b border-slate-200">
              <button
                onClick={() => setActiveTab('issues')}
                className={`flex items-center gap-2 px-5 py-3 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === 'issues'
                    ? 'border-blue-600 text-blue-600 bg-blue-50'
                    : 'border-transparent text-slate-500 hover:text-slate-700 hover:bg-slate-50'
                }`}
              >
                <MdOutlineBugReport className="text-base" />
                Issues & Suggestions
                {result.issues?.length > 0 && (
                  <span className="ml-1 bg-red-100 text-red-600 text-xs px-1.5 py-0.5 rounded-full font-semibold">
                    {result.issues.length}
                  </span>
                )}
              </button>
              <button
                onClick={() => setActiveTab('optimized')}
                className={`flex items-center gap-2 px-5 py-3 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === 'optimized'
                    ? 'border-violet-600 text-violet-600 bg-violet-50'
                    : 'border-transparent text-slate-500 hover:text-slate-700 hover:bg-slate-50'
                }`}
              >
                <MdOutlineAutoFixHigh className="text-base" />
                Optimized Code
              </button>
            </div>

            {/* Issues tab */}
            {activeTab === 'issues' && (
              <div>
                {result.issues?.length > 0 ? (
                  <div className="divide-y divide-slate-100">
                    {result.issues.map((issue, i) => (
                      <div key={i} className="px-5 py-3">
                        <div className="flex items-center gap-2 mb-1">
                          <span className={`text-xs px-2 py-0.5 rounded-full border font-semibold uppercase ${SEVERITY[issue.severity] || SEVERITY.low}`}>
                            {issue.severity}
                          </span>
                          <span className="text-xs text-slate-500">{issue.type}</span>
                          {issue.line && <span className="text-xs text-slate-400 ml-auto">Line {issue.line}</span>}
                        </div>
                        <p className="text-sm text-slate-600">{issue.description}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-slate-400 text-sm text-center py-8">No issues found</p>
                )}

                {result.suggestions?.length > 0 && (
                  <div className="border-t border-slate-100 px-5 py-4">
                    <div className="flex items-center gap-2 mb-3">
                      <MdOutlineLightbulb className="text-amber-500 text-lg" />
                      <p className="text-sm font-semibold text-slate-700">Suggestions</p>
                    </div>
                    <ul className="space-y-2">
                      {result.suggestions.map((s, i) => (
                        <li key={i} className="flex gap-2 text-sm text-slate-600">
                          <span className="text-amber-400 font-bold shrink-0">{i + 1}.</span> {s}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            {/* Optimized code tab */}
            {activeTab === 'optimized' && (
              <div>
                <div className="flex flex-wrap items-center justify-between px-5 py-3 border-b border-slate-100 bg-slate-50 gap-2">
                  <div className="flex items-center gap-2">
                    <MdOutlineCode className="text-violet-500 text-lg" />
                    <p className="text-sm font-semibold text-slate-700">Optimized {language} Code</p>
                    <span className="text-xs bg-violet-100 text-violet-700 px-2 py-0.5 rounded-full border border-violet-200 font-medium">AI Generated</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleCopy}
                      className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors ${
                        copied
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                          : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                      }`}
                    >
                      {copied ? <MdCheck className="text-base" /> : <MdContentCopy className="text-base" />}
                      {copied ? 'Copied!' : 'Copy'}
                    </button>
                    <button
                      onClick={handleDownloadCode}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-violet-600 hover:bg-violet-700 text-white text-xs font-medium rounded-lg transition-colors"
                    >
                      <MdFileDownload className="text-base" /> Download
                    </button>
                  </div>
                </div>
                <div className="relative">
                  <pre className="text-sm text-slate-800 font-mono p-5 overflow-x-auto bg-slate-50 max-h-[520px] overflow-y-auto leading-relaxed whitespace-pre">
                    {result.optimized_code || 'No optimized code returned.'}
                  </pre>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}


