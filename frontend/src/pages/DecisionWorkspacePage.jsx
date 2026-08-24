import { useCallback, useEffect, useState } from 'react'
import AppShell from '../components/layout/AppShell'
import {
  evaluateBusinessLocation,
  fetchDecisionModel,
  fetchDecisionModels,
  fetchPartnershipRequirements,
  fetchProvinces,
  interpretDecision,
} from '../services/api'

const MODE_COPY = {
  PRODUCTION: {
    title: 'Production',
    description: 'Evidence-based recommendation mode',
  },
  EXPLORATORY: {
    title: 'Exploratory',
    description: 'Limited analysis using currently available evidence',
  },
}

const STATUS_COPY = {
  production_usable: {
    label: 'Ready',
    className: 'text-emerald-300 bg-emerald-400/10 border-emerald-400/20',
  },
  exploratory_only: {
    label: 'Exploratory only',
    className: 'text-amber-200 bg-amber-400/10 border-amber-400/20',
  },
  insufficient: {
    label: 'Insufficient',
    className: 'text-rose-200 bg-rose-400/10 border-rose-400/20',
  },
  blocked_by_evidence: {
    label: 'Awaiting production evidence',
    className: 'text-amber-200 bg-amber-400/10 border-amber-400/20',
  },
}

function formatNumber(value) {
  if (value === null || value === undefined || value === '') return '—'
  return Number(value).toLocaleString()
}

function formatScore(value) {
  return typeof value === 'number' ? value.toFixed(3) : '—'
}

function getErrorMessage(error) {
  return error?.response?.data?.detail || error?.detail || 'The decision service could not be reached.'
}

function StatusBadge({ state = 'blocked_by_evidence', children }) {
  const copy = STATUS_COPY[state] || STATUS_COPY.blocked_by_evidence
  return (
    <span className={`inline-flex items-center border px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] ${copy.className}`}>
      {children || copy.label}
    </span>
  )
}

function SectionHeading({ eyebrow, title, children }) {
  return (
    <div className="flex flex-col gap-2 border-b border-white/10 pb-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-cyan-300">{eyebrow}</p>
        <h2 className="mt-1 text-xl font-semibold tracking-[-0.01em] text-white">{title}</h2>
      </div>
      {children}
    </div>
  )
}

function ReadinessGrid({ criteria, readiness, backlog }) {
  const backlogById = new Map(backlog.map((item) => [item.criterion_id, item]))
  const readinessById = new Map(readiness.map((item) => [item.criterion_id, item]))
  return (
    <div className="grid gap-px overflow-hidden border border-white/10 bg-white/10 sm:grid-cols-2 lg:grid-cols-3">
      {criteria.map((criterion) => {
        const backlogItem = backlogById.get(criterion.criterion_id)
        const readinessItem = readinessById.get(criterion.criterion_id)
        const state = readinessItem?.state || criterion.readiness_state || (backlogItem ? 'blocked_by_evidence' : 'production_usable')
        return (
          <div key={criterion.criterion_id} className="bg-slate-950/90 p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-white">{criterion.name}</p>
                <p className="mt-1 text-xs text-slate-500">Weight {(criterion.weight * 100).toFixed(0)}%</p>
              </div>
              <StatusBadge state={state} />
            </div>
            <p className="mt-4 text-xs leading-5 text-slate-400">{backlogItem?.requirement || 'Authoritative district evidence is available for this criterion.'}</p>
            {readinessItem && <p className="mt-2 text-[11px] text-slate-500">Coverage: {readinessItem.evidence_coverage_percentage}% · {readinessItem.freshness_status}</p>}
            {readinessItem?.blockers?.length > 0 && <p className="mt-2 text-[11px] text-amber-200">Blocked by: {readinessItem.blockers.join(', ')}</p>}
          </div>
        )
      })}
    </div>
  )
}

