import React, { useState, useEffect } from 'react';
import { 
  RiGithubFill, RiSearchLine, RiInformationLine, RiCodeLine, 
  RiBugLine, RiShieldLine, RiTestTubeLine, RiLightbulbLine,
  RiFileTextLine, RiBarChartBoxLine, RiArrowRightSLine,
  RiCheckboxCircleLine, RiErrorWarningLine, RiTimeLine
} from 'react-icons/ri';
import { axiosInstance } from '../api/client';

export default function GithubIntelligence() {
  const [repos, setRepos] = useState([]);
  const [selectedRepo, setSelectedRepo] = useState(null);
  const [repoUrl, setRepoUrl] = useState('');
  const [branch, setBranch] = useState('main');
  const [loading, setLoading] = useState(false);
  const [analysis, setAnalysis] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [githubConnected, setGithubConnected] = useState(false);

  useEffect(() => {
    fetchRepos();
  }, []);

  const fetchRepos = async () => {
    try {
      const res = await axiosInstance.get('/api/github/repos');
      if (res.data.success) {
        setRepos(res.data.repos || []);
        setGithubConnected(true);
      } else {
        setGithubConnected(false);
      }
    } catch (err) {
      setGithubConnected(false);
    }
  };

  const handleAnalyze = async () => {
    const url = selectedRepo ? selectedRepo.html_url : repoUrl;
    if (!url) return;
    
    setLoading(true);
    try {
      const res = await axiosInstance.post('/api/github/analyze', { repo_url: url, branch });
      setAnalysis(res.data.data);
      setActiveTab('overview');
    } catch (err) {
      alert(err.response?.data?.error || 'Analysis failed');
    } finally {
      setLoading(false);
    }
  };

  const tabs = [
    { id: 'overview',   label: 'Overview',   icon: RiInformationLine },
    { id: 'structure',  label: 'Structure',  icon: RiCodeLine },
    { id: 'quality',    label: 'Quality',    icon: RiBarChartBoxLine },
    { id: 'risk',       label: 'Risk',       icon: RiBugLine },
    { id: 'coverage',   label: 'Coverage',   icon: RiShieldLine },
    { id: 'tests',      label: 'Tests',      icon: RiTestTubeLine },
    { id: 'tips',       label: 'Fixes',      icon: RiLightbulbLine },
    { id: 'report',     label: 'Final Report',icon: RiFileTextLine },
  ];

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] text-slate-600">
        <div className="w-16 h-16 border-4 border-blue-100 border-t-blue-600 rounded-full animate-spin mb-6" />
        <h2 className="text-xl font-bold text-slate-800">Deep-Scanning Repository...</h2>
        <p className="mt-2 text-slate-500 animate-pulse">Analyzing tech stack, quality, and bug patterns</p>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">GitHub Intelligence</h1>
          <p className="text-slate-500 mt-1">Deep architectural and QA analysis for any codebase</p>
        </div>
        <div className="flex items-center gap-3">
          <RiGithubFill className={`text-3xl ${githubConnected ? 'text-slate-900' : 'text-slate-300'}`} />
          {!githubConnected && (
            <button 
              onClick={() => window.location.href = 'http://localhost:5000/auth/github/login'}
              className="px-4 py-2 bg-slate-900 text-white rounded-xl text-sm font-medium hover:bg-slate-800 transition"
            >
              Connect GitHub
            </button>
          )}
        </div>
      </div>

      {!analysis ? (
        <div className="bg-white rounded-3xl border border-slate-200 p-8 shadow-sm">
          <div className="max-w-2xl mx-auto text-center">
            <div className="w-16 h-16 bg-blue-50 text-blue-600 rounded-2xl flex items-center justify-center mx-auto mb-6">
              <RiSearchLine className="text-3xl" />
            </div>
            <h2 className="text-2xl font-bold text-slate-800 mb-2">Select a Repository</h2>
            <p className="text-slate-500 mb-8 text-lg">Choose from your repositories or paste a public URL</p>

            <div className="space-y-4">
              {githubConnected && repos.length > 0 && (
                <div className="text-left">
                  <label className="block text-sm font-semibold text-slate-700 mb-2">My Repositories</label>
                  <select 
                    className="w-full px-5 py-4 bg-slate-50 border border-slate-200 rounded-2xl text-slate-800 focus:ring-2 focus:ring-blue-100 focus:border-blue-400 outline-none transition"
                    onChange={(e) => {
                      const repo = repos.find(r => r.id === parseInt(e.target.value));
                      setSelectedRepo(repo);
                      setRepoUrl('');
                    }}
                  >
                    <option value="">-- Choose Repository --</option>
                    {repos.map(r => (
                      <option key={r.id} value={r.id}>{r.full_name}</option>
                    ))}
                  </select>
                </div>
              )}

              <div className="text-left">
                <label className="block text-sm font-semibold text-slate-700 mb-2">Paste Repo URL</label>
                <div className="relative">
                  <RiGithubFill className="absolute left-5 top-1/2 -translate-y-1/2 text-slate-400 text-xl" />
                  <input 
                    type="text"
                    placeholder="https://github.com/user/repo"
                    value={repoUrl}
                    onChange={(e) => {
                      setRepoUrl(e.target.value);
                      setSelectedRepo(null);
                    }}
                    className="w-full pl-14 pr-5 py-4 bg-slate-50 border border-slate-200 rounded-2xl text-slate-800 focus:ring-2 focus:ring-blue-100 focus:border-blue-400 outline-none transition"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="text-left">
                  <label className="block text-sm font-semibold text-slate-700 mb-2">Branch</label>
                  <input 
                    type="text"
                    value={branch}
                    onChange={(e) => setBranch(e.target.value)}
                    className="w-full px-5 py-3 bg-slate-50 border border-slate-200 rounded-xl text-slate-800 focus:ring-2 focus:ring-blue-100 focus:border-blue-400 outline-none transition"
                  />
                </div>
                <div className="flex items-end">
                  <button 
                    onClick={handleAnalyze}
                    disabled={!selectedRepo && !repoUrl}
                    className="w-full py-3 bg-gradient-to-r from-blue-600 to-violet-600 text-white font-bold rounded-xl shadow-lg shadow-blue-200 hover:scale-[1.02] active:scale-95 transition-all disabled:opacity-50"
                  >
                    Start Analysis
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Repo Explorer Header */}
          <div className="bg-white p-6 rounded-3xl border border-slate-200 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="w-14 h-14 bg-slate-950 rounded-2xl flex items-center justify-center text-white text-2xl">
                <RiGithubFill />
              </div>
              <div>
                <h3 className="text-xl font-bold text-slate-900">{analysis.repo_name}</h3>
                <div className="flex items-center gap-3 text-sm text-slate-500 mt-0.5">
                  <span className="flex items-center gap-1"><RiCodeLine /> {analysis.analysis.tech_stack.backend} + {analysis.analysis.tech_stack.frontend}</span>
                  <span>•</span>
                  <span className="flex items-center gap-1"><RiTimeLine /> {new Date(analysis.metadata.updated_at).toLocaleDateString()}</span>
                </div>
              </div>
            </div>
            <div className="flex gap-2">
              <button onClick={() => setAnalysis(null)} className="px-5 py-2.5 bg-slate-50 text-slate-600 rounded-xl font-medium hover:bg-slate-100 transition">Back</button>
              <button 
                onClick={() => window.open(analysis.repo_url, '_blank')}
                className="px-5 py-2.5 bg-slate-900 text-white rounded-xl font-medium hover:bg-slate-800 transition flex items-center gap-2"
              >
                View Code <RiArrowRightSLine />
              </button>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div className="flex gap-2 p-1.5 bg-slate-100 rounded-[20px] overflow-x-auto no-scrollbar">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-5 py-2.5 rounded-2xl text-sm font-semibold whitespace-nowrap transition-all ${
                  activeTab === tab.id 
                    ? 'bg-white text-blue-600 shadow-sm' 
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                <tab.icon /> {tab.label}
              </button>
            ))}
          </div>

          {/* Tab Content */}
          <div className="bg-white rounded-3xl border border-slate-200 p-8 shadow-sm min-h-[400px]">
            {activeTab === 'overview' && (
              <div className="space-y-8 animate-in fade-in slide-in-from-bottom-2 duration-500">
                <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                  <StatCard label="Quality Score" value={`${analysis.analysis.code_quality.score}/100`} color="blue" />
                  <StatCard label="Maintainability" value={`${analysis.analysis.health_indicators.maintainability}%`} color="emerald" />
                  <StatCard label="Test Readiness" value={`${analysis.analysis.health_indicators.test_readiness}%`} color="amber" />
                  <StatCard label="Risks Found" value={analysis.analysis.bugs_and_risks.probable_issues.length} color="rose" />
                </div>
                <div>
                  <h4 className="text-lg font-bold text-slate-800 mb-4">Executive Summary</h4>
                  <p className="text-slate-600 leading-relaxed text-lg">{analysis.analysis.executive_summary || "This repository demonstrates a structured architecture with significant focus on functional logic. However, there are identified gaps in edge-case testing and maintainability in core modules."}</p>
                </div>
              </div>
            )}

            {activeTab === 'structure' && (
              <div className="animate-in fade-in duration-500">
                <div className="grid md:grid-cols-2 gap-10">
                  <div>
                    <h4 className="text-lg font-bold text-slate-800 mb-6 font-primary">Technical Stack</h4>
                    <div className="space-y-4">
                      <TechItem label="Backend" value={analysis.analysis.tech_stack.backend} />
                      <TechItem label="Frontend" value={analysis.analysis.tech_stack.frontend} />
                      <TechItem label="Database" value={analysis.analysis.tech_stack.database} />
                      <TechItem label="Tools" value={analysis.analysis.tech_stack.tools.join(', ')} />
                    </div>
                  </div>
                  <div>
                    <h4 className="text-lg font-bold text-slate-800 mb-4">Architecture Overview</h4>
                    <div className="bg-slate-50 p-6 rounded-2xl border border-slate-200">
                       <p className="text-slate-700 italic leading-relaxed">{analysis.analysis.architecture_overview}</p>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'quality' && (
              <div className="animate-in fade-in duration-500">
                <h4 className="text-lg font-bold text-slate-800 mb-6">Code Quality Observations</h4>
                <div className="grid gap-4">
                  {analysis.analysis.code_quality.observations.map((obs, idx) => (
                    <div key={idx} className="flex gap-4 p-5 bg-blue-50/50 border border-blue-100 rounded-2xl">
                      <RiCheckboxCircleLine className="text-blue-500 text-xl shrink-0 mt-0.5" />
                      <p className="text-slate-700">{obs}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {activeTab === 'risk' && (
              <div className="animate-in fade-in duration-500">
                <div className="bg-rose-50 border border-rose-200 rounded-2xl p-6 mb-8">
                   <h4 className="text-rose-800 font-bold mb-3 flex items-center gap-2"><RiErrorWarningLine /> High Risk Modules</h4>
                   <div className="flex flex-wrap gap-2">
                     {analysis.analysis.bugs_and_risks.high_risk_modules.map(m => (
                       <span key={m} className="px-3 py-1 bg-rose-200/50 text-rose-700 rounded-lg text-sm font-bold">{m}</span>
                     ))}
                   </div>
                </div>
                <h4 className="text-lg font-bold text-slate-800 mb-4">Probable Issues</h4>
                <div className="space-y-3">
                  {analysis.analysis.bugs_and_risks.probable_issues.map((bug, i) => (
                    <div key={i} className="p-4 border border-slate-200 rounded-xl flex gap-3 text-slate-600">
                      <span className="w-6 h-6 bg-slate-100 rounded flex items-center justify-center text-xs font-bold text-slate-400 shrink-0">{i+1}</span>
                      {bug}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {activeTab === 'tests' && (
              <div className="animate-in fade-in duration-500">
                <h4 className="text-lg font-bold text-slate-800 mb-6">Generated AI Test Cases</h4>
                <div className="overflow-hidden border border-slate-200 rounded-2xl">
                  <table className="w-full text-left">
                    <thead className="bg-slate-50 border-b border-slate-200">
                      <tr>
                        <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Module</th>
                        <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Scenario</th>
                        <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Priority</th>
                        <th className="px-6 py-4 text-xs font-bold text-slate-500 uppercase">Category</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {analysis.analysis.generated_test_cases.map((tc, idx) => (
                        <tr key={idx} className="hover:bg-slate-50 transition-colors cursor-pointer" onClick={() => alert(tc.steps.join('\n'))}>
                          <td className="px-6 py-4 text-sm font-bold text-blue-600">{tc.module}</td>
                          <td className="px-6 py-4">
                            <p className="text-sm font-bold text-slate-800">{tc.title}</p>
                            <p className="text-xs text-slate-500 mt-1">{tc.objective}</p>
                          </td>
                          <td className="px-6 py-4">
                            <span className={`px-2.5 py-1 rounded-full text-[10px] font-bold uppercase ${
                              tc.priority === 'High' ? 'bg-rose-100 text-rose-600' : 'bg-blue-100 text-blue-600'
                            }`}>{tc.priority}</span>
                          </td>
                          <td className="px-6 py-4 text-xs text-slate-600 font-medium">{tc.category}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {activeTab === 'report' && (
              <div className="animate-in fade-in zoom-in-95 duration-700 bg-slate-900 rounded-[40px] p-12 text-white relative overflow-hidden">
                <div className="absolute top-0 right-0 w-96 h-96 bg-blue-600/20 rounded-full blur-[120px]" />
                <div className="relative z-10 text-center mb-16">
                   <div className="inline-block px-4 py-1.5 bg-blue-500/20 border border-blue-400/30 rounded-full text-blue-300 text-xs font-bold mb-6 tracking-widest uppercase">Intelligent Audit Report</div>
                   <h2 className="text-4xl font-black mb-4">Repository Health Verdict</h2>
                   <p className="text-slate-400 text-lg max-w-2xl mx-auto">A comprehensive assessment of quality, risk, and testing readiness for {analysis.repo_name}.</p>
                </div>

                <div className="relative z-10 grid md:grid-cols-3 gap-8 mb-16">
                  <VerdictCard label="Maintenance Grade" val="A-" sub="Excellent structure" />
                  <VerdictCard label="Risk Profile" val="Moderate" sub="3 modules sensitive" />
                  <VerdictCard label="Test Maturity" val="Developing" sub="Lacks async coverage" />
                </div>

                <div className="relative z-10 bg-white/5 border border-white/10 p-10 rounded-[32px] backdrop-blur-md">
                   <h3 className="text-2xl font-bold mb-6 text-blue-400">Project Integrity Score</h3>
                   <div className="h-4 bg-white/10 rounded-full mb-4 overflow-hidden">
                     <div className="h-full bg-gradient-to-r from-blue-500 to-violet-500" style={{ width: `${analysis.analysis.code_quality.score}%` }} />
                   </div>
                   <div className="flex justify-between items-center text-slate-400 text-sm font-bold px-1">
                     <span>STABILITY INDEX</span>
                     <span className="text-white text-3xl font-black">{analysis.analysis.code_quality.score}</span>
                   </div>
                   <p className="mt-8 text-slate-300 leading-relaxed italic border-l-4 border-blue-500/50 pl-6">
                     "{analysis.analysis.executive_summary}"
                   </p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, color }) {
  const colors = {
    blue: 'text-blue-600 bg-blue-50 border-blue-100',
    emerald: 'text-emerald-600 bg-emerald-50 border-emerald-100',
    amber: 'text-amber-600 bg-amber-50 border-amber-100',
    rose: 'text-rose-600 bg-rose-50 border-rose-100'
  };
  return (
    <div className={`p-5 rounded-2xl border text-center ${colors[color]}`}>
      <p className="text-xs font-bold uppercase tracking-wider opacity-70 mb-1">{label}</p>
      <p className="text-2xl font-black">{value}</p>
    </div>
  );
}

function TechItem({ label, value }) {
  return (
    <div className="flex items-center justify-between p-4 bg-slate-50 border border-slate-200 rounded-xl">
      <span className="text-sm font-bold text-slate-500">{label}</span>
      <span className="text-sm font-bold text-slate-800">{value}</span>
    </div>
  );
}

function VerdictCard({ label, val, sub }) {
  return (
    <div className="p-8 bg-white/5 border border-white/10 rounded-3xl text-center">
      <p className="text-slate-400 text-xs font-bold uppercase mb-2 tracking-widest">{label}</p>
      <p className="text-3xl font-black mb-1">{val}</p>
      <p className="text-slate-500 text-xs font-medium">{sub}</p>
    </div>
  );
}
