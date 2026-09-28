import React, { useState, useMemo } from 'react';
import { 
  MdOutlineAnalytics, MdOutlineLanguage, MdOutlineRule, 
  MdOutlineFactCheck, MdTimeline, MdSearch, MdFilterList,
  MdInfoOutline, MdLink
} from 'react-icons/md';

export default function KnowledgeModelUI({ knowledgeModel }) {
  const [activeTab, setActiveTab] = useState('entities');
  const [searchTerm, setSearchTerm] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [selectedEntityId, setSelectedEntityId] = useState(null);

  const { entities = [], relationships = [], summaries = {}, provenance = {} } = knowledgeModel || {};
  const appSummary = summaries.application_summary || {};

  const filteredEntities = useMemo(() => {
    return entities.filter(e => {
      const matchesSearch = e.name?.toLowerCase().includes(searchTerm.toLowerCase()) || 
                            e.id?.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesType = typeFilter === 'all' || e.entity_type === typeFilter;
      return matchesSearch && matchesType;
    });
  }, [entities, searchTerm, typeFilter]);

  const selectedEntity = useMemo(() => {
    return entities.find(e => e.id === selectedEntityId);
  }, [entities, selectedEntityId]);

  const entityTypes = useMemo(() => {
    const types = new Set(entities.map(e => e.entity_type));
    return Array.from(types).sort();
  }, [entities]);

  const renderGraph = () => {
    if (entities.length === 0) return <div className="text-center text-slate-500 py-10">No graph data</div>;
    
    const cols = Math.ceil(Math.sqrt(entities.length));
    const spacing = 150;
    const width = Math.max(800, cols * spacing + 100);
    const height = Math.max(600, Math.ceil(entities.length / cols) * spacing + 100);
    
    const nodePositions = {};
    entities.forEach((entity, index) => {
      const row = Math.floor(index / cols);
      const col = index % cols;
      nodePositions[entity.id] = {
        x: col * spacing + 100,
        y: row * spacing + 100
      };
    });

    return (
      <div className="w-full h-[600px] overflow-auto border border-slate-200 rounded-lg bg-slate-50 relative">
        <svg width={width} height={height} className="min-w-full min-h-full">
          <defs>
            <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="25" refY="3.5" orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="#94a3b8" />
            </marker>
          </defs>
          
          {relationships.map((rel, idx) => {
            const source = nodePositions[rel.source_id];
            const target = nodePositions[rel.target_id];
            if (!source || !target) return null;
            
            return (
              <g key={`edge-${idx}`}>
                <line 
                  x1={source.x} y1={source.y} 
                  x2={target.x} y2={target.y} 
                  stroke="#cbd5e1" strokeWidth="1.5"
                  markerEnd="url(#arrowhead)"
                />
                <text 
                  x={(source.x + target.x) / 2} 
                  y={(source.y + target.y) / 2 - 5}
                  fontSize="8" fill="#64748b" textAnchor="middle"
                >
                  {rel.relationship}
                </text>
              </g>
            );
          })}
          
          {entities.map(entity => {
            const pos = nodePositions[entity.id];
            const isSelected = selectedEntityId === entity.id;
            let color = "#e2e8f0";
            if (entity.entity_type === 'page') color = "#10b981";
            else if (entity.entity_type === 'control') color = "#f59e0b";
            else if (entity.entity_type === 'form') color = "#ec4899";
            else if (entity.entity_type === 'api_endpoint') color = "#f97316";
            else if (entity.entity_type === 'user_flow') color = "#3b82f6";
            else if (entity.entity_type === 'module') color = "#8b5cf6";

            return (
              <g 
                key={entity.id} 
                transform={`translate(${pos.x}, ${pos.y})`}
                onClick={() => setSelectedEntityId(entity.id)}
                className="cursor-pointer transition-transform hover:scale-110"
              >
                <circle 
                  r={isSelected ? 18 : 14} 
                  fill={color} 
                  stroke={isSelected ? "#1e293b" : "white"} 
                  strokeWidth="2" 
                />
                <text y="24" fontSize="10" fill="#475569" textAnchor="middle" className="pointer-events-none font-medium">
                  {entity.name || entity.id.split(':').pop()}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-indigo-50 to-violet-50 border border-indigo-100 rounded-2xl p-6 shadow-sm">
        <h3 className="text-xs font-black text-indigo-600 uppercase tracking-widest mb-4 flex items-center gap-2">
          <MdOutlineAnalytics className="text-indigo-500" /> Knowledge Model
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
          {[
            { label: 'Entities', val: appSummary.entity_count ?? '—', icon: MdOutlineAnalytics, color: 'text-indigo-500' },
            { label: 'Relationships', val: appSummary.relationship_count ?? '—', icon: MdLink, color: 'text-violet-500' },
            { label: 'Pages', val: appSummary.page_count ?? '—', icon: MdOutlineLanguage, color: 'text-emerald-500' },
            { label: 'Controls', val: appSummary.control_count ?? '—', icon: MdOutlineRule, color: 'text-amber-500' },
            { label: 'Forms', val: appSummary.form_count ?? '—', icon: MdOutlineFactCheck, color: 'text-pink-500' },
            { label: 'APIs', val: appSummary.api_count ?? '—', icon: MdOutlineLanguage, color: 'text-orange-500' },
            { label: 'Flows', val: appSummary.flow_count ?? '—', icon: MdTimeline, color: 'text-blue-500' },
            { label: 'Modules', val: appSummary.module_count ?? '—', icon: MdOutlineFactCheck, color: 'text-amber-500' },
          ].map((stat, i) => (
            <div key={i} className="bg-white/80 p-3 rounded-xl border border-indigo-100 flex flex-col justify-center">
              <div className="flex items-center gap-1.5 mb-1">
                <stat.icon className={`${stat.color} text-sm`} />
                <p className="text-[9px] text-indigo-400 font-bold uppercase truncate">{stat.label}</p>
              </div>
              <p className="text-lg font-black text-slate-800">{stat.val}</p>
            </div>
          ))}
        </div>
        
        {provenance && (
          <div className="mt-4 pt-4 border-t border-indigo-100/50 flex flex-wrap gap-2 text-[10px]">
            <span className="px-2 py-1 bg-indigo-100 text-indigo-700 font-bold uppercase rounded">
              Builder: {provenance.builder || '—'}
            </span>
            <span className="px-2 py-1 bg-emerald-100 text-emerald-700 font-bold uppercase rounded">
              Generated: {provenance.generated_at ? new Date(provenance.generated_at).toLocaleString() : '—'}
            </span>
          </div>
        )}
      </div>

      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm flex flex-col h-[700px]">
        <div className="flex border-b border-slate-200 bg-slate-50 p-2 gap-2">
          <button 
            onClick={() => setActiveTab('entities')}
            className={`px-4 py-2 text-sm font-medium rounded-lg ${activeTab === 'entities' ? 'bg-white shadow-sm text-indigo-600 border border-slate-200' : 'text-slate-600 hover:bg-slate-100'}`}
          >
            Entities
          </button>
          <button 
            onClick={() => setActiveTab('relationships')}
            className={`px-4 py-2 text-sm font-medium rounded-lg ${activeTab === 'relationships' ? 'bg-white shadow-sm text-indigo-600 border border-slate-200' : 'text-slate-600 hover:bg-slate-100'}`}
          >
            Relationships
          </button>
          <button 
            onClick={() => setActiveTab('graph')}
            className={`px-4 py-2 text-sm font-medium rounded-lg ${activeTab === 'graph' ? 'bg-white shadow-sm text-indigo-600 border border-slate-200' : 'text-slate-600 hover:bg-slate-100'}`}
          >
            Visual Graph
          </button>
        </div>

        <div className="flex-1 flex overflow-hidden">
          {activeTab === 'entities' && (
            <>
              <div className="w-1/2 border-r border-slate-200 flex flex-col bg-white">
                <div className="p-3 border-b border-slate-200 flex gap-2">
                  <div className="relative flex-1">
                    <MdSearch className="absolute left-2.5 top-2.5 text-slate-400" />
                    <input 
                      type="text" 
                      placeholder="Search entities..." 
                      className="w-full pl-8 pr-3 py-1.5 text-sm border border-slate-300 rounded-md focus:outline-none focus:ring-1 focus:ring-indigo-500"
                      value={searchTerm}
                      onChange={e => setSearchTerm(e.target.value)}
                    />
                  </div>
                  <select 
                    className="text-sm border border-slate-300 rounded-md px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    value={typeFilter}
                    onChange={e => setTypeFilter(e.target.value)}
                  >
                    <option value="all">All Types</option>
                    {entityTypes.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div className="flex-1 overflow-y-auto p-2 space-y-1">
                  {filteredEntities.map(entity => (
                    <div 
                      key={entity.id}
                      onClick={() => setSelectedEntityId(entity.id)}
                      className={`p-3 rounded-lg border cursor-pointer transition-colors ${selectedEntityId === entity.id ? 'bg-indigo-50 border-indigo-200' : 'border-transparent hover:bg-slate-50 border-b-slate-100'}`}
                    >
                      <div className="flex justify-between items-start mb-1">
                        <span className="text-sm font-semibold text-slate-800 break-all">{entity.name || entity.id}</span>
                        <span className="text-[9px] font-bold uppercase px-2 py-0.5 rounded bg-slate-100 text-slate-600">{entity.entity_type}</span>
                      </div>
                      <div className="text-xs text-slate-500 truncate">{entity.id}</div>
                      <div className="flex gap-2 mt-2">
                        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${entity.status === 'observed' ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}`}>
                          {entity.status || 'unknown'}
                        </span>
                      </div>
                    </div>
                  ))}
                  {filteredEntities.length === 0 && (
                    <div className="text-center p-8 text-sm text-slate-500">No entities found.</div>
                  )}
                </div>
              </div>
              
              <div className="w-1/2 flex flex-col bg-slate-50 overflow-y-auto p-6">
                {selectedEntity ? (
                  <div className="space-y-6">
                    <div>
                      <div className="flex items-center gap-2 mb-2">
                        <span className="text-xs font-bold uppercase px-2 py-1 rounded bg-indigo-100 text-indigo-700">{selectedEntity.entity_type}</span>
                        <span className={`text-xs font-medium px-2 py-1 rounded ${selectedEntity.status === 'observed' ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}`}>
                          {selectedEntity.status || 'unknown'}
                        </span>
                      </div>
                      <h2 className="text-xl font-bold text-slate-800 break-all">{selectedEntity.name || selectedEntity.id}</h2>
                      <p className="text-xs text-slate-500 font-mono mt-1 break-all">{selectedEntity.id}</p>
                    </div>

                    <div className="bg-white rounded-lg border border-slate-200 p-4">
                      <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Properties</h4>
                      {Object.keys(selectedEntity.properties || {}).length > 0 ? (
                        <dl className="grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2 text-sm">
                          {Object.entries(selectedEntity.properties).map(([k, v]) => (
                            <div key={k} className="sm:col-span-1">
                              <dt className="text-slate-500 font-medium text-xs">{k}</dt>
                              <dd className="text-slate-800 mt-1 break-all">{typeof v === 'object' ? JSON.stringify(v) : String(v)}</dd>
                            </div>
                          ))}
                        </dl>
                      ) : (
                        <p className="text-sm text-slate-500">No properties available.</p>
                      )}
                    </div>

                    <div className="bg-white rounded-lg border border-slate-200 p-4">
                      <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Provenance</h4>
                      <dl className="grid grid-cols-1 gap-3 text-sm">
                        {selectedEntity.source_entity_id && (
                          <div>
                            <dt className="text-slate-500 font-medium text-xs">Source Entity ID (Phase 1.5F)</dt>
                            <dd className="text-slate-800 font-mono text-xs mt-1">{selectedEntity.source_entity_id}</dd>
                          </div>
                        )}
                        <div>
                          <dt className="text-slate-500 font-medium text-xs mb-1">Evidence References</dt>
                          <dd>
                            {selectedEntity.evidence_refs?.length > 0 ? (
                              <ul className="list-disc pl-4 space-y-1">
                                {selectedEntity.evidence_refs.map((ref, i) => (
                                  <li key={i} className="text-slate-700 font-mono text-xs break-all">{ref}</li>
                                ))}
                              </ul>
                            ) : (
                              <span className="text-slate-500 text-xs">No evidence references.</span>
                            )}
                          </dd>
                        </div>
                      </dl>
                    </div>

                    <div className="bg-white rounded-lg border border-slate-200 p-4">
                      <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-3">Relationships</h4>
                      <div className="space-y-2">
                        {relationships.filter(r => r.source_id === selectedEntity.id || r.target_id === selectedEntity.id).map(r => {
                          const isSource = r.source_id === selectedEntity.id;
                          const otherId = isSource ? r.target_id : r.source_id;
                          return (
                            <div key={r.id} className="flex flex-col text-xs p-2 rounded bg-slate-50 border border-slate-100">
                              <div className="flex gap-2 items-center">
                                <span className="font-semibold text-slate-600">{isSource ? 'Outgoing' : 'Incoming'}:</span>
                                <span className="font-mono text-indigo-600 bg-indigo-50 px-1 rounded">{r.relationship}</span>
                              </div>
                              <div className="font-mono text-slate-500 truncate mt-1 pl-2">
                                {isSource ? '→' : '←'} {otherId}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="h-full flex flex-col items-center justify-center text-slate-400">
                    <MdInfoOutline className="text-4xl mb-2 text-slate-300" />
                    <p>Select an entity to view details</p>
                  </div>
                )}
              </div>
            </>
          )}

          {activeTab === 'relationships' && (
            <div className="w-full flex flex-col bg-white overflow-hidden">
              <div className="p-4 border-b border-slate-200 bg-slate-50">
                <h3 className="font-semibold text-slate-800">All Relationships ({relationships.length})</h3>
              </div>
              <div className="flex-1 overflow-auto p-4">
                <table className="w-full text-sm text-left">
                  <thead className="text-xs text-slate-500 bg-slate-50 uppercase sticky top-0">
                    <tr>
                      <th className="px-4 py-3">Source</th>
                      <th className="px-4 py-3">Relationship</th>
                      <th className="px-4 py-3">Target</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">Derivation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {relationships.map((rel, idx) => (
                      <tr key={rel.id || idx} className="border-b border-slate-100 hover:bg-slate-50">
                        <td className="px-4 py-3 font-mono text-xs text-slate-600 max-w-[200px] truncate" title={rel.source_id}>{rel.source_id}</td>
                        <td className="px-4 py-3">
                          <span className="bg-indigo-50 text-indigo-600 px-2 py-1 rounded text-xs font-semibold">{rel.relationship}</span>
                        </td>
                        <td className="px-4 py-3 font-mono text-xs text-slate-600 max-w-[200px] truncate" title={rel.target_id}>{rel.target_id}</td>
                        <td className="px-4 py-3">
                          <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${rel.status === 'observed' ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}`}>
                            {rel.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-xs text-slate-500 max-w-[200px] truncate" title={rel.derivation || rel.derivation_kind}>
                          {rel.derivation || rel.derivation_kind}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {activeTab === 'graph' && (
            <div className="w-full h-full p-4 bg-slate-50">
              {renderGraph()}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
