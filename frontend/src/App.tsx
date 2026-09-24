import { BrowserRouter, Routes, Route, Navigate, Link, useLocation, useNavigate } from 'react-router-dom'
import { Layout, Menu, Button } from 'antd'
import { DashboardOutlined, DatabaseOutlined, SettingOutlined, LogoutOutlined } from '@ant-design/icons'
import { auth, api } from './api/client'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Repositories from './pages/Repositories'
import ReviewDetail from './pages/ReviewDetail'
import Settings from './pages/Settings'

const { Header, Content, Sider } = Layout

function RequireAuth({ children }: { children: JSX.Element }) {
  if (!auth.getToken()) return <Navigate to="/login" replace />
  return children
}

function Shell({ children }: { children: JSX.Element }) {
  const location = useLocation()
  const navigate = useNavigate()
  const selected = '/' + (location.pathname.split('/')[1] || 'dashboard')

  const logout = async () => {
    try { await api.post('/api/auth/logout') } catch { /* ignore */ }
    auth.clear()
    navigate('/login')
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider theme="light">
        <div style={{ padding: 16, fontWeight: 600, fontSize: 16 }}>🤖 代码评审平台</div>
        <Menu
          mode="inline"
          selectedKeys={[selected]}
          items={[
            { key: '/dashboard', icon: <DashboardOutlined />, label: <Link to="/dashboard">评审看板</Link> },
            { key: '/repositories', icon: <DatabaseOutlined />, label: <Link to="/repositories">仓库配置</Link> },
            { key: '/settings', icon: <SettingOutlined />, label: <Link to="/settings">设置</Link> },
          ]}
        />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
          <Button icon={<LogoutOutlined />} onClick={logout}>退出登录</Button>
        </Header>
        <Content style={{ margin: 24 }}>{children}</Content>
      </Layout>
    </Layout>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/dashboard" element={<RequireAuth><Shell><Dashboard /></Shell></RequireAuth>} />
        <Route path="/repositories" element={<RequireAuth><Shell><Repositories /></Shell></RequireAuth>} />
        <Route path="/reviews/:id" element={<RequireAuth><Shell><ReviewDetail /></Shell></RequireAuth>} />
        <Route path="/settings" element={<RequireAuth><Shell><Settings /></Shell></RequireAuth>} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
