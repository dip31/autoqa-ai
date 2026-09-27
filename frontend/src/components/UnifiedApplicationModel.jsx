import React, { useMemo, useState } from 'react';
import {
  MdOutlineAccountTree, MdOutlineVisibility, MdOutlinePsychology,
  MdHelpOutline, MdCheckCircle, MdError, MdWarningAmber,
  MdExpandMore, MdExpandLess, MdClose, MdOutlineLayers,
  MdOutlineTouchApp, MdOutlineDynamicForm, MdOutlineApi,
  MdOutlineRoute, MdOutlineWidgets, MdOutlineHub, MdOutlineRule
} from 'react-icons/md';

/**
 * Phase 1.5F — read-only view of the fused UnifiedApplicationModel.
 *
 * Nothing here edits, re-runs or re-interprets anything: it renders what the
 * deterministic fusion engine produced, keeps observed evidence visually
 * distinct from inferred conclusions, and exposes the provenance behind every
 * claim ("Why does AgentQE believe this?").
 */

const STATUS_STYLES = {
  observed: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  inferred: 'bg-amber-50 text-amber-700 border-amber-200',
  unknown: 'bg-slate-100 text-slate-500 border-slate-200',
};

const STATUS_HELP = {
  observed: 'Directly supported by collected evidence.',
  inferred: 'Derived from evidence by deterministic rules — not directly observed.',
  unknown: 'Detected, but the evidence was insufficient to characterise it.',
};

const REF_HELP = {
  crawl: 'Crawled page record',
  dom: 'DOM element / form captured from the live page',
  ax: 'Accessibility tree node',
  visual: 'Visual UI element detected by OmniParser',
  network: 'Observed network request',
  screenshot: 'Screenshot artifact (referenced, not embedded)',
  requirement: 'Normalized requirement',
  repository: 'Repository source file',
  context: 'Field produced by an earlier analysis phase',
};

const REF_STYLES = {
  crawl: 'bg-slate-50 text-slate-600 border-slate-200',
  dom: 'bg-blue-50 text-blue-700 border-blue-200',
  ax: 'bg-indigo-50 text-indigo-700 border-indigo-200',
  visual: 'bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200',
  network: 'bg-cyan-50 text-cyan-700 border-cyan-200',
  screenshot: 'bg-teal-50 text-teal-700 border-teal-200',
  requirement: 'bg-violet-50 text-violet-700 border-violet-200',
  repository: 'bg-orange-50 text-orange-700 border-orange-200',
  context: 'bg-slate-50 text-slate-600 border-slate-200',
};

function StatusChip({ status, title }) {
  const key = STATUS_STYLES[status] ? status : 'unknown';
  return (
    <span
      title={title || STATUS_HELP[key]}
      className={`px-2 py-0.5 rounded border text-[9px] font-bold uppercase tracking-wide ${STATUS_STYLES[key]}`}
    >
      {status || 'unknown'}
    </span>
  );
}

function Metric({ label, value, tone = 'slate' }) {
  const tones = {
    slate: 'bg-slate-50 border-slate-200 text-slate-800',
    emerald: 'bg-emerald-50 border-emerald-200 text-emerald-800',
    amber: 'bg-amber-50 border-amber-200 text-amber-800',
  };
  return (
    <div className={`p-3 rounded-xl border ${tones[tone] || tones.slate}`}>
      <p className="text-[10px] font-bold uppercase tracking-wide opacity-60 mb-1">{label}</p>
      <p className="text-lg font-black leading-none">{value ?? 0}</p>
    </div>
  );
}

function Section({ title, icon, count, open, onToggle, children }) {
  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden bg-white">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-50 transition-colors"
      >
        <span className="flex items-center gap-2 text-xs font-bold text-slate-700 uppercase tracking-wide">
          {icon} {title}
          <span className="px-1.5 py-0.5 bg-slate-100 border border-slate-200 rounded text-[10px] font-bold text-slate-500">
            {count}
          </span>
        </span>
        {open ? <MdExpandLess className="text-slate-400" /> : <MdExpandMore className="text-slate-400" />}
      </button>
      {open && <div className="px-4 pb-4 pt-1 border-t border-slate-100">{children}</div>}
    </div>
  );
}

