import React, { useState } from 'react';
import { testWebsite } from '../api/client';
import { exportToExcel } from '../api/exportExcel';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import { MdOutlineSearch, MdOutlineDynamicForm, MdOutlineSmartButton, MdOutlineInput, MdOutlineLink, MdFileDownload } from 'react-icons/md';

function renderValue(val) {
  if (typeof val === 'string') return val;
  if (Array.isArray(val)) return val.join(', ');
  if (typeof val === 'object' && val !== null) return Object.entries(val).map(([k, v]) => `${k}: ${v}`).join(' | ');
  return String(val ?? '');
}

function renderSteps(steps) {
  if (!steps) return '—';
  const arr = Array.isArray(steps) ? steps : [steps];
  return (
    <ol className="list-decimal list-inside space-y-1">
      {arr.map((s, i) => <li key={i}>{renderValue(s)}</li>)}
    </ol>
  );
}

const TABS = [
  { key: 'functional', label: 'Functional Tests', mapKey: 'functional_tests' },
  { key: 'ui',         label: 'UI Tests',          mapKey: 'ui_tests'         },
  { key: 'edge',       label: 'Edge Cases',         mapKey: 'edge_cases'       },
];

export default function WebsiteTesting() {
  const [url, setUrl]             = useState('');
  const [result, setResult]       = useState(null);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState('');
  const [activeTab, setActiveTab] = useState('functional');

  const handleSubmit = async () => {
    if (!url.trim()) return;
    setLoading(true); setError(''); setResult(null);
    try {
      const res = await testWebsite(url);
      setResult(res.data.data);
    } catch (e) {
      setError(e.response?.data?.error || e.message || 'Failed to analyze website. Check the URL and try again.');
    } finally {
      setLoading(false);
    }
  };

  const getTests = () => {
    if (!result?.test_cases) return [];
    const tab = TABS.find(t => t.key === activeTab);
    return result.test_cases[tab?.mapKey] || [];
  };

  const handleExport = () => {
    exportToExcel(
      TABS.map(({ label, mapKey }) => ({
        sheetName: label,
        rows: (result?.test_cases?.[mapKey] || []).map((tc, i) => ({
          'Test Case ID':    tc.id || `TC-${String(i + 1).padStart(2, '0')}`,
          'Title':           tc.title || '',
          'Test Steps':      Array.isArray(tc.steps) ? tc.steps.join('\n') : (tc.steps || ''),
          'Expected Result': tc.expected_result || '',
        }))
      })),
      'website-test-cases.xlsx'
    );
  };

  const statItems = [
    { label: 'Forms',   value: result?.analysis?.forms_count   ?? 0, icon: MdOutlineDynamicForm },
    { label: 'Buttons', value: result?.analysis?.buttons_count ?? 0, icon: MdOutlineSmartButton },
    { label: 'Inputs',  value: result?.analysis?.inputs_count  ?? 0, icon: MdOutlineInput },
    { label: 'Links',   value: result?.analysis?.links_count   ?? 0, icon: MdOutlineLink },
  ];

  return (
    <div className="p-4 sm:p-6 lg:p-8 w-full">
      <h2 className="text-xl font-semibold text-slate-800 mb-1">Website Testing</h2>
      <p className="text-slate-500 text-sm mb-6">Enter a URL to launch browser automation and generate AI test cases.</p>

      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm mb-5">
        <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">Website URL</label>
        <div className="flex gap-3">
          <div className="relative flex-1">
            <MdOutlineSearch className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-lg" />
            <input
              type="url"
              className="w-full bg-slate-50 text-slate-800 rounded-lg pl-10 pr-4 py-2.5 border border-slate-200 focus:border-blue-400 focus:ring-2 focus:ring-blue-100 focus:outline-none text-sm transition"
              placeholder="https://example.com"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
            />
          </div>
          <button
            onClick={handleSubmit}
            disabled={loading || !url.trim()}
            className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors whitespace-nowrap"
          >
            Analyze Website
          </button>
        </div>
      </div>

      <ErrorAlert message={error} onClose={() => setError('')} />
      {loading && <Loader message="Launching browser and analyzing website..." />}

      {result && (
        <div className="space-y-4">
          {/* Stats */}
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
            <p className="text-sm font-semibold text-slate-700 mb-4">Website Analysis</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {statItems.map(({ label, value, icon: Icon }) => (
                <div key={label} className="bg-slate-50 border border-slate-200 rounded-lg p-4 flex items-center gap-3">
                  <Icon className="text-blue-500 text-2xl shrink-0" />
                  <div>
                    <p className="text-lg font-bold text-slate-800">{value}</p>
                    <p className="text-xs text-slate-500">{label}</p>
                  </div>
                </div>
              ))}
            </div>
            {result.analysis?.title && (
              <p className="text-xs text-slate-500 mt-3">Page title: <span className="text-slate-700 font-medium">{result.analysis.title}</span></p>
            )}
            {result.test_cases?.summary && (
              <p className="text-xs text-slate-500 mt-1">{result.test_cases.summary}</p>
            )}
          </div>

          {/* Table */}
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
            <div className="flex border-b border-slate-200">
              {TABS.map(({ key, label, mapKey }) => (
                <button
                  key={key}
                  onClick={() => setActiveTab(key)}
                  className={`flex-1 py-3 text-sm font-medium transition-colors ${
                    activeTab === key
                      ? 'border-b-2 border-blue-600 text-blue-600 bg-blue-50'
                      : 'text-slate-500 hover:text-slate-700 hover:bg-slate-50'
                  }`}
                >
                  {label} ({result.test_cases?.[mapKey]?.length || 0})
                </button>
              ))}
            </div>

            <div className="px-5 py-3 border-b border-slate-100 flex justify-end">
              <button
                onClick={handleExport}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium rounded-lg transition-colors"
              >
                <MdFileDownload className="text-base" /> Download Excel
              </button>
            </div>

            <div className="overflow-x-auto max-h-[480px] overflow-y-auto">
              {getTests().length === 0 ? (
                <p className="text-slate-400 text-sm text-center py-10">No test cases in this category</p>
              ) : (
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-slate-50 z-10">
                    <tr>
                      {['#', 'Title', 'Test Steps', 'Expected Result'].map(h => (
                        <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-200">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {getTests().map((tc, i) => (
                      <tr key={i} className="hover:bg-slate-50 transition-colors">
                        <td className="px-4 py-3 text-slate-400 font-mono text-xs align-top">{renderValue(tc.id || `TC-${String(i + 1).padStart(2, '0')}`)}</td>
                        <td className="px-4 py-3 text-slate-800 font-medium text-xs align-top">{renderValue(tc.title)}</td>
                        <td className="px-4 py-3 text-slate-600 text-xs align-top">{renderSteps(tc.steps)}</td>
                        <td className="px-4 py-3 text-emerald-700 text-xs align-top">{renderValue(tc.expected_result) || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


