// Runs a workflow script outside Claude Code with stubbed agent(), parallel(), pipeline(), phase() and log().
// The stub answers every agent() call from a schema-shaped generator, overridable per label, so the script's
// control flow (validation, fan-out, dead agents, verification, return shape) is tested without a model.

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

// A minimal value that satisfies a JSON schema (first enum, one array item, required keys only plus listed ones).
export function sample(schema, hint = '') {
  if (!schema) return null
  if (schema.enum) return schema.enum[0]
  switch (schema.type) {
    case 'object': {
      const out = {}
      for (const [k, v] of Object.entries(schema.properties || {})) out[k] = sample(v, `${hint}.${k}`)
      return out
    }
    case 'array':
      return [sample(schema.items, `${hint}[0]`)]
    case 'string':
      return `${hint || 'text'}`
    case 'integer':
    case 'number':
      return 1
    case 'boolean':
      return true
    default:
      return null
  }
}

export async function run(path, args, respond = () => undefined) {
  const { meta, fn } = loadWorkflow(path)
  const calls = []
  const logs = []
  const phases = []
  const agent = async (prompt, opts = {}) => {
    if (typeof prompt !== 'string' || !prompt.length) throw new Error('agent() needs a prompt string')
    calls.push({ prompt, opts })
    const custom = respond(opts.label || '', prompt, opts)
    if (custom !== undefined) return custom
    return opts.schema ? sample(opts.schema, opts.label) : `result of ${opts.label}`
  }
  const parallel = async thunks => Promise.all(thunks.map(t => Promise.resolve().then(t).catch(() => null)))
  const pipeline = async (items, ...stages) =>
    Promise.all(items.map(async (item, i) => {
      let value = item
      try {
        for (const stage of stages) value = await stage(value, item, i)
        return value
      } catch (e) {
        return null
      }
    }))
  const phase = t => phases.push(t)
  const log = m => logs.push(m)
  const budget = { total: null, spent: () => 0, remaining: () => Infinity }
  const result = await fn(args, agent, parallel, pipeline, phase, log, budget)
  return { meta, result, calls, logs, phases }
}