function EvidenceChips({ refs = [], limit = 12 }) {
  if (!refs.length) {
    return <span className="text-[11px] text-slate-400 italic">No evidence references</span>;
  }
  return (
    <div className="flex gap-1 flex-wrap">
      {refs.slice(0, limit).map((ref, i) => {
        const kind = String(ref).split(':')[0];
        return (
          <span
            key={`${ref}-${i}`}
            title={REF_HELP[kind] || 'Evidence reference'}
            className={`px-1.5 py-0.5 rounded border font-mono text-[9px] ${REF_STYLES[kind] || REF_STYLES.context}`}
          >
            {ref}
          </span>
        );
      })}
      {refs.length > limit && (
        <span className="text-[9px] text-slate-400 self-center">+{refs.length - limit} more</span>
      )}
    </div>
  );
}

function Row({ children, onClick, active }) {
  return (
    <div
      onClick={onClick}
      className={`px-3 py-2 rounded-lg border cursor-pointer transition-colors ${
        active ? 'bg-purple-50 border-purple-200' : 'bg-slate-50 border-slate-100 hover:bg-white hover:border-slate-200'
      }`}
    >
      {children}
    </div>
  );
}

function ShowMore({ total, shown, onMore }) {
  if (total <= shown) return null;
  return (
    <button
      type="button"
      onClick={onMore}
      className="text-[11px] font-bold text-purple-600 hover:text-purple-700 px-2 py-1"
    >
      Show {Math.min(25, total - shown)} more of {total}
    </button>
  );
}

