import { readFileSync } from 'node:fs'

export function loadWorkflow(path) {
  const src = readFileSync(path, 'utf8')
  const m = src.match(/^export const meta = (\{[\s\S]*?\n\})\n/)
  if (!m) throw new Error(`${path}: export const meta must be the first statement`)
  const meta = Function(`"use strict"; return (${m[1]})`)()
  const body = src.slice(m[0].length)
  if (/\bDate\.now\(|\bMath\.random\(|new Date\(\s*\)/.test(body)) throw new Error(`${path}: uses Date.now/Math.random/new Date()`)
  if (/\bimport\s*\(|\brequire\s*\(/.test(body)) throw new Error(`${path}: loads modules`)
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
  const fn = new AsyncFunction('args', 'agent', 'parallel', 'pipeline', 'phase', 'log', 'budget', body)
  return { meta, fn }
}
