import React, { useState, useEffect, useRef } from 'react';
import { 
  MdOutlineAutoFixHigh, MdOutlinePlayCircle, MdOutlineHistory,
  MdCheckCircle, MdError, MdInfo, MdOutlineHealthAndSafety,
  MdAutoFixNormal, MdSettingsBackupRestore, MdTimeline,
  MdArrowForward, MdOutlineAnalytics, MdOutlineRule,
  MdOutlineLanguage, MdOutlineAssessment, MdOutlineFactCheck
} from 'react-icons/md';
import { RiRobot2Line, RiLoader4Line, RiHistoryLine, RiShieldFlashLine, RiMagicLine, RiGithubFill, RiUserLine, RiSendPlaneFill, RiCloseLine, RiArrowRightLine } from 'react-icons/ri';
import { runAgentQE, getAutonomousRunDetails, submitAgentQEReview, getAutonomousRuns, getTeamUsers, sendMessage, understandApplication, generateAgentQETests } from '../api/client';
import Loader from '../components/Loader';
import ScoreBadge from '../components/ScoreBadge';

export default function AgentQE() {
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
    max_cycles: 3
  });

  // Application Understanding state
  const [appUnderstanding, setAppUnderstanding] = useState(null);
  const [appUnderstandingLoading, setAppUnderstandingLoading] = useState(false);
  const [appUnderstandingError, setAppUnderstandingError] = useState(null);
  const [selectedPageForUI, setSelectedPageForUI] = useState(null);

  // Test Generation state
  const [testGeneration, setTestGeneration] = useState(null);
  const [testGenerationLoading, setTestGenerationLoading] = useState(false);
  const [testGenerationError, setTestGenerationError] = useState(null);

  const handleGenerateTests = async () => {
    if (!appUnderstanding) {
      alert("Please run App Understanding first");
      return;
    }
    setTestGenerationLoading(true);
    setTestGenerationError(null);
    setTestGeneration(null);
    try {
      const res = await generateAgentQETests({ application_context: appUnderstanding });
      setTestGeneration(res.data);
      setActiveTab('Test Generation');
    } catch (err) {
      setTestGenerationError(err.response?.data?.error || "Test generation failed");
    } finally {
      setTestGenerationLoading(false);
    }
  };

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
AgentQE ML Pipeline Report: ${runDetails.run.title}
Module: ${runDetails.run.module_name}
Final Verdict: ${runDetails.report.final_verdict}
Risk Score: ${runDetails.risk?.confidence_score}%
Summary: ${runDetails.report.executive_summary}
      `;
      await sendMessage({
        receiver_id: selectedRecipient,
        subject: `[AgentQE Report] ${runDetails.run.title}`,
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
        consecutiveErrors = 0;
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
    if (!formData.requirement_text && !formData.url) {
      alert("Please provide either a requirement or URL");
      return;
    }
    setLoading(true);
    setRunDetails(null);
    try {
      const payload = { 
        ...formData, 
        execution_mode: "AgentQE Pipeline",
        max_cycles: parseInt(formData.max_cycles) || 3
      };
      const res = await runAgentQE(payload);
      setActiveRunId(res.data.run_id);
      setActiveTab('Overview');
      startPolling(res.data.run_id);
    } catch (err) {
      alert(err.response?.data?.error || "Execution failed");
    } finally {
      setLoading(false);
    }
  };

  const handleAppUnderstanding = async (e) => {
    e.preventDefault();
    if (!formData.url && !formData.repo_url && !formData.requirement_text) {
      alert("Please provide at least a URL, repository URL, or requirement");
      return;
    }
    setAppUnderstandingLoading(true);
    setAppUnderstandingError(null);
    setAppUnderstanding(null);
    try {
      const payload = {
        url: formData.url,
        repo_url: formData.repo_url,
        requirement: formData.requirement_text,
        module_name: formData.module_name,
      };
      const res = await understandApplication(payload);
      setAppUnderstanding(res.data.context);
      setActiveTab('App Understanding');
    } catch (err) {
      setAppUnderstandingError(err.response?.data?.error || "Application understanding failed");
    } finally {
      setAppUnderstandingLoading(false);
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
            <RiMagicLine className="text-violet-600" />
            AgentQE ML Pipeline
          </h1>
          <p className="text-slate-500 text-sm mt-1">Advanced ML-enhanced QA with multi-agent orchestration and adaptive test execution.</p>
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
              <MdOutlinePlayCircle className="text-violet-600" /> Start AgentQE Pipeline
            </h2>
            <form onSubmit={handleRun} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase mb-1.5 ml-1">Run Title</label>
                <input 
                  required
                  placeholder="e.g. User Auth Lifecycle"
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/20 transition-all"
                  value={formData.title}
                  onChange={e => setFormData({...formData, title: e.target.value})}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase mb-1.5 ml-1">Requirement / User Story</label>
                <textarea 
                  rows={4}
                  placeholder="Describe what should be tested..."
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/20 transition-all resize-none"
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
                  <label className="block text-xs font-semibold text-slate-500 uppercase mb-1.5 ml-1">Max Cycles</label>
                  <input 
                    type="number"
                    min="1"
                    max="10"
                    placeholder="3"
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm"
                    value={formData.max_cycles}
                    onChange={e => setFormData({...formData, max_cycles: e.target.value})}
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase mb-1.5 ml-1">URL (Optional)</label>
                <input 
                  type="url"
                  placeholder="https://..."
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-4 py-2.5 text-sm"
                  value={formData.url}
                  onChange={e => setFormData({...formData, url: e.target.value})}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-500 uppercase mb-1.5 ml-1">Git Repository URL (Optional)</label>
                <div className="relative">
                  <RiGithubFill className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input 
                    type="url"
                    placeholder="https://github.com/user/repo"
                    className="w-full bg-slate-50 border border-slate-200 rounded-xl pl-10 pr-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500/20 transition-all"
                    value={formData.repo_url}
                    onChange={e => setFormData({...formData, repo_url: e.target.value})}
                  />
                </div>
              </div>

              <button
                disabled={loading}
                className={`w-full font-bold py-3 rounded-xl transition-all shadow-lg flex items-center justify-center gap-2 mt-2 disabled:opacity-50 bg-violet-600 hover:bg-violet-700 text-white`}
              >
                {loading ? <RiLoader4Line className="animate-spin text-xl" /> : <RiMagicLine className="text-xl" />}
                {loading ? 'Starting Pipeline...' : 'Run AgentQE Pipeline'}
              </button>
            
            {/* Application Understanding Button */}
            <button
              disabled={appUnderstandingLoading}
              onClick={handleAppUnderstanding}
              className={`w-full font-bold py-3 rounded-xl transition-all shadow-lg flex items-center justify-center gap-2 mt-4 disabled:opacity-50 bg-blue-600 hover:bg-blue-700 text-white`}
            >
              {appUnderstandingLoading ? <RiLoader4Line className="animate-spin text-xl" /> : <MdOutlineAnalytics className="text-xl" />}
              {appUnderstandingLoading ? 'Analyzing Application...' : 'Analyze Application'}
            </button>
            
            {appUnderstandingError && (
              <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                {appUnderstandingError}
              </div>
            )}
            
            {appUnderstanding && !appUnderstandingLoading && (
              <div className="mt-3 p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm">
                Application analysis complete. View results in the <strong>App Understanding</strong> tab.
              </div>
            )}
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
                  className={`w-full text-left p-4 hover:bg-slate-50 transition-colors ${activeRunId === run.id ? 'bg-violet-50/50 border-l-4 border-violet-600' : ''}`}
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
          {!(activeRunId || appUnderstanding) ? (
            <div className="bg-slate-100/50 border-2 border-dashed border-slate-200 rounded-3xl h-[600px] flex flex-col items-center justify-center text-center px-10">
              <RiRobot2Line className="text-slate-300 text-6xl mb-6" />
              <h3 className="text-lg font-bold text-slate-800 mb-2">AgentQE ML Pipeline Ready</h3>
              <p className="text-sm text-slate-500 max-w-sm">Start a new ML-enhanced QA pipeline to begin automated testing with multi-agent orchestration, adaptive quality evaluation, and real-time self-healing.</p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Orchestration Summary */}
              {activeRunId && (
                <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                 <div className="flex items-center justify-between mb-8">
                    <div className="flex items-center gap-4">
                       <div className="w-12 h-12 bg-violet-50 rounded-xl flex items-center justify-center border border-violet-100 text-violet-600 shadow-sm relative">
                          <RiRobot2Line className="text-2xl" />
                          <div className="absolute -top-1 -right-1 w-3 h-3 bg-violet-500 rounded-full border-2 border-white animate-ping" />
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

                 {/* Stepper */}
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
                            isPast ? 'bg-violet-600 border-violet-600 text-white shadow-md shadow-violet-200' : 
                            isActive ? 'bg-white border-violet-600 text-violet-600 ring-4 ring-violet-50 animate-pulse' : 
                            'bg-white border-slate-200 text-slate-300'
                          }`}>
                            <Icon />
                          </div>
                          <span className={`text-[9px] font-bold uppercase tracking-tight ${isActive ? 'text-violet-600 font-black' : 'text-slate-400'}`}>{step}</span>
                        </div>
                      );
                    })}
                 </div>
                 
                 {/* AgentQE Stage Detail */}
                 {runDetails?.logs && (
                   <div className="mt-6 bg-violet-50/50 border border-violet-100 rounded-xl p-4">
                     <p className="text-xs font-black text-violet-700 uppercase mb-3 flex items-center gap-2">
                       <RiMagicLine /> AgentQE Pipeline Stages
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
                   )}
                   
                   {activeTab === 'Unified Model' && (
                     <div className="space-y-8">
                       {appUnderstanding?.unified_model ? (
                         <div className="space-y-8">
                           {/* Unified Model Summary */}
                           <div className="bg-gradient-to-br from-indigo-50 to-violet-50 border border-indigo-100 rounded-2xl p-6 shadow-sm">
                             <h3 className="text-xs font-black text-indigo-600 uppercase tracking-widest mb-4 flex items-center gap-2">
                               <MdOutlineAnalytics className="text-indigo-500" /> Unified Application Model
                             </h3>
                             <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
                               {[
                                 { label: 'Pages', value: appUnderstanding.unified_model.evidence_summary?.pages ?? '—', icon: MdOutlineLanguage, color: 'text-indigo-500' },
                                 { label: 'Controls', value: appUnderstanding.unified_model.evidence_summary?.controls ?? '—', icon: MdOutlineRule, color: 'text-violet-500' },
                                 { label: 'Forms', value: appUnderstanding.unified_model.evidence_summary?.forms ?? '—', icon: MdOutlineFactCheck, color: 'text-emerald-500' },
                                 { label: 'API Endpoints', value: appUnderstanding.unified_model.evidence_summary?.api_endpoints ?? '—', icon: MdOutlineLanguage, color: 'text-orange-500' },
                                 { label: 'User Flows', value: appUnderstanding.unified_model.evidence_summary?.user_flows ?? '—', icon: MdTimeline, color: 'text-blue-500' },
                                 { label: 'Modules', value: appUnderstanding.unified_model.evidence_summary?.modules ?? '—', icon: MdOutlineFactCheck, color: 'text-amber-500' },
                                 { label: 'Relationships', value: appUnderstanding.unified_model.evidence_summary?.relationships ?? '—', icon: MdOutlineAnalytics, color: 'text-cyan-500' },
                                 { label: 'Requirements', value: appUnderstanding.unified_model.evidence_summary?.requirements ?? '—', icon: MdOutlineAssessment, color: 'text-amber-500' },
                               ].map((stat, i) => (
                                 <div key={i} className="bg-white/80 p-3 rounded-xl border border-indigo-100">
                                   <div className="flex items-center gap-2 mb-1">
                                     <stat.icon className={`${stat.color}`} />
                                     <p className="text-[10px] text-indigo-400 font-bold uppercase">{stat.label}</p>
                                   </div>
                                   <p className="text-sm font-black text-slate-800">{stat.value}</p>
                                 </div>
                               ))}
                             </div>
                             {appUnderstanding.unified_model.fusion_metadata && (
                               <div className="mt-4 space-y-2">
                                 <div className="flex flex-wrap gap-2">
                                   <span className="px-2 py-1 bg-indigo-100 text-indigo-700 text-[9px] font-bold uppercase rounded">
                                     Engine: {appUnderstanding.unified_model.fusion_metadata.engine}
                                   </span>
                                   <span className="px-2 py-1 bg-blue-100 text-blue-700 text-[9px] font-bold uppercase rounded">
                                     v{appUnderstanding.unified_model.fusion_metadata.fusion_version}
                                   </span>
                                   <span className="px-2 py-1 bg-emerald-100 text-emerald-700 text-[9px] font-bold uppercase rounded">
                                     {appUnderstanding.unified_model.fusion_metadata.llm_used ? 'LLM Used' : 'Deterministic'}
                                   </span>
                                   <span className="px-2 py-1 bg-amber-100 text-amber-700 text-[9px] font-bold uppercase rounded">
                                     {appUnderstanding.unified_model.fusion_metadata.duration_ms ? `${Math.round(appUnderstanding.unified_model.fusion_metadata.duration_ms)}ms` : '—'}
                                   </span>
                                 </div>
                                 <div className="text-[9px] text-slate-400">
                                   Sources: {appUnderstanding.unified_model.fusion_metadata.sources?.join(', ') || '—'}
                                 </div>
                                 {appUnderstanding.unified_model.fusion_metadata.warnings && appUnderstanding.unified_model.fusion_metadata.warnings.length > 0 && (
                                   <div className="mt-2 space-y-1">
                                     {appUnderstanding.unified_model.fusion_metadata.warnings.map((w, i) => (
                                       <p key={i} className="text-[10px] text-amber-600 bg-amber-50 px-3 py-1.5 rounded-lg border border-amber-100">
                                         ⚠ {w}
                                       </p>
                                     ))}
                                   </div>
                                 )}
                                 {appUnderstanding.unified_model.fusion_metadata.validation && (
                                   <div className="mt-2 p-3 bg-slate-50 rounded-lg border border-slate-200">
                                     <div className="flex items-center gap-2 mb-2">
                                       <span className={`px-2 py-1 rounded text-[9px] font-bold uppercase ${appUnderstanding.unified_model.fusion_metadata.validation.valid ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                                         {appUnderstanding.unified_model.fusion_metadata.validation.valid ? 'Valid' : 'Has Errors'}
                                       </span>
                                       <span className="px-2 py-1 bg-slate-100 text-slate-600 text-[9px] font-bold uppercase rounded">
                                         {appUnderstanding.unified_model.fusion_metadata.validation.error_count} error(s), {appUnderstanding.unified_model.fusion_metadata.validation.warning_count} warning(s)
                                       </span>
                                     </div>
                                     {appUnderstanding.unified_model.fusion_metadata.validation.errors && appUnderstanding.unified_model.fusion_metadata.validation.errors.length > 0 && (
                                       <div className="space-y-1 max-h-24 overflow-y-auto">
                                         {appUnderstanding.unified_model.fusion_metadata.validation.errors.slice(0, 5).map((e, i) => (
                                           <p key={i} className="text-[9px] text-red-600 bg-red-50 px-2 py-1 rounded border border-red-100">
                                             {e.code}: {e.message}
                                           </p>
                                         ))}
                                       </div>
                                     )}
                                     {appUnderstanding.unified_model.fusion_metadata.validation.warnings && appUnderstanding.unified_model.fusion_metadata.validation.warnings.length > 0 && (
                                       <div className="space-y-1 max-h-24 overflow-y-auto mt-2">
                                         {appUnderstanding.unified_model.fusion_metadata.validation.warnings.slice(0, 5).map((w, i) => (
                                           <p key={i} className="text-[9px] text-amber-600 bg-amber-50 px-2 py-1 rounded border border-amber-100">
                                             {w.code}: {w.message}
                                           </p>
                                         ))}
                                       </div>
                                     )}
                                   </div>
                                 )}
                               </div>
                             )}
                           </div>
 
                           {/* Pages */}
                           {appUnderstanding.unified_model.pages && appUnderstanding.unified_model.pages.length > 0 && (
                             <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                               <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                                 <MdOutlineLanguage className="text-indigo-500" /> Pages ({appUnderstanding.unified_model.pages.length})
                               </h3>
                               <div className="overflow-x-auto">
                                 <table className="w-full text-left text-xs">
                                   <thead>
                                     <tr className="text-slate-400 border-b border-slate-100 uppercase tracking-wider font-bold">
                                       <th className="py-2 pl-2">Page</th>
                                       <th className="py-2">Title</th>
                                       <th className="py-2">Type</th>
                                       <th className="py-2">Depth</th>
                                       <th className="py-2">Status</th>
                                       <th className="py-2">Controls</th>
                                       <th className="py-2">Forms</th>
                                       <th className="py-2">APIs</th>
                                     </tr>
                                   </thead>
                                   <tbody className="divide-y divide-slate-50">
                                     {appUnderstanding.unified_model.pages.slice(0, 30).map((p, i) => {
                                       let path = '/';
                                       try { path = new URL(p.url || '').pathname || p.url; } catch { path = p.url || '/'; }
                                       const statusColor = p.crawl_status === 'success' ? 'text-emerald-600 bg-emerald-50' :
                                         p.crawl_status === 'authentication_required' ? 'text-amber-600 bg-amber-50' :
                                         'text-red-600 bg-red-50';
                                       const typeColor = p.page_type_status === 'observed' ? 'bg-blue-100 text-blue-700' : 'bg-slate-100 text-slate-600';
                                       return (
                                         <tr key={i} className="hover:bg-slate-50/50">
                                           <td className="py-3 pl-2 font-mono text-[10px] text-slate-600 max-w-[180px] truncate" title={path}>{path}</td>
                                           <td className="py-3 text-slate-700 max-w-[160px] truncate" title={p.title}>{p.title || '—'}</td>
                                           <td className="py-3">
                                             <span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase ${typeColor}`}>
                                               {p.page_type || 'unknown'}
                                             </span>
                                           </td>
                                           <td className="py-3 text-slate-500 font-bold">{p.depth ?? '—'}</td>
                                           <td className="py-3">
                                             <span className={`px-2 py-0.5 rounded text-[9px] font-bold ${statusColor}`}>
                                               {p.crawl_status || '—'}
                                             </span>
                                           </td>
                                           <td className="py-3 text-slate-500 font-bold">{p.controls?.length || 0}</td>
                                           <td className="py-3 text-slate-500 font-bold">{p.forms?.length || 0}</td>
                                           <td className="py-3 text-slate-500 font-bold">{p.api_endpoints?.length || 0}</td>
                                         </tr>
                                       );
                                     })}
                                   </tbody>
                                 </table>
                                 {appUnderstanding.unified_model.pages.length > 30 && (
                                   <p className="text-[10px] text-slate-400 text-center mt-2">... and {appUnderstanding.unified_model.pages.length - 30} more pages</p>
                                 )}
                               </div>
                             </div>
                           )}
 
                           {/* Controls */}
                           {appUnderstanding.unified_model.controls && appUnderstanding.unified_model.controls.length > 0 && (
                             <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                               <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                                 <MdOutlineRule className="text-violet-500" /> Controls ({appUnderstanding.unified_model.controls.length})
                               </h3>
                               <div className="space-y-4">
                                 {appUnderstanding.unified_model.controls.slice(0, 50).map((c, idx) => (
                                   <div key={idx} className="border border-slate-100 rounded-xl p-4 hover:border-violet-200 transition-colors bg-slate-50/30">
                                     <div className="flex items-start justify-between gap-4">
                                       <div className="flex-1 min-w-0">
                                         <div className="flex items-center gap-2 mb-2 flex-wrap">
                                           <span className="px-1.5 py-0.5 bg-indigo-100 text-indigo-700 text-[9px] font-bold uppercase rounded">{c.type}</span>
                                           {c.dom_ref && <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 text-[9px] font-bold uppercase rounded">{c.dom_ref}</span>}
                                           {c.accessibility_ref && <span className="px-1.5 py-0.5 bg-emerald-100 text-emerald-700 text-[9px] font-bold uppercase rounded">{c.accessibility_ref}</span>}
                                           {c.visual_ref && <span className="px-1.5 py-0.5 bg-violet-100 text-violet-700 text-[9px] font-bold uppercase rounded">{c.visual_ref}</span>}
                                           <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${
                                             c.observation_status === 'observed' ? 'bg-emerald-100 text-emerald-700' :
                                             c.observation_status === 'inferred' ? 'bg-blue-100 text-blue-700' :
                                             'bg-slate-100 text-slate-500'
                                           }`}>
                                             {c.observation_status}
                                           </span>
                                           {c.semantic_role && (
                                             <span className="px-1.5 py-0.5 bg-amber-100 text-amber-700 text-[9px] font-bold uppercase rounded">
                                               {c.semantic_role}
                                             </span>
                                           )}
                                         </div>
                                         <div className="text-slate-600 font-mono text-[10px] space-y-0.5">
                                           {c.label && <span>label: {c.label}</span>}
                                           {c.text && <span>text: {c.text}</span>}
                                           {c.dom_id && <span>dom_id: {c.dom_id}</span>}
                                           {c.dom_name && <span>dom_name: {c.dom_name}</span>}
                                           {c.href && <span>href: {c.href}</span>}
                                           {c.bbox_pixels && <span>bbox (px): [{c.bbox_pixels.join(', ')}]</span>}
                                           {c.bbox_normalized && <span>bbox (norm): [{c.bbox_normalized.map(v => v.toFixed(4)).join(', ')}]</span>}
                                           {c.semantic_role && c.semantic_role_status && (
                                             <span>semantic_role_status: {c.semantic_role_status}</span>
                                           )}
                                           {c.inference_reason && (
                                             <span className="text-amber-600 italic">inference: {c.inference_reason}</span>
                                           )}
                                         </div>
                                       </div>
                                       <div className="flex items-center gap-2">
                                         {c.confidence !== null && c.confidence !== undefined && (
                                           <span className="px-2 py-1 bg-blue-100 text-blue-700 text-[9px] font-bold uppercase rounded">
                                             {Math.round(c.confidence * 100)}%
                                         </span>
                                         )}
                                         {c.confidence_basis && (
                                           <span className="px-2 py-1 bg-slate-100 text-slate-600 text-[9px] font-bold uppercase rounded" title={c.confidence_basis}>
                                             basis
                                           </span>
                                         )}
                                       </div>
                                      </div>
                                    </div>
                                    ))}
                                    {appUnderstanding.unified_model.controls.length > 50 && (
                                      <p className="text-[10px] text-slate-400 text-center mt-2">... and {appUnderstanding.unified_model.controls.length - 50} more controls</p>
                                    )}
</div>
                                      </div>
                            )}
                            {/* Forms */}
                           {appUnderstanding.unified_model.forms && appUnderstanding.unified_model.forms.length > 0 && (
                             <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                               <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                                 <MdOutlineFactCheck className="text-emerald-500" /> Forms ({appUnderstanding.unified_model.forms.length})
                               </h3>
                               <div className="space-y-3">
                                 {appUnderstanding.unified_model.forms.map((f, idx) => (
                                   <div key={idx} className="bg-slate-50 p-4 rounded-lg border border-slate-100">
                                     <div className="flex items-center gap-2 mb-2 text-xs">
                                       <span className="font-mono text-slate-600">{f.id}</span>
                                       <span className="px-1.5 py-0.5 bg-emerald-100 text-emerald-700 text-[9px] font-bold uppercase rounded">{f.method}</span>
                                       {f.action && <span className="text-slate-500 font-mono text-[10px] truncate max-w-[200px]">{f.action}</span>}
                                       {f.semantic_role && <span className="px-1.5 py-0.5 bg-amber-100 text-amber-700 text-[9px] font-bold uppercase rounded">{f.semantic_role}</span>}
                                       <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${
                                         f.observation_status === 'observed' ? 'bg-emerald-100 text-emerald-700' :
                                         f.observation_status === 'inferred' ? 'bg-blue-100 text-blue-700' :
                                         'bg-slate-100 text-slate-500'
                                       }`}>
                                         {f.observation_status}
                                       </span>
                                     </div>
                                     <div className="space-y-1 text-[10px] text-slate-600">
                                       {f.fields && f.fields.length > 0 && (
                                         <div>
                                           <span className="font-bold">Fields:</span>
                                           {f.fields.slice(0, 10).map((fieldId, fi) => (
                                             <span key={fi} className="ml-2 inline-block mr-2 px-1.5 py-0.5 bg-white border border-slate-200 rounded text-slate-700 font-mono">{fieldId}</span>
                                           ))}
                                           {f.fields.length > 10 && <span className="ml-2 text-slate-400">... +{f.fields.length - 10} more</span>}
                                         </div>
                                       )}
                                       {f.submit_control && <span className="text-slate-600">submit: {f.submit_control}</span>}
                                       {f.observed_api_endpoints && f.observed_api_endpoints.length > 0 && (
                                         <span className="text-slate-600">APIs: {f.observed_api_endpoints.join(', ')}</span>
                                       )}
                                       {f.inference_reason && <span className="text-amber-600 italic">inference: {f.inference_reason}</span>}
                                     </div>
                                   </div>
                                 ))}
                               </div>
                             </div>
)}
                            
                            {/* API Endpoints */}
                           {appUnderstanding.unified_model.api_endpoints && appUnderstanding.unified_model.api_endpoints.length > 0 && (
                             <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                               <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                                 <MdOutlineLanguage className="text-orange-500" /> API Endpoints ({appUnderstanding.unified_model.api_endpoints.length})
                               </h3>
                               <div className="space-y-1 max-h-96 overflow-y-auto">
                                 {appUnderstanding.unified_model.api_endpoints.map((endpoint, i) => {
                                   const method = endpoint.method || 'GET';
                                   const path = endpoint.path || endpoint.url || '';
                                   const methodColor = method === 'GET' ? 'text-emerald-600' :
                                                     method === 'POST' ? 'text-blue-600' :
                                                     method === 'PUT' || method === 'PATCH' ? 'text-amber-600' :
                                                     method === 'DELETE' ? 'text-red-600' : 'text-slate-600';
                                   return (
                                     <div key={i} className="bg-slate-50 px-3 py-2 rounded-lg border border-slate-100">
                                       <div className="flex items-center gap-2 flex-wrap mb-1">
                                         <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${methodColor} bg-white border border-slate-200`}>
                                           {method}
                                         </span>
                                         <span className="font-mono text-[10px] text-slate-700 truncate flex-1 min-w-0">{path}</span>
                                         {endpoint.host && <span className="text-[9px] text-slate-400">{endpoint.host}</span>}
                                         <span className="px-1.5 py-0.5 bg-slate-100 text-slate-600 text-[9px] font-bold uppercase rounded">
                                           {endpoint.observation_count} obs
                                         </span>
                                         {endpoint.failure_count > 0 && (
                                           <span className="px-1.5 py-0.5 bg-red-100 text-red-700 text-[9px] font-bold uppercase rounded">
                                             {endpoint.failure_count} failed
                                           </span>
                                         )}
                                         {endpoint.observed_on_pages && endpoint.observed_on_pages.length > 0 && (
                                           <span className="px-1.5 py-0.5 bg-violet-100 text-violet-700 text-[9px] font-bold uppercase rounded">
                                             {endpoint.observed_on_pages.length} page(s)
                                           </span>
                                         )}
                                       </div>
                                       <div className="text-[9px] text-slate-400 ml-10">
                                         {endpoint.request_metadata?.resource_type && <span>resource: {endpoint.request_metadata.resource_type}</span>}
                                         {endpoint.response_metadata?.statuses?.length > 0 && (
                                           <span className="ml-2">status: {endpoint.response_metadata.statuses.join(', ')}</span>
                                         )}
                                         {endpoint.response_metadata?.content_types?.length > 0 && (
                                           <span className="ml-2">content: {endpoint.response_metadata.content_types.join(', ')}</span>
                                         )}
                                       </div>
                                     </div>
                                   );
                                 })}
                                 {appUnderstanding.unified_model.api_endpoints.length > 50 && (
                                   <p className="text-[10px] text-slate-400 text-center mt-2">... and {appUnderstanding.unified_model.api_endpoints.length - 50} more endpoints</p>
                                 )}
                               </div>
                             </div>
)}
                            
                            {/* User Flows */}
                           {appUnderstanding.unified_model.user_flows && appUnderstanding.unified_model.user_flows.length > 0 && (
                             <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                               <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                                 <MdTimeline className="text-blue-500" /> User Flows ({appUnderstanding.unified_model.user_flows.length})
                               </h3>
                               <div className="space-y-4">
                                 {appUnderstanding.unified_model.user_flows.map((flow, fi) => (
                                   <div key={fi} className="bg-slate-50 p-4 rounded-lg border border-slate-100">
                                     <div className="flex items-center gap-3 mb-2">
                                       <span className="px-2 py-1 bg-blue-100 text-blue-700 text-[9px] font-bold uppercase rounded">{flow.source}</span>
                                       <span className="px-2 py-1 bg-slate-100 text-slate-600 text-[9px] font-bold uppercase rounded">{flow.observation_status}</span>
                                       {flow.confidence !== null && flow.confidence !== undefined && (
                                         <span className="px-2 py-1 bg-blue-100 text-blue-700 text-[9px] font-bold uppercase rounded">
                                           {Math.round(flow.confidence * 100)}%
                                         </span>
                                       )}
                                       {flow.semantic_role && <span className="px-1.5 py-0.5 bg-amber-100 text-amber-700 text-[9px] font-bold uppercase rounded">{flow.semantic_role}</span>}
                                     </div>
                                     <p className="text-sm font-semibold text-slate-800">{flow.name}</p>
                                     {flow.inference_reason && <p className="text-xs text-amber-600 italic mt-1">{flow.inference_reason}</p>}
                                     {flow.steps && flow.steps.length > 0 && (
                                       <div className="space-y-1 mt-2 pl-4 border-l border-slate-200">
                                         {flow.steps.map((step, si) => (
                                           <div key={si} className="flex gap-2 text-xs text-slate-600">
                                             <span className="px-1.5 py-0.5 bg-slate-100 text-slate-600 text-[9px] font-bold uppercase rounded">{step.action}</span>
                                             <span className="flex-1">{step.description}</span>
                                             <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${
                                               step.observation_status === 'observed' ? 'bg-emerald-100 text-emerald-700' :
                                               'bg-blue-100 text-blue-700'
                                             }`}>
                                               {step.observation_status}
                                             </span>
                                           </div>
                                         ))}
                                       </div>
                                     )}
                                     {flow.requirement_refs && flow.requirement_refs.length > 0 && (
                                       <div className="mt-2 text-[9px] text-slate-400">
                                         Requirements: {flow.requirement_refs.join(', ')}
                                       </div>
                                     )}
                                   </div>
                                 ))}
                               </div>
                             </div>
)}
                            
                            {/* Modules */}
                           {appUnderstanding.unified_model.modules && appUnderstanding.unified_model.modules.length > 0 && (
                             <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                               <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                                 <MdOutlineFactCheck className="text-violet-500" /> Modules / Features ({appUnderstanding.unified_model.modules.length})
                               </h3>
                               <div className="space-y-3">
                                 {appUnderstanding.unified_model.modules.map((m, idx) => (
                                   <div key={idx} className="bg-slate-50 p-4 rounded-lg border border-slate-100">
                                     <div className="flex items-center gap-2 mb-2 text-xs">
                                       <span className="font-black text-slate-800">{m.name}</span>
                                       <span className="px-1.5 py-0.5 bg-violet-100 text-violet-700 text-[9px] font-bold uppercase rounded">{m.source}</span>
                                       <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${
                                         m.observation_status === 'observed' ? 'bg-emerald-100 text-emerald-700' :
                                         m.observation_status === 'inferred' ? 'bg-blue-100 text-blue-700' :
                                         'bg-slate-100 text-slate-500'
                                       }`}>
                                         {m.observation_status}
                                       </span>
                                     </div>
                                     <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[10px] text-slate-600">
                                       <div className="bg-white p-2 rounded border border-slate-100">
                                         <p className="text-[9px] text-slate-400 font-bold uppercase">Pages</p>
                                         <p className="font-bold">{m.pages?.length || 0}</p>
                                       </div>
                                       <div className="bg-white p-2 rounded border border-slate-100">
                                         <p className="text-[9px] text-slate-400 font-bold uppercase">Controls</p>
                                         <p className="font-bold">{m.controls?.length || 0}</p>
                                       </div>
                                       <div className="bg-white p-2 rounded border border-slate-100">
                                         <p className="text-[9px] text-slate-400 font-bold uppercase">Forms</p>
                                         <p className="font-bold">{m.forms?.length || 0}</p>
                                       </div>
                                       <div className="bg-white p-2 rounded border border-slate-100">
                                         <p className="text-[9px] text-slate-400 font-bold uppercase">APIs</p>
                                         <p className="font-bold">{m.api_endpoints?.length || 0}</p>
                                       </div>
                                     </div>
                                     {m.inference_reason && <p className="text-xs text-amber-600 italic mt-2">{m.inference_reason}</p>}
                                   </div>
                                 ))}
                               </div>
                             </div>
)}
                            
                            {/* Relationships */}
                           {appUnderstanding.unified_model.relationships && appUnderstanding.unified_model.relationships.length > 0 && (
                             <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                               <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                                 <MdOutlineAnalytics className="text-cyan-500" /> Relationships ({appUnderstanding.unified_model.relationships.length})
                               </h3>
                               <div className="space-y-2 max-h-96 overflow-y-auto">
                                 {appUnderstanding.unified_model.relationships.slice(0, 100).map((r, idx) => {
                                   const relColors = {
                                     'contains': 'bg-blue-100 text-blue-700',
                                     'belongs_to': 'bg-indigo-100 text-indigo-700',
                                     'labels': 'bg-emerald-100 text-emerald-700',
                                     'associated_with': 'bg-slate-100 text-slate-600',
                                     'likely_triggers': 'bg-amber-100 text-amber-700',
                                     'submits_to': 'bg-orange-100 text-orange-700',
                                     'navigates_to': 'bg-cyan-100 text-cyan-700',
                                     'rendered_on': 'bg-violet-100 text-violet-700',
                                     'implements': 'bg-purple-100 text-purple-700',
                                     'satisfies': 'bg-emerald-100 text-emerald-700',
                                     'observed_with': 'bg-slate-100 text-slate-600',
                                   };
                                   const relColor = relColors[r.relationship] || 'bg-slate-100 text-slate-600';
                                   return (
                                     <div key={idx} className="bg-slate-50 p-3 rounded-lg border border-slate-100 flex items-center gap-3">
                                       <span className={`px-2 py-1 rounded text-[9px] font-bold uppercase ${relColor}`}>
                                         {r.relationship}
                                       </span>
                                       <span className="font-mono text-[10px] text-slate-700">{r.source_id}</span>
                                       <span className="text-slate-400 mx-1">→</span>
                                       <span className="font-mono text-[10px] text-slate-700">{r.target_id}</span>
                                       <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${
                                         r.observation_status === 'observed' ? 'bg-emerald-100 text-emerald-700' :
                                         r.observation_status === 'inferred' ? 'bg-blue-100 text-blue-700' :
                                         'bg-slate-100 text-slate-500'
                                       }`}>
                                         {r.observation_status}
                                       </span>
                                       {r.confidence !== null && r.confidence !== undefined && (
                                         <span className="px-2 py-1 bg-blue-100 text-blue-700 text-[9px] font-bold uppercase rounded">
                                           {Math.round(r.confidence * 100)}%
                                         </span>
                                       )}
                                     </div>
                                   );
                                 })}
                                 {appUnderstanding.unified_model.relationships.length > 100 && (
                                   <p className="text-[10px] text-slate-400 text-center mt-2">... and {appUnderstanding.unified_model.relationships.length - 100} more relationships</p>
                                 )}
                               </div>
                             </div>
                           )}
 
                           {/* Requirements Traceability */}
                           {appUnderstanding.unified_model.requirements && appUnderstanding.unified_model.requirements.length > 0 && (
                             <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                               <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                                 <MdOutlineAssessment className="text-amber-500" /> Requirements Traceability ({appUnderstanding.unified_model.requirements.length})
                               </h3>
                               <div className="space-y-3">
                                 {appUnderstanding.unified_model.requirements.map((req, idx) => (
                                   <div key={idx} className="bg-slate-50 p-4 rounded-lg border border-slate-100">
                                     <div className="flex items-center gap-2 mb-2">
                                       <span className="px-2 py-1 bg-amber-100 text-amber-700 text-[9px] font-bold uppercase rounded">{req.id}</span>
                                       <span className="px-2 py-1 bg-amber-100 text-amber-700 text-[9px] font-bold uppercase rounded">{req.observation_status}</span>
                                     </div>
                                     <p className="text-sm text-slate-700">{req.description}</p>
                                     {req.keywords && req.keywords.length > 0 && (
                                       <div className="flex flex-wrap gap-1 mt-2">
                                         {req.keywords.slice(0, 10).map((kw, ki) => (
                                           <span key={ki} className="px-1.5 py-0.5 bg-amber-100 text-amber-700 text-[9px] font-bold uppercase rounded">{kw}</span>
                                         ))}
                                       </div>
                                     )}
                                   </div>
                                 ))}
                               </div>
                             </div>
)}
                            
                            {/* Repository Traceability */}
                           {appUnderstanding.unified_model.modules && appUnderstanding.unified_model.modules.some(m => m.repository_refs && m.repository_refs.length > 0) && (
                             <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                               <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                                 <RiGithubFill className="text-slate-500" /> Repository Traceability
                               </h3>
                               <div className="space-y-4">
                                 {appUnderstanding.unified_model.modules.filter(m => m.repository_refs && m.repository_refs.length > 0).map((m, idx) => (
                                   <div key={idx} className="bg-slate-50 p-4 rounded-lg border border-slate-100">
                                     <p className="font-semibold text-slate-800 mb-2">{m.name}</p>
                                     <div className="space-y-1">
                                       {m.repository_refs.map((ref, ri) => (
                                         <div key={ri} className="flex gap-2 text-xs">
                                           <span className="px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded text-slate-700 font-mono">{ref.symbol}</span>
                                           <span className="text-slate-600 truncate max-w-[300px]">{ref.file}</span>
                                           <span className="px-1.5 py-0.5 bg-slate-100 text-slate-500 text-[9px] font-bold uppercase rounded">{ref.match_reason}</span>
                                         </div>
                                       ))}
                                     </div>
                                   </div>
                                 ))}
                               </div>
                             </div>
                           )}
                         </div>
                       ) : (
                         <div className="bg-slate-100/50 border-2 border-dashed border-slate-200 rounded-3xl h-[400px] flex flex-col items-center justify-center text-center px-10">
                           <MdOutlineAnalytics className="text-slate-300 text-6xl mb-6" />
                           <h3 className="text-lg font-bold text-slate-800 mb-2">Unified Application Model</h3>
                           <p className="text-sm text-slate-500 max-w-sm">Run Application Understanding to generate the unified cross-modal model.</p>
                         </div>
                       )}
                     </div>
                   )}

              {/* Interaction Tabs */}
              <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-sm min-h-[500px] flex flex-col">
                <div className="flex border-b border-slate-100 shrink-0 overflow-x-auto no-scrollbar bg-slate-50/50">
                  {['Overview', 'Test Cases', 'Browser Actions', 'Auto-Heal', 'Final Report', 'App Understanding', 'Unified Model', 'Test Generation'].map(tab => (
                    <button
                      key={tab}
                      onClick={() => setActiveTab(tab)}
                      className={`px-6 py-4 text-xs font-bold transition-all whitespace-nowrap border-b-2 ${
                        activeTab === tab ? 'border-violet-600 text-violet-600 bg-white' : 'border-transparent text-slate-500 hover:text-slate-800'
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
                                    <span className="w-1.5 h-1.5 bg-violet-500 rounded-full" />
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
                                              <MdAutoFixNormal /> Healed
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
                          </div>
                       ))}
                    </div>
                  )}

                  {activeTab === 'Auto-Heal' && (
                    <div className="space-y-8">
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
                                        {h.status === 'Success' ? 'Auto-Healed' : 'Failed'}
                                     </span>
                                     <p className="text-[10px] text-slate-400 mt-2 font-bold tracking-widest">{new Date(h.timestamp + 'Z').toLocaleTimeString()}</p>
                                  </div>
                               </div>
                            </div>
                          ))}
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
                                     <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Confidence Score</p>
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
                                  <h3 className="text-xs font-black text-slate-400 uppercase tracking-[0.2em] border-b border-slate-100 pb-2">Recommendations</h3>
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
                            <p className="text-sm font-bold text-slate-400 uppercase tracking-widest">Generating Final Report...</p>
                         </div>
                       )}
                    </div>
                  )}

                  {activeTab === 'Repo Intel' && runDetails?.repo_intelligence && (
                    <div className="space-y-8 animate-in backdrop-blur-sm">
                      <div className="grid md:grid-cols-2 gap-8">
                        <div className="space-y-4">
                          <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest">Tech Stack</h3>
                          <div className="grid grid-cols-2 gap-3">
                             <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                               <p className="text-[10px] text-slate-400 font-bold uppercase mb-1">Backend</p>
                               <p className="text-sm font-black text-slate-800">{runDetails.repo_intelligence.analysis?.tech_stack?.backend || 'Unknown'}</p>
                             </div>
                             <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                               <p className="text-[10px] text-slate-400 font-bold uppercase mb-1">Frontend</p>
                               <p className="text-sm font-black text-slate-800">{runDetails.repo_intelligence.analysis?.tech_stack?.frontend || 'Unknown'}</p>
                             </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {activeTab === 'App Understanding' && (
                    <div className="space-y-8">
                      {appUnderstanding ? (
                        <div className="space-y-8">
                          {/* Application Identity */}
                          <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                            <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                              <MdOutlineAnalytics className="text-blue-500" /> Application Identity
                            </h3>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                              <div>
                                <p className="text-[10px] text-slate-400 font-bold uppercase mb-1">Application Name</p>
                                <p className="text-sm font-black text-slate-800">{appUnderstanding.app_name || 'Not identified'}</p>
                              </div>
                              <div>
                                <p className="text-[10px] text-slate-400 font-bold uppercase mb-1">Application Type</p>
                                <p className="text-sm font-black text-slate-800">{appUnderstanding.app_type || 'Unknown'}</p>
                              </div>
                              <div>
                                <p className="text-[10px] text-slate-400 font-bold uppercase mb-1">Framework</p>
                                <p className="text-sm font-black text-slate-800">{appUnderstanding.framework || 'Not detected'}</p>
                              </div>
                              <div>
                                <p className="text-[10px] text-slate-400 font-bold uppercase mb-1">Module</p>
                                <p className="text-sm font-black text-slate-800">{appUnderstanding.module_name || 'Not specified'}</p>
                              </div>
                            </div>
                          </div>

{/* Phase 1.5A — Crawl Summary */}
                           {appUnderstanding.crawl_metadata && Object.keys(appUnderstanding.crawl_metadata).length > 0 && (
                             <div className="bg-gradient-to-br from-violet-50 to-indigo-50 border border-violet-100 rounded-2xl p-6 shadow-sm">
                               <h3 className="text-xs font-black text-violet-600 uppercase tracking-widest mb-4 flex items-center gap-2">
                                 <MdOutlineLanguage className="text-violet-500" /> Crawl Summary
                               </h3>
                               <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                 {[
                                   { label: 'Pages Discovered', value: appUnderstanding.crawl_metadata.pages_discovered ?? '—' },
                                   { label: 'Pages Analyzed', value: appUnderstanding.crawl_metadata.pages_analyzed ?? '—' },
                                   { label: 'Pages Failed', value: appUnderstanding.crawl_metadata.pages_failed ?? '—' },
                                   { label: 'Max Depth', value: appUnderstanding.crawl_metadata.max_depth ?? '—' },
                                   { label: 'Max Pages', value: appUnderstanding.crawl_metadata.max_pages ?? '—' },
                                   { label: 'Duration', value: appUnderstanding.crawl_metadata.duration_seconds ? `${appUnderstanding.crawl_metadata.duration_seconds}s` : '—' },
                                   { label: 'Same Domain', value: appUnderstanding.crawl_metadata.same_domain_only ? 'Yes' : 'No' },
                                   { label: 'Start URL', value: appUnderstanding.url || '—' },
                                   // Phase 1.5C — Network metadata
                                   { label: 'Network Requests', value: appUnderstanding.crawl_metadata.network_requests ?? '—' },
                                   { label: 'Network Responses', value: appUnderstanding.crawl_metadata.network_responses ?? '—' },
                                   { label: 'Network Failures', value: appUnderstanding.crawl_metadata.network_failures ?? '—' },
                                   { label: 'API Candidates', value: appUnderstanding.crawl_metadata.api_candidates ?? '—' },
                                 ].map((stat, i) => (
                                   <div key={i} className="bg-white/80 p-3 rounded-xl border border-violet-100">
                                     <p className="text-[10px] text-violet-400 font-bold uppercase mb-1">{stat.label}</p>
                                     <p className="text-sm font-black text-slate-800 truncate" title={String(stat.value)}>{String(stat.value)}</p>
                                   </div>
                                 ))}
                               </div>
                               {appUnderstanding.crawl_metadata.warnings && appUnderstanding.crawl_metadata.warnings.length > 0 && (
                                 <div className="mt-3 space-y-1">
                                   {appUnderstanding.crawl_metadata.warnings.map((w, i) => (
                                     <p key={i} className="text-[11px] text-amber-600 bg-amber-50 px-3 py-1.5 rounded-lg border border-amber-100">
                                       ⚠ {w}
                                     </p>
                                   ))}
                                 </div>
                               )}
                             </div>
                           )}

                           {/* Phase 1.5A — Discovered Pages */}
                           {appUnderstanding.pages && appUnderstanding.pages.length > 0 && (
                             <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                               <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                                 <MdOutlineLanguage className="text-indigo-500" /> Discovered Pages ({appUnderstanding.pages.length})
                               </h3>
                               <div className="overflow-x-auto">
                                 <table className="w-full text-left text-xs">
                                   <thead>
                                     <tr className="text-slate-400 border-b border-slate-100 uppercase tracking-wider font-bold">
                                       <th className="py-2 pl-2">Path</th>
                                       <th className="py-2">Title</th>
                                       <th className="py-2">Type</th>
                                       <th className="py-2">Depth</th>
                                       <th className="py-2">Status</th>
                                     </tr>
                                   </thead>
                                   <tbody className="divide-y divide-slate-50">
                                     {appUnderstanding.pages.slice(0, 25).map((p, i) => {
                                       let path = '/';
                                       try { path = new URL(p.url || '').pathname || p.url; } catch { path = p.url || '/'; }
                                       const statusColor = p.crawl_status === 'success' ? 'text-emerald-600 bg-emerald-50' :
                                         p.crawl_status === 'authentication_required' ? 'text-amber-600 bg-amber-50' :
                                         'text-red-600 bg-red-50';
                                       const typeColor = p.page_type_confidence === 'observed' ? 'bg-blue-100 text-blue-700' : 'bg-slate-100 text-slate-600';
                                       return (
                                         <tr key={i} className="hover:bg-slate-50/50">
                                           <td className="py-3 pl-2 font-mono text-[10px] text-slate-600 max-w-[180px] truncate" title={path}>{path}</td>
                                           <td className="py-3 text-slate-700 max-w-[160px] truncate" title={p.title}>{p.title || '—'}</td>
                                           <td className="py-3">
                                             <span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase ${typeColor}`}>
                                               {p.page_type || 'unknown'}
                                             </span>
                                           </td>
                                           <td className="py-3 text-slate-500 font-bold">{p.depth ?? '—'}</td>
                                           <td className="py-3">
                                             <span className={`px-2 py-0.5 rounded text-[9px] font-bold ${statusColor}`}>
                                               {p.crawl_status || '—'}
                                             </span>
                                           </td>
                                         </tr>
                                       );
                                     })}
                                   </tbody>
                                 </table>
                                 {appUnderstanding.pages.length > 25 && (
                                   <p className="text-[10px] text-slate-400 text-center mt-2">... and {appUnderstanding.pages.length - 25} more pages</p>
                                 )}
                               </div>
                             </div>
                           )}

                           {/* Phase 1.5B — UI Structure */}
                           {appUnderstanding.pages && appUnderstanding.pages.length > 0 && (
                             <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                               <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                                 <MdOutlineRule className="text-violet-500" /> UI Structure
                               </h3>
                               <div className="space-y-4">
                                 {appUnderstanding.pages.slice(0, 10).map((p, i) => {
                                   const dom = p.dom || {};
                                   const ax = p.accessibility_tree || {};
                                   const insights = p.ui_insights || {};
                                   const interactiveCount = insights.interactive_element_count ?? dom.interactive_elements?.length ?? 0;
                                   const formCount = insights.form_count ?? dom.forms?.length ?? 0;
                                   const landmarkCount = insights.landmark_count ?? dom.landmarks?.length ?? 0;
                                   const axNodeCount = insights.accessibility_node_count ?? ax.node_count ?? 0;
                                   const axSource = ax.source || 'unknown';
                                   let path = '/';
                                   try { path = new URL(p.url || '').pathname || p.url; } catch { path = p.url || '/'; }
                                   return (
                                     <div key={i} className="border border-slate-100 rounded-xl p-4 hover:border-violet-200 transition-colors cursor-pointer bg-slate-50/30"
                                          onClick={() => setSelectedPageForUI(p)}>
                                       <div className="flex items-start justify-between gap-4">
                                         <div className="flex-1 min-w-0">
                                           <div className="flex items-center gap-2 mb-2">
                                             <p className="font-mono text-[10px] text-slate-600 max-w-[200px] truncate" title={path}>{path}</p>
                                             <span className="px-1.5 py-0.5 bg-violet-100 text-violet-700 text-[9px] font-bold uppercase rounded">
                                               {axSource}
                                             </span>
                                           </div>
                                           <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                                             <div className="bg-white p-2 rounded-lg border border-slate-100">
                                               <p className="text-[10px] text-slate-400 font-bold uppercase">Interactive</p>
                                               <p className="text-sm font-black text-slate-800">{interactiveCount}</p>
                                             </div>
                                             <div className="bg-white p-2 rounded-lg border border-slate-100">
                                               <p className="text-[10px] text-slate-400 font-bold uppercase">Forms</p>
                                               <p className="text-sm font-black text-slate-800">{formCount}</p>
                                             </div>
                                             <div className="bg-white p-2 rounded-lg border border-slate-100">
                                               <p className="text-[10px] text-slate-400 font-bold uppercase">Landmarks</p>
                                               <p className="text-sm font-black text-slate-800">{landmarkCount}</p>
                                             </div>
                                             <div className="bg-white p-2 rounded-lg border border-slate-100">
                                               <p className="text-[10px] text-slate-400 font-bold uppercase">AX Nodes</p>
                                               <p className="text-sm font-black text-slate-800">{axNodeCount}</p>
                                             </div>
                                           </div>
                                           {insights.has_login_controls && (
                                             <span className="inline-flex items-center gap-1 mt-2 px-2 py-0.5 bg-blue-50 text-blue-700 text-[9px] font-bold uppercase rounded border border-blue-100">
                                               Login Controls
                                             </span>
                                           )}
                                           {insights.has_search_controls && (
                                             <span className="inline-flex items-center gap-1 mt-2 ml-1 px-2 py-0.5 bg-emerald-50 text-emerald-700 text-[9px] font-bold uppercase rounded border border-emerald-100">
                                               Search Controls
                                             </span>
                                           )}
                                           {insights.has_submission_controls && (
                                             <span className="inline-flex items-center gap-1 mt-2 ml-1 px-2 py-0.5 bg-amber-50 text-amber-700 text-[9px] font-bold uppercase rounded border border-amber-100">
                                               Submission Controls
                                             </span>
                                           )}
                                         </div>
                                         <RiArrowRightLine className="text-slate-400 shrink-0 mt-1" />
                                       </div>
                                     </div>
                                   );
                                 })}
                                 {appUnderstanding.pages.length > 10 && (
                                   <p className="text-[10px] text-slate-400 text-center mt-2">... and {appUnderstanding.pages.length - 10} more pages</p>
                                 )}
                               </div>
                             </div>
                           )}

                          {/* Phase 1.5B — Selected Page UI Detail */}
                          {selectedPageForUI && (
                            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                              <div className="flex items-center justify-between mb-4">
                                <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest flex items-center gap-2">
                                  <MdOutlineRule className="text-violet-500" /> UI Structure Detail
                                </h3>
                                <button onClick={() => setSelectedPageForUI(null)} className="text-slate-400 hover:text-slate-600">
                                  <RiCloseLine className="text-xl" />
                                </button>
                              </div>
                              <div className="space-y-6">
                                {/* Interactive Elements */}
                                {(selectedPageForUI.dom?.interactive_elements?.length > 0) && (
                                  <div>
                                    <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                                      <MdOutlineLanguage className="text-indigo-500" /> Interactive Elements ({selectedPageForUI.dom.interactive_elements.length})
                                    </h4>
                                    <div className="space-y-2 max-h-60 overflow-y-auto">
                                      {selectedPageForUI.dom.interactive_elements.slice(0, 30).map((el, idx) => (
                                        <div key={idx} className="bg-slate-50 p-3 rounded-lg border border-slate-100 text-xs">
                                          <div className="flex items-center gap-2 mb-1">
                                            <span className="px-1.5 py-0.5 bg-violet-100 text-violet-700 text-[9px] font-bold uppercase rounded">{el.tag}</span>
                                            {el.role && <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 text-[9px] font-bold uppercase rounded">{el.role}</span>}
                                            {el.type && <span className="px-1.5 py-0.5 bg-emerald-100 text-emerald-700 text-[9px] font-bold uppercase rounded">{el.type}</span>}
                                            {el.visible === false && <span className="px-1.5 py-0.5 bg-slate-100 text-slate-500 text-[9px] font-bold uppercase rounded">Hidden</span>}
                                            {el.disabled && <span className="px-1.5 py-0.5 bg-red-100 text-red-700 text-[9px] font-bold uppercase rounded">Disabled</span>}
                                            {el.required && <span className="px-1.5 py-0.5 bg-amber-100 text-amber-700 text-[9px] font-bold uppercase rounded">Required</span>}
                                          </div>
                                          <div className="text-slate-600 font-mono text-[10px] space-y-0.5">
                                            {el.id && <span>id: {el.id}</span>}
                                            {el.name && <span>name: {el.name}</span>}
                                            {el.aria_label && <span>aria-label: {el.aria_label}</span>}
                                            {el.text && <span>text: {el.text}</span>}
                                            {el.placeholder && <span>placeholder: {el.placeholder}</span>}
                                            {el.href && <span>href: {el.href}</span>}
                                            {el.bounding_box && <span>bbox: {Math.round(el.bounding_box.x)},{Math.round(el.bounding_box.y)} {Math.round(el.bounding_box.width)}x{Math.round(el.bounding_box.height)}</span>}
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                {/* Forms */}
                                {(selectedPageForUI.dom?.forms?.length > 0) && (
                                  <div>
                                    <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                                      <MdOutlineFactCheck className="text-emerald-500" /> Forms ({selectedPageForUI.dom.forms.length})
                                    </h4>
                                    <div className="space-y-3">
                                      {selectedPageForUI.dom.forms.map((form, fIdx) => (
                                        <div key={fIdx} className="bg-slate-50 p-4 rounded-lg border border-slate-100">
                                          <div className="flex items-center gap-2 mb-2 text-xs">
                                            {form.id && <span className="font-mono text-slate-600">#{form.id}</span>}
                                            {form.name && <span className="text-slate-500">{form.name}</span>}
                                            <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 text-[9px] font-bold uppercase rounded">{form.method.toUpperCase()}</span>
                                            {form.action && <span className="text-slate-500 font-mono text-[10px] truncate max-w-[200px]">{form.action}</span>}
                                            {form.validation_attrs?.novalidate && <span className="px-1.5 py-0.5 bg-amber-100 text-amber-700 text-[9px] font-bold uppercase rounded">No Validate</span>}
                                          </div>
                                          <div className="space-y-1">
                                            {form.inputs?.map((inp, iIdx) => (
                                              <div key={iIdx} className="bg-white p-2 rounded border border-slate-100 text-[10px]">
                                                <div className="flex items-center gap-2">
                                                  <span className="px-1 py-0.5 bg-slate-100 text-slate-600 text-[9px] font-bold uppercase rounded">{inp.tag}</span>
                                                  <span className="px-1 py-0.5 bg-violet-100 text-violet-700 text-[9px] font-bold uppercase rounded">{inp.type}</span>
                                                  {inp.required && <span className="px-1 py-0.5 bg-amber-100 text-amber-700 text-[9px] font-bold uppercase rounded">Required</span>}
                                                  {inp.disabled && <span className="px-1 py-0.5 bg-red-100 text-red-700 text-[9px] font-bold uppercase rounded">Disabled</span>}
                                                  {inp.value_presence && <span className="px-1 py-0.5 bg-emerald-100 text-emerald-700 text-[9px] font-bold uppercase rounded">Has Value</span>}
                                                </div>
                                                <div className="text-slate-600 ml-6 mt-1 space-y-0.5 font-mono text-[10px]">
                                                  {inp.name && <span>name: {inp.name}</span>}
                                                  {inp.id && <span>id: {inp.id}</span>}
                                                  {inp.placeholder && <span>placeholder: {inp.placeholder}</span>}
                                                  {inp.aria_label && <span>aria-label: {inp.aria_label}</span>}
                                                  {inp.aria_describedby && <span>aria-describedby: {inp.aria_describedby}</span>}
                                                </div>
                                              </div>
                                            ))}
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                {/* Landmarks */}
                                {(selectedPageForUI.dom?.landmarks?.length > 0) && (
                                  <div>
                                    <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                                      <MdOutlineAnalytics className="text-blue-500" /> Landmarks ({selectedPageForUI.dom.landmarks.length})
                                    </h4>
                                    <div className="space-y-2">
                                      {selectedPageForUI.dom.landmarks.map((lm, idx) => (
                                        <div key={idx} className="bg-slate-50 p-3 rounded-lg border border-slate-100 flex items-center gap-3 text-xs">
                                          <span className="px-2 py-1 bg-blue-100 text-blue-700 text-[9px] font-bold uppercase rounded">{lm.type}</span>
                                          <span className="px-2 py-1 bg-violet-100 text-violet-700 text-[9px] font-bold uppercase rounded">{lm.role}</span>
                                          <span className="font-mono text-slate-600">{lm.tag}</span>
                                          {lm.id && <span className="text-slate-500 font-mono text-[10px]">#{lm.id}</span>}
                                          {lm.label && <span className="text-slate-600">"{lm.label}"</span>}
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                {/* Accessibility Tree */}
                                {(selectedPageForUI.accessibility_tree?.root) && (
                                  <div>
                                    <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                                      <MdOutlineAssessment className="text-amber-500" /> Accessibility Tree (Source: {selectedPageForUI.accessibility_tree.source})
                                    </h4>
                                    <div className="bg-slate-50 p-3 rounded-lg border border-slate-100 max-h-80 overflow-y-auto">
                                      <pre className="text-[9px] font-mono text-slate-700 whitespace-pre-wrap">
                                        {JSON.stringify(selectedPageForUI.accessibility_tree.root, null, 2)}
                                      </pre>
                                    </div>
                                  </div>
                                )}

                                {/* Text Summary */}
                                {(selectedPageForUI.dom?.text_summary?.length > 0) && (
                                  <div>
                                    <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                                      <MdInfo className="text-cyan-500" /> Text Summary ({selectedPageForUI.dom.text_summary.length})
                                    </h4>
                                    <div className="space-y-1 max-h-40 overflow-y-auto">
                                      {selectedPageForUI.dom.text_summary.slice(0, 40).map((txt, idx) => (
                                        <div key={idx} className="bg-slate-50 p-2 rounded border border-slate-100 flex items-center gap-2 text-xs">
                                          <span className="px-1.5 py-0.5 bg-cyan-100 text-cyan-700 text-[9px] font-bold uppercase rounded">{txt.type}</span>
                                          <span className="text-slate-700 truncate">{txt.text}</span>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}

                                {/* Phase 1.5C — Network Activity */}
                                {(selectedPageForUI.network_activity?.length > 0) && (
                                  <div>
                                    <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                                      <MdOutlineLanguage className="text-orange-500" /> Network Activity ({selectedPageForUI.network_activity.length})
                                    </h4>
                                    <div className="space-y-2 max-h-80 overflow-y-auto">
                                      {selectedPageForUI.network_activity.slice(0, 50).map((activity, idx) => {
                                        const method = activity.method || 'GET';
                                        const url = activity.url || '';
                                        const resourceType = activity.resource_type || '';
                                        const isApiCandidate = activity.is_api_candidate;
                                        const networkCategory = activity.network_category || '';
                                        const hasResponse = !!activity.response;
                                        const status = hasResponse ? activity.response.status : (activity.request_failed ? 'FAILED' : '—');
                                        const contentType = hasResponse ? activity.response.content_type : '';
                                        const methodColor = method === 'GET' ? 'text-emerald-600' :
                                                          method === 'POST' ? 'text-blue-600' :
                                                          method === 'PUT' || method === 'PATCH' ? 'text-amber-600' :
                                                          method === 'DELETE' ? 'text-red-600' : 'text-slate-600';
                                        const statusColor = hasResponse && status >= 200 && status < 300 ? 'text-emerald-600' :
                                                          hasResponse && status >= 400 ? 'text-red-600' :
                                                          hasResponse && status >= 300 ? 'text-amber-600' : 'text-slate-500';
                                        return (
                                          <div key={idx} className="bg-slate-50 p-3 rounded-lg border border-slate-100">
                                            <div className="flex items-center gap-2 flex-wrap mb-1">
                                              <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${methodColor} bg-white border border-slate-200`}>
                                                {method}
                                              </span>
                                              <span className="px-1.5 py-0.5 bg-violet-100 text-violet-700 text-[9px] font-bold uppercase rounded">{resourceType}</span>
                                              {isApiCandidate && <span className="px-1.5 py-0.5 bg-violet-100 text-violet-700 text-[9px] font-bold uppercase rounded">API Candidate</span>}
                                              {networkCategory && <span className="px-1.5 py-0.5 bg-slate-100 text-slate-600 text-[9px] font-bold uppercase rounded">{networkCategory}</span>}
                                              {activity.request_failed && <span className="px-1.5 py-0.5 bg-red-100 text-red-700 text-[9px] font-bold uppercase rounded">Failed</span>}
                                            </div>
                                            <div className="text-slate-600 font-mono text-[10px] space-y-0.5">
                                              <span className="truncate block">{url}</span>
                                              <div className="flex items-center gap-3 text-[9px]">
                                                <span className={`font-bold ${statusColor}`}>{status}</span>
                                                {contentType && <span className="text-cyan-600">{contentType}</span>}
                                                {activity.has_post_data && <span className="text-amber-600">Has Body ({activity.post_data_size}B)</span>}
                                                {activity.request_failed && <span className="text-red-600">{activity.failure_text}</span>}
                                              </div>
                                            </div>
                                          </div>
                                        );
                                      })}
                                      {selectedPageForUI.network_activity.length > 50 && (
                                        <p className="text-[10px] text-slate-400 text-center mt-2">... and {selectedPageForUI.network_activity.length - 50} more requests</p>
                                      )}
                                    </div>
                                  </div>
                                )}

                                {/* Phase 1.5D — Screenshot Evidence */}
                                {(selectedPageForUI.screenshot && selectedPageForUI.screenshot.status === 'success') && (
                                  <div>
                                    <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                                      <MdOutlineAnalytics className="text-purple-500" /> Screenshot Evidence
                                    </h4>
                                    <div className="bg-slate-50 p-3 rounded-lg border border-slate-100">
                                      <div className="flex items-center gap-3 mb-2">
                                        <span className="px-2 py-1 bg-purple-100 text-purple-700 text-[9px] font-bold uppercase rounded">
                                          {selectedPageForUI.screenshot.capture_type || 'viewport'}
                                        </span>
                                        <span className="px-2 py-1 bg-blue-100 text-blue-700 text-[9px] font-bold uppercase rounded">
                                          {selectedPageForUI.screenshot.format?.toUpperCase() || 'PNG'}
                                        </span>
                                        <span className="px-2 py-1 bg-emerald-100 text-emerald-700 text-[9px] font-bold uppercase rounded">
                                          {selectedPageForUI.screenshot.size_bytes ? `${Math.round(selectedPageForUI.screenshot.size_bytes / 1024)} KB` : '—'}
                                        </span>
                                        <span className="px-2 py-1 bg-cyan-100 text-cyan-700 text-[9px] font-bold uppercase rounded">
                                          {selectedPageForUI.screenshot.width}x{selectedPageForUI.screenshot.height}
                                        </span>
                                      </div>
                                      <div className="space-y-1 text-[10px] font-mono text-slate-600">
                                        <div className="flex justify-between">
                                          <span>SHA256:</span>
                                          <span className="truncate max-w-[300px]">{selectedPageForUI.screenshot.sha256 || '—'}</span>
                                        </div>
                                        <div className="flex justify-between">
                                          <span>Path:</span>
                                          <span className="truncate max-w-[300px]">{selectedPageForUI.screenshot.path || '—'}</span>
                                        </div>
                                        <div className="flex justify-between">
                                          <span>Captured:</span>
                                          <span>{selectedPageForUI.screenshot.timestamp ? new Date(selectedPageForUI.screenshot.timestamp * 1000).toLocaleString() : '—'}</span>
                                        </div>
                                        <div className="flex justify-between">
                                          <span>Duration:</span>
                                          <span>{selectedPageForUI.screenshot.capture_duration_ms || '—'} ms</span>
                                        </div>
                                      </div>
                                      {/* Note: Actual image not displayed inline due to storage architecture - 
                                      screenshots are stored on filesystem and referenced by path */}
                                      <p className="text-[9px] text-slate-400 mt-2 italic">
                                        Screenshot stored on filesystem at: {selectedPageForUI.screenshot.path || 'N/A'}
                                      </p>
                                    </div>
                                  </div>
                                )}
                                {(selectedPageForUI.screenshot && selectedPageForUI.screenshot.status !== 'success') && (
                                  <div>
                                    <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                                      <MdOutlineAnalytics className="text-purple-500" /> Screenshot Evidence
                                    </h4>
                                    <div className="bg-amber-50 p-3 rounded-lg border border-amber-100 text-xs text-amber-700">
                                      Status: {selectedPageForUI.screenshot.status || 'unknown'}
                                      {selectedPageForUI.screenshot.error && (
                                        <span className="ml-2">Error: {selectedPageForUI.screenshot.error}</span>
                                      )}
                                      {selectedPageForUI.screenshot.reason && (
                                        <span className="ml-2">Reason: {selectedPageForUI.screenshot.reason}</span>
                                      )}
                                    </div>
                                  </div>
                                )}
                              </div>
                            </div>
                          )}

                          {/* Phase 1.5E — Visual UI Evidence (OmniParser) */}
                          {(selectedPageForUI?.visual_ui && selectedPageForUI?.visual_ui?.status === 'success') && (
                            <div>
                              <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                                <MdOutlineAnalytics className="text-indigo-500" /> Visual UI Evidence
                              </h4>
                              <div className="bg-slate-50 p-3 rounded-lg border border-slate-100">
                                <div className="flex items-center gap-3 mb-3 flex-wrap">
                                  <span className="px-2 py-1 bg-indigo-100 text-indigo-700 text-[9px] font-bold uppercase rounded">
                                    {selectedPageForUI?.visual_ui?.parser || 'omniparser'}
                                  </span>
                                  <span className="px-2 py-1 bg-blue-100 text-blue-700 text-[9px] font-bold uppercase rounded">
                                    v{selectedPageForUI?.visual_ui?.parser_version || '—'}
                                  </span>
                                  <span className="px-2 py-1 bg-emerald-100 text-emerald-700 text-[9px] font-bold uppercase rounded">
                                    {selectedPageForUI?.visual_ui?.model_version || '—'}
                                  </span>
                                  <span className="px-2 py-1 bg-cyan-100 text-cyan-700 text-[9px] font-bold uppercase rounded">
                                    {selectedPageForUI?.visual_ui?.image_width}x{selectedPageForUI?.visual_ui?.image_height}
                                  </span>
                                  <span className="px-2 py-1 bg-violet-100 text-violet-700 text-[9px] font-bold uppercase rounded">
                                    {selectedPageForUI?.visual_ui?.elements?.length || 0} elements
                                  </span>
                                  {selectedPageForUI?.visual_ui?.parse_duration_ms && (
                                    <span className="px-2 py-1 bg-amber-100 text-amber-700 text-[9px] font-bold uppercase rounded">
                                      {Math.round(selectedPageForUI?.visual_ui?.parse_duration_ms)}ms
                                    </span>
                                  )}
                                </div>
                                <div className="space-y-1 text-[10px] font-mono text-slate-600 mb-3">
                                  <div className="flex justify-between">
                                    <span>SHA256:</span>
                                    <span className="truncate max-w-[300px]">{selectedPageForUI?.visual_ui?.screenshot_sha256 || '—'}</span>
                                  </div>
                                </div>
                                {/* Visual Elements List */}
                                {(selectedPageForUI?.visual_ui?.elements && selectedPageForUI.visual_ui.elements.length > 0) && (
                                  <div className="space-y-2 max-h-96 overflow-y-auto">
                                    <p className="text-[9px] text-slate-400 font-bold uppercase tracking-wider mb-2">Detected Elements:</p>
                                    {selectedPageForUI?.visual_ui?.elements.slice(0, 50).map((el, idx) => (
                                      <div key={idx} className="bg-white p-3 rounded-lg border border-slate-100 text-[10px]">
                                        <div className="flex items-center gap-2 mb-1 flex-wrap">
                                          <span className="px-1.5 py-0.5 bg-indigo-100 text-indigo-700 text-[9px] font-bold uppercase rounded">{el.type}</span>
                                          {el.source && <span className="px-1.5 py-0.5 bg-slate-100 text-slate-600 text-[9px] font-bold uppercase rounded">{el.source}</span>}
                                          {el.interactable === true && <span className="px-1.5 py-0.5 bg-emerald-100 text-emerald-700 text-[9px] font-bold uppercase rounded">Interactable</span>}
                                          {el.interactable === false && <span className="px-1.5 py-0.5 bg-red-100 text-red-700 text-[9px] font-bold uppercase rounded">Non-interactable</span>}
                                          {el.confidence !== null && el.confidence !== undefined && (
                                            <span className="px-1.5 py-0.5 bg-blue-100 text-blue-700 text-[9px] font-bold uppercase rounded">
                                              {Math.round(el.confidence * 100)}%
                                            </span>
                                          )}
                                        </div>
                                        <div className="text-slate-600 font-mono text-[10px] space-y-0.5 ml-2">
                                          {el.text && <span>text: {el.text}</span>}
                                          {el.caption && <span>caption: {el.caption}</span>}
                                          <span>bbox (px): [{el.bbox_pixels?.join(', ')}]</span>
                                          <span>bbox (norm): [{el.bbox_normalized?.map(v => v.toFixed(4)).join(', ')}]</span>
                                        </div>
                                      </div>
                                    ))}
                                    {selectedPageForUI?.visual_ui?.elements.length > 50 && (
                                      <p className="text-[10px] text-slate-400 text-center mt-2">... and {selectedPageForUI.visual_ui.elements.length - 50} more elements</p>
                                    )}
                                  </div>
                                )}
                              </div>
                            </div>
                          )}
                          {(selectedPageForUI?.visual_ui && selectedPageForUI.visual_ui.status !== 'success' && selectedPageForUI.visual_ui.status !== 'skipped') && (
                            <div>
                              <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                                <MdOutlineAnalytics className="text-indigo-500" /> Visual UI Evidence
                              </h4>
                              <div className="bg-amber-50 p-3 rounded-lg border border-amber-100 text-xs text-amber-700">
                                Status: {selectedPageForUI.visual_ui.status || 'unknown'}
                                {selectedPageForUI.visual_ui.error_code && (
                                  <span className="ml-2">Error: {selectedPageForUI.visual_ui.error_code}</span>
                                )}
                                {selectedPageForUI.visual_ui.message && (
                                  <span className="ml-2">Message: {selectedPageForUI.visual_ui.message}</span>
                                )}
                                {selectedPageForUI.visual_ui.reason && (
                                  <span className="ml-2">Reason: {selectedPageForUI.visual_ui.reason}</span>
                                )}
                              </div>
                            </div>
                          )}
                          {(selectedPageForUI?.visual_ui && selectedPageForUI.visual_ui.status === 'skipped') && (
                            <div>
                              <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3 flex items-center gap-2">
                                <MdOutlineAnalytics className="text-indigo-500" /> Visual UI Evidence
                              </h4>
                              <div className="bg-slate-50 p-3 rounded-lg border border-slate-100 text-xs text-slate-600">
                                Skipped: {selectedPageForUI.visual_ui.reason || selectedPageForUI.visual_ui.message || 'unknown reason'}
                              </div>
                            </div>
                          )}

                           {/* Technology Stack */}
                          {Object.keys(appUnderstanding.technology_stack || {}).length > 0 && (
                            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                              <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                                <MdOutlineRule className="text-emerald-500" /> Technology Stack
                              </h3>
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                {Object.entries(appUnderstanding.technology_stack).map(([key, value]) => (
                                  <div key={key} className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                                    <p className="text-[10px] text-slate-400 font-bold uppercase mb-1">{key.charAt(0).toUpperCase() + key.slice(1)}</p>
                                    <p className="text-sm font-black text-slate-800">{typeof value === 'object' ? JSON.stringify(value) : value}</p>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Modules / Features */}
                          {(appUnderstanding.modules && appUnderstanding.modules.length > 0) || (appUnderstanding.features && appUnderstanding.features.length > 0) && (
                            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                              <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                                <MdOutlineFactCheck className="text-violet-500" /> Modules & Features
                              </h3>
                              <div className="space-y-2">
                                {(appUnderstanding.modules || []).map((module, i) => (
                                  <div key={i} className="flex items-center gap-3 text-sm text-slate-700 bg-white p-3 rounded-lg border border-slate-100 shadow-sm">
                                    <span className="w-2 h-2 bg-violet-500 rounded-full" />
                                    {module}
                                    {appUnderstanding.evidence?.modules?.includes('application_crawl') && (
                                      <span className="ml-2 px-2 py-0.5 bg-blue-50 text-blue-600 text-[9px] font-bold uppercase rounded">Crawl</span>
                                    )}
                                  </div>
                                ))}
                                {(appUnderstanding.features || []).map((feature, i) => (
                                  <div key={i} className="flex items-center gap-3 text-sm text-slate-700 bg-white p-3 rounded-lg border border-slate-100 shadow-sm">
                                    <span className="w-2 h-2 bg-emerald-500 rounded-full" />
                                    {typeof feature === 'object' ? feature.name : feature}
                                    <span className="ml-2 px-2 py-0.5 bg-green-50 text-green-600 text-[9px] font-bold uppercase rounded">{typeof feature === 'object' ? feature.source : 'inferred'}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Requirements */}
                          {appUnderstanding.requirements && appUnderstanding.requirements.length > 0 && (
                            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                              <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                                <MdOutlineAssessment className="text-amber-500" /> Requirements
                              </h3>
                              <div className="space-y-3">
                                {appUnderstanding.requirements.map((req, i) => (
                                  <div key={i} className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                                    <p className="text-sm text-slate-700">{req.description || req}</p>
                                    <p className="text-[10px] text-slate-400 font-bold uppercase mt-1">Source: {req.source || 'user_input'}</p>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* User Flows */}
                          {appUnderstanding.user_flows && appUnderstanding.user_flows.length > 0 && (
                            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                              <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                                <MdTimeline className="text-blue-500" /> User Flows
                              </h3>
                              <div className="space-y-2">
                                {appUnderstanding.user_flows.map((flow, i) => (
                                  <div key={i} className="flex items-center gap-3 text-sm text-slate-700 bg-white p-3 rounded-lg border border-slate-100 shadow-sm">
                                    <span className="w-2 h-2 bg-blue-500 rounded-full" />
                                    {typeof flow === 'object' ? (flow.name || flow.description || JSON.stringify(flow)) : flow}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Testable Areas */}
                          {appUnderstanding.testable_areas && appUnderstanding.testable_areas.length > 0 && (
                            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                              <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                                <MdOutlineLanguage className="text-cyan-500" /> Testable Areas
                              </h3>
                              <div className="space-y-2">
                                {appUnderstanding.testable_areas.map((area, i) => (
                                  <div key={i} className="flex items-center gap-3 text-sm text-slate-700 bg-white p-3 rounded-lg border border-slate-100 shadow-sm">
                                    <span className="w-2 h-2 bg-cyan-500 rounded-full" />
                                    {typeof area === 'object' ? (area.area || area.name || JSON.stringify(area)) : area}
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Discovered Routes */}
                          {appUnderstanding.discovered_routes && appUnderstanding.discovered_routes.length > 0 && (
                            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                              <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                                <MdOutlineLanguage className="text-indigo-500" /> Discovered Routes
                              </h3>
                              <div className="space-y-1 max-h-60 overflow-y-auto">
                                {appUnderstanding.discovered_routes.slice(0, 30).map((route, i) => (
                                  <div key={i} className="font-mono text-[11px] text-slate-600 bg-slate-50 px-3 py-2 rounded-lg border border-slate-100 truncate">
                                    {route}
                                  </div>
                                ))}
                                {appUnderstanding.discovered_routes.length > 30 && (
                                  <p className="text-[10px] text-slate-400 text-center mt-2">... and {appUnderstanding.discovered_routes.length - 30} more routes</p>
                                )}
                              </div>
                            </div>
                          )}

                          {/* Forms */}
                          {appUnderstanding.forms && appUnderstanding.forms.length > 0 && (
                            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                              <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                                <MdOutlineFactCheck className="text-pink-500" /> Forms Detected
                              </h3>
                              <div className="space-y-3">
                                {appUnderstanding.forms.map((form, i) => (
                                  <div key={i} className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                                    <div className="flex justify-between items-start mb-2">
                                      <p className="text-sm font-semibold text-slate-800">Form #{i + 1}</p>
                                      <span className="px-2 py-0.5 bg-blue-50 text-blue-600 text-[9px] font-bold uppercase rounded">{form.method?.toUpperCase() || 'GET'}</span>
                                    </div>
                                    <p className="text-[10px] text-slate-500 mb-2">Action: {form.action || 'Not specified'}</p>
                                    <div className="space-y-1">
                                      {(form.inputs || []).slice(0, 5).map((input, j) => (
                                        <div key={j} className="flex gap-2 text-[11px] text-slate-600">
                                          <span className="px-2 py-0.5 bg-white border border-slate-200 rounded text-slate-700 font-mono">{input.type}</span>
                                          <span className="text-slate-500">{input.name || 'unnamed'}</span>
                                          {input.placeholder && <span className="text-slate-400 italic">"{input.placeholder}"</span>}
                                          {input.required && <span className="px-1.5 py-0.5 bg-red-50 text-red-600 text-[9px] font-bold uppercase rounded">Required</span>}
                                        </div>
                                      ))}
                                      {(form.inputs || []).length > 5 && (
                                        <p className="text-[10px] text-slate-400">... and {(form.inputs || []).length - 5} more fields</p>
                                      )}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* API Endpoints — Phase 1.5C Enhanced */}
                          {appUnderstanding.api_endpoints && appUnderstanding.api_endpoints.length > 0 && (
                            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                              <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                                <MdOutlineRule className="text-orange-500" /> API Endpoints (Observed)
                              </h3>
                              <div className="space-y-1 max-h-80 overflow-y-auto">
                                {appUnderstanding.api_endpoints.map((endpoint, i) => {
                                  // Handle both string (legacy) and object (Phase 1.5C) formats
                                  if (typeof endpoint === 'string') {
                                    return (
                                      <div key={i} className="font-mono text-[11px] text-slate-600 bg-slate-50 px-3 py-2 rounded-lg border border-slate-100 truncate">
                                        {endpoint}
                                      </div>
                                    );
                                  }
                                  const method = endpoint.method || 'GET';
                                  const path = endpoint.path || endpoint.url || '';
                                  const status = endpoint.status ? ` → ${endpoint.status}` : '';
                                  const observedOn = endpoint.observed_on_pages && endpoint.observed_on_pages.length > 0 
                                    ? ` (seen on: ${endpoint.observed_on_pages.join(', ')})` : '';
                                  const methodColor = method === 'GET' ? 'text-emerald-600' :
                                                    method === 'POST' ? 'text-blue-600' :
                                                    method === 'PUT' || method === 'PATCH' ? 'text-amber-600' :
                                                    method === 'DELETE' ? 'text-red-600' : 'text-slate-600';
                                  return (
                                    <div key={i} className="bg-slate-50 px-3 py-2 rounded-lg border border-slate-100">
                                      <div className="flex items-center gap-2 flex-wrap">
                                        <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${methodColor} bg-white border border-slate-200`}>
                                          {method}
                                        </span>
                                        <span className="font-mono text-[10px] text-slate-700 truncate flex-1 min-w-0">{path}</span>
                                        {status && <span className="text-[10px] text-slate-500">{status}</span>}
                                        {endpoint.content_type && <span className="text-[9px] text-cyan-600 bg-cyan-50 px-1.5 py-0.5 rounded">{endpoint.content_type}</span>}
                                        {endpoint.is_api_candidate && <span className="px-1.5 py-0.5 bg-violet-100 text-violet-700 text-[9px] font-bold uppercase rounded">API Candidate</span>}
                                      </div>
                                      {observedOn && (
                                        <div className="text-[9px] text-slate-400 mt-1 ml-10">{observedOn}</div>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}

                          {/* Risk Areas */}
                          {appUnderstanding.risk_areas && appUnderstanding.risk_areas.length > 0 && (
                            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                              <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                                <MdError className="text-red-500" /> Risk Areas
                              </h3>
                              <div className="space-y-3">
                                {appUnderstanding.risk_areas.map((risk, i) => (
                                  <div key={i} className="flex gap-3 p-4 bg-red-50 border border-red-100 rounded-2xl">
                                    <MdError className="text-red-500 shrink-0 text-lg" />
                                    <div className="flex-1">
                                      <p className="text-sm font-semibold text-red-800">{risk.area || risk}</p>
                                      {risk.reason && <p className="text-xs text-red-600 mt-1">{risk.reason}</p>}
                                      <p className="text-[10px] text-red-400 font-bold uppercase mt-1">Source: {risk.source || 'analysis'}</p>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Repository Information */}
                          {Object.keys(appUnderstanding.repository_data || {}).length > 0 && (
                            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                              <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                                <RiGithubFill className="text-slate-500" /> Repository Information
                              </h3>
                              <div className="space-y-4">
                                {appUnderstanding.repository_data.analysis && (
                                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                                      <p className="text-[10px] text-slate-400 font-bold uppercase mb-1">Architecture</p>
                                      <p className="text-sm text-slate-700">{appUnderstanding.repository_data.analysis.architecture_overview || 'Not available'}</p>
                                    </div>
                                    <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                                      <p className="text-[10px] text-slate-400 font-bold uppercase mb-1">Code Quality</p>
                                      <p className="text-sm text-slate-700">Score: {appUnderstanding.repository_data.analysis.code_quality?.score || 'N/A'}/100</p>
                                    </div>
                                  </div>
                                )}
                                {appUnderstanding.source_files && appUnderstanding.source_files.length > 0 && (
                                  <div>
                                    <p className="text-[10px] text-slate-400 font-bold uppercase mb-2">Key Source Files</p>
                                    <div className="space-y-1 max-h-40 overflow-y-auto">
                                      {appUnderstanding.source_files.slice(0, 20).map((file, i) => (
                                        <div key={i} className="font-mono text-[11px] text-slate-600 bg-slate-50 px-3 py-2 rounded-lg border border-slate-100 truncate">
                                          {file}
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            </div>
                          )}

                          {/* Evidence Tracking */}
                          {appUnderstanding.evidence && Object.keys(appUnderstanding.evidence).length > 0 && (
                            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
                              <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                                <MdOutlineAssessment className="text-purple-500" /> Evidence Sources
                              </h3>
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                {Object.entries(appUnderstanding.evidence).map(([field, sources]) => (
                                  <div key={field} className="bg-slate-50 p-3 rounded-lg border border-slate-200">
                                    <p className="text-[10px] text-slate-400 font-bold uppercase mb-1">{field}</p>
                                    <div className="flex gap-1 flex-wrap">
                                      {sources.map((source, i) => (
                                        <span key={i} className="px-2 py-0.5 bg-white border border-slate-200 rounded text-[9px] font-medium text-slate-600">
                                          {source}
                                        </span>
                                      ))}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      ) : (
                        <div className="bg-slate-100/50 border-2 border-dashed border-slate-200 rounded-3xl h-[400px] flex flex-col items-center justify-center text-center px-10">
                          <MdOutlineAnalytics className="text-slate-300 text-6xl mb-6" />
                          <h3 className="text-lg font-bold text-slate-800 mb-2">Application Understanding</h3>
                          <p className="text-sm text-slate-500 max-w-sm">Click "Analyze Application" in the left panel to analyze the application using URL, repository, and/or requirements.</p>
                        </div>
                      )}
                    </div>
                  )}
                  
                  {activeTab === 'Test Generation' && (
                    <div className="space-y-8">
                      {!testGeneration && !testGenerationLoading && (
                        <div className="bg-slate-100/50 border-2 border-dashed border-slate-200 rounded-3xl h-[400px] flex flex-col items-center justify-center text-center px-10">
                          <MdOutlineRule className="text-slate-300 text-6xl mb-6" />
                          <h3 className="text-lg font-bold text-slate-800 mb-2">Test Generation</h3>
                          <p className="text-sm text-slate-500 max-w-sm mb-4">Generate comprehensive tests based on the application context.</p>
                          <button
                            onClick={handleGenerateTests}
                            disabled={!appUnderstanding || testGenerationLoading}
                            className="px-6 py-3 bg-violet-600 hover:bg-violet-700 text-white font-bold rounded-xl shadow-lg transition-all disabled:opacity-50"
                          >
                            Generate Tests
                          </button>
                        </div>
                      )}
                      
                      {testGenerationLoading && (
                        <div className="flex flex-col items-center justify-center h-[400px]">
                          <RiLoader4Line className="animate-spin text-4xl text-violet-600 mb-4" />
                          <p className="text-sm font-bold text-slate-500">Generating Tests from Application Context...</p>
                        </div>
                      )}
                      
                      {testGenerationError && (
                        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700">
                          <p className="font-bold">Generation Failed</p>
                          <p className="text-sm mt-1">{testGenerationError}</p>
                        </div>
                      )}

                      {testGeneration && (
                        <div className="space-y-6">
                          <div className="flex justify-between items-center">
                             <h3 className="text-lg font-bold text-slate-800">Candidate Test Pool</h3>
                             <span className="px-3 py-1 bg-violet-100 text-violet-700 text-xs font-bold rounded-full">
                               {testGeneration.metadata.total_merged} Tests Generated
                             </span>
                          </div>
                          
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
                             <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                               <p className="text-[10px] font-bold text-slate-500 uppercase">User Perspective Tests</p>
                               <p className="text-2xl font-black text-slate-800">{testGeneration.user_tests?.length || 0}</p>
                             </div>
                             <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                               <p className="text-[10px] font-bold text-slate-500 uppercase">Engineering QA Tests</p>
                               <p className="text-2xl font-black text-slate-800">{testGeneration.engineering_tests?.length || 0}</p>
                             </div>
                          </div>

                          <div className="space-y-4">
                            {testGeneration.candidate_tests?.map((tc, i) => (
                              <div key={i} className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm hover:shadow-md transition-all">
                                <div className="flex justify-between items-start mb-2">
                                  <div>
                                    <div className="flex items-center gap-2 mb-1">
                                      <span className="font-mono text-[10px] text-slate-400 font-bold">{tc.test_id}</span>
                                      <span className={`px-2 py-0.5 rounded text-[9px] font-bold uppercase ${tc.perspective === 'USER' ? 'bg-blue-100 text-blue-700' : 'bg-orange-100 text-orange-700'}`}>
                                        {tc.perspective} Perspective
                                      </span>
                                      <span className="px-2 py-0.5 bg-slate-100 text-slate-600 rounded text-[9px] font-bold uppercase">
                                        {tc.test_type}
                                      </span>
                                    </div>
                                    <h4 className="font-bold text-slate-800 text-sm">{tc.title}</h4>
                                    <p className="text-xs text-slate-600 mt-1">{tc.description}</p>
                                  </div>
                                  <div className="text-right">
                                    <p className="text-[10px] font-bold text-slate-400 uppercase">Risk Score</p>
                                    <p className="font-black text-slate-700">{(tc.risk_score || 0).toFixed(2)}</p>
                                  </div>
                                </div>
                                <div className="mt-3 pt-3 border-t border-slate-100 flex flex-wrap gap-x-6 gap-y-2 text-[10px]">
                                  <div>
                                    <span className="font-bold text-slate-400 uppercase">Target: </span>
                                    <span className="text-slate-700">{tc.target || 'General'}</span>
                                  </div>
                                  {tc.evidence && (
                                    <div>
                                      <span className="font-bold text-slate-400 uppercase">Evidence: </span>
                                      <span className="text-slate-700">{tc.evidence.source || 'inferred'}</span>
                                    </div>
                                  )}
                                  <div>
                                    <span className="font-bold text-slate-400 uppercase">Source: </span>
                                    <span className="text-slate-700">{tc.source_agent}</span>
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
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

      {showShareModal && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 backdrop-blur-sm bg-slate-900/20 animate-in fade-in duration-300">
          <div className="bg-white w-full max-w-md rounded-[2.5rem] shadow-2xl border border-slate-100 overflow-hidden animate-in zoom-in-95 duration-300">
            <div className="p-8 space-y-6">
              <div className="flex justify-between items-center">
                <div className="space-y-1">
                  <h3 className="text-xl font-black text-slate-900 tracking-tight">Share Report</h3>
                  <p className="text-xs text-slate-500 font-bold uppercase tracking-widest">Select Developer</p>
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
                  <p className="text-[10px] text-blue-600 font-black uppercase tracking-widest mb-1">Preview</p>
                  <p className="text-xs text-slate-600 leading-relaxed italic">
                    "Sent you the AgentQE ML Pipeline report for {runDetails?.run.title}."
                  </p>
                </div>
              </div>

              <button 
                disabled={sharing || !selectedRecipient}
                onClick={handleShare}
                className="w-full bg-slate-900 text-white py-4 rounded-2xl font-black flex items-center justify-center gap-3 hover:bg-slate-800 transition-all shadow-xl disabled:opacity-50 disabled:cursor-not-allowed group"
              >
                {sharing ? <RiLoader4Line className="animate-spin text-xl" /> : <RiSendPlaneFill className="text-xl group-hover:translate-x-1 transition-transform" />}
                {sharing ? 'Sharing...' : 'Send Report'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
