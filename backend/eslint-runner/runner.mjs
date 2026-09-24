// 从 stdin 读 {files:[{path, content}]},逐个用 ESLint Node API 检查(lintText),
// 输出 {results:[{path, messages:[{line,column,ruleId,severity,message}]}]}。
// severity: 2=error, 1=warning。出错时输出 {error} 并以非零码退出。
import { ESLint } from 'eslint'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const CONFIG_FILE = path.join(__dirname, 'eslint.config.mjs')

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = ''
    process.stdin.setEncoding('utf8')
    process.stdin.on('data', (chunk) => (data += chunk))
    process.stdin.on('end', () => resolve(data))
    process.stdin.on('error', reject)
  })
}

async function main() {
  const raw = await readStdin()
  const job = JSON.parse(raw || '{}')
  const files = Array.isArray(job.files) ? job.files : []

  // cwd 设为 runner 目录,保证能解析到自带配置与插件依赖
  const eslint = new ESLint({
    cwd: __dirname,
    overrideConfigFile: CONFIG_FILE,
    errorOnUnmatchedPattern: false,
  })

  const results = []
  const ruleSample = new Map() // ruleId -> 一个真实的 message 对象(用于取元信息)
  let template = null // 一个真实的 LintResult,作为合成结果的模板
  for (const f of files) {
    if (!f || typeof f.path !== 'string' || typeof f.content !== 'string') continue
    try {
      const linted = await eslint.lintText(f.content, { filePath: f.path, warnIgnored: false })
      if (!template && linted.length) template = linted[0]
      const messages = []
      for (const r of linted) {
        for (const m of r.messages) {
          const ruleId = m.ruleId ?? (m.fatal ? 'parse-error' : '')
          if (ruleId && !ruleSample.has(ruleId)) ruleSample.set(ruleId, m)
          messages.push({
            line: m.line ?? null,
            column: m.column ?? null,
            ruleId,
            severity: m.severity, // 2=error 1=warning
            message: m.message,
          })
        }
      }
      results.push({ path: f.path, messages })
    } catch (e) {
      // 单个文件失败不影响其它文件
      results.push({ path: f.path, messages: [], error: String(e && e.message ? e.message : e) })
    }
  }

  // 逐规则取元信息(描述 + 文档链接)。未知规则(如目标文件里引用了本平台未装的插件规则)会抛错,单独跳过。
  const rulesMeta = {}
  if (template) {
    for (const [ruleId, sample] of ruleSample) {
      try {
        const synthetic = { ...template, messages: [sample], suppressedMessages: [] }
        const m = eslint.getRulesMetaForResults([synthetic])
        const meta = m && m[ruleId]
        if (meta) {
          rulesMeta[ruleId] = {
            description: (meta.docs && meta.docs.description) || '',
            url: (meta.docs && meta.docs.url) || '',
          }
        }
      } catch {
        // 未知规则,无元信息
      }
    }
  }

  process.stdout.write(JSON.stringify({ results, rulesMeta }))
}

main().catch((e) => {
  process.stdout.write(JSON.stringify({ error: String(e && e.message ? e.message : e) }))
  process.exit(1)
})
