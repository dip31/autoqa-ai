import React, { useState } from 'react';
import { predictRisk } from '../api/client';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import { Bar } from 'react-chartjs-2';
import { Chart as ChartJS, CategoryScale, LinearScale, BarElement, Tooltip, Legend } from 'chart.js';
import { MdOutlineRadar, MdOutlineWarningAmber, MdOutlineInfo, MdOutlineShield, MdOutlineFlashOn, MdOutlineSchedule, MdOutlineFlagCircle, MdFileDownload } from 'react-icons/md';
import { exportToExcel } from '../api/exportExcel';

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend);

const RISK_STYLE = { high:'bg-red-50 text-red-700 border-red-200', medium:'bg-amber-50 text-amber-700 border-amber-200', low:'bg-emerald-50 text-emerald-700 border-emerald-200' };
const EFFORT_STYLE = { low:'bg-emerald-50 text-emerald-700 border-emerald-200', medium:'bg-amber-50 text-amber-700 border-amber-200', high:'bg-red-50 text-red-700 border-red-200' };
const TABS = [{ key:'analysis', label:'Risk Analysis' }, { key:'reduction', label:'Risk Reduction Plan' }];

export default function RiskPrediction() {
  const [content, setContent]     = useState('');
  const [inputType, setInputType] = useState('general');
  const [result, setResult]       = useState(null);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState('');
  const [activeTab, setActiveTab] = useState('analysis');

  const handleSubmit = async () => {
    if (!content.trim()) return;
    setLoading(true); setError(''); setResult(null); setActiveTab('analysis');
    try {
      const res = await predictRisk(content, inputType);
      setResult(res.data.data);
    } catch (e) {
      setError(e.response?.data?.error || e.message || 'Failed to predict risk.');
    } finally { setLoading(false); }
  };

  const handleExport = () => {
    const plan = result?.risk_reduction_plan || {};
    exportToExcel([
      { sheetName:'Module Risk', rows:(result.modules||[]).map(m=>({'Module':m.name,'Risk Level':m.risk_level,'Risk Score':m.risk_score,'Reasons':(m.reasons||[]).join('\n')})) },
      { sheetName:'Immediate Actions', rows:(plan.immediate_actions||[]).map(a=>({'Priority':a.priority,'Action':a.action,'Impact':a.impact,'Effort':a.effort})) },
      { sheetName:'Short-Term Actions', rows:(plan.short_term_actions||[]).map(a=>({'Priority':a.priority,'Action':a.action,'Impact':a.impact,'Effort':a.effort})) },
      { sheetName:'Long-Term Actions', rows:(plan.long_term_actions||[]).map(a=>({'Priority':a.priority,'Action':a.action,'Impact':a.impact,'Effort':a.effort})) },
    ], 'risk-reduction-plan.xlsx');
  };

  const chartData = result?.modules?.length ? {
    labels: result.modules.map(m => m.name),
    datasets: [{ label:'Risk Score', data:result.modules.map(m=>m.risk_score), backgroundColor:result.modules.map(m=>m.risk_level==='high'?'rgba(239,68,68,0.8)':m.risk_level==='medium'?'rgba(245,158,11,0.8)':'rgba(16,185,129,0.8)'), borderRadius:4 }]
  } : null;

  const chartOptions = { responsive:true, plugins:{legend:{display:false}}, scales:{ y:{min:0,max:100,ticks:{color:'#94a3b8',font:{size:11}},grid:{color:'#f1f5f9'}}, x:{ticks:{color:'#64748b',font:{size:11}},grid:{display:false}} } };
  const scoreColor = (result?.overall_risk_score??0)>=70?'text-red-600':(result?.overall_risk_score??0)>=40?'text-amber-600':'text-emerald-600';
  const plan = result?.risk_reduction_plan || {};
  const afterScore = plan.estimated_risk_after_reduction ?? null;

  return (
    <div className="p-4 sm:p-6 lg:p-8 w-full">
      <h2 className="text-xl font-semibold text-slate-800 mb-1">Risk Prediction</h2>
      <p className="text-slate-500 text-sm mb-6">Paste test cases, code, or feature descriptions to predict bug risk and get a reduction plan.</p>

      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm mb-5 space-y-4">
        <div>
          <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">Input Type</label>
          <select value={inputType} onChange={e=>setInputType(e.target.value)}
            className="bg-slate-50 text-slate-800 rounded-lg px-4 py-2.5 border border-slate-200 focus:border-blue-400 focus:ring-2 focus:ring-blue-100 focus:outline-none text-sm transition">
            <option value="general">General</option>
            <option value="test_cases">Test Cases</option>
            <option value="code">Code</option>
            <option value="requirements">Requirements</option>
          </select>
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">Content to Analyze</label>
          <textarea className="w-full h-40 bg-slate-50 text-slate-800 rounded-lg p-4 text-sm border border-slate-200 focus:border-blue-400 focus:ring-2 focus:ring-blue-100 focus:outline-none resize-none transition"
            placeholder="Paste your test cases, code, or feature description here..."
            value={content} onChange={e=>setContent(e.target.value)} />
        </div>
        <button onClick={handleSubmit} disabled={loading||!content.trim()}
          className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors">
          Predict Risk
        </button>
      </div>

      <ErrorAlert message={error} onClose={()=>setError('')} />
      {loading && <Loader message="Analyzing risk and generating reduction plan..." />}

      {result && (
        <div className="space-y-4">
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
              <div className="flex items-center gap-2">
                <MdOutlineRadar className="text-blue-500 text-xl" />
                <p className="text-sm font-semibold text-slate-700">Overall Risk Score</p>
              </div>
              <div className="flex items-center gap-3">
                <p className={`text-3xl font-bold ${scoreColor}`}>{result.overall_risk_score}<span className="text-base font-normal text-slate-400">/100</span></p>
                <button onClick={handleExport}
                  className="flex items-center gap-1.5 px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-medium rounded-lg transition-colors">
                  <MdFileDownload className="text-base" /> Export Plan
                </button>
              </div>
            </div>
            <p className="text-sm text-slate-500 mb-4">{result.risk_summary}</p>

            {afterScore !== null && (
              <div className="flex items-center gap-4 mb-4 bg-slate-50 border border-slate-200 rounded-lg px-4 py-3">
                <MdOutlineShield className="text-blue-500 text-xl shrink-0" />
                <div className="flex-1">
                  <p className="text-xs font-semibold text-slate-600 mb-1">Estimated risk after applying all suggestions</p>
                  <div className="flex items-center gap-3"><div className="flex-1 h-2 bg-slate-200 rounded-full overflow-hidden"><div className="h-full bg-red-400 rounded-full" style={{width:`${result.overall_risk_score}%`}} /></div><span className="text-xs text-red-500 font-semibold w-10 text-right">{result.overall_risk_score}</span></div>
                  <div className="flex items-center gap-3 mt-1"><div className="flex-1 h-2 bg-slate-200 rounded-full overflow-hidden"><div className="h-full bg-emerald-400 rounded-full transition-all duration-700" style={{width:`${afterScore}%`}} /></div><span className="text-xs text-emerald-600 font-semibold w-10 text-right">{afterScore}</span></div>
                  <div className="flex gap-4 mt-1.5 text-xs text-slate-400">
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-400 inline-block" /> Current</span>
                    <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-400 inline-block" /> After reduction</span>
                  </div>
                </div>
              </div>
            )}

            <div className="flex gap-3">
              {[{label:'High Risk',count:result.high_risk_count,style:'bg-red-50 text-red-700 border-red-200'},{label:'Medium Risk',count:result.medium_risk_count,style:'bg-amber-50 text-amber-700 border-amber-200'},{label:'Low Risk',count:result.low_risk_count,style:'bg-emerald-50 text-emerald-700 border-emerald-200'}].map(({label,count,style})=>(
                <div key={label} className={`flex-1 border rounded-lg px-4 py-3 text-center ${style}`}>
                  <p className="text-xl font-bold">{count||0}</p>
                  <p className="text-xs mt-0.5">{label}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
            <div className="flex border-b border-slate-200">
              {TABS.map(({key,label})=>(
                <button key={key} onClick={()=>setActiveTab(key)}
                  className={`flex-1 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab===key?'border-blue-600 text-blue-600 bg-blue-50':'border-transparent text-slate-500 hover:text-slate-700 hover:bg-slate-50'}`}>
                  {label}
                </button>
              ))}
            </div>

            {activeTab==='analysis' && (
              <div className="p-5 space-y-4">
                {chartData && <div><p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Risk Score by Module</p><Bar data={chartData} options={chartOptions} /></div>}
                {result.modules?.length>0 && (
                  <div className="border border-slate-200 rounded-xl overflow-hidden">
                    <div className="px-4 py-3 bg-slate-50 border-b border-slate-200"><p className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Module Breakdown</p></div>
                    <div className="divide-y divide-slate-100">
                      {result.modules.map((mod,i)=>(
                        <div key={i} className="px-5 py-4">
                          <div className="flex items-center justify-between mb-2">
                            <p className="text-sm font-medium text-slate-800">{mod.name}</p>
                            <span className={`text-xs px-2.5 py-1 rounded-full border font-semibold ${RISK_STYLE[mod.risk_level]||RISK_STYLE.low}`}>{mod.risk_level?.toUpperCase()} — {mod.risk_score}/100</span>
                          </div>
                          {mod.reasons?.length>0 && <div className="flex items-start gap-2 mt-1"><MdOutlineWarningAmber className="text-amber-400 text-sm shrink-0 mt-0.5" /><ul className="text-xs text-slate-500 space-y-0.5">{mod.reasons.map((r,j)=><li key={j}>{r}</li>)}</ul></div>}
                          {mod.recommendations?.length>0 && <div className="flex items-start gap-2 mt-2"><MdOutlineInfo className="text-blue-400 text-sm shrink-0 mt-0.5" /><ul className="text-xs text-blue-600 space-y-0.5">{mod.recommendations.map((r,j)=><li key={j}>{r}</li>)}</ul></div>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab==='reduction' && (
              <div className="p-5 space-y-5">
                {[
                  {key:'immediate_actions',label:'Immediate Actions',subtitle:'Do these now to reduce critical risk',icon:MdOutlineFlashOn,iconColor:'text-red-500',headerStyle:'bg-red-50 border-red-100'},
                  {key:'short_term_actions',label:'Short-Term Actions',subtitle:'Complete within the next sprint or week',icon:MdOutlineSchedule,iconColor:'text-amber-500',headerStyle:'bg-amber-50 border-amber-100'},
                  {key:'long_term_actions',label:'Long-Term Actions',subtitle:'Strategic improvements for sustained quality',icon:MdOutlineFlagCircle,iconColor:'text-blue-500',headerStyle:'bg-blue-50 border-blue-100'},
                ].map(({key,label,subtitle,icon:Icon,iconColor,headerStyle})=>{
                  const actions=plan[key]||[];
                  return (
                    <div key={key} className="border border-slate-200 rounded-xl overflow-hidden">
                      <div className={`flex items-center gap-3 px-5 py-3 border-b ${headerStyle}`}>
                        <Icon className={`text-xl ${iconColor}`} />
                        <div><p className="text-sm font-semibold text-slate-700">{label}</p><p className="text-xs text-slate-500">{subtitle}</p></div>
                        <span className="ml-auto text-xs bg-white border border-slate-200 text-slate-600 px-2 py-0.5 rounded-full font-medium">{actions.length} actions</span>
                      </div>
                      {actions.length===0 ? <p className="text-slate-400 text-sm text-center py-6">No actions in this category</p> : (
                        <div className="divide-y divide-slate-100">
                          {actions.sort((a,b)=>(a.priority||5)-(b.priority||5)).map((action,i)=>(
                            <div key={i} className="px-5 py-4 flex items-start gap-4">
                              <div className="w-6 h-6 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center shrink-0 mt-0.5"><span className="text-xs font-bold text-slate-600">{action.priority||i+1}</span></div>
                              <div className="flex-1 min-w-0">
                                <p className="text-sm text-slate-800 font-medium">{action.action}</p>
                                {action.impact && <p className="text-xs text-slate-500 mt-1"><span className="font-medium text-slate-600">Impact:</span> {action.impact}</p>}
                              </div>
                              {action.effort && <span className={`text-xs px-2 py-0.5 rounded-full border font-semibold shrink-0 ${EFFORT_STYLE[action.effort?.toLowerCase()]||EFFORT_STYLE.medium}`}>{action.effort} effort</span>}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
