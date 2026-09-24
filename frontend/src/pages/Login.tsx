import { useState } from 'react'
import { Card, Form, Input, Button, message } from 'antd'
import { useNavigate } from 'react-router-dom'
import { api, auth } from '../api/client'

export default function Login() {
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true)
    try {
      const resp = await api.post('/api/auth/login', values)
      auth.setToken(resp.data.token)
      navigate('/dashboard')
    } catch {
      message.error('登录失败,请检查用户名或密码')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#f0f2f5' }}>
      <Card title="🤖 代码评审平台登录" style={{ width: 360 }}>
        <Form onFinish={onFinish} layout="vertical">
          <Form.Item name="username" label="用户名" rules={[{ required: true }]}>
            <Input autoFocus />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true }]}>
            <Input.Password />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>登录</Button>
        </Form>
      </Card>
    </div>
  )
}
