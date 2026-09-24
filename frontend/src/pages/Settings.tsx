import { useEffect, useState } from 'react'
import { Card, Descriptions, Tag, Typography, Spin, Alert } from 'antd'
import { api } from '../api/client'

interface SettingsInfo {
  review_engine: string
  review_model: string
  claude_max_tokens: number
  anthropic_base_url: string
  llm_configured: boolean
  poll_interval_minutes: number
}

export default function Settings() {
  const [info, setInfo] = useState<SettingsInfo | null>(null)

  useEffect(() => {
    api.get<SettingsInfo>('/api/settings').then((r) => setInfo(r.data))
  }, [])

  if (!info) return <Spin />

  const ok = (v: boolean) => (v ? <Tag color="success">已配置</Tag> : <Tag color="error">未配置</Tag>)

  return (
    <div>
      <Typography.Title level={4}>设置</Typography.Title>
      <Card style={{ marginBottom: 16 }}>
        <Descriptions title="运行时配置" column={1}>
          <Descriptions.Item label="评审引擎">
            {info.review_engine === 'ocr' ? 'open-code-review (ocr CLI)' : '内置引擎'}
          </Descriptions.Item>
          <Descriptions.Item label="评审模型">{info.review_model}</Descriptions.Item>
          <Descriptions.Item label="Max Tokens">{info.claude_max_tokens}</Descriptions.Item>
          <Descriptions.Item label="模型端点">{info.anthropic_base_url}</Descriptions.Item>
          <Descriptions.Item label="模型凭证">{ok(info.llm_configured)}</Descriptions.Item>
          <Descriptions.Item label="定时检查">
            {info.poll_interval_minutes > 0 ? `每 ${info.poll_interval_minutes} 分钟` : '关闭(仅手动)'}
          </Descriptions.Item>
        </Descriptions>
      </Card>
      <Alert
        type="info"
        showIcon
        message="工作方式"
        description={
          <div>
            <p>平台对<b>本地已克隆</b>的仓库工作:配置本地路径后,点「立即检查」会先 <Typography.Text code>git pull</Typography.Text>,再对每个新提交单独评审,结果只保存在平台内查看。</p>
            {info.review_engine === 'ocr' ? (
              <p>当前评审引擎为 <Typography.Text code>open-code-review</Typography.Text>(ocr CLI)。它的模型与端点由 <Typography.Text code>ocr config</Typography.Text> 管理(可用 <Typography.Text code>ocr llm test</Typography.Text> 验证),与后端 <Typography.Text code>.env</Typography.Text> 独立;ocr 不可用时会自动回退到内置引擎。</p>
            ) : (
              <p>当前为内置引擎:模型、端点等配置通过后端 <Typography.Text code>.env</Typography.Text> 管理,修改后需重启后端。</p>
            )}
            <p>设 <Typography.Text code>POLL_INTERVAL_MINUTES</Typography.Text> 大于 0 可开启定时自动检查。</p>
          </div>
        }
      />
    </div>
  )
}
