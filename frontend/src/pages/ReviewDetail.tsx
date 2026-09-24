import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Card, Descriptions, Tag, Typography, Spin, Alert, Empty, Steps, Segmented, Button, message } from 'antd'
import { api, ReviewDetail as ReviewDetailType, Finding, LintIssue } from '../api/client'
import CommitDiffView from '../components/CommitDiffView'

const MONO = '"SF Mono","Cascadia Code","JetBrains Mono",Consolas,"Liberation Mono",ui-monospace,monospace'

// 分类 → 颜色(参考 open-code-review viewer)
const CATEGORY_COLORS: Record<string, { bg: string; fg: string }> = {
  bug: { bg: '#fef2f2', fg: '#dc2626' },
  security: { bg: '#fdf2f8', fg: '#be185d' },
  performance: { bg: '#fff7ed', fg: '#ea580c' },
  maintainability: { bg: '#eff6ff', fg: '#2563eb' },
  test: { bg: '#f0fdf4', fg: '#15803d' },
  style: { bg: '#f5f3ff', fg: '#7c3aed' },
  documentation: { bg: '#ecfeff', fg: '#0e7490' },
}
const NEUTRAL = { bg: '#f0f0f0', fg: 'rgba(0,0,0,0.62)' }
// 严重度 → 颜色(error≈high 橙,warning≈medium 琥珀,info≈low 中性)
const SEVERITY_COLORS: Record<string, { bg: string; fg: string }> = {
  error: { bg: '#fff7ed', fg: '#c2410c' },
  warning: { bg: '#fefce8', fg: '#a16207' },
  info: NEUTRAL,
}

function Badge({ text, colors }: { text: string; colors: { bg: string; fg: string } }) {
  return (
    <span
      style={{
        padding: '0.15em 0.55em',
        borderRadius: 20,
        fontSize: '0.68rem',
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.03em',
        background: colors.bg,
        color: colors.fg,
      }}
    >
      {text}
    </span>
  )
}

function CodePanel({ label, code, variant }: { label: string; code: string; variant: 'existing' | 'suggestion' }) {
  const isExisting = variant === 'existing'
  return (
    <div style={{ borderRadius: 6, overflow: 'hidden', border: '1px solid rgba(0,0,0,0.06)' }}>
      <div
        style={{
          fontSize: '0.68rem',
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.04em',
          padding: '0.4rem 0.75rem',
          borderBottom: '1px solid rgba(0,0,0,0.06)',
          background: isExisting ? '#fef2f2' : '#ecfdf5',
          color: isExisting ? '#dc2626' : '#065f46',
        }}
      >
        {label}
      </div>
      <pre
        style={{
          margin: 0,
          padding: '0.65rem 0.75rem',
          fontSize: '0.76rem',
          lineHeight: 1.55,
          overflowX: 'auto',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          background: isExisting ? '#fef8f8' : '#f8fdfb',
          fontFamily: MONO,
        }}
      >
        <code>{code}</code>
      </pre>
    </div>
  )
}

function FindingCard({ f }: { f: Finding }) {
  const cat = (f.category || '').toLowerCase()
  const hasCode = !!(f.existing_code || f.suggestion)
  return (
    <div style={{ background: '#fff', border: '1px solid rgba(0,0,0,0.08)', borderRadius: 6, padding: '1rem', marginBottom: '0.75rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.6rem', flexWrap: 'wrap' }}>
        {f.category && <Badge text={f.category} colors={CATEGORY_COLORS[cat] || NEUTRAL} />}
        <Badge text={f.severity} colors={SEVERITY_COLORS[f.severity] || NEUTRAL} />
        <span
          style={{
            fontFamily: MONO,
            fontSize: '0.72rem',
            color: 'rgba(0,0,0,0.55)',
            background: '#f0f0f0',
            padding: '0.15em 0.5em',
            borderRadius: 4,
          }}
        >
          {f.file_path}
          {f.line ? `:${f.line}` : ''}
        </span>
      </div>
      <div style={{ fontSize: '0.85rem', lineHeight: 1.7, color: 'rgba(0,0,0,0.87)', whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
        {f.message}
      </div>
      {hasCode && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 26rem), 1fr))',
            gap: '0.75rem',
            marginTop: '0.85rem',
          }}
        >
          {f.existing_code && <CodePanel label="Existing Code" code={f.existing_code} variant="existing" />}
          {f.suggestion && <CodePanel label="Suggested Change" code={f.suggestion} variant="suggestion" />}
        </div>
      )}
    </div>
  )
}

