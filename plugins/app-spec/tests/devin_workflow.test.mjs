import assert from 'node:assert/strict'
import { execFileSync, spawnSync } from 'node:child_process'
import { existsSync, mkdtempSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { run } from './harness.mjs'

const here = dirname(fileURLToPath(import.meta.url))
const plugin = join(here, '..')
const driverPath = join(plugin, 'scripts', 'devin_workflow.mjs')
const workflowPath = name => join(plugin, 'workflows', `${name}.js`)
const readJson = path => JSON.parse(readFileSync(path, 'utf8'))
const writeJson = (path, value) => {
  mkdirSync(dirname(path), { recursive: true })
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`)
}

function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), 'app-spec-devin-workflow-'))
  t.after(() => rmSync(root, { recursive: true, force: true }))
  const out = join(root, 'out')
  const appPath = join(root, 'app')
  const shardsPath = join(out, 'shards')
  mkdirSync(shardsPath, { recursive: true })
  mkdirSync(appPath, { recursive: true })
  writeFileSync(join(appPath, 'App.swift'), 'struct App {}\n')
  const env = {
    ...process.env,
    GIT_AUTHOR_NAME: 'app-spec test',
    GIT_AUTHOR_EMAIL: 'app-spec-test@example.invalid',
    GIT_COMMITTER_NAME: 'app-spec test',
    GIT_COMMITTER_EMAIL: 'app-spec-test@example.invalid',
  }
  execFileSync('git', ['-C', appPath, 'init', '-q'], { env })
  execFileSync('git', ['-C', appPath, 'add', 'App.swift'], { env })
  execFileSync('git', ['-C', appPath, 'commit', '-q', '-m', 'fixture'], { env })
  execFileSync('git', ['-C', appPath, 'remote', 'add', 'origin', 'https://github.com/example/app.git'], { env })

  const shards = [
    { id: 'core-01', kind: 'core', name: 'Payslips', loc: 100 },
    { id: 'touch-01', kind: 'touch', name: 'Shared', loc: 50 },
  ].map(shard => ({ ...shard, file: join(shardsPath, `${shard.id}.json`) }))
  for (const shard of shards) writeJson(shard.file, { files: ['App.swift'], hints: [] })
  writeJson(join(out, 'app-spec.json'), {
    app: { name: 'test-app', path: appPath, stack: 'ios-native' },
    contracts: [],
  })
  const args = {
    out,
    app: { name: 'test-app', path: appPath, stack: 'ios-native' },
    shards,
  }
  const argsFile = join(root, 'args.json')
  writeJson(argsFile, args)
  return { root, out, appPath, args, argsFile }
}

function invoke(f, workflow, ...flags) {
  return spawnSync(process.execPath, [driverPath, workflow, f.out, ...flags], { encoding: 'utf8' })
}

function roundBatches(f, workflow, round) {
  const dir = join(f.out, 'devin', workflow, `round-${round}`)
  return readdirSync(dir, { withFileTypes: true })
    .filter(entry => entry.isDirectory() && /^batch-\d+$/.test(entry.name))
    .sort((left, right) => left.name.localeCompare(right.name))
    .map(entry => join(dir, entry.name))
}

function roundTasks(f, workflow, round) {
  return roundBatches(f, workflow, round).flatMap(batch => readJson(join(batch, 'tasks.json')))
}

function saveRound(f, workflow, round, respond, structured = false) {
  const answers = {}
  for (const task of roundTasks(f, workflow, round)) {
    const label = task.key.slice(0, task.key.lastIndexOf('~'))
    const answer = respond(label, task.prompt)
    if (answer instanceof Error) answers[task.key] = { error: answer.message }
    else {
      assert.notEqual(answer, undefined, `no fixture answer for ${label}`)
      answers[task.key] = answer
    }
  }
  const file = join(f.root, `answers-${round}.json`)
  writeJson(file, structured ? { structured_output: { answers } } : { answers })
  return invoke(f, workflow, '--save-answers', file)
}

const claim = {
  name: 'View payslips',
  description: 'A person reviews their payslips.',
  evidence: 'VERIFIED',
  files: ['Modules/Payslips/PayslipList.swift:10'],
  screens: ['PayslipListView'],
  endpoints: [],
  events: [],
}

function understandAnswer(label) {
  if (label === 'extract:core-01') {
    return {
      fragments: [{ name: 'View payslips', description: 'A person reviews their payslips.', evidence: 'Modules/Payslips/PayslipList.swift:10' }],
      injectionSuspects: [],
      outOfScope: [],
    }
  }
  if (label === 'extract:touch-01') return { fragments: [], injectionSuspects: [], outOfScope: [] }
  if (label === 'map') return { useCases: [claim], screens: [], flows: [], injectionSuspects: [] }
  if (label.startsWith('verify:')) return { real: true, badEvidence: [], reason: 'ok' }
}

test('workflow driver resumes understand-module through extract, map, and verify', async t => {
  const f = fixture(t)
  const expected = await run(workflowPath('understand-module.js'), f.args, understandAnswer)

  let result = invoke(f, 'understand-module', '--args', f.argsFile)
  assert.equal(result.status, 3, result.stderr)
  assert.equal(result.stdout.trim().split('\n').length, 1)
  const first = roundTasks(f, 'understand-module', 1)
  assert.deepEqual(first.map(task => task.key), ['extract:core-01~1', 'extract:touch-01~1'])
  assert.ok(first.every(task => task.schema && task.prompt.includes('Read ONE area')))
  const firstBatch = roundBatches(f, 'understand-module', 1)[0]
  assert.deepEqual(readJson(join(firstBatch, 'schema.json')), {
    type: 'object',
    required: ['answers'],
    properties: { answers: { type: 'object', properties: Object.fromEntries(first.map(task => [task.key, task.schema])) } },
  })
  const child = readJson(join(firstBatch, 'child.json'))
  assert.equal(child.agentType, 'app-spec:ios-analyst')
  assert.equal(child.agentFile, 'ios-analyst')
  assert.equal(child.version, readJson(join(plugin, '.claude-plugin', 'plugin.json')).version)
  assert.equal(child.repo, 'example/app')
  assert.match(child.sha, /^[0-9a-f]{40}$/)
  assert.equal(child.appPath, f.appPath)
  assert.equal(child.out, f.out)
  assert.deepEqual(child.contracts, [])
  const archive = join(f.out, 'devin', 'understand-module', 'round-1', 'shards.zip')
  assert.ok(existsSync(archive))
  assert.match(execFileSync('python3', ['-m', 'zipfile', '-l', archive], { encoding: 'utf8' }), /shards\/core-01\.json/)

  result = saveRound(f, 'understand-module', 1, understandAnswer, true)
  assert.equal(result.status, 0, result.stderr)
  assert.match(result.stdout, /Saved 2 answer\(s\); 0 key\(s\) of the latest round unanswered/)
  result = invoke(f, 'understand-module', '--args', f.argsFile)
  assert.equal(result.status, 3, result.stderr)
  assert.deepEqual(roundTasks(f, 'understand-module', 2).map(task => task.key), ['map~1'])

  result = saveRound(f, 'understand-module', 2, understandAnswer)
  assert.equal(result.status, 0, result.stderr)
  result = invoke(f, 'understand-module', '--args', f.argsFile)
  assert.equal(result.status, 3, result.stderr)
  assert.ok(roundTasks(f, 'understand-module', 3).every(task => task.key.startsWith('verify:')))

  result = saveRound(f, 'understand-module', 3, understandAnswer)
  assert.equal(result.status, 0, result.stderr)
  result = invoke(f, 'understand-module', '--args', f.argsFile)
  assert.equal(result.status, 0, result.stderr)
  assert.deepEqual(readJson(join(f.out, 'devin', 'understand-module', 'result.json')), expected)
})

test('workflow driver turns an error referee answer into an unverified use case', async t => {
  const f = fixture(t)
  const throwingReferee = (label, prompt, opts) => {
    if (label.startsWith('verify:')) throw new Error('dead')
    return understandAnswer(label, prompt, opts)
  }
  const expected = await run(workflowPath('understand-module.js'), f.args, throwingReferee)
  let result = invoke(f, 'understand-module', '--args', f.argsFile)
  assert.equal(result.status, 3, result.stderr)
  result = saveRound(f, 'understand-module', 1, understandAnswer)
  assert.equal(result.status, 0, result.stderr)
  result = invoke(f, 'understand-module', '--args', f.argsFile)
  assert.equal(result.status, 3, result.stderr)
  result = saveRound(f, 'understand-module', 2, understandAnswer)
  assert.equal(result.status, 0, result.stderr)
  result = invoke(f, 'understand-module', '--args', f.argsFile)
  assert.equal(result.status, 3, result.stderr)
  result = saveRound(f, 'understand-module', 3, label => {
    if (label.startsWith('verify:')) return new Error('dead')
    return understandAnswer(label)
  })
  assert.equal(result.status, 0, result.stderr)
  result = invoke(f, 'understand-module', '--args', f.argsFile)
  assert.equal(result.status, 0, result.stderr)
  const actual = readJson(join(f.out, 'devin', 'understand-module', 'result.json'))
  assert.deepEqual(actual, expected)
  assert.equal(actual.result.unverified.length, 1)
  assert.equal(actual.result.useCases[0].evidence, 'INFERRED')
})

test('workflow driver keeps P0 judge lanes in distinct batches', t => {
  const f = fixture(t)
  f.args.useCaseIndex = join(f.out, 'use-cases.json')
  writeJson(f.args.useCaseIndex, { useCases: [] })
  writeJson(f.argsFile, f.args)
  const rule = {
    name: 'Preserve the highest balance',
    category: 'calculation',
    priority: 'P0',
    source: 'Sources/Balance.swift:1-5',
    plainEnglish: 'Keep the highest balance.',
    given: 'Two balances',
    when: 'The balance is chosen',
    then: 'The larger balance is kept',
    parameters: [],
    edgeCases: [],
    suspectedDefect: null,
    confidence: 'High',
    question: null,
    useCase: '',
  }
  const respond = label => {
    if (label === 'extract:core-01') return { rules: [rule], injectionSuspects: [] }
    if (label === 'extract:touch-01') return { rules: [], injectionSuspects: [] }
    if (label.startsWith('verify:')) return { real: true, badEvidence: [], reason: 'ok' }
    if (label.startsWith('p0:')) return { real: true, badEvidence: [], reason: 'ok' }
  }
  let result = invoke(f, 'extract-rules', '--args', f.argsFile, '--children', '2')
  assert.equal(result.status, 3, result.stderr)
  result = saveRound(f, 'extract-rules', 1, respond)
  assert.equal(result.status, 0, result.stderr)
  result = invoke(f, 'extract-rules', '--args', f.argsFile, '--children', '2')
  assert.equal(result.status, 3, result.stderr)
  result = saveRound(f, 'extract-rules', 2, respond)
  assert.equal(result.status, 0, result.stderr)
  result = invoke(f, 'extract-rules', '--args', f.argsFile, '--children', '2')
  assert.equal(result.status, 3, result.stderr)

  const batches = roundBatches(f, 'extract-rules', 3)
  assert.equal(batches.length, 2)
  const assignments = batches.map(batch => ({
    batch,
    keys: readJson(join(batch, 'tasks.json')).map(task => task.key),
  }))
  const judgeOne = assignments.find(batch => batch.keys.some(key => key.endsWith('#1~1')))
  const judgeTwo = assignments.find(batch => batch.keys.some(key => key.endsWith('#2~1')))
  assert.ok(judgeOne)
  assert.ok(judgeTwo)
  assert.notEqual(judgeOne.batch, judgeTwo.batch)
})

test('workflow task keys are stable across replays', t => {
  const f = fixture(t)
  let result = invoke(f, 'understand-module', '--args', f.argsFile)
  assert.equal(result.status, 3, result.stderr)
  const first = roundTasks(f, 'understand-module', 1).map(task => task.key)
  result = invoke(f, 'understand-module', '--args', f.argsFile)
  assert.equal(result.status, 3, result.stderr)
  assert.deepEqual(roundTasks(f, 'understand-module', 2).map(task => task.key), first)
})

test('workflow driver rejects unknown answer keys with exit code 2', t => {
  const f = fixture(t)
  let result = invoke(f, 'understand-module', '--args', f.argsFile)
  assert.equal(result.status, 3, result.stderr)
  const answersFile = join(f.root, 'unknown.json')
  writeJson(answersFile, { answers: { 'not-a-task~1': {} } })
  result = invoke(f, 'understand-module', '--save-answers', answersFile)
  assert.equal(result.status, 2)
  assert.match(result.stderr, /not-a-task~1/)
})
