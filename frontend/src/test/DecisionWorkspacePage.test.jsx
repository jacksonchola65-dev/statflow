import React from 'react'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import DecisionWorkspacePage from '../pages/DecisionWorkspacePage'
import * as api from '../services/api'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { id: '1', email: 'analyst@example.com', role: 'ANALYST', full_name: 'Analyst' },
    isAuthenticated: true,
    isLoading: false,
    logout: vi.fn(),
  }),
}))

vi.mock('../services/api', () => ({
  fetchDecisionModels: vi.fn(),
  fetchDecisionModel: vi.fn(),
  fetchProvinces: vi.fn(),
  fetchPartnershipRequirements: vi.fn(),
  evaluateBusinessLocation: vi.fn(),
  interpretDecision: vi.fn(),
}))

const CRITERIA = [
  ['market_demand', 'Market Demand', 0.25],
  ['market_growth', 'Market Growth', 0.15],
  ['purchasing_power', 'Purchasing Power', 0.2],
  ['accessibility', 'Accessibility', 0.2],
  ['competition', 'Competition', 0.15],
  ['operating_feasibility', 'Operating Feasibility', 0.05],
].map(([criterion_id, name, weight]) => ({ criterion_id, name, weight }))

const MODEL = {
  model_id: 'BUSINESS_LOCATION_OPPORTUNITY',
  version: 'business-location-v1',
  name: 'Business Location Opportunity Analysis',
  description: 'District-level business location analysis.',
  geographic_level: 'district',
  readiness_percentage: 25,
  production_ready: false,
  criteria: CRITERIA,
  supported_business_categories: ['GENERAL_RETAIL', 'SUPERMARKET'],
  limitations: [],
}

const BACKLOG = [
  ['market_growth', 'Comparable historical district population evidence'],
  ['purchasing_power', 'Reliable district household consumption/income evidence'],
  ['accessibility', 'District-comparable transport/access evidence'],
  ['competition', 'Current category-specific operating establishment evidence'],
  ['operating_feasibility', 'District-compatible infrastructure/service evidence'],
].map(([criterion_id, requirement]) => ({ criterion_id, requirement }))

const DETAILS = {
  ...MODEL,
  evidence_backlog: BACKLOG,
  methodology_versions: { confidence: 'confidence-v1' },
}

const DISTRICTS = ['Mansa', 'Nchelenge', 'Chienge', 'Samfya', 'Kawambwa', 'Mwense', 'Chifunabuli', 'Mwansabombwe', 'Milenge', 'Chembe', 'Chipili', 'Lunga']

function evidence(name, value) {
  return {
    indicator_name: 'Total Population',
    raw_value: value,
    unit: 'People',
    geography_name: name,
    reference_year: 2022,
    dataset_name: '2022 Census of Population and Housing - Luapula District',
    source_institution: 'Zambia Statistics Agency (ZamStats)',
    source_reference: 'https://www.zamstats.gov.zm/source',
    quality: 'unknown',
    freshness_status: 'current',
  }
}

const EXPLORATORY_SCORES = DISTRICTS.map((name, index) => {
  const item = evidence(name, 329622 - index * 12000)
  return {
    alternative: { identifier: name.toLowerCase(), display_name: name },
    final_score: 1 - index / 12,
    criterion_scores: [{ normalized_value: 1 - index / 12, weighted_contribution: 1 - index / 12, effective_weight: 1, evidence: item }],
  }
})

