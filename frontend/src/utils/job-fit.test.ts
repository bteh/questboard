import { describe, expect, it } from 'vitest'

import { computeRequirementFit } from './job-fit'
import type { EvaluationReport, RequirementMatch } from '@/types/application'

function req(strength: RequirementMatch['strength'], requirement = 'req'): RequirementMatch {
  return { requirement, strength, evidence: '', mitigation: '' }
}

function report(requirements: RequirementMatch[]): EvaluationReport {
  return {
    archetype: 'builder',
    tldr: '',
    requirements,
    top_gaps: [],
    recommended_framing: '',
    red_flags: [],
  }
}

describe('computeRequirementFit', () => {
  it('returns null for a missing report', () => {
    expect(computeRequirementFit(null)).toBeNull()
    expect(computeRequirementFit(undefined)).toBeNull()
  })

  it('returns null for a malformed report without requirements', () => {
    expect(computeRequirementFit({} as EvaluationReport)).toBeNull()
  })

  it('returns null for an empty requirements list', () => {
    expect(computeRequirementFit(report([]))).toBeNull()
  })

  it('counts strong/partial/missing into the right buckets', () => {
    const strong = req('strong', 'python')
    const partial = req('partial', 'kubernetes')
    const missing = req('missing', 'rust')
    const fit = computeRequirementFit(report([strong, partial, missing]))

    expect(fit).not.toBeNull()
    expect(fit!.total).toBe(3)
    expect(fit!.strong).toBe(1)
    expect(fit!.partial).toBe(1)
    expect(fit!.missing).toBe(1)
    expect(fit!.covered).toEqual([strong])
    expect(fit!.partials).toEqual([partial])
    expect(fit!.gaps).toEqual([missing])
  })

  it('weights partial coverage at half', () => {
    // 1 strong + 2 partial of 4 => (1 + 2*0.5) / 4 = 0.5
    const fit = computeRequirementFit(
      report([req('strong'), req('partial'), req('partial'), req('missing')]),
    )
    expect(fit!.ratio).toBe(0.5)
  })

  it('labels Strong fit at ratio >= 0.8 (boundary included)', () => {
    // 4 strong of 5 => 0.8 exactly
    const fit = computeRequirementFit(
      report([req('strong'), req('strong'), req('strong'), req('strong'), req('missing')]),
    )
    expect(fit!.ratio).toBe(0.8)
    expect(fit!.label).toBe('Strong fit')

    const perfect = computeRequirementFit(report([req('strong')]))
    expect(perfect!.ratio).toBe(1)
    expect(perfect!.label).toBe('Strong fit')
  })

  it('labels Good fit at 0.6 <= ratio < 0.8', () => {
    // 3 strong of 5 => 0.6 exactly
    const atBoundary = computeRequirementFit(
      report([req('strong'), req('strong'), req('strong'), req('missing'), req('missing')]),
    )
    expect(atBoundary!.ratio).toBe(0.6)
    expect(atBoundary!.label).toBe('Good fit')

    // 3 strong + 1 partial of 5 => 0.7
    const mid = computeRequirementFit(
      report([req('strong'), req('strong'), req('strong'), req('partial'), req('missing')]),
    )
    expect(mid!.ratio).toBe(0.7)
    expect(mid!.label).toBe('Good fit')
  })

  it('labels Partial fit at 0.4 <= ratio < 0.6', () => {
    // 2 strong of 5 => 0.4 exactly
    const fit = computeRequirementFit(
      report([req('strong'), req('strong'), req('missing'), req('missing'), req('missing')]),
    )
    expect(fit!.ratio).toBe(0.4)
    expect(fit!.label).toBe('Partial fit')
  })

  it('labels Stretch below 0.4', () => {
    // 1 strong of 5 => 0.2
    const fit = computeRequirementFit(
      report([req('strong'), req('missing'), req('missing'), req('missing'), req('missing')]),
    )
    expect(fit!.ratio).toBe(0.2)
    expect(fit!.label).toBe('Stretch')

    const allMissing = computeRequirementFit(report([req('missing'), req('missing')]))
    expect(allMissing!.ratio).toBe(0)
    expect(allMissing!.label).toBe('Stretch')
  })

  it('keeps unknown strength values in the total but out of every bucket', () => {
    const weird = { ...req('strong'), strength: 'unclear' } as unknown as RequirementMatch
    const fit = computeRequirementFit(report([req('strong'), weird]))

    expect(fit!.total).toBe(2)
    expect(fit!.strong).toBe(1)
    expect(fit!.partial).toBe(0)
    expect(fit!.missing).toBe(0)
    // Unknown strength dilutes the ratio instead of inflating it.
    expect(fit!.ratio).toBe(0.5)
  })
})
