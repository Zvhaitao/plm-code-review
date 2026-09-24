import { useEffect, useState } from 'react'
import { Table, Tag, Typography, Button, Space, Select, message, Popconfirm } from 'antd'
import { ReloadOutlined, PlayCircleOutlined, RedoOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { api, Review, ReviewFacets } from '../api/client'

const statusColor: Record<string, string> = {
  pending: 'default',
  running: 'processing',
  succeeded: 'success',
  failed: 'error',
}

export default function Dashboard() {
  const [reviews, setReviews] = useState<Review[]>([])
  const [facets, setFacets] = useState<ReviewFacets>({ repositories: [], authors: [], pending_count: 0 })
  const [repoId, setRepoId] = useState<number | undefined>()
  const [author, setAuthor] = useState<string | undefined>()
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const load = async () => {
    setLoading(true)
    try {
      const params: Record<string, string | number> = {}
      if (repoId != null) params.repository_id = repoId
      if (author) params.commit_author = author
      const resp = await api.get<Review[]>('/api/reviews', { params })
      setReviews(resp.data)
    } finally {
      setLoading(false)
    }
  }

  const loadFacets = async () => {
    setFacets((await api.get<ReviewFacets>('/api/reviews/facets')).data)
  }

  const processPending = async () => {
    try {
      const resp = await api.post<{ message: string }>('/api/reviews/process-pending')
      message.success(resp.data.message)
      load()
      loadFacets()
    } catch {
      message.error('处理未完成评审失败')
    }
  }

  const rerun = async (id: number) => {
    try {
      await api.post(`/api/reviews/${id}/rerun`)
      message.success(`已重新排队评审 #${id}`)
      load()
      loadFacets()
    } catch {
      message.error('重新评审失败')
    }
  }

  useEffect(() => {
    load()
    const timer = setInterval(load, 5000) // 轮询刷新进行中的评审
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repoId, author])

  useEffect(() => {
    loadFacets()
  }, [])

  return (
    <div>
      <Space style={{ marginBottom: 16, justifyContent: 'space-between', width: '100%' }} wrap>
        <Typography.Title level={4} style={{ margin: 0 }}>评审看板</Typography.Title>
        <Space wrap>
          <Select
            allowClear
            placeholder="按仓库筛选"
            style={{ width: 220 }}
            value={repoId}
            onChange={(v) => setRepoId(v)}
            options={facets.repositories.map((r) => ({
              value: r.id,
              label: `${r.name} (${r.review_count})`,
            }))}
          />
          <Select
            allowClear
            showSearch
            placeholder="按提交人筛选"
            style={{ width: 200 }}
            value={author}
            onChange={(v) => setAuthor(v)}
            optionFilterProp="label"
            options={facets.authors.map((a) => ({
              value: a.name,
              label: `${a.name} (${a.review_count})`,
            }))}
          />
          <Popconfirm
            title={`处理 ${facets.pending_count} 条未完成评审?`}
            description="将在后台串行评审所有 pending 记录(含上次中断后重置的),会消耗模型额度。"
            onConfirm={processPending}
            okText="开始"
            cancelText="取消"
            disabled={!facets.pending_count}
          >
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              disabled={!facets.pending_count}
            >
              处理未完成{facets.pending_count ? ` (${facets.pending_count})` : ''}
            </Button>
          </Popconfirm>
          <Button icon={<ReloadOutlined />} onClick={() => { load(); loadFacets() }}>刷新</Button>
        </Space>
      </Space>
      <Table
        rowKey="id"
        loading={loading}
        dataSource={reviews}
        onRow={(r) => ({ onClick: () => navigate(`/reviews/${r.id}`), style: { cursor: 'pointer' } })}
        columns={[
          { title: 'ID', dataIndex: 'id', width: 70 },
          { title: '仓库', dataIndex: 'repository_name', width: 200, ellipsis: true },
          { title: '提交人', dataIndex: 'commit_author', width: 140, render: (v) => v || '-' },
          {
            title: '提交',
            render: (_, r) => (
              <span>
                <Tag>{r.commit_sha?.slice(0, 8)}</Tag>
                {r.commit_message}
              </span>
            ),
          },
          { title: '触发', dataIndex: 'trigger', width: 90, render: (t) => (t === 'scheduled' ? '定时' : '手动') },
          { title: '评分', dataIndex: 'score', width: 80, render: (s) => (s == null ? '-' : s) },
          {
            title: '状态',
            dataIndex: 'status',
            width: 110,
            render: (s) => <Tag color={statusColor[s]}>{s}</Tag>,
          },
          { title: '创建时间', dataIndex: 'created_at', width: 200, render: (t) => new Date(t).toLocaleString() },
          {
            title: '操作',
            width: 90,
            render: (_, r) =>
              r.status === 'running' ? null : (
                <Button
                  size="small"
                  type="link"
                  icon={<RedoOutlined />}
                  onClick={(e) => {
                    e.stopPropagation()
                    rerun(r.id)
                  }}
                >
                  重试
                </Button>
              ),
          },
        ]}
      />
    </div>
  )
}