function ProvenancePanel({ evidence, selectedName }) {
  const item = evidence.find((entry) => entry.geography_name === selectedName) || evidence[0]
  if (!item) return <p className="text-sm text-slate-400">Run an analysis to inspect evidence provenance.</p>

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div>
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">Observation</p>
        <dl className="mt-3 space-y-2 text-sm">
          <div className="flex justify-between gap-4"><dt className="text-slate-500">District</dt><dd className="font-semibold text-white">{item.geography_name}</dd></div>
          <div className="flex justify-between gap-4"><dt className="text-slate-500">Population</dt><dd className="tabular-nums font-semibold text-white">{formatNumber(item.raw_value)}</dd></div>
          <div className="flex justify-between gap-4"><dt className="text-slate-500">Indicator</dt><dd className="text-right text-white">{item.indicator_name || item.indicator_id}</dd></div>
          <div className="flex justify-between gap-4"><dt className="text-slate-500">Reference</dt><dd className="text-white">{item.reference_year || '—'}</dd></div>
        </dl>
      </div>
      <div>
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">Source trail</p>
        <dl className="mt-3 space-y-2 text-sm">
          <div><dt className="text-slate-500">Dataset</dt><dd className="mt-1 text-white">{item.dataset_name || '—'}</dd></div>
          <div><dt className="text-slate-500">Organization</dt><dd className="mt-1 text-white">{item.source_institution || '—'}</dd></div>
          <div className="flex flex-wrap gap-2 pt-1"><StatusBadge>{item.quality || 'unknown'}</StatusBadge><StatusBadge>{item.freshness_status || 'unknown'}</StatusBadge></div>
          {item.source_reference && <a className="mt-2 block truncate text-xs text-cyan-300 underline decoration-cyan-300/30 underline-offset-4 hover:text-cyan-200" href={item.source_reference} target="_blank" rel="noreferrer">Open source reference</a>}
        </dl>
      </div>
    </div>
  )
}

