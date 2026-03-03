import { describe, it, expect } from 'vitest'
import { formatCost, formatTokens, formatContext, formatLatency } from '../cost'

describe('formatCost', () => {
  it('returns "free" for zero', () => {
    expect(formatCost(0)).toBe('free')
  })

  it('returns "< $0.0001" for very small amounts', () => {
    expect(formatCost(0.00001)).toBe('< $0.0001')
  })

  it('formats small amounts with 4 decimal places', () => {
    expect(formatCost(0.0012)).toBe('$0.0012')
  })

  it('formats normal amounts with 3 decimal places', () => {
    expect(formatCost(0.123)).toBe('$0.123')
    expect(formatCost(1.5)).toBe('$1.500')
  })
})

describe('formatTokens', () => {
  it('returns plain number for small counts', () => {
    expect(formatTokens(500)).toBe('500')
    expect(formatTokens(0)).toBe('0')
  })

  it('formats thousands as K', () => {
    expect(formatTokens(1500)).toBe('1.5K')
    expect(formatTokens(10000)).toBe('10.0K')
  })

  it('formats millions as M', () => {
    expect(formatTokens(1500000)).toBe('1.5M')
    expect(formatTokens(2000000)).toBe('2.0M')
  })
})

describe('formatContext', () => {
  it('returns 0 when total is 0', () => {
    expect(formatContext(100, 0)).toBe(0)
  })

  it('returns rounded percentage', () => {
    expect(formatContext(50, 100)).toBe(50)
    expect(formatContext(1, 3)).toBe(33)
  })
})

describe('formatLatency', () => {
  it('formats sub-second as ms', () => {
    expect(formatLatency(500)).toBe('500ms')
    expect(formatLatency(0)).toBe('0ms')
  })

  it('formats seconds with one decimal', () => {
    expect(formatLatency(1500)).toBe('1.5s')
    expect(formatLatency(10000)).toBe('10.0s')
  })
})