const STATUS_COLORS: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  succeeded: 'success',
  failed: 'error',
}

const STAGE_STEPS = [
  { key: 'queued', title: '排队' },
  { key: 'preparing', title: '准备' },
  { key: 'reviewing', title: '评审分析' },
  { key: 'parsing', title: '整理结果' },
]

function stageIndex(status: string, stage: string): number {
  if (status === 'pending') return 0
  switch (stage) {
    case 'preparing':
      return 1
    case 'parsing':
      return 3
    case 'reviewing':
    default:
      return 2
  }
}

function RunningPanel({ review }: { review: ReviewDetailType }) {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    const start = new Date(review.created_at).getTime()
    const tick = () => setElapsed(Math.max(0, Math.floor((Date.now() - start) / 1000)))
    tick()
    const h = window.setInterval(tick, 1000)
    return () => window.clearInterval(h)
  }, [review.created_at])
  const cur = stageIndex(review.status, review.stage)
  const mm = String(Math.floor(elapsed / 60)).padStart(2, '0')
  const ss = String(elapsed % 60).padStart(2, '0')
  return (
    <Card>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '1rem' }}>
        <Spin size="small" />
        <span style={{ fontWeight: 600 }}>评审进行中</span>
        <span style={{ fontFamily: MONO, fontSize: '0.8rem', color: 'rgba(0,0,0,0.55)' }}>已用时 {mm}:{ss}</span>
      </div>
      <Steps size="small" current={cur} status="process" items={STAGE_STEPS.map((s) => ({ title: s.title }))} />
      {review.stage_detail && (
        <div
          style={{
            marginTop: '0.9rem',
            fontFamily: MONO,
            fontSize: '0.76rem',
            color: 'rgba(0,0,0,0.65)',
            background: '#fafafa',
            border: '1px solid rgba(0,0,0,0.06)',
            borderRadius: 6,
            padding: '0.55rem 0.75rem',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {review.stage_detail}
        </div>
      )}
    </Card>
  )
}

const LINT_SEVERITY: Record<string, { bg: string; fg: string; label: string }> = {
  error: { bg: '#fff7ed', fg: '#c2410c', label: 'ERROR' },
  warning: { bg: '#fefce8', fg: '#a16207', label: 'WARNING' },
}