function RankingTable({ scores, onSelect, selectedName }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[650px] text-left text-sm">
        <thead className="border-b border-white/10 text-[10px] uppercase tracking-[0.16em] text-slate-500">
          <tr><th className="px-4 py-3">Rank</th><th className="px-4 py-3">District</th><th className="px-4 py-3 text-right">Demand score</th><th className="px-4 py-3 text-right">Population</th><th className="px-4 py-3 text-right">Year</th><th className="px-4 py-3">Source</th></tr>
        </thead>
        <tbody className="divide-y divide-white/5">
          {scores.map((score, index) => {
            const component = score.criterion_scores?.[0]
            const evidence = component?.evidence
            const name = score.alternative?.display_name
            const selected = name === selectedName
            return (
              <tr key={score.alternative?.identifier || name} className={selected ? 'bg-cyan-400/[0.08]' : 'hover:bg-white/[0.03]'}>
                <td className="px-4 py-3 tabular-nums text-slate-500">{index + 1}</td>
                <td className="px-4 py-3"><button type="button" onClick={() => onSelect(name)} className="font-semibold text-white underline decoration-white/10 underline-offset-4 hover:text-cyan-200 focus-visible:ring-2 focus-visible:ring-cyan-300">{name}</button></td>
                <td className="px-4 py-3 text-right tabular-nums font-semibold text-cyan-200">{formatScore(score.final_score)}</td>
                <td className="px-4 py-3 text-right tabular-nums text-slate-300">{formatNumber(evidence?.raw_value)}</td>
                <td className="px-4 py-3 text-right tabular-nums text-slate-400">{evidence?.reference_year || '—'}</td>
                <td className="max-w-[180px] truncate px-4 py-3 text-xs text-slate-500">{evidence?.source_institution || '—'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default function DecisionWorkspacePage() {
  const [models, setModels] = useState([])
  const [modelDetails, setModelDetails] = useState(null)
  const [provinces, setProvinces] = useState([])
  const [modelId, setModelId] = useState('')
  const [province, setProvince] = useState('LP')
  const [category, setCategory] = useState('')
  const [mode, setMode] = useState('PRODUCTION')
  const [result, setResult] = useState(null)
  const [selectedDistrict, setSelectedDistrict] = useState('Mansa')
  const [loading, setLoading] = useState(true)
  const [evaluating, setEvaluating] = useState(false)
  const [error, setError] = useState('')
  const [languageInput, setLanguageInput] = useState('')
  const [interpretation, setInterpretation] = useState(null)
  const [interpreting, setInterpreting] = useState(false)
  const [partnerships, setPartnerships] = useState([])

  useEffect(() => {
    let active = true
    Promise.all([fetchDecisionModels(), fetchProvinces()])
      .then(([modelResponse, provinceResponse]) => {
        if (!active) return
        const loadedModels = modelResponse.models || []
        setModels(loadedModels)
        setModelId(loadedModels[0]?.model_id || '')
        setCategory(loadedModels[0]?.supported_business_categories?.[0] || '')
        setProvinces(provinceResponse || [])
        fetchPartnershipRequirements().then((response) => active && setPartnerships(response.requirements || []))
        if (provinceResponse?.some((item) => item.code === 'LP')) setProvince('LP')
        else if (provinceResponse?.[0]) setProvince(provinceResponse[0].code)
      })
      .catch((requestError) => active && setError(getErrorMessage(requestError)))
      .finally(() => active && setLoading(false))
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!modelId) return
    fetchDecisionModel(modelId).then(setModelDetails).catch((requestError) => setError(getErrorMessage(requestError)))
  }, [modelId])

  const evaluate = useCallback(async () => {
    if (!modelId || !province) return
    setEvaluating(true)
    setError('')
    try {
      const response = await evaluateBusinessLocation({ model_id: modelId, province, mode, business_category: category, reference_year: 2022 })
      setResult(response)
      const firstDistrict = response.criterion_scores?.[0]?.alternative?.display_name
      if (firstDistrict) setSelectedDistrict(firstDistrict)
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setEvaluating(false)
    }
  }, [category, mode, modelId, province])

  const interpretAndAnalyze = useCallback(async () => {
    const text = languageInput.trim()
    if (!text) return
    setInterpreting(true)
    setError('')
    try {
      const intent = await interpretDecision(text)
      setInterpretation(intent)
      if (!['SUPPORTED', 'PARSED'].includes(intent.status) || !intent.business_category || !intent.province) return
      setCategory(intent.business_category)
      setProvince(intent.province)
      setMode(intent.requested_mode)
      const response = await evaluateBusinessLocation({
        model_id: intent.model_id,
        province: intent.province,
        mode: intent.requested_mode,
        business_category: intent.business_category,
        reference_year: 2022,
      })
      setResult(response)
      const firstDistrict = response.criterion_scores?.[0]?.alternative?.display_name
      if (firstDistrict) setSelectedDistrict(firstDistrict)
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setInterpreting(false)
    }
  }, [languageInput])

  const model = models.find((item) => item.model_id === modelId)
  const backlog = result?.evidence_backlog || modelDetails?.evidence_backlog || []
  const criteria = model?.criteria || modelDetails?.criteria || []
  const readiness = result?.criterion_readiness || []
  const scores = result?.criterion_scores || []
  const isExploratory = result?.mode === 'EXPLORATORY'

  if (loading) {
    return <AppShell><div className="flex min-h-[60vh] items-center justify-center text-sm text-slate-400" role="status">Loading decision workspace…</div></AppShell>
  }

  return (
    <AppShell>
      <div className="decision-workspace space-y-8 pb-10">
        <header className="relative overflow-hidden border border-cyan-300/15 bg-[radial-gradient(circle_at_top_right,_rgba(34,211,238,0.12),_transparent_38%),linear-gradient(135deg,_rgba(15,23,42,0.98),_rgba(15,23,42,0.78))] px-5 py-7 sm:px-8 sm:py-9">
          <div className="relative max-w-3xl">
            <p className="text-[10px] font-bold uppercase tracking-[0.25em] text-cyan-300">Decision Intelligence / Workspace</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-[-0.03em] text-white sm:text-4xl">What decision are you trying to make?</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-300">Explore the evidence behind a location analysis, understand what is ready, and see exactly what StatFlow still needs before it can recommend a district.</p>
          </div>
        </header>

        {error && <div className="border border-rose-300/25 bg-rose-400/10 px-4 py-3 text-sm text-rose-100" role="alert"><strong className="font-semibold">Decision service unavailable.</strong> <span className="ml-1">{error}</span><button type="button" onClick={() => { setError(''); evaluate() }} className="ml-3 font-semibold underline underline-offset-4">Retry</button></div>}

        <section className="border border-cyan-300/20 bg-slate-900/70 p-5 sm:p-6" aria-labelledby="language-heading">
          <SectionHeading eyebrow="Natural language" title="Describe the decision you want help with" />
          <div className="mt-5 flex flex-col gap-3 sm:flex-row">
            <label htmlFor="decision-language" className="sr-only">Describe the decision you want help with</label>
            <input id="decision-language" value={languageInput} onChange={(event) => setLanguageInput(event.target.value)} placeholder="Where should I open a supermarket in Luapula?" className="min-w-0 flex-1 border border-white/10 bg-slate-950 px-3 py-3 text-sm text-white placeholder:text-slate-600 focus:border-cyan-300 focus:outline-none" />
            <button type="button" onClick={interpretAndAnalyze} disabled={interpreting || !languageInput.trim()} className="bg-cyan-300 px-4 py-3 text-sm font-bold text-slate-950 disabled:cursor-not-allowed disabled:opacity-50">{interpreting ? 'Interpreting…' : 'Interpret and analyze'}</button>
          </div>
          {interpretation && <div className="mt-4 border-l-2 border-cyan-300/60 bg-cyan-300/[0.04] px-4 py-3 text-sm" role="status"><p className="font-semibold text-white">Interpretation: {interpretation.status}</p>{interpretation.business_category && <p className="mt-1 text-slate-300">Business: {interpretation.business_category.replaceAll('_', ' ')}</p>}{interpretation.province && <p className="mt-1 text-slate-300">Province: {interpretation.province}</p>}{interpretation.candidate_geography && <p className="mt-1 text-slate-300">Candidate geography: {interpretation.candidate_geography}</p>}{interpretation.requested_mode && <p className="mt-1 text-slate-300">Mode: {interpretation.requested_mode}</p>}{interpretation.missing_fields?.length > 0 && <p className="mt-1 text-slate-400">Missing: {interpretation.missing_fields.join(', ')}</p>}{interpretation.unsupported_parts?.length > 0 && <p className="mt-1 text-slate-400">{interpretation.unsupported_parts.join(' ')}</p>}{interpretation.original_text && <p className="mt-1 text-xs text-slate-500">Original request retained: “{interpretation.original_text}”</p>}</div>}
        </section>

        <section className="grid gap-6 lg:grid-cols-[minmax(260px,0.75fr)_minmax(0,1.7fr)]">
          <div className="border border-white/10 bg-slate-900/70 p-5 sm:p-6">
            <SectionHeading eyebrow="01 / Set the question" title="Location opportunity" />
            <div className="mt-6 space-y-5">
              <div>
                <label htmlFor="decision-model" className="text-xs font-semibold text-slate-300">Decision model</label>
                <select id="decision-model" value={modelId} onChange={(event) => setModelId(event.target.value)} className="mt-2 w-full border border-white/10 bg-slate-950 px-3 py-3 text-sm text-white focus:border-cyan-300 focus:outline-none">
                  {models.map((item) => <option key={item.model_id} value={item.model_id}>{item.name}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="decision-category" className="text-xs font-semibold text-slate-300">Business category</label>
                <select id="decision-category" value={category} onChange={(event) => setCategory(event.target.value)} className="mt-2 w-full border border-white/10 bg-slate-950 px-3 py-3 text-sm text-white focus:border-cyan-300 focus:outline-none">
                  {(model?.supported_business_categories || []).map((value) => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}
                </select>
              </div>
              <div>
                <label htmlFor="decision-province" className="text-xs font-semibold text-slate-300">Province</label>
                <select id="decision-province" value={province} onChange={(event) => setProvince(event.target.value)} className="mt-2 w-full border border-white/10 bg-slate-950 px-3 py-3 text-sm text-white focus:border-cyan-300 focus:outline-none">
                  {provinces.map((item) => <option key={item.code} value={item.code}>{item.name} ({item.code})</option>)}
                </select>
              </div>
              <fieldset>
                <legend className="text-xs font-semibold text-slate-300">Analysis mode</legend>
                <div className="mt-2 grid grid-cols-2 border border-white/10 p-1">
                  {Object.entries(MODE_COPY).map(([value, copy]) => <button key={value} type="button" aria-pressed={mode === value} onClick={() => setMode(value)} className={`px-2 py-3 text-left transition-colors ${mode === value ? 'bg-cyan-300 text-slate-950' : 'text-slate-400 hover:bg-white/5 hover:text-white'}`}><span className="block text-xs font-bold uppercase tracking-[0.14em]">{copy.title}</span><span className="mt-1 block text-[11px] leading-4 opacity-80">{copy.description}</span></button>)}
                </div>
              </fieldset>
              <button type="button" onClick={evaluate} disabled={evaluating || !modelId || !province} className="w-full bg-cyan-300 px-4 py-3 text-sm font-bold text-slate-950 transition-colors hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-50">{evaluating ? 'Analyzing evidence…' : 'Analyze location opportunity'}</button>
              <p className="text-xs leading-5 text-slate-500">Production mode never falls back to exploratory results. Choose Exploratory explicitly to inspect available evidence.</p>
            </div>
          </div>

          <div className="space-y-6">
            <div className="border border-white/10 bg-slate-900/70 p-5 sm:p-6">
              <div className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
                <div><p className="text-[10px] font-bold uppercase tracking-[0.22em] text-cyan-300">02 / Readiness</p><h2 className="mt-2 text-2xl font-semibold text-white">Evidence portfolio</h2></div>
                <div className="flex items-end gap-4"><div><p className="text-[10px] uppercase tracking-[0.16em] text-slate-500">Model readiness</p><p className="mt-1 tabular-nums text-3xl font-semibold text-cyan-200">{result?.model_readiness_percentage ?? model?.readiness_percentage ?? 0}%</p></div>{result && <StatusBadge state={isExploratory ? 'exploratory_only' : result.decision_readiness === 'insufficient_evidence' ? 'blocked_by_evidence' : 'production_usable'}>{isExploratory ? 'Exploratory' : result.decision_readiness === 'insufficient_evidence' ? 'Insufficient evidence' : 'Recommendation ready'}</StatusBadge>}</div>
              </div>
              <div className="mt-6"><ReadinessGrid criteria={criteria} readiness={readiness} backlog={backlog} /></div>
            </div>

            <div className="grid gap-6 md:grid-cols-2">
              <div className="border border-white/10 bg-slate-900/70 p-5"><p className="text-[10px] font-bold uppercase tracking-[0.2em] text-rose-300">Production gate</p><h2 className="mt-2 text-xl font-semibold text-white">{result?.decision_readiness === 'insufficient_evidence' ? 'No recommendation available' : 'Awaiting analysis'}</h2><p className="mt-3 text-sm leading-6 text-slate-400">{result?.decision_readiness === 'insufficient_evidence' ? 'Required criteria do not yet meet the production evidence standard. Market Demand cannot override the remaining gaps.' : 'Run an analysis to evaluate the current evidence portfolio.'}</p><div className="mt-5 border-t border-white/10 pt-4"><p className="text-[10px] uppercase tracking-[0.16em] text-slate-500">Production recommendation</p><p className="mt-2 text-lg font-semibold text-rose-200">{result?.recommendation ? result.recommendation.alternative?.display_name : 'Not available'}</p></div></div>
              <div className="border border-white/10 bg-slate-900/70 p-5"><p className="text-[10px] font-bold uppercase tracking-[0.2em] text-amber-200">Confidence</p><h2 className="mt-2 text-xl font-semibold text-white">Evidence quality, not success probability</h2><p className="mt-3 text-sm leading-6 text-slate-400">Confidence describes the evidence used in this analysis. Model readiness describes how much required production evidence exists.</p><div className="mt-5 grid grid-cols-2 gap-4 border-t border-white/10 pt-4"><div><p className="text-[10px] uppercase tracking-[0.16em] text-slate-500">Score</p><p className="mt-1 tabular-nums text-xl font-semibold text-amber-100">{result?.confidence?.score != null ? `${(result.confidence.score * 100).toFixed(0)}%` : '—'}</p></div><div><p className="text-[10px] uppercase tracking-[0.16em] text-slate-500">Band</p><p className="mt-1 text-xl font-semibold capitalize text-amber-100">{result?.confidence?.band || '—'}</p></div></div></div>
            </div>
          </div>
        </section>

        {result && !isExploratory && <section className="border border-white/10 bg-slate-900/70 p-5 sm:p-6"><SectionHeading eyebrow="03 / Explain the gate" title="Why can’t StatFlow recommend a location yet?" /><div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">{backlog.map((item) => { const blocker = result.blocker_reasons?.find((entry) => entry.criterion_id === item.criterion_id); return <div key={item.criterion_id} className="border-l-2 border-amber-300/60 bg-amber-300/[0.04] px-4 py-3"><p className="text-sm font-semibold text-white">{criteria.find((criterion) => criterion.criterion_id === item.criterion_id)?.name || item.criterion_id}</p><p className="mt-1 text-xs leading-5 text-slate-400">StatFlow does not yet have evidence meeting the production standard for this criterion.</p>{blocker?.reasons?.length > 0 && <p className="mt-2 text-[11px] text-amber-200">Blocker category: {blocker.reasons.join(', ')}</p>}</div> })}</div></section>}

        {result && !isExploratory && <section className="border border-white/10 bg-slate-900/70 p-5 sm:p-6"><SectionHeading eyebrow="04 / Evidence backlog" title="What would unlock this decision?" /><div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">{backlog.map((item) => <div key={item.criterion_id} className="border border-white/10 bg-slate-950/60 p-4"><p className="text-sm font-semibold text-white">{criteria.find((criterion) => criterion.criterion_id === item.criterion_id)?.name || item.criterion_id}</p><p className="mt-2 text-xs uppercase tracking-[0.12em] text-cyan-300">Needs</p><p className="mt-1 text-sm leading-5 text-slate-300">{item.requirement}</p></div>)}</div></section>}

        {result && !isExploratory && <section className="border border-white/10 bg-slate-900/70 p-5 sm:p-6"><SectionHeading eyebrow="05 / Data partnerships" title="Evidence needed from candidate partners" /><div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">{partnerships.map((item) => <div key={item.criterion_id} className="border border-white/10 bg-slate-950/60 p-4"><div className="flex items-start justify-between gap-3"><p className="text-sm font-semibold text-white">{item.criterion_id.replaceAll('_', ' ')}</p><span className="text-xs tabular-nums text-cyan-200">+{item.current_readiness_impact_percentage}%</span></div><p className="mt-2 text-sm text-slate-300">{item.title}</p><p className="mt-2 text-xs leading-5 text-slate-400">Candidate partner: {item.preferred_source_institution}</p><p className="mt-1 text-xs leading-5 text-slate-500">{item.preferred_geography} · {item.freshness_requirement}</p></div>)}</div></section>}

        {result && isExploratory && <section className="space-y-6"><div className="border border-amber-200/30 bg-amber-300/[0.08] px-5 py-4" role="alert"><div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-[10px] font-bold uppercase tracking-[0.2em] text-amber-200">Exploratory analysis</p><p className="mt-1 text-sm font-semibold text-white">Not a production recommendation.</p></div><span className="border border-amber-200/30 px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.16em] text-amber-100">Production flag: false</span></div></div><div className="border border-white/10 bg-slate-900/70 p-5 sm:p-6"><SectionHeading eyebrow="03 / Compare districts" title="Market Demand ranking"><span className="text-xs text-slate-500">Rendered from Decision Intelligence API</span></SectionHeading><div className="mt-5"><p className="mb-4 text-sm leading-6 text-slate-300"><span className="font-semibold text-white">Market Demand Leader: {scores[0]?.alternative?.display_name || '—'}</span>. This district ranks first because it has the highest available population evidence among eligible districts. This is not a production Business Location recommendation.</p><RankingTable scores={scores} selectedName={selectedDistrict} onSelect={setSelectedDistrict} /></div></div><div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]"><div className="border border-white/10 bg-slate-900/70 p-5 sm:p-6"><SectionHeading eyebrow="04 / Source trail" title={`${selectedDistrict || 'District'} evidence`} /><div className="mt-5"><ProvenancePanel evidence={result.evidence || []} selectedName={selectedDistrict} /></div></div><div className="border border-white/10 bg-slate-900/70 p-5 sm:p-6"><SectionHeading eyebrow="05 / Stability" title="What could change the result?" /><p className="mt-4 text-sm leading-6 text-slate-400">The tested Market Demand weighting leaves the leader unchanged. This has limited meaning because the other required production criteria are unavailable.</p><div className="mt-5 flex items-center justify-between border-t border-white/10 pt-4 text-sm"><span className="text-slate-500">Leader changes</span><span className="tabular-nums font-semibold text-emerald-300">{result.sensitivity?.cases?.filter((item) => item.leader_changed).length || 0}</span></div></div></div></section>}

        {!result && <div className="border border-dashed border-white/15 px-5 py-12 text-center text-sm text-slate-500">Choose a scope and mode, then analyze the evidence.</div>}
      </div>
    </AppShell>
  )
}
