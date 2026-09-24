import { useEffect, useState } from 'react'
import { Collapse, Spin, Alert, Empty, Tag, Typography, Segmented } from 'antd'
import { api, CommitDiff, FileDiff } from '../api/client'

const MONO = '"SF Mono","Cascadia Code","JetBrains Mono",Consolas,"Liberation Mono",ui-monospace,monospace'

type RowType = 'hunk' | 'add' | 'del' | 'ctx'
interface Row {
  type: RowType
  oldNo: number | null
  newNo: number | null
  text: string
}

const HUNK_RE = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/

// 把 unified diff 的 patch(从首个 @@ 开始)解析为可渲染的行
function parsePatch(patch: string): Row[] {
  const rows: Row[] = []
  let oldNo = 0
  let newNo = 0
  for (const line of patch.split('\n')) {
    const m = HUNK_RE.exec(line)
    if (m) {
      oldNo = parseInt(m[1], 10)
      newNo = parseInt(m[2], 10)
      rows.push({ type: 'hunk', oldNo: null, newNo: null, text: line })
      continue
    }
    const c = line[0]
    if (c === '+') {
      rows.push({ type: 'add', oldNo: null, newNo: newNo++, text: line.slice(1) })
    } else if (c === '-') {
      rows.push({ type: 'del', oldNo: oldNo++, newNo: null, text: line.slice(1) })
    } else if (c === '\\') {
      // "\ No newline at end of file" —— 跳过
    } else {
      rows.push({ type: 'ctx', oldNo: oldNo++, newNo: newNo++, text: line.slice(1) })
    }
  }
  return rows
}

const ROW_BG: Record<RowType, string> = {
  hunk: '#eef4fd',
  add: '#e6ffec',
  del: '#ffebe9',
  ctx: '#fff',
}
const SIGN: Record<RowType, string> = { hunk: '', add: '+', del: '-', ctx: '' }

const STATUS_TAG: Record<string, { color: string; label: string }> = {
  added: { color: 'green', label: '新增' },
  modified: { color: 'blue', label: '修改' },
  deleted: { color: 'red', label: '删除' },
  renamed: { color: 'gold', label: '重命名' },
}

const GUTTER = 'rgba(0,0,0,0.35)'

type DiffMode = 'unified' | 'split'

interface SplitRow {
  hunk?: string
  left: Row | null
  right: Row | null
}

// 把统一 diff 行转成左右分列行:删除块与其后的新增块按序两两配对
function toSplitRows(rows: Row[]): SplitRow[] {
  const out: SplitRow[] = []
  let dels: Row[] = []
  let adds: Row[] = []
  const flush = () => {
    const n = Math.max(dels.length, adds.length)
    for (let i = 0; i < n; i++) out.push({ left: dels[i] || null, right: adds[i] || null })
    dels = []
    adds = []
  }
  for (const r of rows) {
    if (r.type === 'hunk') {
      flush()
      out.push({ hunk: r.text, left: null, right: null })
    } else if (r.type === 'del') dels.push(r)
    else if (r.type === 'add') adds.push(r)
    else {
      flush()
      out.push({ left: r, right: r })
    }
  }
  flush()
  return out
}

function DiffBody({ file, mode }: { file: FileDiff; mode: DiffMode }) {
  if (file.binary) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="二进制文件,不显示差异" />
  if (!file.patch.trim()) return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无文本差异" />
  const rows = parsePatch(file.patch)
  return (
    <div style={{ overflowX: 'auto', fontFamily: MONO, fontSize: '0.75rem', lineHeight: 1.6 }}>
      {mode === 'split' ? <SplitRows rows={rows} /> : <UnifiedRows rows={rows} />}
      {file.truncated && (
        <div style={{ padding: '0.4rem 0.6rem', color: '#a16207', background: '#fefce8' }}>
          diff 过大,已截断显示。
        </div>
      )}
    </div>
  )
}


function UnifiedRows({ rows }: { rows: Row[] }) {
  return (
    <>
      {rows.map((r, i) =>
        r.type === 'hunk' ? (
          <div key={i} style={{ background: ROW_BG.hunk, color: '#57606a', padding: '0.1rem 0.6rem', whiteSpace: 'pre' }}>
            {r.text}
          </div>
        ) : (
          <div
            key={i}
            style={{
              display: 'grid',
              gridTemplateColumns: '44px 44px 18px 1fr',
              background: ROW_BG[r.type],
              color: 'rgba(0,0,0,0.85)',
              whiteSpace: 'pre',
            }}
          >
            <span style={{ textAlign: 'right', padding: '0 0.4rem', color: GUTTER, userSelect: 'none' }}>{r.oldNo ?? ''}</span>
            <span style={{ textAlign: 'right', padding: '0 0.4rem', color: GUTTER, userSelect: 'none' }}>{r.newNo ?? ''}</span>
            <span style={{ textAlign: 'center', color: GUTTER, userSelect: 'none' }}>{SIGN[r.type]}</span>
            <span style={{ paddingRight: '0.6rem' }}>{r.text || ' '}</span>
          </div>
        )
      )}
    </>
  )
}