function LintPanel({ reviewId, issues, running }: { reviewId: string; issues: LintIssue[]; running: boolean }) {
  const [onlyChanged, setOnlyChanged] = useState(false)
  const [linting, setLinting] = useState(false)

  const errorCount = issues.filter((i) => i.severity === 'error').length
  const warnCount = issues.filter((i) => i.severity === 'warning').length
  const shown = onlyChanged ? issues.filter((i) => i.on_changed_line) : issues

  // 按文件分组
  const byFile = new Map<string, LintIssue[]>()
  for (const i of shown) {
    const arr = byFile.get(i.file_path) || []
    arr.push(i)
    byFile.set(i.file_path, arr)
  }

  const runLint = async () => {
    setLinting(true)
    try {
      await api.post(`/api/reviews/${reviewId}/lint`)
      message.success('已开始静态检查,稍后刷新查看结果')
    } catch {
      message.error('静态检查启动失败')
    } finally {
      setLinting(false)
    }
  }

  const title = (
    <span>
      静态检查 (ESLint)
      {issues.length > 0 && (
        <span style={{ marginLeft: '0.6rem', fontSize: '0.8rem', fontWeight: 400 }}>
          {errorCount > 0 && <span style={{ color: '#c2410c' }}>{errorCount} error</span>}
          {errorCount > 0 && warnCount > 0 && ' · '}
          {warnCount > 0 && <span style={{ color: '#a16207' }}>{warnCount} warning</span>}
        </span>
      )}
    </span>
  )

  const extra = (
    <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
      {issues.length > 0 && (
        <Segmented
          size="small"
          value={onlyChanged ? 'changed' : 'all'}
          onChange={(v) => setOnlyChanged(v === 'changed')}
          options={[
            { label: '全部', value: 'all' },
            { label: '仅本次改动行', value: 'changed' },
          ]}
        />
      )}
      <Button size="small" onClick={runLint} loading={linting}>
        重新检查
      </Button>
    </span>
  )

  return (
    <Card title={title} size="small" extra={running ? undefined : extra}>
      {issues.length === 0 ? (
        <Empty description="没有发现 ESLint 问题(或该提交无可检查的 JS/TS 文件)">
          <Button type="primary" onClick={runLint} loading={linting}>
            运行静态检查
          </Button>
        </Empty>
      ) : shown.length === 0 ? (
        <Empty description="本次改动行上没有 ESLint 问题" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {[...byFile.entries()].map(([file, list]) => (
            <div key={file}>
              <div style={{ fontFamily: MONO, fontSize: '0.78rem', fontWeight: 600, marginBottom: '0.4rem', wordBreak: 'break-all' }}>
                {file} <span style={{ color: 'rgba(0,0,0,0.45)', fontWeight: 400 }}>({list.length})</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                {list.map((i) => (
                  <LintRow key={i.id} issue={i} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}

function LintRow({ issue }: { issue: LintIssue }) {
  const sev = LINT_SEVERITY[issue.severity] || LINT_SEVERITY.warning
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState<'where' | 'why'>('where')
  const hasDetail = !!(issue.code_context || issue.rule_desc || issue.rule_url)

  return (
    <div
      style={{
        background: '#fafafa',
        border: '1px solid rgba(0,0,0,0.06)',
        borderRadius: 6,
        overflow: 'hidden',
      }}
    >
      <div
        onClick={() => hasDetail && setOpen((v) => !v)}
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: '0.5rem',
          flexWrap: 'wrap',
          padding: '0.4rem 0.6rem',
          cursor: hasDetail ? 'pointer' : 'default',
        }}
      >
        {hasDetail && (
          <span style={{ fontSize: '0.7rem', color: 'rgba(0,0,0,0.4)', transition: 'transform 0.15s', transform: open ? 'rotate(90deg)' : 'none' }}>
            ▶
          </span>
        )}
        <Badge text={sev.label} colors={sev} />
        <span style={{ fontFamily: MONO, fontSize: '0.72rem', color: 'rgba(0,0,0,0.5)' }}>
          {issue.line ?? '?'}:{issue.column ?? '?'}
        </span>
        <span style={{ fontSize: '0.85rem', color: 'rgba(0,0,0,0.85)', flex: 1, minWidth: '12rem' }}>{issue.message}</span>
        {issue.rule_id && (
          <span style={{ fontFamily: MONO, fontSize: '0.7rem', color: '#7c3aed', background: '#f5f3ff', padding: '0.1em 0.45em', borderRadius: 4 }}>
            {issue.rule_id}
          </span>
        )}
        {issue.on_changed_line && <Badge text="本次改动" colors={{ bg: '#eff6ff', fg: '#2563eb' }} />}
      </div>

      {open && hasDetail && (
        <div style={{ borderTop: '1px solid rgba(0,0,0,0.06)', background: '#fff' }}>
          <Segmented
            size="small"
            value={tab}
            onChange={(v) => setTab(v as 'where' | 'why')}
            style={{ margin: '0.6rem 0.6rem 0' }}
            options={[
              { label: '问题位置', value: 'where' },
              { label: '为什么是问题', value: 'why', disabled: !(issue.rule_desc || issue.rule_url) },
            ]}
          />
          <div style={{ padding: '0.6rem' }}>
            {tab === 'where' ? (
              issue.code_context ? (
                <CodeContext code={issue.code_context} start={issue.context_start} hlLine={issue.line} />
              ) : (
                <span style={{ fontSize: '0.8rem', color: 'rgba(0,0,0,0.45)' }}>无代码片段</span>
              )
            ) : (
              <div style={{ fontSize: '0.85rem', lineHeight: 1.7 }}>
                {issue.rule_desc && <p style={{ margin: '0 0 0.6rem' }}>{issue.rule_desc}</p>}
                {issue.rule_url && (
                  <a href={issue.rule_url} target="_blank" rel="noreferrer" style={{ fontSize: '0.8rem' }}>
                    查看规则文档 ({issue.rule_id}) ↗
                  </a>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function CodeContext({ code, start, hlLine }: { code: string; start: number | null; hlLine: number | null }) {
  const lines = code.split('\n')
  const base = start ?? 1
  return (
    <div style={{ borderRadius: 6, overflow: 'hidden', border: '1px solid rgba(0,0,0,0.08)' }}>
      <pre style={{ margin: 0, fontSize: '0.76rem', lineHeight: 1.6, overflowX: 'auto', fontFamily: MONO, background: '#f8f8f8' }}>
        {lines.map((ln, idx) => {
          const num = base + idx
          const isHl = hlLine != null && num === hlLine
          return (
            <div
              key={num}
              style={{
                display: 'flex',
                background: isHl ? '#fff1e6' : 'transparent',
                borderLeft: isHl ? '3px solid #ea580c' : '3px solid transparent',
              }}
            >
              <span style={{ display: 'inline-block', width: '3rem', textAlign: 'right', paddingRight: '0.75rem', color: 'rgba(0,0,0,0.35)', userSelect: 'none', flexShrink: 0 }}>
                {num}
              </span>
              <code style={{ whiteSpace: 'pre', paddingRight: '0.75rem' }}>{ln || ' '}</code>
            </div>
          )
        })}
      </pre>
    </div>
  )
}

export default function ReviewDetail() {
  const { id } = useParams<{ id: string }>()
  const [review, setReview] = useState<ReviewDetailType | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const pollRef = useRef<number | null>(null)

  useEffect(() => {
    let alive = true
    const clearPoll = () => {
      if (pollRef.current !== null) {
        window.clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
    const fetchOnce = () =>
      api
        .get<ReviewDetailType>(`/api/reviews/${id}`)
        .then((resp) => {
          if (!alive) return
          setReview(resp.data)
          // 结束态停止轮询
          if (resp.data.status === 'succeeded' || resp.data.status === 'failed') {
            clearPoll()
          }
        })
        .catch((e) => {
          if (alive) setError(e.response?.data?.detail || '加载失败')
        })
        .finally(() => {
          if (alive) setLoading(false)
        })

    setLoading(true)
    fetchOnce().then(() => {
      // 运行/排队中开启轮询,实时刷新评审步骤与结果
      if (alive && pollRef.current === null) {
        pollRef.current = window.setInterval(fetchOnce, 2500)
      }
    })
    return () => {
      alive = false
      clearPoll()
    }
  }, [id])

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '4rem' }}>
        <Spin />
      </div>
    )
  }
  if (error || !review) {
    return <Alert type="error" message={error || '评审不存在'} showIcon />
  }

  const findings = review.findings || []
  const running = review.status === 'pending' || review.status === 'running'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
      <Card>
        <Descriptions title="评审信息" column={{ xs: 1, sm: 2 }} size="small" bordered>
          <Descriptions.Item label="仓库">{review.repository_name || review.repository_id}</Descriptions.Item>
          <Descriptions.Item label="状态">
            <Tag color={STATUS_COLORS[review.status] || 'default'}>{review.status}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="提交">
            <span style={{ fontFamily: MONO, fontSize: '0.8rem' }}>{review.commit_sha.slice(0, 10)}</span>
          </Descriptions.Item>
          <Descriptions.Item label="提交人">{review.commit_author || '—'}</Descriptions.Item>
          <Descriptions.Item label="提交信息" span={2}>
            {review.commit_message || '—'}
          </Descriptions.Item>
          <Descriptions.Item label="评分">{review.score ?? '—'}</Descriptions.Item>
          <Descriptions.Item label="模型">{review.model || '—'}</Descriptions.Item>
          <Descriptions.Item label="触发方式">{review.trigger}</Descriptions.Item>
          <Descriptions.Item label="完成时间">
            {review.finished_at ? new Date(review.finished_at).toLocaleString() : '—'}
          </Descriptions.Item>
          {review.tool_summary && (
            <Descriptions.Item label="评审过程" span={2}>
              {review.tool_summary}
            </Descriptions.Item>
          )}
        </Descriptions>
        {review.summary && (
          <Typography.Paragraph style={{ marginTop: '1rem', marginBottom: 0, whiteSpace: 'pre-wrap' }}>
            {review.summary}
          </Typography.Paragraph>
        )}
        {review.error && <Alert style={{ marginTop: '1rem' }} type="error" message={review.error} showIcon />}
      </Card>

      <Card title="本次改动" size="small">
        {id && <CommitDiffView reviewId={id} />}
      </Card>

      {id && !running && <LintPanel reviewId={id} issues={review.lint_issues || []} running={running} />}

      {running ? (
        <RunningPanel review={review} />
      ) : (
        <Card title={`评审意见 (${findings.length})`}>
          {findings.length === 0 ? (
            <Empty description="没有评审意见" />
          ) : (
            findings.map((f) => <FindingCard key={f.id} f={f} />)
          )}
        </Card>
      )}
    </div>
  )
}
