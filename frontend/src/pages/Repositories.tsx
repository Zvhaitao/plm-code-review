import { useEffect, useState } from 'react'
import { Table, Button, Modal, Form, Input, Switch, Space, Typography, message, Popconfirm, Tag } from 'antd'
import { api, Repository } from '../api/client'

export default function Repositories() {
  const [repos, setRepos] = useState<Repository[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [checking, setChecking] = useState<number | null>(null)
  const [form] = Form.useForm()

  const load = async () => {
    setLoading(true)
    try {
      setRepos((await api.get<Repository[]>('/api/repositories')).data)
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { load() }, [])

  const create = async () => {
    const values = await form.validateFields()
    try {
      await api.post('/api/repositories', values)
      message.success('已添加仓库')
      setModalOpen(false)
      form.resetFields()
      load()
    } catch (e: any) {
      message.error(e.response?.data?.detail || '添加失败')
    }
  }

  const toggleEnabled = async (repo: Repository, enabled: boolean) => {
    await api.patch(`/api/repositories/${repo.id}`, { enabled })
    load()
  }

  const remove = async (repo: Repository) => {
    await api.delete(`/api/repositories/${repo.id}`)
    message.success('已删除')
    load()
  }

  const checkNow = async (repo: Repository) => {
    setChecking(repo.id)
    try {
      const resp = await api.post(`/api/reviews/check/${repo.id}`)
      message.success(resp.data.message || '已开始检查')
    } catch (e: any) {
      message.error(e.response?.data?.detail || '检查失败')
    } finally {
      setChecking(null)
    }
  }

  return (
    <div>
      <Space style={{ marginBottom: 16, justifyContent: 'space-between', width: '100%' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>仓库配置</Typography.Title>
        <Button type="primary" onClick={() => setModalOpen(true)}>添加仓库</Button>
      </Space>
      <Table
        rowKey="id"
        loading={loading}
        dataSource={repos}
        columns={[
          { title: '名称', render: (_, r) => `${r.gitea_owner}/${r.gitea_name}` },
          { title: '本地路径', dataIndex: 'local_path', ellipsis: true },
          { title: '分支', dataIndex: 'branch', width: 120, render: (v) => v || <Typography.Text type="secondary">当前</Typography.Text> },
          {
            title: '评审基线',
            dataIndex: 'last_reviewed_sha',
            width: 110,
            render: (v) => (v ? <Tag>{v.slice(0, 8)}</Tag> : <Tag color="warning">未检查</Tag>),
          },
          {
            title: '启用',
            dataIndex: 'enabled',
            width: 80,
            render: (v, r) => <Switch checked={v} onChange={(c) => toggleEnabled(r, c)} />,
          },
          {
            title: '操作',
            width: 220,
            render: (_, r) => (
              <Space>
                <Button size="small" type="primary" loading={checking === r.id} onClick={() => checkNow(r)}>
                  立即检查
                </Button>
                <Popconfirm title="确认删除该仓库?" onConfirm={() => remove(r)}>
                  <Button size="small" danger>删除</Button>
                </Popconfirm>
              </Space>
            ),
          },
        ]}
      />

      <Modal title="添加本地仓库" open={modalOpen} onOk={create} onCancel={() => setModalOpen(false)} okText="添加">
        <Form form={form} layout="vertical">
          <Form.Item name="gitea_owner" label="分组/前缀" rules={[{ required: true }]} tooltip="仅用于展示区分">
            <Input placeholder="如 SCHPRO" />
          </Form.Item>
          <Form.Item name="gitea_name" label="仓库名" rules={[{ required: true }]}>
            <Input placeholder="如 schpro_package" />
          </Form.Item>
          <Form.Item name="local_path" label="本地路径" rules={[{ required: true }]} tooltip="已克隆到本地的仓库目录绝对路径">
            <Input placeholder="如 D:\\repos\\schpro_package" />
          </Form.Item>
          <Form.Item name="branch" label="分支(可选)" tooltip="留空则用仓库当前分支">
            <Input placeholder="如 main / master" />
          </Form.Item>
          <Form.Item name="review_rules" label="评审规则(可选)">
            <Input.TextArea rows={3} placeholder="例如:重点关注 SQL 注入与空指针;忽略格式问题" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
