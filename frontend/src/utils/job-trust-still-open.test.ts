import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { classifyFreshness, postedAgoLabel, staleWarning } from './job-trust'

// Rows older than the saved window stay on the board when the source still
// lists, updated, or verified them (freshness_basis). The card must say so
// instead of implying the row is new or warning that it is filled.

const NOW = new Date('2026-10-01T12:00:00Z')

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

describe('postedAgoLabel with a freshness basis', () => {
  it('says older, still open when the board kept an old row on listed', () => {
    expect(postedAgoLabel(daysAgo(120), 'exact', 'listed')).toBe('older, still open')
  })

  it('says older, still open when the board kept an old row on verified_open', () => {
    expect(postedAgoLabel(daysAgo(120), 'exact', 'verified_open')).toBe('older, still open')
  })

  it('prefers the update age when the source updated the row', () => {
    expect(postedAgoLabel(daysAgo(120), 'exact', 'updated', daysAgo(3))).toBe(
      'updated 3d ago, still open',
    )
  })

  it('falls back to older, still open when the update date does not parse', () => {
    expect(postedAgoLabel(daysAgo(120), 'exact', 'updated', 'garbage')).toBe('older, still open')
    expect(postedAgoLabel(daysAgo(120), 'exact', 'updated', null)).toBe('older, still open')
  })

  it('says older, still open when the post date is unknown but the row was kept', () => {
    expect(postedAgoLabel(null, null, 'listed')).toBe('older, still open')
    expect(postedAgoLabel(daysAgo(3), 'missing', 'listed')).toBe('older, still open')
  })

  it('keeps the old-posting label when the basis is posted', () => {
    expect(postedAgoLabel(daysAgo(120), 'exact', 'posted')).toBe(postedAgoLabel(daysAgo(120)))
    expect(postedAgoLabel(daysAgo(120), 'exact', 'posted')).toBe('Posted 4 months ago')
  })

  it('never says older for a fresh posting, whatever the basis', () => {
    expect(postedAgoLabel(daysAgo(5), 'exact', 'listed')).toBe('Posted 5 days ago')
    expect(postedAgoLabel(daysAgo(45), 'exact', 'listed')).toBe('Posted 45 days ago')
  })

  it('leaves every label unchanged when the basis is absent', () => {
    expect(postedAgoLabel(daysAgo(120), 'exact', null)).toBe('Posted 4 months ago')
    expect(postedAgoLabel(daysAgo(120), 'exact', undefined)).toBe('Posted 4 months ago')
    expect(postedAgoLabel(null, null, null)).toBeNull()
  })
})

describe('staleWarning with a freshness basis', () => {
  it('stays quiet for a row the board kept on listed', () => {
    expect(staleWarning(daysAgo(120), 'exact', 'listed')).toBeNull()
  })

  it('stays quiet for a row the board kept on updated or verified_open', () => {
    expect(staleWarning(daysAgo(120), 'exact', 'updated')).toBeNull()
    expect(staleWarning(daysAgo(40), 'exact', 'verified_open')).toBeNull()
  })

  it('still warns when the basis is posted or absent', () => {
    expect(staleWarning(daysAgo(120), 'exact', 'posted')).toBe('Open 120+ days, may be filled')
    expect(staleWarning(daysAgo(120), 'exact')).toBe('Open 120+ days, may be filled')
  })
})

describe('classifyFreshness with a freshness basis', () => {
  it('reads recent, not stale, for an old row the board kept on verified_open', () => {
    expect(classifyFreshness(daysAgo(120), 'exact', 'verified_open')).toBe('recent')
  })

  it('reads recent, not aging, for a kept row inside the aging band', () => {
    expect(classifyFreshness(daysAgo(40), 'exact', 'listed')).toBe('recent')
  })

  it('keeps fresh as fresh and stale as stale when the basis is posted', () => {
    expect(classifyFreshness(daysAgo(3), 'exact', 'listed')).toBe('fresh')
    expect(classifyFreshness(daysAgo(120), 'exact', 'posted')).toBe('stale')
  })
})
