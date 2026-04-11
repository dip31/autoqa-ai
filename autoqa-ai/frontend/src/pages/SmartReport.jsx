import React, { useState, useRef } from 'react';
import html2canvas from 'html2canvas';
import { generateReport, generateReportImage } from '../api/client';
import { exportToExcel } from '../api/exportExcel';
import { exportReportPDF } from '../api/exportPdf';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import { useAuth } from '../context/AuthContext';
import { Doughnut } from 'react-chartjs-2';
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js';
import {
  MdFileDownload, MdOutlineRefresh, MdOutlineInfo,
  MdOutlineLightbulb, MdOutlinePictureAsPdf, MdOutlineImage,
  MdOutlineTableChart, MdSend, MdOutlineClose,
} from 'react-icons/md';
import { RiRobot2Line } from 'react-icons/ri';
import { getTeamUsers, sendMessage } from '../api/client';

ChartJS.register(ArcElement, Tooltip, Legend);

// Renders the AI content into a styled card for screenshot
function ReportImageCard({ content, result, user }) {
  const score = result?.quality_score ?? 0;
  const scoreColor = score >= 80 ? '#10b981' : score >= 50 ? '#f59e0b' : '#ef4444';
  const sections = content.split('\n\n').filter(Boolean);
  const initials = user?.username ? user.username.slice(0, 2).toUpperCase() : 'QA';

  return (
    <div style={{
      width: 800, background: 'linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%)',
      padding: 40, fontFamily: 'Inter, sans-serif', color: '#e2e8f0',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 32 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <div style={{ width: 36, height: 36, background: '#2563eb', borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <span style={{ color: '#fff', fontSize: 18 }}>Q</span>
            </div>
            <span style={{ fontSize: 20, fontWeight: 700, color: '#fff' }}>AutoQA AI</span>
          </div>
          <p style={{ color: '#94a3b8', fontSize: 13, margin: 0 }}>Smart QA Report · {new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}</p>
          {/* User info */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 10 }}>
            <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'linear-gradient(135deg,#6366f1,#8b5cf6)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <span style={{ color: '#fff', fontSize: 11, fontWeight: 700 }}>{initials}</span>
            </div>
            <div>
              <span style={{ color: '#e2e8f0', fontSize: 12, fontWeight: 600 }}>{user?.username || 'User'}</span>
              <span style={{ color: '#64748b', fontSize: 11, marginLeft: 6 }}>{user?.email || ''}</span>
            </div>
          </div>
        </div>
        {/* Score circle */}
        <div style={{ textAlign: 'center', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 16, padding: '16px 24px' }}>
          <div style={{ fontSize: 48, fontWeight: 800, color: scoreColor, lineHeight: 1 }}>{score}</div>
          <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 4 }}>Quality Score / 100</div>
          <div style={{ marginTop: 8, height: 6, background: 'rgba(255,255,255,0.1)', borderRadius: 3, overflow: 'hidden' }}>
            <div style={{ height: '100%', width: `${score}%`, background: scoreColor, borderRadius: 3 }} />
          </div>
        </div>
      </div>

      {/* Stats row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12, marginBottom: 28 }}>
        {[
          { label: 'Test Cases', value: result?.stats?.total_testcases ?? 0, color: '#3b82f6' },
          { label: 'Code Reviews', value: result?.stats?.total_code_reviews ?? 0, color: '#8b5cf6' },
          { label: 'Website Tests', value: result?.stats?.total_website_tests ?? 0, color: '#06b6d4' },
          { label: 'Avg TC Score', value: result?.stats?.avg_testcase_score ?? 0, color: '#10b981' },
          { label: 'Avg Code Score', value: result?.stats?.avg_code_score ?? 0, color: '#f59e0b' },
        ].map(({ label, value, color }) => (
          <div key={label} style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 12, padding: '14px 10px', textAlign: 'center' }}>
            <div style={{ fontSize: 26, fontWeight: 700, color }}>{value}</div>
            <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 4 }}>{label}</div>
          </div>
        ))}
      </div>

      {/* AI Content sections */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {sections.slice(0, 6).map((section, i) => {
          const lines = section.split('\n').filter(Boolean);
          const title = lines[0];
          const body = lines.slice(1).join(' ');
          if (!body) return null;
          return (
            <div key={i} style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 12, padding: 16 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: '#6366f1', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 8 }}>{title}</div>
              <div style={{ fontSize: 12, color: '#cbd5e1', lineHeight: 1.6 }}>{body.slice(0, 200)}{body.length > 200 ? '...' : ''}</div>
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div style={{ marginTop: 24, paddingTop: 16, borderTop: '1px solid rgba(255,255,255,0.08)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 11, color: '#475569' }}>Generated by AutoQA AI · Powered by Gemini AI</span>
        <span style={{ fontSize: 11, color: '#475569' }}>autoqa-ai.platform</span>
      </div>
    </div>
  );
}

export default function SmartReport() {
  const { user } = useAuth();
  const [result, setResult]         = useState(null);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState('');
  const [imgContent, setImgContent] = useState('');
  const [imgLoading, setImgLoading] = useState(false);
  const [imgError, setImgError]     = useState('');
  const [pdfLoading, setPdfLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  
  const [showSendModal, setShowSendModal] = useState(false);
  const [developers, setDevelopers] = useState([]);
  const [selectedDevId, setSelectedDevId] = useState('');
  const [sendNote, setSendNote] = useState('');
  const [sendLoading, setSendLoading] = useState(false);
  const [sendSuccess, setSendSuccess] = useState(false);
  
  const cardRef = useRef(null);

  const handleGenerate = async () => {
    setLoading(true); setError(''); setResult(null); setImgContent('');
    try {
      const res = await generateReport();
      setResult(res.data.data);
    } catch (e) {
      setError(e.response?.data?.error || e.message || 'Failed to generate report.');
    } finally { setLoading(false); }
  };

  const handleExcelExport = () => {
    exportToExcel([
      { sheetName: 'Summary', rows: [{ 'Quality Score': result.quality_score ?? 0, 'Executive Summary': result.executive_summary || '', 'Test Coverage Analysis': result.test_coverage_analysis || '', 'Bug Summary': result.bug_summary || '' }] },
      { sheetName: 'Recommendations', rows: (result.recommendations || []).map((r, i) => ({ '#': i + 1, Recommendation: r })) },
      { sheetName: 'Stats', rows: [{ 'Total Test Cases': result.stats?.total_testcases ?? 0, 'Total Code Reviews': result.stats?.total_code_reviews ?? 0, 'Total Website Tests': result.stats?.total_website_tests ?? 0, 'Avg Test Case Score': result.stats?.avg_testcase_score ?? 0, 'Avg Code Score': result.stats?.avg_code_score ?? 0 }] }
    ], 'autoqa-smart-report.xlsx');
  };

  const handlePdfExport = () => {
    setPdfLoading(true);
    try { exportReportPDF(result, user); }
    catch (e) { setError('PDF export failed: ' + e.message); }
    finally { setPdfLoading(false); }
  };

  const openSendModal = async () => {
    setShowSendModal(true);
    setSendSuccess(false);
    if (developers.length === 0) {
      try {
        const res = await getTeamUsers();
        setDevelopers(res.data.users || []);
      } catch (e) { setError('Failed to load developers.'); }
    }
  };

  const handleSendToDeveloper = async () => {
    if (!selectedDevId) return;
    setSendLoading(true);
    try {
      const summary = `
🚀 *QA SMART REPORT* - ${new Date().toLocaleDateString()}
-----------------------------------
📊 *OVERALL QUALITY SCORE: ${result.quality_score}/100*

📈 *ACTIVITY SUMMARY:*
• Test Cases: ${result.stats?.total_testcases || 0}
• Code Reviews: ${result.stats?.total_code_reviews || 0}
• Website Tests: ${result.stats?.total_website_tests || 0}
• Avg TC Score: ${result.stats?.avg_testcase_score || 0}
• Avg Code Score: ${result.stats?.avg_code_score || 0}

📝 *EXECUTIVE SUMMARY:*
${result.executive_summary || 'No summary available.'}

💡 *TOP RECOMMENDATIONS:*
${(result.recommendations || []).slice(0, 3).map((r, i) => `${i + 1}. ${r}`).join('\n')}

${sendNote ? `💬 *QA NOTE:* ${sendNote}` : ''}
-----------------------------------
_Sent via AutoQA AI Report Sharing_
      `.trim();

      await sendMessage({
        receiver_id: parseInt(selectedDevId),
        subject: `QA Smart Report - ${user?.username}`,
        body: summary
      });
      setSendSuccess(true);
      setTimeout(() => setShowSendModal(false), 2000);
    } catch (e) {
      setError('Failed to send report: ' + e.message);
    } finally {
      setSendLoading(false);
    }
  };

  // Step 1: Get AI content from Gemini, Step 2: Screenshot the rendered card
  const handleGenerateImage = async () => {
    setImgLoading(true); setImgError(''); setImgContent('');
    try {
      const res = await generateReportImage(result);
      setImgContent(res.data.content);
    } catch (e) {
      setImgError(e.response?.data?.error || 'Failed to generate report image.');
    } finally { setImgLoading(false); }
  };

  // Download the rendered card as PNG
  const handleDownloadImage = async () => {
    if (!cardRef.current) return;
    setDownloading(true);
    try {
      const canvas = await html2canvas(cardRef.current, {
        scale: 2,
        useCORS: true,
        backgroundColor: null,
        logging: false,
      });
      const link = document.createElement('a');
      link.download = 'autoqa-report.png';
      link.href = canvas.toDataURL('image/png');
      link.click();
    } catch (e) {
      setImgError('Image download failed: ' + e.message);
    } finally { setDownloading(false); }
  };

  const hasResult  = result !== null;
  const score      = hasResult ? (result.quality_score ?? 0) : 0;
  const scoreColor = score >= 80 ? 'text-emerald-600' : score >= 50 ? 'text-amber-600' : 'text-red-600';
  const barColor   = score >= 80 ? 'bg-emerald-500'   : score >= 50 ? 'bg-amber-500'   : 'bg-red-500';
  const hasActivity = hasResult && ((result.stats?.total_testcases || 0) + (result.stats?.total_code_reviews || 0) + (result.stats?.total_website_tests || 0)) > 0;

  const chartData = hasResult ? {
    labels: ['Test Cases', 'Code Reviews', 'Website Tests'],
    datasets: [{ data: [result.stats?.total_testcases || 0, result.stats?.total_code_reviews || 0, result.stats?.total_website_tests || 0], backgroundColor: ['#3b82f6', '#8b5cf6', '#06b6d4'], borderWidth: 0 }]
  } : null;

  return (
    <div className="p-4 sm:p-6 lg:p-8 w-full">
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-slate-800 mb-1">Smart Report</h2>
        <p className="text-slate-500 text-sm">Generate a comprehensive QA report with PDF export and AI-powered image card.</p>
      </div>

      {/* Actions */}
      <div className="flex flex-wrap gap-3 mb-6">
        <button onClick={handleGenerate} disabled={loading}
          className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white rounded-lg text-sm font-medium transition-colors">
          <MdOutlineRefresh className={`text-base ${loading ? 'animate-spin' : ''}`} />
          Generate Report
        </button>
        {hasResult && (
          <>
            <button onClick={handlePdfExport} disabled={pdfLoading}
              className="flex items-center gap-2 px-5 py-2.5 bg-red-600 hover:bg-red-700 disabled:opacity-40 text-white rounded-lg text-sm font-medium transition-colors">
              <MdOutlinePictureAsPdf className="text-base" />
              {pdfLoading ? 'Generating...' : 'Download PDF'}
            </button>
            <button onClick={handleExcelExport}
              className="flex items-center gap-2 px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-medium transition-colors">
              <MdOutlineTableChart className="text-base" /> Export Excel
            </button>
            <button onClick={handleGenerateImage} disabled={imgLoading}
              className="flex items-center gap-2 px-5 py-2.5 bg-violet-600 hover:bg-violet-700 disabled:opacity-40 text-white rounded-lg text-sm font-medium transition-colors">
              <RiRobot2Line className="text-base" />
              {imgLoading ? 'Generating...' : 'Generate Image'}
            </button>
            <button onClick={openSendModal}
              className="flex items-center gap-2 px-5 py-2.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-sm font-medium transition-colors">
              <MdSend className="text-base" />
              Send to Developer
            </button>
          </>
        )}
      </div>

      <ErrorAlert message={error} onClose={() => setError('')} />
      {loading && <Loader message="Generating your report..." />}

      {hasResult && (
        <div className="space-y-4">
          {!hasActivity && (
            <div className="flex items-start gap-3 bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-700">
              <MdOutlineInfo className="text-amber-500 text-lg shrink-0 mt-0.5" />
              No activity recorded yet. Use Test Case Review, Code Review, or Website Testing first.
            </div>
          )}

          {/* Score + Stats */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Overall Quality Score</p>
              <p className={`text-6xl font-bold ${scoreColor}`}>{score}</p>
              <p className="text-slate-400 text-sm mt-1">out of 100</p>
              <div className="mt-4 h-2.5 bg-slate-100 rounded-full overflow-hidden">
                <div className={`h-full rounded-full transition-all duration-700 ${barColor}`} style={{ width: `${score}%` }} />
              </div>
              <div className="mt-3">
                {score >= 80
                  ? <span className="text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 px-2.5 py-1 rounded-full font-medium">Excellent Quality</span>
                  : score >= 50
                  ? <span className="text-xs bg-amber-50 text-amber-700 border border-amber-200 px-2.5 py-1 rounded-full font-medium">Needs Improvement</span>
                  : <span className="text-xs bg-red-50 text-red-700 border border-red-200 px-2.5 py-1 rounded-full font-medium">Critical Issues</span>
                }
              </div>
            </div>
            <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm grid grid-cols-2 gap-3">
              {[
                { label: 'Test Cases',     value: result.stats?.total_testcases    ?? 0, color: 'text-blue-600' },
                { label: 'Code Reviews',   value: result.stats?.total_code_reviews ?? 0, color: 'text-violet-600' },
                { label: 'Avg TC Score',   value: result.stats?.avg_testcase_score ?? 0, color: 'text-cyan-600' },
                { label: 'Avg Code Score', value: result.stats?.avg_code_score     ?? 0, color: 'text-emerald-600' },
              ].map(({ label, value, color }) => (
                <div key={label} className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-center">
                  <p className={`text-xl font-bold ${color}`}>{value}</p>
                  <p className="text-xs text-slate-500 mt-0.5">{label}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Chart */}
          {chartData && (
            <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm flex flex-col sm:flex-row items-center gap-6">
              <div className="w-36 h-36 shrink-0">
                <Doughnut data={chartData} options={{ plugins: { legend: { display: false } }, cutout: '72%' }} />
              </div>
              <div className="space-y-3 flex-1 w-full">
                {chartData.labels.map((label, i) => (
                  <div key={label} className="flex items-center gap-3">
                    <span className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: chartData.datasets[0].backgroundColor[i] }} />
                    <span className="text-sm text-slate-600 flex-1">{label}</span>
                    <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                      <div className="h-full rounded-full" style={{ backgroundColor: chartData.datasets[0].backgroundColor[i], width: `${Math.min(100, (chartData.datasets[0].data[i] / Math.max(1, Math.max(...chartData.datasets[0].data))) * 100)}%` }} />
                    </div>
                    <span className="text-sm font-semibold text-slate-800 w-6 text-right">{chartData.datasets[0].data[i]}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Text sections */}
          {[
            { title: 'Executive Summary',     content: result.executive_summary },
            { title: 'Test Coverage Analysis', content: result.test_coverage_analysis },
            { title: 'Bug Summary',            content: result.bug_summary },
          ].map(({ title, content }) => (
            <div key={title} className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">{title}</p>
              <p className="text-sm text-slate-600 leading-relaxed">{content || '—'}</p>
            </div>
          ))}

          {result.recommendations?.length > 0 && (
            <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
              <div className="flex items-center gap-2 mb-3">
                <MdOutlineLightbulb className="text-amber-500 text-lg" />
                <p className="text-sm font-semibold text-slate-700">Recommendations</p>
              </div>
              <ul className="space-y-2">
                {result.recommendations.map((r, i) => (
                  <li key={i} className="flex gap-3 text-sm text-slate-600 items-start">
                    <span className="text-blue-500 font-semibold shrink-0">{i + 1}.</span>
                    <span>{typeof r === 'string' ? r : JSON.stringify(r)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* AI Image Card */}
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-slate-100">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 bg-gradient-to-br from-violet-600 to-blue-600 rounded-lg flex items-center justify-center">
                  <MdOutlineImage className="text-white text-base" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-800">AI Report Image</p>
                  <p className="text-xs text-slate-500">Gemini AI generates content · html2canvas renders PNG</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {imgContent && (
                  <button onClick={handleDownloadImage} disabled={downloading}
                    className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white text-xs font-semibold rounded-lg transition-colors">
                    <MdFileDownload className="text-base" />
                    {downloading ? 'Saving...' : 'Download PNG'}
                  </button>
                )}
                <button onClick={handleGenerateImage} disabled={imgLoading}
                  className="flex items-center gap-1.5 px-4 py-2 bg-gradient-to-r from-violet-600 to-blue-600 hover:from-violet-700 hover:to-blue-700 disabled:opacity-40 text-white text-xs font-semibold rounded-lg transition-all">
                  <RiRobot2Line className="text-base" />
                  {imgLoading ? 'Generating...' : imgContent ? 'Regenerate' : 'Generate Image'}
                </button>
              </div>
            </div>

            {imgLoading && (
              <div className="flex flex-col items-center justify-center py-14 gap-3 bg-slate-50">
                <div className="w-10 h-10 rounded-full border-[3px] border-violet-200 border-t-violet-600 animate-spin" />
                <p className="text-slate-500 text-sm animate-pulse">Gemini AI is writing your report card...</p>
              </div>
            )}

            {imgError && <div className="p-5"><ErrorAlert message={imgError} onClose={() => setImgError('')} /></div>}

            {imgContent && !imgLoading && (
              <div className="p-4 bg-slate-100 overflow-auto">
                {/* This div is captured as PNG */}
                <div ref={cardRef} className="inline-block">
                  <ReportImageCard content={imgContent} result={result} user={user} />
                </div>
              </div>
            )}

            {!imgContent && !imgLoading && !imgError && (
              <div className="flex flex-col items-center justify-center py-14 gap-3 bg-slate-50 text-center px-6">
                <div className="w-14 h-14 bg-violet-100 rounded-2xl flex items-center justify-center">
                  <MdOutlineImage className="text-violet-500 text-3xl" />
                </div>
                <p className="text-slate-600 text-sm font-medium">Generate a Report Image Card</p>
                <p className="text-slate-400 text-xs max-w-xs">Gemini AI writes the content, then it's rendered as a beautiful dark-themed PNG you can download and share.</p>
              </div>
            )}
          </div>

        </div>
      )}

      {/* Send to Developer Modal */}
      {showSendModal && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in duration-200">
            <div className="bg-gradient-to-r from-amber-500 to-orange-600 px-6 py-4 flex items-center justify-between">
              <h3 className="text-white font-bold flex items-center gap-2">
                <MdSend /> Send Report to Developer
              </h3>
              <button onClick={() => setShowSendModal(false)} className="text-white/80 hover:text-white transition-colors">
                <MdOutlineClose className="text-xl" />
              </button>
            </div>
            
            <div className="p-6 space-y-4">
              {sendSuccess ? (
                <div className="py-8 text-center space-y-3">
                  <div className="w-16 h-16 bg-emerald-100 text-emerald-600 rounded-full flex items-center justify-center mx-auto mb-4">
                    <MdSend className="text-3xl" />
                  </div>
                  <p className="text-slate-800 font-bold text-lg">Report Sent Successfully!</p>
                  <p className="text-slate-500 text-sm">The developer will receive it in their inbox.</p>
                </div>
              ) : (
                <>
                  <div>
                    <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1.5">Select Developer</label>
                    <select
                      value={selectedDevId}
                      onChange={(e) => setSelectedDevId(e.target.value)}
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-all"
                    >
                      <option value="">— Select a Developer —</option>
                      {developers.map(dev => (
                        <option key={dev.id} value={dev.id}>{dev.username} ({dev.email})</option>
                      ))}
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1.5">Add a Note (Optional)</label>
                    <textarea
                      value={sendNote}
                      onChange={(e) => setSendNote(e.target.value)}
                      placeholder="e.g., Please review the quality score and bug summary..."
                      rows={3}
                      className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500 transition-all resize-none"
                    />
                  </div>
                  
                  <div className="pt-2">
                    <button
                      onClick={handleSendToDeveloper}
                      disabled={sendLoading || !selectedDevId}
                      className="w-full bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white font-bold py-3 rounded-xl transition-all shadow-lg shadow-amber-200 flex items-center justify-center gap-2"
                    >
                      {sendLoading ? (
                        <>
                          <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                          Sending...
                        </>
                      ) : (
                        <>
                          <MdSend /> Confirm & Send Report
                        </>
                      )}
                    </button>
                    <p className="text-[10px] text-slate-400 text-center mt-3">
                      This will send the executive summary, stats, and recommendations as a message.
                    </p>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
