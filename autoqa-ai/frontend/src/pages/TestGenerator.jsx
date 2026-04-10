import React, { useState } from 'react';
import { generateTestCases } from '../api/client';
import { exportToExcel } from '../api/exportExcel';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import { MdFileDownload } from 'react-icons/md';

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
  { key: 'positive_tests',  label: 'Positive',  activeClass: 'border-emerald-500 text-emerald-600 bg-emerald-50' },
  { key: 'negative_tests',  label: 'Negative',  activeClass: 'border-red-500 text-red-600 bg-red-50' },
  { key: 'boundary_tests',  label: 'Boundary',  activeClass: 'border-amber-500 text-amber-600 bg-amber-50' },
  { key: 'ui_tests',        label: 'UI Tests',  activeClass: 'border-blue-500 text-blue-600 bg-blue-50' },
];

export default function TestGenerator() {
  const [requirement, setRequirement] = useState('');
  const [result, setResult]           = useState(null);
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState('');
  const [activeTab, setActiveTab]     = useState('positive_tests');

  const handleSubmit = async () => {
    if (!requirement.trim()) return;
    setLoading(true); setError(''); setResult(null);
    try {
      const res = await generateTestCases(requirement);
      setResult(res.data.data);
    } catch (e) {
      setError(e.response?.data?.error || e.message || 'Failed to generate test cases. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleExport = () => {
    exportToExcel(
      TABS.map(({ key, label }) => ({
        sheetName: label,
        rows: (result[key] || []).map((tc, i) => ({
          'Test Case ID':    tc.id || `TC-${String(i + 1).padStart(2, '0')}`,
          'Title':           tc.title || '',
          'Preconditions':   tc.preconditions || '',
          'Test Steps':      Array.isArray(tc.steps) ? tc.steps.join('\n') : (tc.steps || ''),
          'Expected Result': tc.expected_result || '',
        }))
      })),
      'test-cases.xlsx'
    );
  };

  const currentTests = result?.[activeTab] || [];

  return (
    <div className="p-4 sm:p-6 lg:p-8 w-full">
      <h2 className="text-xl font-semibold text-slate-800 mb-1">AI Test Case Generator</h2>
      <p className="text-slate-500 text-sm mb-6">Describe a requirement or user story and AI will generate comprehensive test cases.</p>

      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm mb-5">
        <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">Requirement / User Story / Feature</label>
        <textarea
          className="w-full h-36 bg-slate-50 text-slate-800 rounded-lg p-4 text-sm border border-slate-200 focus:border-blue-400 focus:ring-2 focus:ring-blue-100 focus:outline-none resize-none transition"
          placeholder="Example: As a user, I want to reset my password via email so I can regain access if I forget my credentials."
          value={requirement}
          onChange={(e) => setRequirement(e.target.value)}
        />
        <button
          onClick={handleSubmit}
          disabled={loading || !requirement.trim()}
          className="mt-4 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors"
        >
          Generate Test Cases
        </button>
      </div>

      <ErrorAlert message={error} onClose={() => setError('')} />
      {loading && <Loader message="Generating test cases..." />}

      {result && (
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
          {/* Header */}
          <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
            <div>
              <p className="text-sm font-semibold text-slate-700">Generated Test Cases</p>
              <p className="text-xs text-slate-400 mt-0.5">Total: {result.total_count || 0} test cases</p>
            </div>
            <button
              onClick={handleExport}
              className="flex items-center gap-1.5 px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium rounded-lg transition-colors"
            >
              <MdFileDownload className="text-base" /> Download Excel
            </button>
          </div>

          {/* Tabs */}
          <div className="flex border-b border-slate-200">
            {TABS.map(({ key, label, activeClass }) => (
              <button
                key={key}
                onClick={() => setActiveTab(key)}
                className={`flex-1 py-3 text-sm font-medium transition-colors border-b-2 ${
                  activeTab === key
                    ? activeClass
                    : 'border-transparent text-slate-500 hover:text-slate-700 hover:bg-slate-50'
                }`}
              >
                {label} ({result[key]?.length || 0})
              </button>
            ))}
          </div>

          {/* Table */}
          <div className="overflow-x-auto max-h-[540px] overflow-y-auto">
            {currentTests.length === 0 ? (
              <p className="text-slate-400 text-sm text-center py-10">No test cases in this category</p>
            ) : (
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-slate-50 z-10">
                  <tr>
                    {['#', 'Title', 'Preconditions', 'Test Steps', 'Expected Result'].map(h => (
                      <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wider border-b border-slate-200">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {currentTests.map((tc, i) => (
                    <tr key={i} className="hover:bg-slate-50 transition-colors">
                      <td className="px-4 py-3 text-slate-400 font-mono text-xs align-top">{renderValue(tc.id || `TC-${String(i + 1).padStart(2, '0')}`)}</td>
                      <td className="px-4 py-3 text-slate-800 font-medium text-xs align-top">{renderValue(tc.title)}</td>
                      <td className="px-4 py-3 text-slate-500 text-xs align-top">{renderValue(tc.preconditions) || '—'}</td>
                      <td className="px-4 py-3 text-slate-600 text-xs align-top">{renderSteps(tc.steps)}</td>
                      <td className="px-4 py-3 text-emerald-700 text-xs align-top">{renderValue(tc.expected_result) || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </div>
  );
}


