import { spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { loadWorkflow } from './workflow_loader.mjs'

const PLUGIN = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const WORKFLOWS = new Set(['understand-module', 'extract-rules'])
const USAGE = 'usage: node devin_workflow.mjs <understand-module|extract-rules> OUT --args <args.json> [--children N] | node devin_workflow.mjs <workflow> OUT --save-answers <file>'

function jsonFile(path) {
  return JSON.parse(readFileSync(path, 'utf8'))
}

function writeAtomic(path, text) {
  mkdirSync(dirname(path), { recursive: true })
  const temp = `${path}.${process.pid}.tmp`
  try {
    writeFileSync(temp, text, { encoding: 'utf8', flag: 'w' })
    renameSync(temp, path)
  } catch (error) {
    try {
      rmSync(temp, { force: true })
    } catch {}
    throw error
  }
}

function writeJson(path, value) {
  writeAtomic(path, `${JSON.stringify(value, null, 2)}\n`)
}

function parseCli(argv) {
  if (argv.length < 2) throw new Error(USAGE)
  const [name, outArg, ...flags] = argv
  if (!WORKFLOWS.has(name)) throw new Error(`unknown workflow ${name}; expected ${[...WORKFLOWS].join(' or ')}`)
  const options = { name, out: resolve(outArg), children: 6, argsFile: null, answersFile: null }
  for (let i = 0; i < flags.length; i++) {
    const flag = flags[i]
    if (flag === '--args' || flag === '--save-answers' || flag === '--children') {
      const value = flags[++i]
      if (!value || value.startsWith('--')) throw new Error(`${flag} requires a value`)
      if (flag === '--args') options.argsFile = resolve(value)
      else if (flag === '--save-answers') options.answersFile = resolve(value)
      else {
        options.children = Number(value)
        if (!Number.isInteger(options.children) || options.children < 1 || options.children > 12) {
          throw new Error('--children must be an integer from 1 to 12')
        }
      }
    } else {
      throw new Error(`unknown option ${flag}`)
    }
  }
  if (Boolean(options.argsFile) === Boolean(options.answersFile)) {
    throw new Error(`choose exactly one of --args or --save-answers; ${USAGE}`)
  }
  if (options.answersFile && flags.includes('--children')) throw new Error('--children is only valid with --args')
  return options
}

function runGit(path, args) {
  const result = spawnSync('git', ['-C', path, ...args], { encoding: 'utf8' })
  return result.status === 0 ? result.stdout.trim() : null
}

function repoName(remote) {
  if (!remote) return null
  let path = remote
  if (/^[A-Za-z][A-Za-z0-9+.-]*:\/\//.test(remote)) {
    try {
      path = new URL(remote).pathname
    } catch {
      return null
    }
  } else if (/^[^/:@]+@[^:]+:/.test(remote)) {
    path = remote.slice(remote.indexOf(':') + 1)
  } else if (remote.startsWith('/') || remote.startsWith('.')) {
    return null
  }
  const parts = path.replace(/\.git\/?$/, '').split('/').filter(Boolean)
  return parts.length >= 2 ? parts.slice(-2).join('/') : null
}

function sourceIdentity(path) {
  const sha = runGit(path, ['rev-parse', 'HEAD'])
  if (!sha) return { repo: null, sha: null }
  return { repo: repoName(runGit(path, ['remote', 'get-url', 'origin'])), sha }
}

function latestRound(workflowDir) {
  if (!existsSync(workflowDir)) return 0
  return readdirSync(workflowDir, { withFileTypes: true })
    .filter(entry => entry.isDirectory())
    .map(entry => /^round-(\d+)$/.exec(entry.name))
    .filter(Boolean)
    .reduce((latest, match) => Math.max(latest, Number(match[1])), 0)
}

function zipShards(out, zipPath) {
  const python = [
    'import os, sys, zipfile',
    'root, target = sys.argv[1:3]',
    'with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:',
    '  if os.path.isdir(root):',
    '    for base, dirs, files in os.walk(root):',
    '      dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(base, d))]',
    '      for name in sorted(files):',
    '        path = os.path.join(base, name)',
    '        if not os.path.islink(path) and os.path.isfile(path):',
    '          rel = os.path.relpath(path, root).replace(os.sep, "/")',
    '          archive.write(path, "shards/" + rel)',
  ].join('\n')
  const result = spawnSync('python3', ['-c', python, join(out, 'shards'), zipPath], { encoding: 'utf8' })
  if (result.status !== 0) throw new Error(result.stderr || 'could not zip OUT/shards')
}

function batchGroups(tasks, children) {
  const groups = new Map()
  for (const task of tasks) {
    const lane = /#(\d+)$/.exec(task.label)?.[1] || ''
    const groupKey = `${task.agentType}\u0000${lane}`
    if (!groups.has(groupKey)) groups.set(groupKey, [])
    groups.get(groupKey).push(task)
  }
  const grouped = [...groups.values()]
  const counts = grouped.map(() => 1)
  let remaining = Math.max(0, children - grouped.length)
  while (remaining) {
    let allocated = false
    for (let i = 0; i < grouped.length && remaining; i++) {
      if (counts[i] >= grouped[i].length) continue
      counts[i]++
      remaining--
      allocated = true
    }
    if (!allocated) break
  }
  const batches = []
  grouped.forEach((items, groupIndex) => {
    const count = counts[groupIndex]
    const lanes = Array.from({ length: count }, () => [])
    items.forEach((task, index) => lanes[index % count].push(task))
    for (const batch of lanes) {
      if (batch.length) batches.push(batch)
    }
  })
  return batches
}

function childMetadata(out, config, agentType) {
  const appPath = config?.app?.path
  if (typeof appPath !== 'string' || !appPath) throw new Error('app-spec.json must contain app.path')
  const identity = sourceIdentity(appPath)
  const manifest = jsonFile(join(PLUGIN, '.claude-plugin', 'plugin.json'))
  const contracts = (Array.isArray(config.contracts) ? config.contracts : [])
    .filter(contract => contract && typeof contract.path === 'string' && contract.path)
    .map(contract => ({ ...sourceIdentity(contract.path), path: contract.path }))
  return {
    agentType,
    agentFile: agentType.startsWith('app-spec:') ? agentType.slice('app-spec:'.length) : agentType,
    version: manifest.version,
    repo: identity.repo,
    sha: identity.sha,
    appPath,
    out,
    contracts,
  }
}

function writeRound(options, config, pending) {
  const workflowDir = join(options.out, 'devin', options.name)
  const round = latestRound(workflowDir) + 1
  const roundDir = join(workflowDir, `round-${round}`)
  mkdirSync(roundDir, { recursive: true })
  const batches = batchGroups(pending, options.children)
  if (!batches.length) throw new Error('no pending tasks to write')
  zipShards(options.out, join(roundDir, 'shards.zip'))
  batches.forEach((tasks, index) => {
    const batchDir = join(roundDir, `batch-${index + 1}`)
    mkdirSync(batchDir, { recursive: true })
    const agentType = tasks[0].agentType
    writeJson(join(batchDir, 'tasks.json'), tasks.map(({ key, prompt, schema }) => ({ key, prompt, schema: schema ?? {} })))
    const properties = Object.fromEntries(tasks.map(task => [task.key, task.schema || {}]))
    writeJson(join(batchDir, 'schema.json'), {
      type: 'object',
      required: ['answers'],
      properties: { answers: { type: 'object', properties } },
    })
    writeJson(join(batchDir, 'child.json'), childMetadata(options.out, config, agentType))
    console.log(`${batchDir} ${agentType} ${tasks.length} task(s)`)
  })
  return round
}

function answerPath(out, workflow, key) {
  return join(out, 'devin', workflow, 'answers', `${key}.json`)
}

function tasksFromRound(roundDir) {
  const tasks = []
  for (const entry of readdirSync(roundDir, { withFileTypes: true })) {
    if (!entry.isDirectory() || !/^batch-\d+$/.test(entry.name)) continue
    const batch = jsonFile(join(roundDir, entry.name, 'tasks.json'))
    if (!Array.isArray(batch)) throw new Error(`${entry.name}/tasks.json must be an array`)
    tasks.push(...batch)
  }
  return tasks
}

function saveAnswers(options) {
  const workflowDir = join(options.out, 'devin', options.name)
  const latest = latestRound(workflowDir)
  if (!latest) throw new Error(`no pending rounds for ${options.name} in ${options.out}`)
  const roundDir = join(workflowDir, `round-${latest}`)
  const tasks = tasksFromRound(roundDir)
  const payload = jsonFile(options.answersFile)
  const answers = payload?.structured_output?.answers ?? payload?.answers
  if (!answers || typeof answers !== 'object' || Array.isArray(answers)) {
    throw new Error('answer file must contain an answers object or structured_output.answers')
  }
  const known = new Set(tasks.map(task => task.key))
  const keys = Object.keys(answers)
  const unknown = keys.filter(key => !known.has(key))
  if (unknown.length) throw new Error(`unknown answer key(s): ${unknown.join(', ')}`)
  for (const key of keys) writeJson(answerPath(options.out, options.name, key), answers[key])
  const unanswered = [...known].filter(key => !existsSync(answerPath(options.out, options.name, key))).length
  console.log(`Saved ${keys.length} answer(s); ${unanswered} key(s) of the latest round unanswered`)
  return 0
}

function rebaseOutPaths(args, out) {
  if (!args || typeof args !== 'object' || Array.isArray(args)) throw new Error('--args must contain a JSON object')
  const originalOut = typeof args.out === 'string' ? args.out.replace(/\/+$/, '') : ''
  args.out = out
  if (Array.isArray(args.shards)) {
    for (const shard of args.shards) {
      if (typeof shard?.file !== 'string') continue
      const file = shard.file.replace(/\\/g, '/')
      const prefixes = [originalOut && `${originalOut}/shards/`, 'shards/'].filter(Boolean)
      const prefix = prefixes.find(candidate => file.startsWith(candidate))
      if (prefix) shard.file = `${out}/shards/${file.slice(prefix.length)}`
    }
  }
  if (typeof args.useCaseIndex === 'string' && originalOut && args.useCaseIndex.startsWith(`${originalOut}/`)) {
    args.useCaseIndex = `${out}/${args.useCaseIndex.slice(originalOut.length + 1)}`
  }
  return args
}

function parallel(thunks) {
  return Promise.all(thunks.map(thunk => Promise.resolve().then(thunk).catch(() => null)))
}

function pipeline(items, ...stages) {
  return Promise.all(items.map(async (item, index) => {
    let value = item
    try {
      for (const stage of stages) value = await stage(value, item, index)
      return value
    } catch {
      return null
    }
  }))
}

async function runWorkflow(options) {
  const config = jsonFile(join(options.out, 'app-spec.json'))
  const args = rebaseOutPaths(jsonFile(options.argsFile), options.out)
  if (!args || typeof args !== 'object' || Array.isArray(args)) throw new Error('--args must contain a JSON object')
  const { meta, fn } = loadWorkflow(join(PLUGIN, 'workflows', `${options.name}.js`))
  const calls = []
  const logs = []
  const phases = []
  const pending = []
  const occurrences = new Map()
  let finished = false

  const agent = async (prompt, opts = {}) => {
    if (typeof prompt !== 'string' || !prompt.length) throw new Error('agent() needs a prompt string')
    calls.push({ prompt, opts })
    const label = String(opts.label || '')
    const sanitized = label.replace(/[^A-Za-z0-9:_#.-]/g, '-') || 'task'
    const occurrence = (occurrences.get(sanitized) || 0) + 1
    occurrences.set(sanitized, occurrence)
    const key = `${sanitized}~${occurrence}`
    const path = answerPath(options.out, options.name, key)
    if (existsSync(path)) {
      const answer = jsonFile(path)
      if (answer && typeof answer === 'object' && !Array.isArray(answer) && Object.hasOwn(answer, 'error')) {
        throw new Error(String(answer.error))
      }
      return answer
    }
    pending.push({
      key,
      label,
      agentType: String(opts.agentType || 'unknown'),
      phase: opts.phase,
      prompt,
      schema: opts.schema,
    })
    return new Promise(() => {})
  }

  const budget = { total: null, spent: () => 0, remaining: () => Infinity }
  process.on('beforeExit', () => {
    if (finished || !pending.length) return
    finished = true
    try {
      writeRound(options, config, pending)
      process.exitCode = 3
    } catch (error) {
      console.error(error.message || String(error))
      process.exitCode = 2
    }
  })

  const result = await fn(args, agent, parallel, pipeline, title => phases.push(title), message => logs.push(message), budget)
  if (pending.length) {
    finished = true
    writeRound(options, config, pending)
    process.exitCode = 3
    return
  }
  finished = true
  writeJson(join(options.out, 'devin', options.name, 'result.json'), { meta, result, calls, logs, phases })
  console.log(`Wrote ${join(options.out, 'devin', options.name, 'result.json')}`)
  process.exitCode = 0
}

async function main(argv) {
  const options = parseCli(argv)
  if (options.answersFile) return saveAnswers(options)
  try {
    await runWorkflow(options)
    return process.exitCode || 0
  } catch (error) {
    console.error(error.message || String(error))
    return 2
  }
}

main(process.argv.slice(2)).then(code => {
  if (code !== undefined) process.exitCode = code
}).catch(error => {
  console.error(error.message || String(error))
  process.exitCode = 2
})
