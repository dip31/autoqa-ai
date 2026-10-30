import React, { useState, useEffect, useRef } from 'react';
import {
  MdOutlineSecurity, MdOutlinePlayCircle, MdOutlineHistory,
  MdCheckCircle, MdError, MdInfo, MdOutlineShield,
  MdOutlineAnalytics, MdOutlineRule, MdOutlineLanguage,
  MdOutlineAssessment, MdOutlineFactCheck, MdOutlineDownload,
  MdOutlineKey, MdOutlineCheckCircle, MdOutlineWarning
} from 'react-icons/md';
import { RiLoader4Line, RiHistoryLine, RiShieldFlashLine, RiMagicLine, RiSendPlaneFill, RiCloseLine, RiArrowRightLine, RiFileTextLine, RiLockLine } from 'react-icons/ri';
import { createSecurityRun, getSecurityRuns, getSecurityRunDetail, startSecurityRun, cancelSecurityRun, getSecurityRunFindings, getFindingEvidence, generateSecurityReport, getSecurityProfiles, createAuthorization, verifyAuthorization, getAuthorizations } from '../api/client';
import Loader from '../components/Loader';
import ScoreBadge from '../components/ScoreBadge';

export default function Security() {
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState([]);
  const [activeRunId, setActiveRunId] = useState(null);
  const [runDetails, setRunDetails] = useState(null);
  const [findings, setFindings] = useState([]);
  const [activeTab, setActiveTab] = useState('Overview');
  const [selectedFinding, setSelectedFinding] = useState(null);
  const [evidence, setEvidence] = useState([]);
  const [report, setReport] = useState(null);
  const [reportLoading, setReportLoading] = useState(false);
  // Authorization flow state
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [authCreating, setAuthCreating] = useState(false);
  const [authVerifying, setAuthVerifying] = useState(false);
  const [authData, setAuthData] = useState(null); // {authorization_id, hostname, challenge_token, challenge_url, expires_at}
  const [authError, setAuthError] = useState(null);
  const [authSuccess, setAuthSuccess] = useState(false);

  const pollingRef = useRef(null);

  useEffect(() => {
    fetchHistory();
    return () => stopPolling();
  }, []);

  const fetchHistory = async () => {
    try {
      const res = await getSecurityRuns();
      setHistory(res.data.runs);
    } catch (err) {
      console.error(err);
    }
  };

  const startPolling = (id) => {
    stopPolling();
    let consecutiveErrors = 0;
    const MAX_ERRORS = 3;

    pollingRef.current = setInterval(async () => {
      try {
        const res = await getSecurityRunDetail(id);
        consecutiveErrors = 0;
        const data = res.data;
        setRunDetails(data);
        if (['Completed', 'Failed', 'Cancelled'].includes(data.run.status)) {
          stopPolling();
          fetchHistory();
        }
      } catch (err) {
        consecutiveErrors++;
        console.warn(`[Polling] Network error ${consecutiveErrors}/${MAX_ERRORS}:`, err.message);
        if (consecutiveErrors >= MAX_ERRORS) {
          console.error('[Polling] Max consecutive errors reached. Stopping.');
          stopPolling();
        }
      }
    }, 2500);
  };

  const stopPolling = () => {
    if (pollingRef.current) clearInterval(pollingRef.current);
  };

  const handleRun = async (e) => {
    e.preventDefault();
    if (!formData.target_url) {
      alert("Please provide a target URL");
      return;
    }
    setLoading(true);
    setRunDetails(null);
    try {
      const payload = { 
        ...formData, 
        execution_mode: "Security Validation",
      };
      const res = await createSecurityRun(payload);
      setActiveRunId(res.data.run_id);
      setActiveTab('Overview');
      startPolling(res.data.run_id);
    } catch (err) {
      const errorData = err.response?.data;
      if (errorData?.reason_code === 'REQUIRES_AUTHORIZATION') {
        // Open authorization modal with details from backend
        setAuthData({
          hostname: errorData.hostname,
          challenge_path: errorData.challenge_path,
        });
        setAuthModalOpen(true);
        setAuthError(null);
        setAuthSuccess(false);
      } else {
        alert(errorData?.error || "Execution failed");
      }
    } finally {
      setLoading(false);
    }
  };

  const selectRun = (id) => {
    setActiveRunId(id);
    setActiveTab('Overview');
    stopPolling();
    getSecurityRunDetail(id).then(res => {
      setRunDetails(res.data);
      if (!['Completed', 'Failed', 'Cancelled'].includes(res.data.run.status)) {
        startPolling(id);
      }
    });
  };

  const handleStartRun = async (id) => {
    try {
      const res = await startSecurityRun(id);
      if (res.data?.status === 'Running') {
        setRunDetails(prev => prev ? {
          ...prev,
          run: { ...prev.run, status: 'Running', started_at: prev.run.started_at || new Date().toISOString() }
        } : prev);
      }
      startPolling(id);
    } catch (err) {
      const message = err.response?.data?.error || "Failed to start run";
      alert(message);
    }
  };

  const handleConfirmRun = async (id) => {
    if (!window.confirm("This will start an active security assessment. Ensure you have explicit authorization for the target. Continue?")) return;
    try {
      const token = prompt("Enter the confirmation token sent to you:");
      if (!token) return;
      const res = await fetch(`/api/security/run/${id}/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmation_token: token }),
        credentials: 'include'
      });
      const data = await res.json();
      if (!res.ok) {
        alert(data.error || "Confirmation failed");
        return;
      }
      // Refresh run details
      const res2 = await getSecurityRunDetail(id);
      setRunDetails(res2.data);
      if (res2.data.run.status === 'Authorized') {
        // Auto-start the assessment
        await handleStartRun(id);
      }
    } catch (err) {
      alert(err.response?.data?.error || "Confirmation failed");
    }
  };

  const handleCancelRun = async (id) => {
    if (!window.confirm("Are you sure you want to cancel this security assessment?")) return;
    try {
      await cancelSecurityRun(id);
      stopPolling();
      fetchHistory();
    } catch (err) {
      alert(err.response?.data?.error || "Failed to cancel run");
    }
  };

  const handleCreateAuthorization = async () => {
    if (!authData?.hostname) return;
    setAuthCreating(true);
    setAuthError(null);
    try {
      const res = await createAuthorization({
        hostname: authData.hostname,
        scheme: 'https',
        path_prefix: '/',
        allow_subdomains: false,
      });
      const auth = res.data;
      setAuthData(prev => ({
        ...prev,
        authorization_id: auth.authorization_id,
        challenge_token: auth.challenge_token,
        challenge_url: auth.challenge_url,
        expires_at: auth.expires_at,
      }));
      setAuthSuccess(true);
    } catch (err) {
      setAuthError(err.response?.data?.error || "Failed to create authorization");
    } finally {
      setAuthCreating(false);
    }
  };

  const handleVerifyAuthorization = async () => {
    if (!authData?.authorization_id) return;
    setAuthVerifying(true);
    setAuthError(null);
    try {
      await verifyAuthorization({ authorization_id: authData.authorization_id });
      setAuthSuccess(true);
      // After verification, close modal and retry run creation
      setAuthModalOpen(false);
      // Retry creating the run
      const payload = { ...formData, execution_mode: "Security Validation" };
      const res = await createSecurityRun(payload);
      setActiveRunId(res.data.run_id);
      setActiveTab('Overview');
      startPolling(res.data.run_id);
    } catch (err) {
      setAuthError(err.response?.data?.error || "Verification failed");
    } finally {
      setAuthVerifying(false);
    }
  };

  const handleGenerateReport = async (id) => {
    setReportLoading(true);
    setReport(null);
    try {
      const res = await generateSecurityReport(id);
      setReport(res.data.report);
    } catch (err) {
      alert(err.response?.data?.error || "Failed to generate report");
    } finally {
      setReportLoading(false);
    }
  };

  const loadFindings = async (runId) => {
    try {
      const res = await getSecurityRunFindings(runId);
      setFindings(res.data.findings);
      setActiveTab('Findings');
    } catch (err) {
      console.error(err);
    }
  };

  const loadEvidence = async (findingId) => {
    try {
      const res = await getFindingEvidence(findingId);
      setEvidence(res.data.evidence);
      setSelectedFinding(findingId);
    } catch (err) {
      console.error(err);
    }
  };

  const renderStatusBadge = (status) => {
    const colors = {
      'Authorized': 'bg-blue-100 text-blue-700',
      'Pending': 'bg-yellow-100 text-yellow-700',
      'Running': 'bg-cyan-100 text-cyan-700',
      'Completed': 'bg-green-100 text-green-700',
      'Failed': 'bg-red-100 text-red-700',
      'Cancelled': 'bg-slate-100 text-slate-700'
    };
    return (
      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${colors[status] || 'bg-slate-100'}`}>
        {status}
      </span>
    );
  };

  const getSeverityColor = (severity) => {
    const colors = {
      'Critical': 'bg-red-100 text-red-700 border-red-200',
      'High': 'bg-orange-100 text-orange-700 border-orange-200',
      'Medium': 'bg-yellow-100 text-yellow-700 border-yellow-200',
      'Low': 'bg-blue-100 text-blue-700 border-blue-200',
      'Informational': 'bg-slate-100 text-slate-700 border-slate-200'
    };
    return colors[severity] || 'bg-slate-100 text-slate-700';
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleString();
  };

  const formatDuration = (seconds) => {
    if (!seconds || seconds < 1) return 'N/A';
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m ${Math.round(seconds % 60)}s`;
    return `${Math.floor(seconds / 3600)}h ${Math.round((seconds % 3600) / 60)}m`;
  };

  const [formData, setFormData] = useState({
    target_url: '',
    title: 'Security Validation Run',
    mode: 'passive', // 'passive' or 'active'
    profile: 'passive_only', // 'passive_only', 'safe_active', 'custom'
    dry_run: false,
    confirmed: false
  });

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-[1600px] mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
            <MdOutlineSecurity className="text-emerald-600" />
            Security Validation
          </h1>
          <p className="text-slate-500 text-sm mt-1">Passive security assessment with passive validators and scope-enforced browser execution.</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => { setActiveRunId(null); setRunDetails(null); }} className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-sm font-semibold transition-colors">
            New Assessment
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Input & History */}
        <div className="lg:col-span-4 space-y-6">
          <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
            <h2 className="text-sm font-bold text-slate-800 mb-4 flex items-center gap-2">
              <MdOutlinePlayCircle className="text-emerald-600" /> Start Security Assessment
            </h2>
            <form onSubmit={handleRun} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase mb-1.5 ml-1">Target URL</label>
                <input 
                  required
                  type="url"
                  placeholder="https://example.com"
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/20 transition-all"
                  value={formData.target_url}
                  onChange={e => setFormData({...formData, target_url: e.target.value})}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase mb-1.5 ml-1">Assessment Title</label>
                <input 
                  placeholder="e.g. Production Security Review"
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm"
                  value={formData.title}
                  onChange={e => setFormData({...formData, title: e.target.value})}
                />
              </div>

              {/* Mode Selection */}
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase mb-1.5 ml-1">Assessment Mode</label>
                <div className="grid grid-cols-3 gap-3">
                  <label className={`relative cursor-pointer ${formData.mode === 'passive' ? 'bg-emerald-50 border-emerald-200' : 'bg-slate-50 border-slate-200'} border rounded-xl p-3 transition-all`}>
                    <input
                      type="radio"
                      name="mode"
                      value="passive"
                      checked={formData.mode === 'passive'}
                      onChange={e => setFormData({...formData, mode: e.target.value, profile: 'passive_only'})}
                      className="sr-only"
                    />
                    <div className="flex items-center gap-2">
                      <MdOutlineFactCheck className="text-emerald-600" />
                      <div>
                        <p className="font-medium text-slate-800">Passive</p>
                        <p className="text-xs text-slate-500">Passive analysis only (headers, cookies, TLS)</p>
                      </div>
                    </div>
                  </label>
                  <label className={`relative cursor-pointer ${formData.mode === 'active' ? 'bg-emerald-50 border-emerald-200' : 'bg-slate-50 border-slate-200'} border rounded-xl p-3 transition-all`}>
                    <input
                      type="radio"
                      name="mode"
                      value="active"
                      checked={formData.mode === 'active'}
                      onChange={e => setFormData({...formData, mode: e.target.value, profile: 'safe_active', confirmed: false})}
                      className="sr-only"
                    />
                    <div className="flex items-center gap-2">
                      <MdOutlineShield className="text-emerald-600" />
                      <div>
                        <p className="font-medium text-slate-800">Active</p>
                        <p className="text-xs text-slate-500">Safe active checks (requires authorization)</p>
                      </div>
                    </div>
                  </label>
                  <label className={`relative cursor-pointer ${formData.mode === 'zap' ? 'bg-emerald-50 border-emerald-200' : 'bg-slate-50 border-slate-200'} border rounded-xl p-3 transition-all`}>
                    <input
                      type="radio"
                      name="mode"
                      value="zap"
                      checked={formData.mode === 'zap'}
                      onChange={e => setFormData({...formData, mode: e.target.value, profile: 'zap_baseline'})}
                      className="sr-only"
                    />
                    <div className="flex items-center gap-2">
                      <MdOutlineAnalytics className="text-emerald-600" />
                      <div>
                        <p className="font-medium text-slate-800">ZAP Baseline</p>
                        <p className="text-xs text-slate-500">OWASP ZAP passive baseline scan</p>
                      </div>
                    </div>
                  </label>
                </div>
              </div>

              {/* Profile Selection (only for active mode) */}
              {formData.mode === 'active' && (
                <div>
                  <label className="block text-xs font-semibold text-slate-500 uppercase mb-1.5 ml-1">Testing Profile</label>
                  <select
                    value={formData.profile}
                    onChange={e => setFormData({...formData, profile: e.target.value})}
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/20 transition-all"
                  >
                    <option value="safe_active">Safe Active - Non-destructive checks only</option>
                    <option value="custom">Custom (requires admin approval)</option>
                  </select>
                </div>
              )}

              {/* Dry-run option */}
              {formData.mode === 'active' && (
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="dry_run"
                    checked={formData.dry_run}
                    onChange={e => setFormData({...formData, dry_run: e.target.checked, confirmed: false})}
                    className="w-4 h-4 text-emerald-600 border-slate-300 rounded focus:ring-emerald-500"
                  />
                  <label htmlFor="dry_run" className="text-sm text-slate-700 cursor-pointer">
                    Dry-run mode (generate execution plan without running active checks)
                  </label>
                </div>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase mb-1.5 ml-1">Assessment Title</label>
                <input 
                  placeholder="e.g. Production Security Review"
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm"
                  value={formData.title}
                  onChange={e => setFormData({...formData, title: e.target.value})}
                />
              </div>

              <button
                disabled={loading || (formData.mode === 'active' && !formData.dry_run && !formData.confirmed)}
                className={`w-full font-bold py-3 rounded-xl transition-all shadow-lg flex items-center justify-center gap-2 mt-2 disabled:opacity-50 ${formData.mode === 'active' ? 'bg-emerald-600 hover:bg-emerald-700' : 'bg-emerald-600 hover:bg-emerald-700'} text-white`}
              >
                {loading ? <RiLoader4Line className="animate-spin text-xl" /> : <RiMagicLine className="text-xl" />}
                {loading ? 'Starting Assessment...' : formData.dry_run ? 'Generate Dry-run Plan' : (formData.mode === 'active' ? 'Run Active Assessment' : 'Run Security Assessment')}
              </button>
            </form>
          </div>

          {/* History */}
          <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
            <h2 className="text-sm font-bold text-slate-800 mb-4 flex items-center gap-2">
              <MdOutlineHistory className="text-emerald-600" /> Recent Assessments
            </h2>
            {history.length === 0 ? (
              <p className="text-slate-500 text-sm text-center py-8">No security assessments yet</p>
            ) : (
              <div className="space-y-3 max-h-[400px] overflow-y-auto">
                {history.map(run => (
                  <button
                    key={run.id}
                    onClick={() => selectRun(run.id)}
                    className={`w-full text-left p-4 rounded-xl border transition-all ${activeRunId === run.id ? 'bg-emerald-50 border-emerald-200' : 'bg-slate-50 border-slate-200 hover:bg-slate-100'}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-slate-800 truncate">{run.title}</span>
                      {renderStatusBadge(run.status)}
                    </div>
                    <div className="text-xs text-slate-500 mt-1 flex items-center gap-3">
                      <span>{formatDate(run.created_at)}</span>
                      <span>{run.module_name || 'Security'}</span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right: Run Details */}
        <div className="lg:col-span-8 space-y-6">
          {!runDetails ? (
            <div className="bg-white border border-slate-200 rounded-2xl p-12 text-center">
              <MdOutlineShield className="text-slate-300 text-6xl mb-4" />
              <h3 className="text-lg font-semibold text-slate-600">Select an assessment</h3>
              <p className="text-slate-500 mt-1">Choose from history or start a new security assessment</p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Run Header */}
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div>
                    <h2 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                      <MdOutlineShield className="text-emerald-600" />
                      {runDetails.run.title}
                    </h2>
                    <div className="flex items-center gap-3 mt-2 flex-wrap">
                      {renderStatusBadge(runDetails.run.status)}
                      <span className="text-sm text-slate-500">{runDetails.run.execution_mode || 'Security Validation'}</span>
                      <span className="text-sm text-slate-500">Target: {runDetails.run.url}</span>
{runDetails.run.mode === 'active' && (
                        <React.Fragment>
                          <span className="px-2 py-1 bg-emerald-100 text-emerald-700 rounded-full text-xs font-medium">Active Mode</span>
                          <span className="px-2 py-1 bg-blue-100 text-blue-700 rounded-full text-xs font-medium">{runDetails.run.profile}</span>
                          {runDetails.run.dry_run && (
                            <span className="px-2 py-1 bg-violet-100 text-violet-700 rounded-full text-xs font-medium">Dry-run</span>
                          )}
                        </React.Fragment>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {runDetails.run.status === 'Running' && (
                      <button onClick={() => handleCancelRun(runDetails.run.id)} className="px-4 py-2 bg-red-100 hover:bg-red-200 text-red-700 rounded-xl text-sm font-semibold transition-colors flex items-center gap-2">
                        <RiCloseLine className="text-xl" />
                        Cancel
                      </button>
                    )}
                    {runDetails.run.status === 'AwaitingConfirmation' && (
                      <button onClick={() => handleConfirmRun(runDetails.run.id)} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-sm font-semibold transition-colors flex items-center gap-2">
                        <RiLockLine className="text-xl" />
                        Confirm & Start Active Assessment
                      </button>
                    )}
                    {runDetails.run.status === 'Authorized' && (
                      <button onClick={() => handleStartRun(runDetails.run.id)} className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl text-sm font-semibold transition-colors flex items-center gap-2">
                        <RiMagicLine className="text-xl" />
                        Start Assessment
                      </button>
                    )}
                    {runDetails.run.status === 'Completed' && (
                      <button onClick={() => loadFindings(runDetails.run.id)} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-sm font-semibold transition-colors flex items-center gap-2">
                        <RiFileTextLine className="text-xl" />
                        View Findings
                      </button>
                    )}
                    {runDetails.run.status === 'Completed' && (
                      <button 
                        onClick={() => handleGenerateReport(runDetails.run.id)} 
                        disabled={reportLoading}
                        className="px-4 py-2 bg-violet-600 hover:bg-violet-700 text-white rounded-xl text-sm font-semibold transition-colors flex items-center gap-2 disabled:opacity-50"
                      >
                        {reportLoading ? <RiLoader4Line className="animate-spin text-xl" /> : <RiFileTextLine className="text-xl" />}
                        {reportLoading ? 'Generating...' : 'Generate Report'}
                      </button>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6 pt-6 border-t border-slate-200">
                  <div>
                    <p className="text-xs font-semibold text-slate-500 uppercase">Started</p>
                    <p className="text-sm font-medium text-slate-800">{formatDate(runDetails.run.started_at)}</p>
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-slate-500 uppercase">Completed</p>
                    <p className="text-sm font-medium text-slate-800">{formatDate(runDetails.run.completed_at)}</p>
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-slate-500 uppercase">Duration</p>
                    <p className="text-sm font-medium text-slate-800">{formatDuration(runDetails.run.duration_seconds)}</p>
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-slate-500 uppercase">Findings</p>
                    <p className="text-sm font-medium text-slate-800">{runDetails.run.findings_count || 0}</p>
                  </div>
                </div>
              </div>

              {/* Tabs */}
              <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
                <div className="border-b border-slate-200">
                  <nav className="flex gap-1 p-1" aria-label="Tabs">
                    <button onClick={() => setActiveTab('Overview')} className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${activeTab === 'Overview' ? 'bg-emerald-100 text-emerald-700' : 'text-slate-600 hover:bg-slate-100'}`}>
                      Overview
                    </button>
                    <button onClick={() => { setActiveTab('Findings'); loadFindings(runDetails.run.id); }} className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${activeTab === 'Findings' ? 'bg-emerald-100 text-emerald-700' : 'text-slate-600 hover:bg-slate-100'}`}>
                      Findings ({findings.length})
                    </button>
                    <button onClick={() => setActiveTab('Evidence')} className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${activeTab === 'Evidence' ? 'bg-emerald-100 text-emerald-700' : 'text-slate-600 hover:bg-slate-100'}`}>
                      Evidence
                    </button>
                  </nav>
                </div>

                <div className="p-6">
                  {activeTab === 'Overview' && (
                    <div className="space-y-6">
                      <div className="bg-slate-50 rounded-xl p-4">
                        <h3 className="text-sm font-semibold text-slate-800 mb-2">Scope</h3>
                        <dl className="grid grid-cols-2 gap-2 text-sm">
                          <dt className="text-slate-500">Scheme</dt>
                          <dd className="font-medium text-slate-800">{runDetails.scope?.scheme || 'https'}</dd>
                          <dt className="text-slate-500">Host</dt>
                          <dd className="font-medium text-slate-800">{runDetails.scope?.host || 'N/A'}</dd>
                          <dt className="text-slate-500">Port</dt>
                          <dd className="font-medium text-slate-800">{runDetails.scope?.port || 'Default'}</dd>
                          <dt className="text-slate-500">Normalized Target</dt>
                          <dd className="font-medium text-slate-800 truncate">{runDetails.normalized_target || runDetails.run.url}</dd>
                        </dl>
                      </div>
                      
                      <div className="bg-slate-50 rounded-xl p-4">
                        <h3 className="text-sm font-semibold text-slate-800 mb-2">Validators Executed</h3>
                        <div className="flex flex-wrap gap-2">
                          {['HTTPS Enforcement', 'Security Headers', 'Cookie Security', 'Information Disclosure', 'Redirect Analysis', 'TLS Configuration'].map(v => (
                            <span key={v} className="px-3 py-1 bg-white border border-slate-200 rounded-full text-xs text-slate-600">{v}</span>
                          ))}
                        </div>
                      </div>

                      {runDetails.run.error_summary && (
                        <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700">
                          <h3 className="font-semibold mb-1">Error Summary</h3>
                          <p className="text-sm">{runDetails.run.error_summary}</p>
                        </div>
                      )}

                      {report && (
                        <div className="space-y-6">
                          <div className="bg-violet-50 border border-violet-200 rounded-xl p-4">
                            <h3 className="font-semibold text-violet-800 mb-2 flex items-center gap-2">
                              <RiFileTextLine className="text-xl" />
                              Security Assessment Report
                            </h3>
                            <div className="prose text-sm text-violet-700 max-h-96 overflow-y-auto">
                              <pre className="whitespace-pre-wrap text-sm">{JSON.stringify(report, null, 2)}</pre>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {activeTab === 'Findings' && (
                    <div className="space-y-4">
                      {findings.length === 0 ? (
                        <div className="text-center py-12">
                          <MdOutlineFactCheck className="text-slate-300 text-4xl mb-3" />
                          <h3 className="text-lg font-semibold text-slate-600">No findings</h3>
                          <p className="text-slate-500">No security issues were detected by the validators.</p>
                        </div>
                      ) : (
                        <div className="space-y-3">
                          {findings.map(finding => (
                            <div key={finding.id} className={`bg-white border rounded-xl p-4 ${getSeverityColor(finding.severity)}`}>
                              <div className="flex items-start justify-between gap-4">
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-center gap-2 mb-1">
                                    <h4 className="font-semibold text-slate-800">{finding.title || finding.finding_type}</h4>
                                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${getSeverityColor(finding.severity)}`}>
                                      {finding.severity}
                                    </span>
                                  </div>
                                  <p className="text-sm text-slate-600 mb-2">{finding.description}</p>
                                  <div className="flex flex-wrap gap-2 text-xs text-slate-500">
                                    <span className="px-2 py-0.5 bg-slate-100 rounded">{finding.category}</span>
                                    <span className="px-2 py-0.5 bg-slate-100 rounded">{finding.validator_id}</span>
                                    {finding.affected_url && <span className="px-2 py-0.5 bg-slate-100 rounded truncate max-w-xs">{finding.affected_url}</span>}
                                  </div>
                                </div>
                                <button onClick={() => loadEvidence(finding.id)} className="px-3 py-1.5 bg-white/80 hover:bg-white rounded-lg text-sm font-medium text-emerald-700 border border-emerald-200 transition-colors flex-shrink-0">
                                  View Evidence
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {activeTab === 'Evidence' && (
                    <div className="space-y-4">
                      {selectedFinding ? (
                        <div>
                          <div className="flex items-center justify-between mb-4">
                            <h3 className="font-semibold text-slate-800">Evidence for Finding</h3>
                            <button onClick={() => { setSelectedFinding(null); setEvidence([]); }} className="text-sm text-slate-500 hover:text-slate-700">
                              Back to Findings
                            </button>
                          </div>
                          {evidence.length === 0 ? (
                            <div className="text-center py-8 text-slate-500">No evidence recorded for this finding</div>
                          ) : (
                            <div className="space-y-3">
                              {evidence.map((ev, idx) => (
                                <div key={idx} className="bg-slate-50 border border-slate-200 rounded-xl p-4">
                                  <div className="flex items-center gap-2 mb-2 text-xs">
                                    <span className="px-2 py-0.5 bg-white border border-slate-200 rounded">{ev.evidence_type}</span>
                                    <span className="text-slate-500">{ev.method} {ev.status_code ? `${ev.status_code}` : ''}</span>
                                    <span className="text-slate-500 truncate max-w-md">{ev.url}</span>
                                  </div>
                                  <pre className="bg-white border border-slate-200 rounded-lg p-3 text-xs text-slate-700 overflow-x-auto max-h-64 overflow-y-auto">
                                    {JSON.stringify(ev.data, null, 2)}
                                  </pre>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="text-center py-12">
                          <MdOutlineFactCheck className="text-slate-300 text-4xl mb-3" />
                          <h3 className="text-lg font-semibold text-slate-600">Select a finding</h3>
                          <p className="text-slate-500">Click "View Evidence" on a finding to see supporting evidence.</p>
                        </div>
                      )}
                    </div>
                  )}

                </div>
              </div>
            </div>
          )}
        </div>
      </div>
      {/* Authorization Modal */}
      {authModalOpen && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-md p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                <MdOutlineKey className="text-emerald-600" />
                Target Authorization Required
              </h3>
              <button onClick={() => setAuthModalOpen(false)} className="text-slate-400 hover:text-slate-600">
                <RiCloseLine className="text-xl" />
              </button>
            </div>

            {!authData?.authorization_id ? (
              // Step 1: create authorization
              <div className="space-y-3">
                <p className="text-sm text-slate-600">
                  The hostname <strong>{authData.hostname}</strong> must be verified before a security assessment can run.
                </p>
                <p className="text-xs text-slate-500">
                  We will create a pending authorization and give you a challenge token.
                </p>
                {authError && (
                  <div className="bg-red-50 border border-red-200 text-red-700 text-sm p-3 rounded-lg">
                    {authError}
                  </div>
                )}
                <button
                  disabled={authCreating}
                  onClick={handleCreateAuthorization}
                  className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-2 rounded-xl transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {authCreating ? <RiLoader4Line className="animate-spin" /> : <MdOutlineKey />}
                  {authCreating ? 'Creating Authorization…' : 'Create Authorization'}
                </button>
              </div>
            ) : (
              // Step 2: show challenge and verify
              <div className="space-y-3">
                <p className="text-sm text-slate-600">
                  Authorization created. Publish the challenge file to verify ownership.
                </p>
                <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 space-y-2 text-sm">
                  <div>
                    <span className="font-medium text-slate-700">Challenge URL:</span>
                    <code className="block text-xs text-slate-600 break-all mt-1">{authData.challenge_url}</code>
                  </div>
                  <div>
                    <span className="font-medium text-slate-700">Token (place in file):</span>
                    <code className="block text-xs text-slate-600 break-all mt-1 font-mono">{authData.challenge_token}</code>
                  </div>
                  <div>
                    <span className="font-medium text-slate-700">File path on target:</span>
                    <code className="block text-xs text-slate-600 break-all mt-1">{authData.challenge_path}</code>
                  </div>
                  {authData.expires_at && (
                    <div className="text-xs text-slate-500">
                      Expires: {new Date(authData.expires_at).toLocaleString()}
                    </div>
                  )}
                </div>
                <p className="text-xs text-slate-500">
                  Create a file at <code>/.well-known/autoqa-challenge.txt</code> on <strong>{authData.hostname}</strong> containing exactly the token above.
                </p>
                {authError && (
                  <div className="bg-red-50 border border-red-200 text-red-700 text-sm p-3 rounded-lg">
                    {authError}
                  </div>
                )}
                {authSuccess && !authVerifying && (
                  <div className="bg-emerald-50 border border-emerald-200 text-emerald-700 text-sm p-3 rounded-lg flex items-center gap-2">
                    <MdOutlineCheckCircle />
                    Authorization verified! Starting assessment…
                  </div>
                )}
                <button
                  disabled={authVerifying}
                  onClick={handleVerifyAuthorization}
                  className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 rounded-xl transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
                >
                  {authVerifying ? <RiLoader4Line className="animate-spin" /> : <MdOutlineCheckCircle />}
                  {authVerifying ? 'Verifying…' : 'Verify Ownership'}
                </button>
                <button
                  onClick={() => setAuthModalOpen(false)}
                  className="w-full text-center text-sm text-slate-500 hover:text-slate-700"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
