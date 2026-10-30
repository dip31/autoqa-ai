import React, { useState, useEffect, useRef } from 'react';
import { 
  MdOutlineAutoFixHigh, MdOutlinePlayCircle, MdOutlineHistory,
  MdOutlineRule, MdOutlineFactCheck, MdOutlineLanguage, 
  MdOutlineAnalytics, MdOutlineAssessment, MdArrowForward,
  MdCheckCircle, MdError, MdInfo, MdOutlineHealthAndSafety,
  MdAutoFixNormal, MdSettingsBackupRestore, MdTimeline
} from 'react-icons/md';
import { RiRobot2Line, RiLoader4Line, RiHistoryLine, RiShieldFlashLine, RiMagicLine, RiGithubFill, RiUserLine, RiSendPlaneFill, RiCloseLine } from 'react-icons/ri';
import { runAutonomousQA, runAgentQE, submitAgentQEReview, getAutonomousRuns, getAutonomousRunDetails, getTeamUsers, sendMessage } from '../api/client';
import Loader from '../components/Loader';
import ScoreBadge from '../components/ScoreBadge';

export default function AutonomousQA() {
  const [showShareModal, setShowShareModal] = useState(false);
  const [team, setTeam] = useState([]);
  const [selectedRecipient, setSelectedRecipient] = useState('');
  const [sharing, setSharing] = useState(false);
  const [formData, setFormData] = useState({
    title: '',
    module_name: '',
    requirement_text: '',
    url: '',
    repo_url: '',
    execution_mode: 'Full Autonomous Run'
  });
  const [pipelineMode, setPipelineMode] = useState('standard'); // 'standard' | 'agentqe'

  useEffect(() => {
    if (showShareModal) {
      getTeamUsers().then(res => setTeam(res.data.users || []));
    }
  }, [showShareModal]);

  const handleShare = async () => {
    if (!selectedRecipient) return alert("Select a recipient");
    setSharing(true);
    try {
      const reportText = `
Autonomous QA Report: ${runDetails.run.title}
Module: ${runDetails.run.module_name}
Final Verdict: ${runDetails.report.final_verdict}
Risk Score: ${runDetails.risk?.confidence_score}%
Summary: ${runDetails.report.executive_summary}
      `;
      await sendMessage({
        receiver_id: selectedRecipient,
        subject: `[QA Report] ${runDetails.run.title}`,
        body: reportText,
        project_id: null
      });
      alert("Report successfully shared with developer!");
      setShowShareModal(false);
    } catch (err) {
      alert("Failed to share report");
    } finally {
      setSharing(false);
    }
  };
  
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState([]);
  const [activeRunId, setActiveRunId] = useState(null);
  const [runDetails, setRunDetails] = useState(null);
  const [activeTab, setActiveTab] = useState('Overview');
  
  const pollingRef = useRef(null);

  useEffect(() => {
    fetchHistory();
    return () => stopPolling();
  }, []);

  const fetchHistory = async () => {
    try {
      const res = await getAutonomousRuns();
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
        const res = await getAutonomousRunDetails(id);
        consecutiveErrors = 0; // reset on success
        const data = res.data;
        setRunDetails(data);
        if (['Completed', 'Failed'].includes(data.run.status)) {
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
    setLoading(true);
    setRunDetails(null);
    try {
      const apiFn = pipelineMode === 'agentqe' ? runAgentQE : runAutonomousQA;
      const payload = pipelineMode === 'agentqe'
        ? { ...formData, max_cycles: 3 }
        : formData;
      const res = await apiFn(payload);
      setActiveRunId(res.data.run_id);
      setActiveTab('Overview');
      startPolling(res.data.run_id);
    } catch (err) {
      alert(err.response?.data?.error || "Execution failed");
    } finally {
      setLoading(false);
    }
  };

  const selectRun = (id) => {
    setActiveRunId(id);
    setActiveTab('Overview');
    stopPolling();
    getAutonomousRunDetails(id).then(res => {
      setRunDetails(res.data);
      if (!['Completed', 'Failed'].includes(res.data.run.status)) {
        startPolling(id);
      }
    });
  };

  const renderStatusBadge = (status) => {
    const colors = {
      'Starting': 'bg-blue-100 text-blue-700',
      'Analysis': 'bg-violet-100 text-violet-700',
      'Generation': 'bg-indigo-100 text-indigo-700',
      'Execution': 'bg-cyan-100 text-cyan-700',
      'Reporting': 'bg-emerald-100 text-emerald-700',
      'Repo Scan': 'bg-rose-100 text-rose-700 font-bold',
      'Completed': 'bg-green-100 text-green-700',
      'Failed': 'bg-red-100 text-red-700'
    };
    return (
      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${colors[status] || 'bg-slate-100'}`}>
        {status}
      </span>
    );
  };

  const getHealStats = () => {
    if (!runDetails?.healing) return { total: 0, healed: 0, rate: 0, unresolved: 0 };
    const total = runDetails.healing.length;
    const healed = runDetails.healing.filter(h => h.status === 'Success').length;
    const unresolved = total - healed;
    const rate = total > 0 ? Math.round((healed / total) * 100) : 0;
    return { total, healed, rate, unresolved };
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 max-w-[1600px] mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
            <MdOutlineAutoFixHigh className="text-emerald-600" />
            Autonomous QA
          </h1>
          <p className="text-slate-500 text-sm mt-1">End-to-end self-driven QA lifecycle with dynamic auto-healing.</p>
        </div>
        <div className="flex items-center gap-2">
           <button onClick={() => { setActiveRunId(null); setRunDetails(null); }} className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-sm font-semibold transition-colors">
             New Run
           </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Input & History */}
        <div className="lg:col-span-4 space-y-6">
          <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
            <h2 className="text-sm font-bold text-slate-800 mb-4 flex items-center gap-2">
              <MdOutlinePlayCircle className="text-blue-600" /> Start Autonomous Run
            </h2>
            <form onSubmit={handleRun} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase mb-1.5 ml-1">Run Title</label>
                <input 
                  required
                  placeholder="e.g. User Auth Lifecycle"
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition-all"
                  value={formData.title}
                  onChange={e => setFormData({...formData, title: e.target.value})}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase mb-1.5 ml-1">Requirement / User Story</label>
                <textarea 
                  required
                  rows={4}
                  placeholder="Paste your requirement text here..."
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition-all resize-none"
                  value={formData.requirement_text}
                  onChange={e => setFormData({...formData, requirement_text: e.target.value})}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-500 uppercase mb-1.5 ml-1">Module</label>
                  <input 
                    placeholder="e.g. Frontend"
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm"
                    value={formData.module_name}
                    onChange={e => setFormData({...formData, module_name: e.target.value})}
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-500 uppercase mb-1.5 ml-1">Initial URL</label>
                  <input 
                    type="url"
                    placeholder="https://..."
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm"
                    value={formData.url}
                    onChange={e => setFormData({...formData, url: e.target.value})}
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase mb-1.5 ml-1">Git Repository URL (Optional)</label>
                <div className="relative">
                  <RiGithubFill className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input 
                    type="url"
                    placeholder="https://github.com/user/repo"
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-10 pr-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20 transition-all"
                    value={formData.repo_url}
                    onChange={e => setFormData({...formData, repo_url: e.target.value})}
                  />
                </div>
              </div>

              {/* Pipeline Mode Toggle */}
              <div className="bg-slate-50 border border-slate-200 rounded-xl p-3">
                <p className="text-xs font-semibold text-slate-500 uppercase mb-2 ml-1">Pipeline Mode</p>
                <div className="grid grid-cols-2 gap-2">
                  <button type="button" onClick={() => setPipelineMode('standard')}
                    className={`py-2 px-3 rounded-lg text-xs font-bold transition-all ${pipelineMode === 'standard' ? 'bg-blue-600 text-white shadow' : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-100'}`}>
                    🤖 Standard
                  </button>
                  <button type="button" onClick={() => setPipelineMode('agentqe')}
                    className={`py-2 px-3 rounded-lg text-xs font-bold transition-all ${pipelineMode === 'agentqe' ? 'bg-violet-600 text-white shadow' : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-100'}`}>
                    ⚡ AgentQE ML
                  </button>
                </div>
                {pipelineMode === 'agentqe' && (
                  <p className="text-[10px] text-violet-600 mt-2 ml-1 font-medium">
                    Uses ML ranking + multi-perspective generation + adaptive quality loop
                  </p>
                )}
              </div>

              <button
                disabled={loading}
                className={`w-full font-bold py-3 rounded-xl transition-all shadow-lg flex items-center justify-center gap-2 mt-2 disabled:opacity-50 ${
                  pipelineMode === 'agentqe'
                    ? 'bg-violet-600 hover:bg-violet-700 text-white'
                    : 'bg-blue-600 hover:bg-blue-700 text-white'
                }`}
              >
                {loading ? <RiLoader4Line className="animate-spin text-xl" /> : <MdOutlineAutoFixHigh className="text-xl" />}
                {loading ? 'Starting Agents...' : pipelineMode === 'agentqe' ? 'Run AgentQE Pipeline' : 'Run Autonomous QA'}
              </button>
            </form>
          </div>

          <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-sm">
            <div className="p-4 border-b border-slate-100 flex items-center justify-between">
              <h2 className="text-sm font-bold text-slate-800 flex items-center gap-2">
                <RiHistoryLine className="text-slate-400" /> Recent Runs
              </h2>
            </div>
            <div className="divide-y divide-slate-50 max-h-[400px] overflow-y-auto">
              {history.map(run => (
                <button 
                  key={run.id}
                  onClick={() => selectRun(run.id)}
                  className={`w-full text-left p-4 hover:bg-slate-50 transition-colors ${activeRunId === run.id ? 'bg-blue-50/50 border-l-4 border-blue-600' : ''}`}
                >
                  <div className="flex justify-between items-start mb-1">
                    <p className="text-sm font-semibold text-slate-800 truncate pr-4">{run.title}</p>
                    {renderStatusBadge(run.status)}
                  </div>
                  <p className="text-[10px] text-slate-400">{new Date(run.created_at + 'Z').toLocaleString()}</p>
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Right: Work Area */}
        <div className="lg:col-span-8 space-y-6">
          {!activeRunId ? (
            <div className="bg-slate-100/50 border-2 border-dashed border-slate-200 rounded-3xl h-[600px] flex flex-col items-center justify-center text-center px-10">
              <RiRobot2Line className="text-slate-300 text-6xl mb-6" />
              <h3 className="text-lg font-bold text-slate-800 mb-2">Awaiting Instructions</h3>
              <p className="text-sm text-slate-500 max-w-sm">Launch an autonomous run to see AI agents plan, generate, and heal test cases in real-time.</p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Orchestration Summary */}
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                 <div className="flex items-center justify-between mb-8">
                    <div className="flex items-center gap-4">
                       <div className="w-12 h-12 bg-emerald-50 rounded-xl flex items-center justify-center border border-emerald-100 text-emerald-600 shadow-sm relative">
                          <RiRobot2Line className="text-2xl" />
                          <div className="absolute -top-1 -right-1 w-3 h-3 bg-emerald-500 rounded-full border-2 border-white animate-ping" />
                       </div>
                       <div>
                          <p className="text-sm font-bold text-slate-800">{runDetails?.run?.title}</p>
                          <div className="flex items-center gap-2 mt-0.5">
                             {renderStatusBadge(runDetails?.run?.status)}
                             {runDetails?.healing?.length > 0 && (
                                <span className="flex items-center gap-1 bg-amber-50 text-amber-600 px-2 py-0.5 rounded-full text-[9px] font-black uppercase border border-amber-100 animate-pulse">
                                   <MdAutoFixNormal /> Self-Heal Active
                                </span>
                             )}
                          </div>
                       </div>
                    </div>
                    {runDetails?.risk && (
                       <ScoreBadge score={runDetails.risk.module_risk_score} label={runDetails.risk.release_readiness} />
                    )}
                 </div>

                 {/* Stepper - Enhanced for AgentQE */}
                 <div className="grid grid-cols-5 gap-2 relative">
                    <div className="absolute top-4 left-10 right-10 h-0.5 bg-slate-100" />
                    {[
                      { step: 'Analysis', icon: MdOutlineAnalytics },
                      { step: 'Generation', icon: MdOutlineRule },
                      { step: 'Execution', icon: MdOutlineLanguage },
                      { step: 'Reporting', icon: MdOutlineAssessment },
                      { step: 'Completed', icon: MdCheckCircle },
                    ].map(({ step, icon: Icon }) => {
                      const stages = ['Starting', 'Analysis', 'Generation', 'Execution', 'Reporting', 'Completed'];
                      const currentIdx = stages.indexOf(runDetails?.run?.status || 'Starting');
                      const isActive = step === runDetails?.run?.status;
                      const isPast = stages.indexOf(step) < currentIdx;
                      
                      return (
                        <div key={step} className="flex flex-col items-center gap-2 z-10">
                          <div className={`w-8 h-8 rounded-full flex items-center justify-center border-2 transition-all ${
                            isPast ? 'bg-blue-600 border-blue-600 text-white shadow-md shadow-blue-200' : 
                            isActive ? 'bg-white border-blue-600 text-blue-600 ring-4 ring-blue-50 animate-pulse' : 
                            'bg-white border-slate-200 text-slate-300'
                          }`}>
                            <Icon />
                          </div>
                          <span className={`text-[9px] font-bold uppercase tracking-tight ${isActive ? 'text-blue-600 font-black' : 'text-slate-400'}`}>{step}</span>
                        </div>
                      );
                    })}
                 </div>
                 
                 {/* AgentQE Stage Detail */}
                 {runDetails?.run?.execution_mode === 'AgentQE Pipeline' && runDetails?.logs && (
                   <div className="mt-6 bg-violet-50/50 border border-violet-100 rounded-xl p-4">
                     <p className="text-xs font-black text-violet-700 uppercase mb-3 flex items-center gap-2">
                       <RiMagicLine /> AgentQE ML Pipeline Stages
                     </p>
                     <div className="space-y-2">
                       {['STRATEGY', 'GENERATION', 'POOL', 'ENRICHMENT', 'RANKING', 'SELECTION', 'EXECUTION', 'FAILURE_ANALYSIS', 'PIPELINE'].map(stage => {
                         const stageLogs = runDetails.logs.filter(l => l.action_type === stage);
                         const hasStage = stageLogs.length > 0;
                         const latestLog = stageLogs[stageLogs.length - 1];
                         const isFailed = latestLog?.status === 'FAIL';
                         
                         return hasStage ? (
                           <div key={stage} className="flex items-center justify-between text-xs bg-white px-3 py-2 rounded-lg">
                             <span className="font-semibold text-slate-700 flex items-center gap-2">
                               {isFailed ? <MdError className="text-red-500" /> : <MdCheckCircle className="text-emerald-500" />}
                               {stage.replace(/_/g, ' ')}
                             </span>
                             <span className="text-[10px] text-slate-400">{stageLogs.length} ops</span>
                           </div>
                         ) : null;
                       })}
                     </div>
                   </div>
                 )}
              </div>

              {/* Interaction Tabs */}
              <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-sm min-h-[500px] flex flex-col">
                <div className="flex border-b border-slate-100 shrink-0 overflow-x-auto no-scrollbar bg-slate-50/50">
                  {['Overview', 'Test Cases', 'Browser Actions', 'Auto-Heal', 'Final Report'].map(tab => (
                    <button
                      key={tab}
                      onClick={() => setActiveTab(tab)}
                      className={`px-6 py-4 text-xs font-bold transition-all whitespace-nowrap border-b-2 ${
                        activeTab === tab ? 'border-blue-600 text-blue-600 bg-white' : 'border-transparent text-slate-500 hover:text-slate-800'
                      }`}
                    >
                      {tab}
                      {tab === 'Auto-Heal' && runDetails?.healing?.length > 0 && (
                        <span className="ml-2 bg-amber-500 text-white px-1.5 py-0.5 rounded-full text-[9px]">{runDetails.healing.length}</span>
                      )}
                    </button>
                  ))}
                  {runDetails?.repo_intelligence && (
                    <button
                      onClick={() => setActiveTab('Repo Intel')}
                      className={`px-6 py-4 text-xs font-bold transition-all whitespace-nowrap border-b-2 ${
                        activeTab === 'Repo Intel' ? 'border-violet-600 text-violet-600 bg-white' : 'border-transparent text-slate-500 hover:text-slate-800'
                      }`}
                    >
                      Repo Intel
                    </button>
                  )}
                </div>

                <div className="p-6 flex-1 overflow-y-auto">
                  {activeTab === 'Overview' && (
                    <div className="space-y-6">
                       <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                          <div className="space-y-4">
                             <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest flex items-center gap-2">
                                <MdInfo className="text-blue-500" /> Feature Intent
                             </h3>
                             <div className="bg-slate-50 p-4 rounded-xl border border-slate-100 text-sm text-slate-700 leading-relaxed min-h-[100px]">
                                {runDetails?.scope?.feature_summary || "Analyzing requirements..."}
                             </div>
                          </div>
                          <div className="space-y-4">
                             <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest flex items-center gap-2">
                                <MdTimeline className="text-emerald-500" /> Extracted Scope
                             </h3>
                             <div className="space-y-2">
                                {JSON.parse(runDetails?.scope?.scope_items || "[]").map((item, i) => (
                                  <div key={i} className="flex items-center gap-3 text-xs text-slate-600 bg-white p-2.5 rounded-lg border border-slate-100 shadow-sm">
                                    <span className="w-1.5 h-1.5 bg-blue-500 rounded-full" />
                                    {item}
                                  </div>
                                ))}
                             </div>
                          </div>
                       </div>
                    </div>
                  )}

                  {activeTab === 'Test Cases' && (
                    <div className="space-y-4">
                       <table className="w-full text-left text-xs">
                          <thead>
                             <tr className="text-slate-400 border-b border-slate-100 uppercase tracking-wider font-bold">
                               <th className="py-2 pl-2">ID</th>
                               <th className="py-2">Scenario</th>
                               <th className="py-2">Status</th>
                               <th className="py-2">Priority</th>
                             </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-50">
                             {runDetails?.test_cases?.map((tc, i) => {
                               const isHealed = runDetails.healing?.some(h => h.test_case_id === tc.case_id && h.status === 'Success');
                               return (
                                 <tr key={i} className="hover:bg-slate-50/50 group">
                                   <td className="py-4 pl-2 font-mono text-[10px] text-slate-400">{tc.case_id}</td>
                                   <td className="py-4">
                                      <p className="font-semibold text-slate-700">{tc.scenario}</p>
                                      <p className="text-[10px] text-slate-400 mt-1">{tc.expected_result}</p>
                                   </td>
                                   <td className="py-4">
                                      <div className="flex items-center gap-2">
                                        <span className="px-2 py-0.5 bg-slate-100 text-slate-500 rounded-full font-bold text-[9px] uppercase">{tc.case_type}</span>
                                        {isHealed && (
                                           <span className="flex items-center gap-1 bg-emerald-50 text-emerald-600 px-2 py-0.5 rounded-full text-[8px] font-black uppercase border border-emerald-100">
                                              <MdAutoFixNormal /> Auto-Healed
                                           </span>
                                        )}
                                      </div>
                                   </td>
                                   <td className="py-4 font-black uppercase text-[10px]">{tc.priority}</td>
                                 </tr>
                               );
                             })}
                          </tbody>
                       </table>
                    </div>
                  )}

                  {activeTab === 'Browser Actions' && (
                    <div className="bg-slate-900 rounded-2xl p-6 font-mono text-[11px] space-y-3 min-h-[400px]">
                       {runDetails?.logs?.map((l, i) => (
                          <div key={i} className="flex gap-4 group">
                             <span className="text-slate-600 shrink-0">{new Date(l.timestamp + 'Z').toLocaleTimeString()}</span>
                             <span className={`font-black shrink-0 ${l.status === 'FAIL' ? 'text-red-400' : 'text-emerald-400'}`}>[{l.status}]</span>
                             <span className="text-blue-400 shrink-0 text-right w-24">[{l.action_type}]</span>
                             <span className="text-slate-300 flex-1">{l.action_detail}</span>
                             {runDetails.healing?.some(h => h.step_detail === l.action_detail) && (
                                <span className="text-[10px] text-amber-500 font-bold shrink-0">**[Auto-Heal Trigged]**</span>
                             )}
                          </div>
                       ))}
                    </div>
                  )}

                  {activeTab === 'Auto-Heal' && (
                    <div className="space-y-8">
                       {/* Summary Cards */}
                       <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                          {[
                            { label: 'Total Failures', value: getHealStats().total, icon: MdError, color: 'text-red-500', bg: 'bg-red-50' },
                            { label: 'Successfully Healed', value: getHealStats().healed, icon: MdAutoFixNormal, color: 'text-emerald-500', bg: 'bg-emerald-50' },
                            { label: 'Heal Success Rate', value: `${getHealStats().rate}%`, icon: MdOutlineHealthAndSafety, color: 'text-blue-500', bg: 'bg-blue-50' },
                            { label: 'Unresolved', value: getHealStats().unresolved, icon: MdSettingsBackupRestore, color: 'text-amber-500', bg: 'bg-amber-50' },
                          ].map((stat, i) => (
                            <div key={i} className="bg-white border border-slate-100 p-4 rounded-2xl shadow-sm flex items-center gap-3">
                               <div className={`w-10 h-10 ${stat.bg} rounded-xl flex items-center justify-center`}>
                                  <stat.icon className={`${stat.color} text-xl`} />
                               </div>
                               <div>
                                  <p className="text-lg font-black text-slate-800 leading-none">{stat.value}</p>
                                  <p className="text-[10px] font-bold text-slate-400 uppercase mt-1">{stat.label}</p>
                               </div>
                            </div>
                          ))}
                       </div>

                       {/* Healing Logs */}
                       <div className="space-y-4">
                          <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest px-2">Detailed Healing Analysis</h3>
                          {runDetails?.healing?.map((h, i) => (
                            <div key={i} className={`border-l-4 p-5 bg-white border border-slate-100 rounded-2xl shadow-sm space-y-4 ${
                              h.status === 'Success' ? 'border-l-emerald-500' : 'border-l-red-500'
                            }`}>
                               <div className="flex justify-between items-start">
                                  <div className="flex items-center gap-3">
                                     <div className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 ${h.status === 'Success' ? 'bg-emerald-50 text-emerald-600' : 'bg-red-50 text-red-600'}`}>
                                        {h.status === 'Success' ? <RiShieldFlashLine className="text-xl" /> : <MdError className="text-xl" />}
                                     </div>
                                     <div>
                                        <p className="text-sm font-bold text-slate-800">Test Case: {h.test_case_id}</p>
                                        <p className="text-xs text-slate-500">{h.step_detail}</p>
                                     </div>
                                  </div>
                                  <div className="text-right">
                                     <span className={`px-3 py-1 rounded-full text-[10px] font-black uppercase ${h.status === 'Success' ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                                        {h.status === 'Success' ? 'Auto-Healed' : 'Unresolved Failure'}
                                     </span>
                                     <p className="text-[10px] text-slate-400 mt-2 font-bold tracking-widest">{new Date(h.timestamp + 'Z').toLocaleTimeString()}</p>
                                  </div>
                               </div>

                               <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                  <div className="bg-slate-50 p-4 rounded-xl border border-slate-100 space-y-2">
                                     <p className="text-[10px] font-black text-red-400 uppercase flex items-center gap-1"><MdError /> Detected Failure</p>
                                     <p className="text-xs text-slate-600 mt-1"><strong>Selector:</strong> <code className="bg-red-100 px-1 rounded text-red-700">{h.original_selector}</code></p>
                                     <p className="text-xs text-slate-500 mt-1 italic">Reason: {h.failure_reason}</p>
                                  </div>
                                  <div className={`p-4 rounded-xl border space-y-2 ${h.status === 'Success' ? 'bg-emerald-50/50 border-emerald-100' : 'bg-slate-50 border-slate-100'}`}>
                                     <p className={`text-[10px] font-black uppercase flex items-center gap-1 ${h.status === 'Success' ? 'text-emerald-500' : 'text-slate-400'}`}>
                                        {h.status === 'Success' ? <><RiMagicLine /> Applied Fix</> : <><MdSettingsBackupRestore /> No Candidate Found</>}
                                     </p>
                                     {h.status === 'Success' ? (
                                        <>
                                           <p className="text-xs text-slate-600 mt-1"><strong>New Selector:</strong> <code className="bg-emerald-100 px-1 rounded text-emerald-700">{h.suggested_selector}</code></p>
                                           <p className="text-xs text-emerald-600 font-bold mt-1 uppercase text-[10px]">Confidence: {(h.confidence_score * 100).toFixed(0)}% Match</p>
                                        </>
                                     ) : (
                                        <p className="text-xs text-slate-400 italic">Exhausted retries without meeting 0.6 confidence threshold.</p>
                                     )}
                                  </div>
                               </div>
                            </div>
                          ))}
                          {runDetails?.healing?.length === 0 && (
                            <div className="p-20 text-center text-slate-300">
                               <RiShieldFlashLine className="text-6xl mx-auto mb-4 opacity-20" />
                               <p className="text-sm font-bold">No healing events recorded for this run.</p>
                            </div>
                          )}
                       </div>
                    </div>
                  )}

                  {activeTab === 'Final Report' && (
                    <div className="space-y-8">
                       {runDetails?.report ? (
                         <div className="space-y-8">
                            {/* Verdict Banner */}
                            <div className={`p-8 rounded-3xl border-2 flex items-center justify-between gap-6 ${
                              runDetails.report.final_verdict?.toLowerCase().includes('ready')
                                ? 'bg-emerald-50/50 border-emerald-100' : 'bg-red-50/50 border-red-100'
                            }`}>
                               <div className="flex gap-6">
                                  <div className={`w-16 h-16 rounded-3xl flex items-center justify-center text-3xl shadow-lg border-2 ${
                                    runDetails.report.final_verdict?.toLowerCase().includes('ready')
                                      ? 'bg-emerald-500 border-emerald-400 text-white' : 'bg-red-500 border-red-400 text-white'
                                  }`}>
                                     <MdOutlineAssessment />
                                  </div>
                                  <div>
                                     <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-1">Final Deployment Verdict</p>
                                     <h4 className="text-2xl font-black text-slate-900">{runDetails.report.final_verdict}</h4>
                                     <p className="text-sm text-slate-500 mt-1">{runDetails.report.executive_summary?.substring(0, 150)}...</p>
                                  </div>
                               </div>
                               <div className="flex items-center gap-6">
                                  <div className="text-right">
                                     <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Platform Confidence</p>
                                     <p className="text-3xl font-black text-slate-800">{runDetails.risk?.confidence_score}%</p>
                                  </div>
                                  <button 
                                    onClick={() => setShowShareModal(true)}
                                    className="bg-slate-900 text-white px-6 py-3 rounded-2xl font-bold flex items-center gap-2 hover:bg-slate-800 transition-all shadow-lg"
                                  >
                                    <MdArrowForward className="text-xl" /> Send to Dev
                                  </button>
                               </div>
                            </div>

                            {/* Auto-Healing Analysis */}
                            <div className="bg-gradient-to-br from-slate-900 to-slate-800 rounded-3xl p-8 text-white relative overflow-hidden shadow-xl">
                               <div className="absolute top-0 right-0 w-64 h-64 bg-blue-500/10 rounded-full blur-3xl" />
                               <div className="relative z-10 space-y-4">
                                  <h3 className="text-sm font-black text-blue-400 uppercase tracking-[0.2em] flex items-center gap-2">
                                     <RiShieldFlashLine className="text-xl" /> Auto-Healing Intelligence Analysis
                                  </h3>
                                  <p className="text-sm text-slate-300 leading-relaxed max-w-3xl">
                                     {runDetails.report.auto_healing_analysis || "Performing adaptability analysis..."}
                                  </p>
                                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-4">
                                     <div className="bg-white/5 border border-white/10 p-4 rounded-2xl">
                                        <p className="text-2xl font-black">{getHealStats().healed}</p>
                                        <p className="text-[10px] text-slate-400 uppercase font-black tracking-widest">Self-Recoveries</p>
                                     </div>
                                     <div className="bg-white/5 border border-white/10 p-4 rounded-2xl">
                                        <p className="text-2xl font-black text-emerald-400">High</p>
                                        <p className="text-[10px] text-slate-400 uppercase font-black tracking-widest">UI Adaptability</p>
                                     </div>
                                     <div className="bg-white/5 border border-white/10 p-4 rounded-2xl">
                                        <p className="text-2xl font-black text-blue-400">{getHealStats().rate}%</p>
                                        <p className="text-[10px] text-slate-400 uppercase font-black tracking-widest">Healing Reliability</p>
                                     </div>
                                  </div>
                               </div>
                            </div>

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                               <div className="space-y-4">
                                  <h3 className="text-xs font-black text-slate-400 uppercase tracking-[0.2em] border-b border-slate-100 pb-2">High Risk Areas</h3>
                                  <div className="space-y-3">
                                     {JSON.parse(runDetails.risk?.high_risk_areas || "[]").map((area, i) => (
                                       <div key={i} className="flex gap-3 text-xs text-slate-700 bg-red-50 p-4 rounded-2xl border border-red-100">
                                          <MdError className="text-red-500 shrink-0 text-lg" />
                                          {area}
                                       </div>
                                     ))}
                                  </div>
                               </div>
                               <div className="space-y-4">
                                  <h3 className="text-xs font-black text-slate-400 uppercase tracking-[0.2em] border-b border-slate-100 pb-2">Strategic Recommendations</h3>
                                  <div className="space-y-3">
                                     {JSON.parse(runDetails.risk?.recommendations || "[]").map((rec, i) => (
                                       <div key={i} className="flex gap-3 text-sm text-slate-700 bg-white p-4 rounded-2xl border border-slate-100 shadow-sm">
                                          <MdCheckCircle className="text-emerald-500 shrink-0 text-lg" />
                                          {rec}
                                       </div>
                                     ))}
                                  </div>
                               </div>
                            </div>
                         </div>
                       ) : (
                         <div className="flex flex-col items-center justify-center p-32 text-slate-300">
                            <RiLoader4Line className="animate-spin text-4xl mb-4" />
                            <p className="text-sm font-bold text-slate-400 uppercase tracking-widest">Generating Final Audit Intelligence...</p>
                         </div>
                       )}
                    </div>
                  )}

                  {activeTab === 'Repo Intel' && runDetails?.repo_intelligence && (
                    <div className="space-y-8 animate-in backdrop-blur-sm">
                      <div className="grid md:grid-cols-2 gap-8">
                        {/* Stack Summary */}
                        <div className="space-y-4">
                          <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest">Repository Stack</h3>
                          <div className="grid grid-cols-2 gap-3">
                             <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                               <p className="text-[10px] text-slate-400 font-bold uppercase mb-1">Backend</p>
                               <p className="text-sm font-black text-slate-800">{runDetails.repo_intelligence.analysis.tech_stack.backend}</p>
                             </div>
                             <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                               <p className="text-[10px] text-slate-400 font-bold uppercase mb-1">Frontend</p>
                               <p className="text-sm font-black text-slate-800">{runDetails.repo_intelligence.analysis.tech_stack.frontend}</p>
                             </div>
                             <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 col-span-2">
                               <p className="text-[10px] text-slate-400 font-bold uppercase mb-1">Tools</p>
                               <p className="text-sm font-black text-slate-800">{runDetails.repo_intelligence.analysis.tech_stack.tools.join(', ')}</p>
                             </div>
                          </div>
                        </div>

                        {/* Health Stats */}
                        <div className="space-y-4">
                          <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest">Architectural Quality</h3>
                          <div className="space-y-3">
                             {['Quality', 'Test Readiness', 'Maintainability'].map(key => (
                               <div key={key} className="space-y-1">
                                 <div className="flex justify-between text-[10px] font-bold">
                                   <span className="text-slate-500 uppercase">{key}</span>
                                   <span className="text-blue-600">{runDetails.repo_intelligence.analysis.health_indicators[key.toLowerCase().replace(' ', '_')]}%</span>
                                 </div>
                                 <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                                   <div 
                                     className="h-full bg-blue-500" 
                                     style={{ width: `${runDetails.repo_intelligence.analysis.health_indicators[key.toLowerCase().replace(' ', '_')]}%` }} 
                                   />
                                 </div>
                               </div>
                             ))}
                          </div>
                        </div>
                      </div>

                      {/* Risks */}
                      <div className="space-y-4 pt-4 border-t border-slate-100">
                         <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest">AI Identified Bug Risks</h3>
                         <div className="grid md:grid-cols-2 gap-4">
                            {runDetails.repo_intelligence.analysis.bugs_and_risks.probable_issues.slice(0, 4).map((issue, i) => (
                              <div key={i} className="flex gap-3 p-4 bg-rose-50 border border-rose-100 rounded-xl text-xs text-rose-800">
                                <span className="shrink-0 w-5 h-5 bg-rose-200 text-rose-700 rounded-full flex items-center justify-center font-bold">{i+1}</span>
                                {issue}
                              </div>
                            ))}
                         </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {showShareModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 backdrop-blur-sm bg-slate-900/20 animate-in fade-in duration-300">
          <div className="bg-white w-full max-w-md rounded-[2.5rem] shadow-2xl border border-slate-100 overflow-hidden animate-in zoom-in-95 duration-300">
            <div className="p-8 space-y-6">
              <div className="flex justify-between items-center">
                <div className="space-y-1">
                  <h3 className="text-xl font-black text-slate-900 tracking-tight">Share Intelligence</h3>
                  <p className="text-xs text-slate-500 font-bold uppercase tracking-widest">Select Developer Recipient</p>
                </div>
                <button 
                  onClick={() => setShowShareModal(false)}
                  className="w-10 h-10 rounded-2xl flex items-center justify-center text-slate-400 hover:bg-slate-50 hover:text-slate-600 transition-all"
                >
                  <RiCloseLine className="text-2xl" />
                </button>
              </div>

              <div className="space-y-4">
                <div className="relative">
                  <RiUserLine className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                  <select 
                    value={selectedRecipient}
                    onChange={(e) => setSelectedRecipient(e.target.value)}
                    className="w-full pl-12 pr-6 py-4 bg-slate-50 border-2 border-slate-100 rounded-2xl text-sm font-bold text-slate-700 outline-none focus:border-slate-900 transition-all appearance-none"
                  >
                    <option value="">Choose Developer...</option>
                    {team.map(u => (
                      <option key={u.id} value={u.id}>{u.username} ({u.email})</option>
                    ))}
                  </select>
                </div>

                <div className="p-4 bg-blue-50/50 rounded-2xl border border-blue-100">
                  <p className="text-[10px] text-blue-600 font-black uppercase tracking-widest mb-1">Preview Message</p>
                  <p className="text-xs text-slate-600 leading-relaxed italic">
                    "Sent you the full QA Audit Report for {runDetails?.run.title}. Ready for deployment review."
                  </p>
                </div>
              </div>

              <button 
                disabled={sharing || !selectedRecipient}
                onClick={handleShare}
                className="w-full bg-slate-900 text-white py-4 rounded-2xl font-black flex items-center justify-center gap-3 hover:bg-slate-800 transition-all shadow-xl disabled:opacity-50 disabled:cursor-not-allowed group"
              >
                {sharing ? <RiLoader4Line className="animate-spin text-xl" /> : <RiSendPlaneFill className="text-xl group-hover:translate-x-1 transition-transform" />}
                {sharing ? 'Sharing Intelligence...' : 'Confirm & Send Report'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
