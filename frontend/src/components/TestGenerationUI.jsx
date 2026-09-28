import React, { useState, useMemo } from 'react';
import { MdOutlineRule, MdCode, MdOutlineBuild, MdArrowDropDown, MdArrowRight, MdInfoOutline, MdLink } from 'react-icons/md';

export default function TestGenerationUI({ generationResult }) {
  const [filterType, setFilterType] = useState('All');
  const [filterSource, setFilterSource] = useState('All');
  const [search, setSearch] = useState('');
  const [expandedTests, setExpandedTests] = useState(new Set());

  const summary = generationResult?.generation_summary || {};
  const tests = generationResult?.candidate_tests || [];

  const filteredTests = useMemo(() => {
    return tests.filter(tc => {
      // Source filter
      if (filterSource !== 'All') {
        if (filterSource === 'User Agent' && !tc.source_agent.includes('user_agent')) return false;
        if (filterSource === 'Engineering Agent' && !tc.source_agent.includes('engineering_agent')) return false;
      }
      
      // Type filter
      if (filterType !== 'All') {
        const typeMatch = tc.test_type?.toLowerCase() === filterType.toLowerCase() || 
                         (filterType === 'Functional UI' && tc.test_type?.toLowerCase() === 'ui');
        if (!typeMatch) return false;
      }

      // Search
      if (search) {
        const s = search.toLowerCase();
        const matches = (tc.title || '').toLowerCase().includes(s) ||
                        (tc.description || '').toLowerCase().includes(s) ||
                        (tc.requirement_refs || []).some(r => r.toLowerCase().includes(s)) ||
                        (tc.page_refs || []).some(r => r.toLowerCase().includes(s)) ||
                        (tc.api_refs || []).some(r => r.toLowerCase().includes(s)) ||
                        (tc.flow_refs || []).some(r => r.toLowerCase().includes(s));
        if (!matches) return false;
      }
      return true;
    });
  }, [tests, filterType, filterSource, search]);

  const toggleExpand = (id) => {
    const newSet = new Set(expandedTests);
    if (newSet.has(id)) newSet.delete(id);
    else newSet.add(id);
    setExpandedTests(newSet);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h3 className="text-xl font-bold text-slate-800">Generated Candidate Tests</h3>
          <p className="text-sm text-slate-500">Pipeline Phase 3 Output</p>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
          <p className="text-[10px] font-bold text-slate-500 uppercase">Final Candidates</p>
          <p className="text-2xl font-black text-slate-800">{summary.final_tests}</p>
        </div>
        <div className="bg-blue-50 p-4 rounded-xl border border-blue-200">
          <p className="text-[10px] font-bold text-blue-500 uppercase">User Agent Tests</p>
          <p className="text-2xl font-black text-blue-800">{summary.user_agent}</p>
        </div>
        <div className="bg-orange-50 p-4 rounded-xl border border-orange-200">
          <p className="text-[10px] font-bold text-orange-500 uppercase">Eng Agent Tests</p>
          <p className="text-2xl font-black text-orange-800">{summary.engineering_agent}</p>
        </div>
        <div className="bg-violet-50 p-4 rounded-xl border border-violet-200">
          <p className="text-[10px] font-bold text-violet-500 uppercase">Duplicates Merged</p>
          <p className="text-2xl font-black text-violet-800">{summary.merged}</p>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 flex flex-wrap gap-4 items-center">
        <div className="flex-1 min-w-[200px]">
          <input 
            type="text" 
            placeholder="Search title, requirement, page, API..." 
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-2 text-sm outline-none focus:border-violet-500"
          />
        </div>
        <select 
          value={filterSource} 
          onChange={e => setFilterSource(e.target.value)}
          className="bg-slate-50 border border-slate-200 rounded-lg px-4 py-2 text-sm outline-none"
        >
          <option value="All">All Sources</option>
          <option value="User Agent">User Agent</option>
          <option value="Engineering Agent">Engineering Agent</option>
        </select>
        <select 
          value={filterType} 
          onChange={e => setFilterType(e.target.value)}
          className="bg-slate-50 border border-slate-200 rounded-lg px-4 py-2 text-sm outline-none"
        >
          <option value="All">All Types</option>
          <option value="Functional UI">Functional UI</option>
          <option value="API">API</option>
          <option value="Integration">Integration</option>
          <option value="Navigation">Navigation</option>
          <option value="Form Validation">Form Validation</option>
          <option value="Accessibility">Accessibility</option>
        </select>
      </div>

      {/* Test Cards */}
      <div className="space-y-4">
        {filteredTests.map((tc, idx) => {
          const isExpanded = expandedTests.has(tc.test_id);
          const isUser = tc.source_agent.includes('user_agent');
          const isEng = tc.source_agent.includes('engineering_agent');
          const isMerged = isUser && isEng;
          
          return (
            <div key={tc.test_id} className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm hover:shadow transition-all">
              <div 
                className="p-4 cursor-pointer flex justify-between items-start"
                onClick={() => toggleExpand(tc.test_id)}
              >
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="font-mono text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-bold">{tc.test_id}</span>
                    <span className="px-2 py-0.5 bg-slate-100 text-slate-600 rounded text-[9px] font-bold uppercase">{tc.test_type}</span>
                    {isUser && <span className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-[9px] font-bold uppercase flex items-center gap-1"><MdOutlineRule /> User Agent</span>}
                    {isEng && <span className="px-2 py-0.5 bg-orange-100 text-orange-700 rounded text-[9px] font-bold uppercase flex items-center gap-1"><MdCode /> Eng Agent</span>}
                  </div>
                  <h4 className="font-bold text-slate-800">{tc.title}</h4>
                  <div className="flex flex-wrap gap-2 mt-2">
                    {tc.requirement_refs?.map((r, i) => <span key={i} className="text-[10px] text-slate-500 flex items-center gap-1"><MdLink /> {r}</span>)}
                    {tc.page_refs?.map((r, i) => <span key={i} className="text-[10px] text-blue-500 flex items-center gap-1"><MdLink /> {r}</span>)}
                    {tc.api_refs?.map((r, i) => <span key={i} className="text-[10px] text-orange-500 flex items-center gap-1"><MdLink /> {r}</span>)}
                  </div>
                </div>
                <div className="text-slate-400">
                  {isExpanded ? <MdArrowDropDown className="text-2xl" /> : <MdArrowRight className="text-2xl" />}
                </div>
              </div>
              
              {isExpanded && (
                <div className="p-4 border-t border-slate-100 bg-slate-50/50 space-y-4">
                  {/* Generation Trace */}
                  <div className="bg-slate-100 rounded-lg p-3 text-xs font-mono text-slate-600">
                    <p className="font-bold text-slate-700 mb-1 flex items-center gap-1"><MdInfoOutline /> Generation Trace</p>
                    <div className="flex items-center gap-2 overflow-x-auto whitespace-nowrap">
                      <span>Requirement</span>
                      <span>→</span>
                      <span className="text-blue-600">Context: {tc.page_refs?.length || 0} pages, {tc.api_refs?.length || 0} APIs</span>
                      <span>→</span>
                      <span className={isUser ? "text-blue-600" : "text-orange-600"}>{tc.source_agent}</span>
                      {tc.metadata?.merged_from && (
                         <><span>→</span><span className="text-violet-600">Merged from {tc.metadata.merged_from.join(", ")}</span></>
                      )}
                      <span>→</span>
                      <span>Final Test</span>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                      <h5 className="text-xs font-bold text-slate-500 uppercase mb-2">Preconditions</h5>
                      {tc.preconditions && tc.preconditions.length > 0 ? (
                        <ul className="list-disc list-inside text-sm text-slate-700 space-y-1">
                          {tc.preconditions.map((p, i) => <li key={i}>{p}</li>)}
                        </ul>
                      ) : (
                        <p className="text-sm text-slate-400 italic">None specified</p>
                      )}
                    </div>
                    <div>
                      <h5 className="text-xs font-bold text-slate-500 uppercase mb-2">Expected Results</h5>
                      <p className="text-sm text-slate-700 whitespace-pre-line">{tc.expected_result || <span className="text-slate-400 italic">None specified</span>}</p>
                    </div>
                  </div>

                  <div>
                    <h5 className="text-xs font-bold text-slate-500 uppercase mb-2">Steps</h5>
                    <ol className="list-decimal list-inside text-sm text-slate-700 space-y-2">
                      {tc.steps?.map((step, i) => (
                        <li key={i} className="pl-2">{step}</li>
                      ))}
                    </ol>
                  </div>
                  
                  {tc.evidence_refs && tc.evidence_refs.length > 0 && (
                    <div>
                      <h5 className="text-xs font-bold text-slate-500 uppercase mb-2">Evidence References</h5>
                      <div className="flex flex-wrap gap-2">
                        {tc.evidence_refs.map((ref, i) => (
                          <span key={i} className="px-2 py-1 bg-white border border-slate-200 rounded text-[10px] text-slate-500 font-mono">
                            {ref}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
        {filteredTests.length === 0 && (
          <div className="text-center py-10 text-slate-400">
            No tests match the current filters.
          </div>
        )}
      </div>
    </div>
  );
}