/** "Why does AgentQE believe this?" — provenance for a single entity. */
function WhyPanel({ entity, kind, model, onClose }) {
  const [showRaw, setShowRaw] = useState(false);
  if (!entity) return null;

  const nameOf = (id) => {
    const all = [
      ...(model.pages || []), ...(model.controls || []), ...(model.forms || []),
      ...(model.api_endpoints || []), ...(model.user_flows || []),
      ...(model.modules || []), ...(model.requirements || []),
    ];
    const hit = all.find((e) => e.id === id);
    if (!hit) return id;
    return `${id} · ${hit.label || hit.name || hit.title || hit.path || hit.url || hit.description || ''}`.trim();
  };

  const related = (model.relationships || []).filter(
    (r) => r.source_id === entity.id || r.target_id === entity.id
  );

  return (
    <div className="mt-3 border border-purple-200 bg-purple-50/40 rounded-xl p-4">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-widest text-purple-500 flex items-center gap-1">
            <MdHelpOutline /> Why does AgentQE believe this?
          </p>
          <p className="text-sm font-bold text-slate-800 mt-1">
            {kind} · {entity.id}
          </p>
        </div>
        <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-600">
          <MdClose />
        </button>
      </div>

      <div className="space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <StatusChip status={entity.observation_status} />
          {entity.semantic_role && (
            <span className="px-2 py-0.5 bg-white border border-slate-200 rounded text-[9px] font-bold text-slate-600 uppercase">
              role: {entity.semantic_role} ({entity.semantic_role_status})
            </span>
          )}
          {entity.confidence !== null && entity.confidence !== undefined && (
            <span className="px-2 py-0.5 bg-white border border-slate-200 rounded text-[9px] font-bold text-slate-600">
              confidence {entity.confidence}
            </span>
          )}
          {(entity.confidence === null || entity.confidence === undefined) && (
            <span
              title="No documented formula applies, so no confidence is claimed."
              className="px-2 py-0.5 bg-white border border-dashed border-slate-300 rounded text-[9px] font-bold text-slate-400"
            >
              confidence not claimed
            </span>
          )}
        </div>

        {entity.inference_reason && (
          <div className="bg-white border border-amber-200 rounded-lg p-3">
            <p className="text-[10px] font-bold uppercase text-amber-600 mb-1">Inference reason</p>
            <p className="text-[11px] text-slate-700 leading-relaxed">{entity.inference_reason}</p>
          </div>
        )}

        {entity.confidence_basis && (
          <div className="bg-white border border-slate-200 rounded-lg p-3">
            <p className="text-[10px] font-bold uppercase text-slate-500 mb-1">Confidence basis</p>
            <p className="text-[11px] text-slate-600 font-mono leading-relaxed">{entity.confidence_basis}</p>
          </div>
        )}

        <div className="bg-white border border-slate-200 rounded-lg p-3">
          <p className="text-[10px] font-bold uppercase text-slate-500 mb-2">Evidence references</p>
          <EvidenceChips refs={entity.evidence_refs} limit={30} />
          {entity.evidence_sources?.length > 0 && (
            <p className="text-[10px] text-slate-400 mt-2">
              Observed in: {entity.evidence_sources.join(', ')}
            </p>
          )}
        </div>

        {entity.correlation && Object.keys(entity.correlation).length > 0 && (
          <div className="bg-white border border-slate-200 rounded-lg p-3">
            <p className="text-[10px] font-bold uppercase text-slate-500 mb-2">
              Cross-modal correlation (internal matching scores, not model confidence)
            </p>
            <div className="space-y-2">
              {Object.entries(entity.correlation).map(([modality, info]) => (
                <div key={modality} className="text-[11px] text-slate-600">
                  <span className="font-bold uppercase text-slate-500">{modality}</span>
                  {info?.match && <span className="ml-2 text-slate-500">match: {info.match}</span>}
                  {info?.score !== undefined && info?.score !== null && (
                    <span className="ml-2 font-mono">score {info.score}</span>
                  )}
                  {info?.signals && (
                    <div className="mt-1 flex gap-1 flex-wrap">
                      {Object.entries(info.signals)
                        .filter(([k]) => k !== 'weights')
                        .map(([k, v]) => (
                          <span key={k} className="px-1.5 py-0.5 bg-slate-50 border border-slate-200 rounded font-mono text-[9px]">
                            {k}={typeof v === 'number' ? Math.round(v * 10000) / 10000 : String(v)}
                          </span>
                        ))}
                    </div>
                  )}
                  {info?.geometry && <p className="text-[10px] text-slate-400 mt-1">{info.geometry}</p>}
                </div>
              ))}
            </div>
          </div>
        )}

        {entity.requirement_refs?.length > 0 && (
          <div className="bg-white border border-violet-200 rounded-lg p-3">
            <p className="text-[10px] font-bold uppercase text-violet-600 mb-1">Requirement traceability</p>
            <p className="text-[11px] text-slate-600">{entity.requirement_refs.join(', ')}</p>
          </div>
        )}

        {entity.repository_refs?.length > 0 && (
          <div className="bg-white border border-orange-200 rounded-lg p-3">
            <p className="text-[10px] font-bold uppercase text-orange-600 mb-1">Repository traceability</p>
            <div className="space-y-1">
              {entity.repository_refs.map((r, i) => (
                <p key={i} className="text-[11px] text-slate-600 font-mono">
                  {r.file}
                  {r.match_reason ? <span className="text-slate-400 font-sans"> — {r.match_reason}</span> : null}
                </p>
              ))}
            </div>
          </div>
        )}

        {related.length > 0 && (
          <div className="bg-white border border-slate-200 rounded-lg p-3">
            <p className="text-[10px] font-bold uppercase text-slate-500 mb-2">
              Relationships ({related.length})
            </p>
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {related.slice(0, 40).map((r) => (
                <div key={r.id} className="text-[11px] text-slate-600 flex items-start gap-2">
                  <StatusChip status={r.observation_status} />
                  <span className="font-mono">
                    {r.source_id === entity.id ? '→' : '←'} {r.relationship}
                  </span>
                  <span className="text-slate-500">
                    {nameOf(r.source_id === entity.id ? r.target_id : r.source_id)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div>
          <button
            type="button"
            onClick={() => setShowRaw((v) => !v)}
            className="text-[11px] font-bold text-slate-500 hover:text-slate-700"
          >
            {showRaw ? 'Hide' : 'Show'} raw entity JSON
          </button>
          {showRaw && (
            <pre className="mt-2 bg-slate-900 text-slate-100 text-[10px] p-3 rounded-lg overflow-x-auto max-h-64">
              {JSON.stringify(entity, null, 2)}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}

export default function UnifiedApplicationModel({ model }) {
  const [open, setOpen] = useState({ pages: true });
  const [selected, setSelected] = useState(null); // { kind, id }
  const [limits, setLimits] = useState({});
  const [controlFilter, setControlFilter] = useState('');
  const [relFilter, setRelFilter] = useState('');

  const summary = model?.evidence_summary || {};
  const meta = model?.fusion_metadata || {};
  const validation = meta.validation || {};
  const coverage = summary.coverage || {};
  const correlation = summary.correlation || {};

  const toggle = (key) => setOpen((prev) => ({ ...prev, [key]: !prev[key] }));
  const limitOf = (key, fallback = 15) => limits[key] || fallback;
  const more = (key, fallback = 15) =>
    setLimits((prev) => ({ ...prev, [key]: (prev[key] || fallback) + 25 }));

  const byId = useMemo(() => {
    const map = {};
    [
      ['page', model?.pages], ['control', model?.controls], ['form', model?.forms],
      ['endpoint', model?.api_endpoints], ['flow', model?.user_flows],
      ['module', model?.modules], ['requirement', model?.requirements],
    ].forEach(([kind, list]) => (list || []).forEach((e) => { map[e.id] = { kind, entity: e }; }));
    return map;
  }, [model]);

  const pageLabel = (id) => {
    const hit = byId[id];
    if (!hit) return id;
    return hit.entity.title || hit.entity.url || id;
  };

  const select = (kind, id) =>
    setSelected((prev) => (prev && prev.id === id ? null : { kind, id }));

  const detail = selected ? byId[selected.id] : null;

  if (!model) return null;

  const filteredControls = (model.controls || []).filter((c) => {
    if (!controlFilter.trim()) return true;
    const needle = controlFilter.trim().toLowerCase();
    return [c.id, c.type, c.label, c.semantic_role, c.observation_status, c.page_id]
      .filter(Boolean)
      .some((v) => String(v).toLowerCase().includes(needle));
  });

  const filteredRelationships = (model.relationships || []).filter((r) => {
    if (!relFilter.trim()) return true;
    const needle = relFilter.trim().toLowerCase();
    return [r.relationship, r.source_id, r.target_id, r.observation_status]
      .filter(Boolean)
      .some((v) => String(v).toLowerCase().includes(needle));
  });

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
      <div className="flex items-start justify-between gap-4 mb-4 flex-wrap">
        <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest flex items-center gap-2">
          <MdOutlineAccountTree className="text-purple-500" /> Unified Application Model
        </h3>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="px-2 py-0.5 bg-slate-100 border border-slate-200 rounded text-[9px] font-bold text-slate-600 uppercase">
            engine: {meta.engine || 'unknown'}{meta.llm_used ? '' : ' · no LLM'}
          </span>
          <span className="px-2 py-0.5 bg-slate-100 border border-slate-200 rounded text-[9px] font-bold text-slate-600">
            v{meta.fusion_version}
          </span>
          {meta.duration_ms !== undefined && meta.duration_ms !== null && (
            <span className="px-2 py-0.5 bg-slate-100 border border-slate-200 rounded text-[9px] font-bold text-slate-600">
              {meta.duration_ms} ms
            </span>
          )}
          {validation.valid === true && (
            <span className="px-2 py-0.5 bg-emerald-50 border border-emerald-200 rounded text-[9px] font-bold text-emerald-700 flex items-center gap-1">
              <MdCheckCircle /> validated
            </span>
          )}
          {validation.valid === false && (
            <span className="px-2 py-0.5 bg-red-50 border border-red-200 rounded text-[9px] font-bold text-red-700 flex items-center gap-1">
              <MdError /> {validation.error_count} validation error(s)
            </span>
          )}
        </div>
      </div>

      <p className="text-[11px] text-slate-500 mb-4 leading-relaxed">
        One traceable model fused from requirement, repository, DOM, accessibility, network,
        screenshot and visual-UI evidence. Raw evidence is referenced, never replaced —
        <span className="text-emerald-700 font-semibold"> observed</span> facts and
        <span className="text-amber-700 font-semibold"> inferred</span> conclusions are labelled
        separately, and nothing is asserted without a reference.
      </p>

      {/* Summary counts — computed from the model itself */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <Metric label="Pages" value={summary.pages} />
        <Metric label="Controls" value={summary.controls} />
        <Metric label="Forms" value={summary.forms} />
        <Metric label="API Endpoints" value={summary.api_endpoints} />
        <Metric label="User Flows" value={summary.user_flows} />
        <Metric label="Modules" value={summary.modules} />
        <Metric label="Relationships" value={summary.relationships} />
        <Metric label="Requirements" value={summary.requirements} />
      </div>

      <div className="grid grid-cols-3 gap-3 mb-4">
        <Metric label="Observed" value={summary.observed_entities} tone="emerald" />
        <Metric label="Inferred" value={summary.inferred_entities} tone="amber" />
        <Metric label="Unknown" value={summary.unknown_entities} />
      </div>

      {/* Evidence coverage */}
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 mb-4">
        <p className="text-[10px] font-bold uppercase text-slate-400 mb-2">Evidence coverage</p>
        <div className="flex gap-2 flex-wrap">
          {[
            ['DOM', coverage.pages_with_dom],
            ['Accessibility', coverage.pages_with_accessibility],
            ['Network', coverage.pages_with_network],
            ['Screenshot', coverage.pages_with_screenshot],
            ['Visual UI', coverage.pages_with_visual_ui],
          ].map(([label, value]) => (
            <span key={label} className="px-2 py-1 bg-white border border-slate-200 rounded-lg text-[10px] font-medium text-slate-600">
              {label}: <span className="font-bold text-slate-800">{value ?? 0}</span>/{summary.pages ?? 0} pages
            </span>
          ))}
          {[
            ['DOM elements', summary.dom_controls],
            ['AX nodes', summary.accessibility_nodes],
            ['Visual elements', summary.visual_elements],
            ['Visual merges', correlation.controls_with_visual_correlation],
            ['Visual-only', correlation.visual_only_controls],
            ['Ambiguous (not merged)', correlation.ambiguous_visual_matches],
            ['Semantic roles', correlation.controls_with_semantic_role],
          ].map(([label, value]) => (
            <span key={label} className="px-2 py-1 bg-white border border-slate-200 rounded-lg text-[10px] font-medium text-slate-600">
              {label}: <span className="font-bold text-slate-800">{value ?? 0}</span>
            </span>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        {/* Pages */}
        <Section
          title="Pages" icon={<MdOutlineLayers className="text-blue-500" />}
          count={(model.pages || []).length} open={!!open.pages} onToggle={() => toggle('pages')}
        >
          <div className="space-y-2 mt-2">
            {(model.pages || []).slice(0, limitOf('pages')).map((p) => (
              <Row key={p.id} onClick={() => select('Page', p.id)} active={selected?.id === p.id}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[12px] font-bold text-slate-800 truncate">{p.title || p.url}</p>
                    <p className="text-[10px] text-slate-500 font-mono truncate">{p.url}</p>
                  </div>
                  <div className="flex items-center gap-1 flex-wrap justify-end">
                    <StatusChip status={p.observation_status} />
                    {p.page_type && (
                      <span className="px-1.5 py-0.5 bg-white border border-slate-200 rounded text-[9px] font-bold text-slate-500">
                        {p.page_type} ({p.page_type_status})
                      </span>
                    )}
                    <span className="text-[9px] text-slate-400">
                      {p.controls?.length || 0} controls · {p.forms?.length || 0} forms · {p.api_endpoints?.length || 0} APIs
                    </span>
                  </div>
                </div>
              </Row>
            ))}
            <ShowMore total={(model.pages || []).length} shown={limitOf('pages')} onMore={() => more('pages')} />
          </div>
        </Section>

        {/* Controls */}
        <Section
          title="Controls" icon={<MdOutlineTouchApp className="text-indigo-500" />}
          count={(model.controls || []).length} open={!!open.controls} onToggle={() => toggle('controls')}
        >
          <input
            value={controlFilter}
            onChange={(e) => setControlFilter(e.target.value)}
            placeholder="Filter by label, type, role, status or page..."
            className="w-full mt-2 mb-2 px-3 py-2 text-[11px] border border-slate-200 rounded-lg focus:outline-none focus:border-purple-300"
          />
          <div className="space-y-2">
            {filteredControls.slice(0, limitOf('controls')).map((c) => (
              <Row key={c.id} onClick={() => select('Control', c.id)} active={selected?.id === c.id}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[12px] font-bold text-slate-800 truncate">
                      {c.label || <span className="text-slate-400 italic">unlabelled</span>}
                    </p>
                    <p className="text-[10px] text-slate-500">
                      <span className="font-bold uppercase">{c.type}</span>
                      {c.semantic_role ? ` · ${c.semantic_role}` : ' · no semantic role'}
                      {' · '}{pageLabel(c.page_id)}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 flex-wrap justify-end">
                    <StatusChip status={c.observation_status} />
                    {(c.evidence_sources || []).filter((s) => s !== 'crawl').map((s) => (
                      <span key={s} className={`px-1.5 py-0.5 rounded border text-[9px] font-bold ${
                        REF_STYLES[s === 'accessibility' ? 'ax' : s === 'visual_ui' ? 'visual' : s] || REF_STYLES.context
                      }`}>
                        {s}
                      </span>
                    ))}
                  </div>
                </div>
              </Row>
            ))}
            <ShowMore total={filteredControls.length} shown={limitOf('controls')} onMore={() => more('controls')} />
          </div>
        </Section>

        {/* Forms */}
        <Section
          title="Forms" icon={<MdOutlineDynamicForm className="text-emerald-500" />}
          count={(model.forms || []).length} open={!!open.forms} onToggle={() => toggle('forms')}
        >
          <div className="space-y-2 mt-2">
            {(model.forms || []).slice(0, limitOf('forms')).map((f) => (
              <Row key={f.id} onClick={() => select('Form', f.id)} active={selected?.id === f.id}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[12px] font-bold text-slate-800 truncate">
                      {f.name || f.id} {f.semantic_role && <span className="text-slate-500">· {f.semantic_role}</span>}
                    </p>
                    <p className="text-[10px] text-slate-500 font-mono truncate">
                      {f.method} {f.action || '(no action attribute)'} · {f.fields?.length || 0} fields
                      {f.submit_control ? ` · submit ${f.submit_control}` : ' · no submit control identified'}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 flex-wrap justify-end">
                    <StatusChip status={f.observation_status} />
                    {(f.observed_api_endpoints || []).map((a) => (
                      <span key={a} className="px-1.5 py-0.5 bg-cyan-50 border border-cyan-200 rounded text-[9px] font-bold text-cyan-700">
                        {a}
                      </span>
                    ))}
                  </div>
                </div>
              </Row>
            ))}
            <ShowMore total={(model.forms || []).length} shown={limitOf('forms')} onMore={() => more('forms')} />
          </div>
        </Section>

        {/* API endpoints */}
        <Section
          title="API Endpoints" icon={<MdOutlineApi className="text-cyan-500" />}
          count={(model.api_endpoints || []).length} open={!!open.apis} onToggle={() => toggle('apis')}
        >
          <div className="space-y-2 mt-2">
            {(model.api_endpoints || []).slice(0, limitOf('apis')).map((a) => (
              <Row key={a.id} onClick={() => select('API endpoint', a.id)} active={selected?.id === a.id}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[12px] font-bold text-slate-800 font-mono truncate">
                      {a.method} {a.path}
                    </p>
                    <p className="text-[10px] text-slate-500 truncate">
                      {a.host} · observed {a.observation_count}×
                      {a.failure_count ? ` · ${a.failure_count} failure(s)` : ''}
                      {a.response_metadata?.statuses?.length ? ` · status ${a.response_metadata.statuses.join(', ')}` : ''}
                    </p>
                  </div>
                  <div className="flex items-center gap-1 flex-wrap justify-end">
                    <StatusChip status={a.observation_status} />
                    {(a.observed_on_pages || []).slice(0, 3).map((p) => (
                      <span key={p} className="px-1.5 py-0.5 bg-white border border-slate-200 rounded text-[9px] font-mono text-slate-500">
                        {p}
                      </span>
                    ))}
                  </div>
                </div>
              </Row>
            ))}
            <ShowMore total={(model.api_endpoints || []).length} shown={limitOf('apis')} onMore={() => more('apis')} />
          </div>
          <p className="text-[10px] text-slate-400 mt-2 italic">
            Request/response headers, cookies, tokens and bodies are deliberately excluded from this model.
          </p>
        </Section>

        {/* User flows */}
        <Section
          title="User Flows" icon={<MdOutlineRoute className="text-orange-500" />}
          count={(model.user_flows || []).length} open={!!open.flows} onToggle={() => toggle('flows')}
        >
          <div className="space-y-2 mt-2">
            {(model.user_flows || []).slice(0, limitOf('flows')).map((f) => (
              <div key={f.id} className="bg-slate-50 border border-slate-100 rounded-lg p-3">
                <div
                  className="flex items-start justify-between gap-3 cursor-pointer"
                  onClick={() => select('User flow', f.id)}
                >
                  <div className="min-w-0">
                    <p className="text-[12px] font-bold text-slate-800 truncate">{f.name}</p>
                    <p className="text-[10px] text-slate-500">
                      source: {f.source} · {f.steps?.length || 0} step(s)
                      {f.confidence !== null && f.confidence !== undefined
                        ? ` · confidence ${f.confidence}`
                        : ' · confidence not claimed'}
                    </p>
                  </div>
                  <StatusChip status={f.observation_status} />
                </div>
                {(f.steps || []).length > 0 && (
                  <ol className="mt-2 space-y-1">
                    {f.steps.map((s) => (
                      <li key={s.order} className="flex items-start gap-2 text-[11px] text-slate-600">
                        <span className="font-mono text-slate-400">{s.order}.</span>
                        <StatusChip status={s.observation_status} />
                        <span className="font-bold uppercase text-[9px] text-slate-500 mt-0.5">{s.action}</span>
                        <span className="flex-1">{s.description}</span>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            ))}
            <ShowMore total={(model.user_flows || []).length} shown={limitOf('flows')} onMore={() => more('flows')} />
          </div>
        </Section>

        {/* Modules */}
        <Section
          title="Modules" icon={<MdOutlineWidgets className="text-violet-500" />}
          count={(model.modules || []).length} open={!!open.modules} onToggle={() => toggle('modules')}
        >
          <div className="space-y-2 mt-2">
            {(model.modules || []).slice(0, limitOf('modules')).map((m) => (
              <Row key={m.id} onClick={() => select('Module', m.id)} active={selected?.id === m.id}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-[12px] font-bold text-slate-800 truncate">{m.name}</p>
                    <p className="text-[10px] text-slate-500">
                      named by {m.source} · {m.pages?.length || 0} page(s) · {m.forms?.length || 0} form(s) · {m.api_endpoints?.length || 0} endpoint(s)
                    </p>
                  </div>
                  <StatusChip status={m.observation_status} />
                </div>
              </Row>
            ))}
            <ShowMore total={(model.modules || []).length} shown={limitOf('modules')} onMore={() => more('modules')} />
          </div>
        </Section>

        {/* Requirements */}
        {(model.requirements || []).length > 0 && (
          <Section
            title="Requirements" icon={<MdOutlineRule className="text-purple-500" />}
            count={(model.requirements || []).length} open={!!open.requirements}
            onToggle={() => toggle('requirements')}
          >
            <div className="space-y-2 mt-2">
              {(model.requirements || []).slice(0, limitOf('requirements')).map((r) => (
                <Row key={r.id} onClick={() => select('Requirement', r.id)} active={selected?.id === r.id}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[12px] font-bold text-slate-800">{r.id}</p>
                      <p className="text-[11px] text-slate-600">{r.description}</p>
                    </div>
                    <StatusChip status={r.observation_status} />
                  </div>
                </Row>
              ))}
              <ShowMore total={(model.requirements || []).length} shown={limitOf('requirements')} onMore={() => more('requirements')} />
            </div>
          </Section>
        )}

        {/* Relationships */}
        <Section
          title="Relationships" icon={<MdOutlineHub className="text-slate-500" />}
          count={(model.relationships || []).length} open={!!open.rels} onToggle={() => toggle('rels')}
        >
          <input
            value={relFilter}
            onChange={(e) => setRelFilter(e.target.value)}
            placeholder="Filter by type or entity id (e.g. likely_triggers, control_003)..."
            className="w-full mt-2 mb-2 px-3 py-2 text-[11px] border border-slate-200 rounded-lg focus:outline-none focus:border-purple-300"
          />
          <div className="space-y-1">
            {filteredRelationships.slice(0, limitOf('rels', 25)).map((r) => (
              <div key={r.id} className="px-3 py-2 bg-slate-50 border border-slate-100 rounded-lg">
                <div className="flex items-start gap-2 flex-wrap">
                  <StatusChip status={r.observation_status} />
                  <span className="text-[11px] font-mono text-slate-700">
                    {r.source_id} <span className="font-bold text-purple-600">{r.relationship}</span> {r.target_id}
                  </span>
                  {r.confidence !== null && r.confidence !== undefined && (
                    <span className="text-[9px] font-bold text-slate-500">conf {r.confidence}</span>
                  )}
                </div>
                {r.inference_reason && (
                  <p className="text-[10px] text-slate-500 mt-1 leading-relaxed">{r.inference_reason}</p>
                )}
              </div>
            ))}
            <ShowMore total={filteredRelationships.length} shown={limitOf('rels', 25)} onMore={() => more('rels', 25)} />
          </div>
        </Section>

        {/* Fusion provenance */}
        <Section
          title="Fusion Provenance" icon={<MdOutlinePsychology className="text-fuchsia-500" />}
          count={(meta.sources || []).length} open={!!open.provenance} onToggle={() => toggle('provenance')}
        >
          <div className="space-y-3 mt-2">
            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
              <p className="text-[10px] font-bold uppercase text-slate-400 mb-2">Evidence sources fused</p>
              <div className="flex gap-1 flex-wrap">
                {(meta.sources || []).map((s) => (
                  <span key={s} className="px-2 py-0.5 bg-white border border-slate-200 rounded text-[10px] font-medium text-slate-600">
                    {s}
                  </span>
                ))}
                {!(meta.sources || []).length && (
                  <span className="text-[11px] text-slate-400 italic">No evidence sources were present</span>
                )}
              </div>
              <p className="text-[10px] text-slate-400 mt-2">
                Fused at {meta.fusion_timestamp} by the <span className="font-bold">{meta.engine}</span> engine
                (LLM used: {String(meta.llm_used)}).
              </p>
            </div>

            {(meta.warnings || []).length > 0 && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                <p className="text-[10px] font-bold uppercase text-amber-600 mb-2 flex items-center gap-1">
                  <MdWarningAmber /> Fusion warnings ({meta.warnings.length})
                </p>
                <ul className="space-y-1">
                  {meta.warnings.slice(0, 15).map((w, i) => (
                    <li key={i} className="text-[11px] text-amber-800">{w}</li>
                  ))}
                </ul>
              </div>
            )}

            {(validation.errors || []).length > 0 && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                <p className="text-[10px] font-bold uppercase text-red-600 mb-2 flex items-center gap-1">
                  <MdError /> Validation errors ({validation.error_count})
                </p>
                <ul className="space-y-1">
                  {validation.errors.slice(0, 15).map((e, i) => (
                    <li key={i} className="text-[11px] text-red-800">
                      <span className="font-mono font-bold">{e.code}</span> {e.message}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {(validation.warnings || []).length > 0 && (
              <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
                <p className="text-[10px] font-bold uppercase text-slate-400 mb-2">
                  Validation warnings ({validation.warning_count})
                </p>
                <ul className="space-y-1 max-h-40 overflow-y-auto">
                  {validation.warnings.slice(0, 25).map((w, i) => (
                    <li key={i} className="text-[11px] text-slate-600">
                      <span className="font-mono font-bold">{w.code}</span> {w.message}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
              <p className="text-[10px] font-bold uppercase text-slate-400 mb-1 flex items-center gap-1">
                <MdOutlineVisibility /> How to read this model
              </p>
              <p className="text-[11px] text-slate-600 leading-relaxed">
                <span className="font-bold text-emerald-700">Observed</span> means the claim comes
                straight from captured evidence. <span className="font-bold text-amber-700">Inferred</span>{' '}
                means deterministic rules derived it — for example a semantic role, a visual element
                merged into a DOM control, or a form associated with an endpoint that was never
                actually submitted during the crawl. Correlation scores are internal matching scores,
                not model probabilities, and confidence is left unset wherever no documented formula
                applies.
              </p>
            </div>
          </div>
        </Section>
      </div>

      {detail && (
        <WhyPanel
          entity={detail.entity}
          kind={selected.kind}
          model={model}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