const PRODUCTION_RESULT = {
  run_id: 'production-run',
  model_id: MODEL.model_id,
  model_version: MODEL.version,
  mode: 'PRODUCTION',
  province: 'LP',
  decision_readiness: 'insufficient_evidence',
  model_readiness_percentage: 25,
  production_recommendation: false,
  recommendation: null,
  candidates: [],
  evidence: [evidence('Mansa', 329622)],
  criterion_scores: [],
  evidence_coverage: [],
  confidence: { score: 0.66, band: 'medium' },
  sensitivity: null,
  ties: {},
  blockers: BACKLOG.map((item) => item.criterion_id),
  blocker_reasons: BACKLOG.map((item) => ({ criterion_id: item.criterion_id, reasons: ['no_district_coverage'] })),
  criterion_readiness: [
    { criterion_id: 'market_demand', state: 'production_usable', evidence_coverage_percentage: 100, freshness_status: 'current', blockers: [] },
    ...BACKLOG.map((item) => ({ criterion_id: item.criterion_id, state: 'blocked_by_evidence', evidence_coverage_percentage: 0, freshness_status: 'not_assessed', blockers: ['no_district_coverage'] })),
  ],
  limitations: [],
  explanation: { why_winner_ranked_first: 'No recommendation was produced.' },
  evidence_backlog: BACKLOG,
  methodology_versions: { confidence: 'confidence-v1' },
}

const EXPLORATORY_RESULT = {
  ...PRODUCTION_RESULT,
  run_id: 'exploratory-run',
  mode: 'EXPLORATORY',
  production_recommendation: false,
  criterion_scores: EXPLORATORY_SCORES,
  evidence: EXPLORATORY_SCORES.map((item) => item.criterion_scores[0].evidence),
  limitations: ['This exploratory output is not a production-grade Business Location recommendation.'],
  sensitivity: { cases: [{ leader_changed: false }] },
}

function renderWorkspace() {
  return render(
    <MemoryRouter initialEntries={['/decisions']}>
      <DecisionWorkspacePage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.fetchDecisionModels.mockResolvedValue({ models: [MODEL] })
  api.fetchDecisionModel.mockResolvedValue(DETAILS)
  api.fetchProvinces.mockResolvedValue([{ code: 'LP', name: 'Luapula' }])
  api.fetchPartnershipRequirements.mockResolvedValue({ requirements: BACKLOG.map((item) => ({ criterion_id: item.criterion_id, title: item.requirement, preferred_source_institution: 'Candidate partner', preferred_geography: 'district', freshness_requirement: 'Current' })) })
  api.evaluateBusinessLocation.mockResolvedValue(PRODUCTION_RESULT)
  api.interpretDecision.mockResolvedValue({
    original_text: 'Where should I open a supermarket in Luapula?',
    status: 'PARSED',
    model_id: 'BUSINESS_LOCATION_OPPORTUNITY',
    business_category: 'SUPERMARKET',
    province: 'LP',
    candidate_geography: 'DISTRICT',
    requested_mode: 'PRODUCTION',
    confidence: 0.98,
    missing_fields: [],
    unsupported_parts: [],
  })
})