// 分列视图的一侧单元格(行号 + 符号 + 代码);row 为空则渲染灰底占位
function SplitHalf({ row, side }: { row: Row | null; side: 'left' | 'right' }) {
  if (!row) {
    return (
      <>
        <span style={{ background: '#f6f8fa' }} />
        <span style={{ background: '#f6f8fa' }} />
        <span style={{ background: '#f6f8fa' }} />
      </>
    )
  }
  const isChange = side === 'left' ? row.type === 'del' : row.type === 'add'
  const bg = isChange ? (side === 'left' ? ROW_BG.del : ROW_BG.add) : '#fff'
  const no = side === 'left' ? row.oldNo : row.newNo
  const sign = isChange ? (side === 'left' ? '-' : '+') : ''
  return (
    <>
      <span style={{ textAlign: 'right', padding: '0 0.4rem', color: GUTTER, userSelect: 'none', background: bg }}>{no ?? ''}</span>
      <span style={{ textAlign: 'center', color: GUTTER, userSelect: 'none', background: bg }}>{sign}</span>
      <span style={{ background: bg, paddingRight: '0.5rem', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{row.text || ' '}</span>
    </>
  )
}

function SplitRows({ rows }: { rows: Row[] }) {
  const split = toSplitRows(rows)
  return (
    <>
      {split.map((sr, i) =>
        sr.hunk !== undefined ? (
          <div key={i} style={{ background: ROW_BG.hunk, color: '#57606a', padding: '0.1rem 0.6rem', whiteSpace: 'pre' }}>
            {sr.hunk}
          </div>
        ) : (
          <div
            key={i}
            style={{
              display: 'grid',
              gridTemplateColumns: '40px 16px minmax(0,1fr) 40px 16px minmax(0,1fr)',
              color: 'rgba(0,0,0,0.85)',
              borderLeft: '0',
            }}
          >
            <SplitHalf row={sr.left} side="left" />
            <SplitHalf row={sr.right} side="right" />
          </div>
        )
      )}
    </>
  )
}

function fileHeader(file: FileDiff) {
  const tag = STATUS_TAG[file.status] || { color: 'default', label: file.status }
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', minWidth: 0 }}>
      <Tag color={tag.color} style={{ marginInlineEnd: 0 }}>
        {tag.label}
      </Tag>
      <span style={{ fontFamily: MONO, fontSize: '0.78rem', wordBreak: 'break-all' }}>
        {file.status === 'renamed' && file.old_path !== file.path ? `${file.old_path} → ${file.path}` : file.path}
      </span>
      {file.additions > 0 && <span style={{ color: '#1a7f37', fontSize: '0.75rem' }}>+{file.additions}</span>}
      {file.deletions > 0 && <span style={{ color: '#cf222e', fontSize: '0.75rem' }}>−{file.deletions}</span>}
    </div>
  )
}

export default function CommitDiffView({ reviewId }: { reviewId: string }) {
  const [diff, setDiff] = useState<CommitDiff | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [mode, setMode] = useState<DiffMode>('unified')

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError('')
    api
      .get<CommitDiff>(`/api/reviews/${reviewId}/diff`)
      .then((resp) => alive && setDiff(resp.data))
      .catch((e) => alive && setError(e.response?.data?.detail || '加载改动失败'))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [reviewId])

  if (loading) return <Spin />
  if (error) return <Alert type="warning" message={error} showIcon />
  if (!diff || diff.files.length === 0) return <Empty description="本次提交没有文件改动" />

  const defaultOpen = diff.files.length <= 10 ? diff.files.map((_, i) => String(i)) : []
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
        <Typography.Text>
          共 <b>{diff.files_changed}</b> 个文件被更改,包括 <b style={{ color: '#1a7f37' }}>{diff.insertions}</b> 次插入和{' '}
          <b style={{ color: '#cf222e' }}>{diff.deletions}</b> 次删除
          {diff.parent_sha && (
            <span style={{ marginLeft: '0.75rem', fontFamily: MONO, fontSize: '0.75rem', color: 'rgba(0,0,0,0.5)' }}>
              {diff.parent_sha.slice(0, 8)} → {diff.sha.slice(0, 8)}
            </span>
          )}
        </Typography.Text>
        <Segmented
          size="small"
          value={mode}
          onChange={(v) => setMode(v as DiffMode)}
          options={[
            { label: '合并视图', value: 'unified' },
            { label: '分列视图', value: 'split' },
          ]}
        />
      </div>
      <Collapse
        defaultActiveKey={defaultOpen}
        items={diff.files.map((f, i) => ({
          key: String(i),
          label: fileHeader(f),
          children: <DiffBody file={f} mode={mode} />,
          styles: { body: { padding: 0 } },
        }))}
      />
    </div>
  )
}

