import React from 'react';
import {
  ApartmentOutlined,
  AuditOutlined,
  CloudServerOutlined,
  DashboardOutlined,
  DiffOutlined,
  ExperimentOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MonitorOutlined,
  SaveOutlined,
  SettingOutlined,
  SwapOutlined,
  ThunderboltOutlined,
  WifiOutlined,
} from '@ant-design/icons';
import { Button, ConfigProvider, Layout, Menu, Segmented, Space, Tag, Typography, theme } from 'antd';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useTheme } from '../theme';
import RulesDrawer from '../components/RulesDrawer';

const { Header, Sider, Content } = Layout;

const THEME_OPTIONS = [
  { label: '🌙 深色运维', value: 'dark' },
  { label: '☀️ 浅色企业', value: 'light' },
];

const items = [
  { key: '/', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/workbench', icon: <ThunderboltOutlined />, label: '终端工作台' },
  { key: '/devices', icon: <CloudServerOutlined />, label: '设备管理' },
  { key: '/backups', icon: <SaveOutlined />, label: '配置备份' },
  { key: '/strategies', icon: <SwapOutlined />, label: '备份策略' },
  { key: '/inspect', icon: <ExperimentOutlined />, label: '智能巡检' },
  { key: '/topology', icon: <ApartmentOutlined />, label: '拓扑发现' },
  { key: '/capture', icon: <WifiOutlined />, label: '抓包分析' },
  { key: '/detect', icon: <MonitorOutlined />, label: '运维检测站' },
  { key: '/drift', icon: <DiffOutlined />, label: '配置漂移' },
  { key: '/audit', icon: <AuditOutlined />, label: '审计日志' },
  { key: '/settings', icon: <SettingOutlined />, label: '系统设置' },
];

export default function Shell() {
  const { dark, mode, setMode } = useTheme();
  const nav = useNavigate();
  const loc = useLocation();
  const [collapsed, setCollapsed] = React.useState(false);
  const [rulesOpen, setRulesOpen] = React.useState(false);

  return (
    <ConfigProvider
      theme={{
        algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: {
          colorPrimary: dark ? '#2f81f7' : '#1677ff',
          borderRadius: 8,
        },
      }}
    >
      {/* 三区分离：侧边栏（导航）/ 顶栏 固定不动，只有内容区滚动。
          之前整页一起滚，看长内容时菜单会被滚出视口。 */}
      <Layout style={{ height: '100vh', overflow: 'hidden' }}>
        <Sider
          trigger={null}
          collapsible
          collapsed={collapsed}
          theme={dark ? 'dark' : 'light'}
          width={200}
          style={{
            borderRight: '1px solid rgba(127,127,127,0.12)',
            height: '100vh',
            overflowY: 'auto',
            overflowX: 'hidden',
          }}
        >
          <div
            style={{
              height: 56,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 10,
              fontWeight: 700,
              fontSize: collapsed ? 14 : 16,
              letterSpacing: 1,
            }}
          >
            <img
              src="/logo.svg"
              alt="抽象的工作台"
              width={30}
              height={30}
              style={{ borderRadius: 7, display: 'block' }}
            />
            {!collapsed && <span>抽象的工作台</span>}
          </div>
          <Menu
            mode="inline"
            selectedKeys={[loc.pathname]}
            items={items}
            onClick={(e) => nav(e.key)}
          />
          {!collapsed && (
            <div
              className="sider-module"
              onClick={() => setRulesOpen(true)}
              title="点击查看连接方式 · 使用规则 · 免责声明"
            >
              <div className="sider-module-title">SSH · Telnet · Serial · 带外</div>
              <div className="sider-module-sub">统一连接 + AI 接入模块</div>
              <div className="sider-module-link">使用规则 / 免责声明 ›</div>
            </div>
          )}
        </Sider>
        <RulesDrawer open={rulesOpen} onClose={() => setRulesOpen(false)} />
        <Layout style={{ height: '100vh', overflow: 'hidden', minWidth: 0 }}>
          <Header
            style={{
              padding: '0 16px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              borderBottom: '1px solid rgba(127,127,127,0.12)',
              background: dark ? '#0f172a' : '#fff',
              height: 56,
              lineHeight: '56px',
              flex: '0 0 auto',
            }}
          >
            <Space>
              <Button
                type="text"
                icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                onClick={() => setCollapsed(!collapsed)}
              />
              <Typography.Text strong>
                {items.find((i) => i.key === loc.pathname)?.label || '抽象的工作台'}
              </Typography.Text>
              <Tag color="blue">v0.1.0</Tag>
            </Space>
            <Space>
              <Tag color="blue">v0.2.0</Tag>
              <Segmented size="small" value={mode} onChange={setMode} options={THEME_OPTIONS} />
            </Space>
          </Header>
          <Content
            style={{
              padding: 16,
              overflow: 'auto',
              flex: '1 1 auto',
              minHeight: 0,
            }}
          >
            <Outlet />
          </Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  );
}
