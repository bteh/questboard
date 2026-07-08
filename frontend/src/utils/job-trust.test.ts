import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  classifyFreshness,
  isFresh,
  postedAgoLabel,
  postingAgeDays,
  staleWarning,
} from './job-trust'

const NOW = new Date('2026-07-07T12:00:00Z')

function daysAgo(days: number): string {
  return new Date(NOW.getTime() - days * 86_400_000).toISOString()
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(NOW)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('postingAgeDays', () => {
  it('returns null when the date is absent', () => {
    expect(postingAgeDays(undefined)).toBeNull()
    expect(postingAgeDays(null)).toBeNull()
    expect(postingAgeDays('')).toBeNull()
  })

  it('returns null when the date does not parse', () => {
    expect(postingAgeDays('not-a-date')).toBeNull()
  })

  it('returns whole days since the post date', () => {
    expect(postingAgeDays(daysAgo(0))).toBe(0)
    expect(postingAgeDays(daysAgo(10))).toBe(10)
  })

  it('clamps future dates to 0 instead of going negative', () => {
    expect(postingAgeDays(daysAgo(-3))).toBe(0)
  })
})

describe('classifyFreshness', () => {
  it('is never fresh without a verifiable date', () => {
    expect(classifyFreshness(undefined)).toBe('unknown')
    expect(classifyFreshness(null)).toBe('unknown')
    expect(classifyFreshness('garbage')).toBe('unknown')
  })

  it("degrades to unknown when date_confidence is 'missing', even with a date", () => {
    expect(classifyFreshness(daysAgo(1), 'missing')).toBe('unknown')
    expect(classifyFreshness(daysAgo(1), 'MISSING')).toBe('unknown')
  })

  it('classifies fresh at 7 days or less', () => {
    expect(classifyFreshness(daysAgo(0))).toBe('fresh')
    expect(classifyFreshness(daysAgo(7))).toBe('fresh')
  })

  it('classifies recent from 8 to 30 days', () => {
    expect(classifyFreshness(daysAgo(8))).toBe('recent')
    expect(classifyFreshness(daysAgo(30))).toBe('recent')
  })

  it('classifies aging from 31 to 60 days', () => {
    expect(classifyFreshness(daysAgo(31))).toBe('aging')
    expect(classifyFreshness(daysAgo(60))).toBe('aging')
  })

  it('classifies stale past 60 days', () => {
    expect(classifyFreshness(daysAgo(61))).toBe('stale')
    expect(classifyFreshness(daysAgo(365))).toBe('stale')
  })

  it('accepts a non-missing confidence value', () => {
    expect(classifyFreshness(daysAgo(2), 'exact')).toBe('fresh')
  })
})

describe('postedAgoLabel', () => {
  it('says nothing when the date is unknown', () => {
    expect(postedAgoLabel(undefined)).toBeNull()
    expect(postedAgoLabel('garbage')).toBeNull()
  })

  it("says nothing when date_confidence is 'missing'", () => {
    expect(postedAgoLabel(daysAgo(3), 'missing')).toBeNull()
  })

  it('labels today and yesterday specially', () => {
    expect(postedAgoLabel(daysAgo(0))).toBe('Posted today')
    expect(postedAgoLabel(daysAgo(1))).toBe('Posted yesterday')
  })

  it('labels day counts up to 45 days', () => {
    expect(postedAgoLabel(daysAgo(5))).toBe('Posted 5 days ago')
    expect(postedAgoLabel(daysAgo(45))).toBe('Posted 45 days ago')
  })

  it('switches to months past 45 days', () => {
    expect(postedAgoLabel(daysAgo(46))).toBe('Posted 2 months ago')
    expect(postedAgoLabel(daysAgo(90))).toBe('Posted 3 months ago')
  })
})

describe('staleWarning', () => {
  it('warns only when age is provable', () => {
    expect(staleWarning(undefined)).toBeNull()
    expect(staleWarning(daysAgo(90), 'missing')).toBeNull()
  })

  it('stays quiet for fresh and recent postings', () => {
    expect(staleWarning(daysAgo(3))).toBeNull()
    expect(staleWarning(daysAgo(20))).toBeNull()
  })

  it('warns with the age for aging and stale postings', () => {
    expect(staleWarning(daysAgo(40))).toBe('Open 40 days')
    expect(staleWarning(daysAgo(75))).toBe('Open 75+ days, may be filled')
  })
})

describe('isFresh', () => {
  it('mirrors classifyFreshness', () => {
    expect(isFresh(daysAgo(3))).toBe(true)
    expect(isFresh(daysAgo(10))).toBe(false)
    expect(isFresh(daysAgo(3), 'missing')).toBe(false)
  })
})
