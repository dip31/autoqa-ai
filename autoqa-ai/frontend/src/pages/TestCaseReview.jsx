import React, { useState } from 'react';
import { reviewTestCase } from '../api/client';
import Loader from '../components/Loader';
import ScoreBadge from '../components/ScoreBadge';
import ErrorAlert from '../components/ErrorAlert';
import { MdOutlineWarningAmber, MdOutlineLightbulb, MdOutlineCheckCircle, MdFileDownload } from 'react-icons/md';
import { exportToExcel } from '../api/exportExcel';

function renderValue(val) {
  if (typeof val === 'string') return val;
  if (Array.isArray(val)) return val.join(', ');
  if (typeof val === 'object' && val !== null) return Object.entries(val).map(([k, v]) => `${k}: ${v}`).join(' | ');
  return String(val ?? '');
}

export default function TestCaseReview() {
  const [testcase, setTestcase] = useState('');
  const [result, setResult]     = useState(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState('');

  const handleSubmit = async () => {
    if (!testcase.trim()) return;
    setLoading(true); setError(''); setResult(null);
    try {
      const res = await reviewTestCase(testcase);
      setResult(res.data.data);
    } catch (e) {
      setError(e.response?.data?.error || e.message || 'Failed to analyze test case. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleExport = () => {
    exportToExcel([
      { sheetName: 'Issues',      rows: (result.issues || []).map((v, i) => ({ '#': i + 1, Issue: renderValue(v) })) },
      { sheetName: 'Suggestions', rows: (result.suggestions || []).map((v, i) => ({ '#': i + 1, Suggestion: renderValue(v) })) },
      {
        sheetName: 'Improved Test Case',
        rows: typeof result.improved_testcase === 'object' && result.improved_testcase !== null
          ? [result.improved_testcase]
          : [{ 'Improved Test Case': renderValue(result.improved_testcase) }]
      }
    ], 'test-case-review.xlsx');
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 w-full">
      <h2 className="text-xl font-semibold text-slate-800 mb-1">Test Case Review</h2>
      <p className="text-slate-500 text-sm mb-6">Paste your manual test case and AI will analyze it for completeness, clarity, and edge cases.</p>

      {/* Input */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm mb-5">
        <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">Test Case Input</label>
        <textarea
          className="w-full h-44 bg-slate-50 text-slate-800 rounded-lg p-4 text-sm border border-slate-200 focus:border-blue-400 focus:ring-2 focus:ring-blue-100 focus:outline-none resize-none transition"
          placeholder={`Example:\nTest Case: Login with valid credentials\nSteps:\n  1. Open login page\n  2. Enter username and password\n  3. Click Login\nExpected: User is redirected to dashboard`}
          value={testcase}
          onChange={(e) => setTestcase(e.target.value)}
        />
        <button
          onClick={handleSubmit}
          disabled={loading || !testcase.trim()}
          className="mt-4 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors"
        >
          Analyze Test Case
        </button>
      </div>

      <ErrorAlert message={error} onClose={() => setError('')} />
      {loading && <Loader message="Analyzing your test case..." />}

      {result && (
        <div className="space-y-4">
          {/* Score bar */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-slate-700">Review Result</p>
              <p className="text-xs text-slate-400 mt-0.5">AI quality assessment</p>
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

          {/* Issues */}
          {result.issues?.length > 0 && (
            <div className="bg-white border border-red-100 rounded-xl p-5 shadow-sm">
              <div className="flex items-center gap-2 mb-3">
                <MdOutlineWarningAmber className="text-red-500 text-lg" />
                <h4 className="text-sm font-semibold text-slate-700">Issues Found ({result.issues.length})</h4>
              </div>
              <ul className="space-y-2">
                {result.issues.map((issue, i) => (
                  <li key={i} className="flex gap-2 text-sm text-slate-600">
                    <span className="text-red-400 font-bold shrink-0">•</span>
                    {renderValue(issue)}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Suggestions */}
          {result.suggestions?.length > 0 && (
            <div className="bg-white border border-amber-100 rounded-xl p-5 shadow-sm">
              <div className="flex items-center gap-2 mb-3">
                <MdOutlineLightbulb className="text-amber-500 text-lg" />
                <h4 className="text-sm font-semibold text-slate-700">Suggestions</h4>
              </div>
              <ul className="space-y-2">
                {result.suggestions.map((s, i) => (
                  <li key={i} className="flex gap-2 text-sm text-slate-600">
                    <span className="text-amber-400 font-bold shrink-0">{i + 1}.</span>
                    {renderValue(s)}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Improved test case */}
          {result.improved_testcase && (
            <div className="bg-white border border-emerald-100 rounded-xl overflow-hidden shadow-sm">
              <div className="flex items-center gap-2 px-5 py-4 border-b border-emerald-100">
                <MdOutlineCheckCircle className="text-emerald-500 text-lg" />
                <h4 className="text-sm font-semibold text-slate-700">Improved Test Case</h4>
              </div>
              {typeof result.improved_testcase === 'object' && result.improved_testcase !== null ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50">
                      <tr>
                        {Object.keys(result.improved_testcase).map((key) => (
                          <th key={key} className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-200">
                            {key}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        {Object.values(result.improved_testcase).map((val, i) => (
                          <td key={i} className="px-4 py-3 text-slate-700 text-xs align-top border-b border-slate-100">
                            {Array.isArray(val)
                              ? <ol className="list-decimal list-inside space-y-1">{val.map((v, j) => <li key={j}>{String(v)}</li>)}</ol>
                              : String(val ?? '—')}
                          </td>
                        ))}
                      </tr>
                    </tbody>
                  </table>
                </div>
              ) : (
                <pre className="text-sm text-slate-700 whitespace-pre-wrap font-mono p-5 bg-slate-50">
                  {renderValue(result.improved_testcase)}
                </pre>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}