describe('DecisionWorkspacePage', () => {
  it('shows a loading state while models load', () => {
    api.fetchDecisionModels.mockReturnValue(new Promise(() => {}))
    api.fetchProvinces.mockReturnValue(new Promise(() => {}))
    renderWorkspace()
    expect(screen.getByRole('status')).toHaveTextContent('Loading decision workspace')
  })

  it('renders the production gate, readiness, blockers, and backlog', async () => {
    renderWorkspace()
    const evaluateButton = await screen.findByRole('button', { name: /analyze location opportunity/i })
    expect(screen.getByText('Choose a scope and mode, then analyze the evidence.')).toBeInTheDocument()
    await userEvent.setup().click(evaluateButton)
    await waitFor(() => expect(screen.getByText('No recommendation available')).toBeInTheDocument())
    expect(screen.getByText('25%')).toBeInTheDocument()
    expect(screen.getAllByText('Awaiting production evidence')).toHaveLength(5)
    expect(screen.getByRole('heading', { name: /why can.t statflow recommend/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /what would unlock this decision/i })).toBeInTheDocument()
    expect(screen.getAllByText('Blocker category: no_district_coverage')).toHaveLength(5)
    expect(await screen.findByRole('heading', { name: /evidence needed from candidate partners/i })).toBeInTheDocument()
    expect(screen.queryByText('Mansa', { selector: 'p' })).not.toBeInTheDocument()
  })

  it('requires an explicit exploratory action and renders API ranking/provenance', async () => {
    const user = userEvent.setup()
    api.evaluateBusinessLocation.mockImplementation(async ({ mode }) => mode === 'EXPLORATORY' ? EXPLORATORY_RESULT : PRODUCTION_RESULT)
    renderWorkspace()
    const evaluateButton = await screen.findByRole('button', { name: /analyze location opportunity/i })
    await user.click(evaluateButton)
    await waitFor(() => expect(screen.getByText('No recommendation available')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /exploratory limited analysis/i }))
    await user.click(screen.getByRole('button', { name: /analyze location opportunity/i }))
    await waitFor(() => expect(screen.getByText('Not a production recommendation.')).toBeInTheDocument())
    expect(screen.getByText('Production flag: false')).toBeInTheDocument()
    const table = screen.getByRole('table')
    expect(within(table).getAllByRole('row')[1]).toHaveTextContent('Mansa')
    expect(screen.getAllByText('Zambia Statistics Agency (ZamStats)').length).toBeGreaterThan(0)
    expect(screen.getAllByText('unknown').length).toBeGreaterThan(0)
  })

  it('keeps confidence separate from model readiness', async () => {
    renderWorkspace()
    await userEvent.setup().click(await screen.findByRole('button', { name: /analyze location opportunity/i }))
    await waitFor(() => expect(screen.getByText('No recommendation available')).toBeInTheDocument())
    expect(screen.getByText('Model readiness')).toBeInTheDocument()
    expect(screen.getByText('Confidence')).toBeInTheDocument()
    expect(screen.getByText('medium')).toBeInTheDocument()
  })

  it('surfaces API errors', async () => {
    api.fetchDecisionModels.mockRejectedValue({ response: { data: { detail: 'Network unavailable' } } })
    api.fetchProvinces.mockResolvedValue([])
    renderWorkspace()
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Network unavailable'))
  })

  it('interprets a supported request before handing off to the decision API', async () => {
    const user = userEvent.setup()
    renderWorkspace()
    await screen.findByRole('button', { name: /interpret and analyze/i })
    await user.type(screen.getByLabelText(/describe the decision/i), 'Where should I open a supermarket in Luapula?')
    await user.click(screen.getByRole('button', { name: /interpret and analyze/i }))
    await waitFor(() => expect(screen.getByText('Interpretation: PARSED')).toBeInTheDocument())
    expect(api.interpretDecision).toHaveBeenCalledWith('Where should I open a supermarket in Luapula?')
    expect(api.evaluateBusinessLocation).toHaveBeenCalledWith(expect.objectContaining({ business_category: 'SUPERMARKET', province: 'LP', mode: 'PRODUCTION' }))
  })

  it('does not execute incomplete natural-language requests', async () => {
    const user = userEvent.setup()
    api.interpretDecision.mockResolvedValue({ original_text: 'Where should I open my business?', status: 'CLARIFICATION_REQUIRED', missing_fields: ['business_category', 'province'], clarification_questions: [] })
    renderWorkspace()
    await user.type(await screen.findByLabelText(/describe the decision/i), 'Where should I open my business?')
    await user.click(screen.getByRole('button', { name: /interpret and analyze/i }))
    await waitFor(() => expect(screen.getByText('Missing: business_category, province')).toBeInTheDocument())
    expect(api.evaluateBusinessLocation).not.toHaveBeenCalled()
  })

  it('surfaces unsupported requests without invoking the decision engine', async () => {
    const user = userEvent.setup()
    api.interpretDecision.mockResolvedValue({ original_text: 'Which football team will win tomorrow?', status: 'UNSUPPORTED_DECISION', missing_fields: [], unsupported_parts: ['Only Business Location Opportunity decisions are supported.'] })
    renderWorkspace()
    await user.type(await screen.findByLabelText(/describe the decision/i), 'Which football team will win tomorrow?')
    await user.click(screen.getByRole('button', { name: /interpret and analyze/i }))
    await waitFor(() => expect(screen.getByText('Interpretation: UNSUPPORTED_DECISION')).toBeInTheDocument())
    expect(screen.getByText(/Only Business Location Opportunity decisions are supported/)).toBeInTheDocument()
    expect(api.evaluateBusinessLocation).not.toHaveBeenCalled()
  })
})
