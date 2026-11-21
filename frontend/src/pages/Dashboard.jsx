import React, { useEffect, useState } from 'react';
import {
  AuditOutlined,
  CloudServerOutlined,
  RobotOutlined,
  SaveOutlined,
  SwapOutlined,
  WifiOutlined,
} from '@ant-design/icons';
import { Button, Card, Col, List, Row, Space, Statistic, Tag, Typography, message } from 'antd';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';

export default function Dashboard() {
  const nav = useNavigate();
  const [stats, setStats] = useState(null);
  const [devices, setDevices] = useState([]);

  const load = async () => {
    try {
      const [s, d] = await Promise.all([api.get('/api/stats'), api.get('/api/devices')]);
      setStats(s);
      setDevices(d);
    } catch (e) {
      message.error(e.message);
    }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  const statusColor = (s) => (s === 'ok' ? 'success' : s === 'failed' ? 'error' : 'processing');

  // AI 接入状态：说清缺哪一项，而不是笼统"未配置"。
  // （曾经出现过配了 API Key 却显示"未配置"，用户以为软件坏了 —— 其实是 Base URL 没填）
  const aiSt = stats?.ai_status || {};
  const aiReady = !!aiSt.ready;
  const aiMissing = aiSt.missing || [];
  const aiStatusText = aiSt.status_text || (stats?.ai_configured ? '已配置' : '未配置');
  const aiConfiguredParts = [
    aiSt.has_base_url ? 'Base URL' : null,
    aiSt.has_api_key ? 'API Key' : null,
    aiSt.has_model ? '模型名' : null,
  ]
    .filter(Boolean)
    .join(' · ') || '（全部未填）';

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Row gutter={[12, 12]}>
        <Col xs={12} md={8} lg={4}>
          <Card size="small">
            <Statistic title="设备总数" value={stats?.devices ?? '—'} prefix={<CloudServerOutlined />} />
          </Card>
        </Col>
        <Col xs={12} md={8} lg={4}>
          <Card size="small">
            <Statistic title="备份总数" value={stats?.backups ?? '—'} prefix={<SaveOutlined />} />
          </Card>
        </Col>
        <Col xs={12} md={8} lg={4}>
          <Card size="small">
            <Statistic title="今日备份" value={stats?.backups_today ?? '—'} />
          </Card>
        </Col>
        <Col xs={12} md={8} lg={4}>
          <Card size="small">
            <Statistic
              title="启用策略"
              value={stats?.strategies ?? '—'}
              prefix={<SwapOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} md={8} lg={4}>
          <Card size="small">
            <Statistic
              title="审计事件"
              value={stats?.audits ?? '—'}
              prefix={<AuditOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} md={8} lg={4}>
          <Card size="small">
            <Statistic
              title="AI 接入"
              value={aiStatusText}
              valueStyle={{
                fontSize: aiReady ? 20 : 15,
                color: aiReady ? '#52c41a' : '#faad14',
              }}
              prefix={<RobotOutlined />}
            />
            {!aiReady && aiMissing.length > 0 && (
              <div style={{ fontSize: 11, color: '#faad14', marginTop: 2, lineHeight: 1.5 }}>
                已配：{aiConfiguredParts}
                <br />
                <a onClick={() => nav('/settings')}>去补全 →</a>
              </div>
            )}
          </Card>
        </Col>
        <Col xs={12} md={8} lg={4}>
          <Card size="small">
            <Statistic
              title="Wireshark 抓包"
              value={stats?.capture?.files ?? '—'}
              suffix={<span style={{ fontSize: 12, opacity: 0.7 }}>个文件</span>}
              valueStyle={{
                fontSize: 20,
                color: stats?.capture?.ready ? '#52c41a' : '#8b949e',
              }}
              prefix={<WifiOutlined />}
            />
            <div style={{ fontSize: 11, opacity: 0.7, marginTop: 2, lineHeight: 1.5 }}>
              {stats?.capture?.ready ? (
                <>
                  tshark {stats.capture.version} 已就绪
                  <br />
                  <a onClick={() => nav('/capture')}>去抓包分析 →</a>
                </>
              ) : (
                <a onClick={() => nav('/capture')}>Wireshark 未就绪 →</a>
              )}
            </div>
          </Card>
        </Col>
      </Row>

      <Row gutter={[12, 12]}>
        <Col xs={24} lg={14}>
          <Card
            size="small"
            title="最近动态"
            extra={<Button size="small" onClick={() => nav('/audit')}>全部</Button>}
          >
            <List
              size="small"
              dataSource={stats?.recent_audits || []}
              locale={{ emptyText: '暂无事件' }}
              renderItem={(a) => (
                <List.Item>
                  <Space>
                    <Tag color={statusColor(a.status)}>{a.kind}</Tag>
                    <Typography.Text>{a.action}</Typography.Text>
                    {a.device_name && (
                      <Typography.Text type="secondary">· {a.device_name}</Typography.Text>
                    )}
                  </Space>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {a.created_at ? new Date(a.created_at + 'Z').toLocaleString() : ''}
                  </Typography.Text>
                </List.Item>
              )}
            />
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card
            size="small"
            title="设备一览"
            extra={<Button size="small" onClick={() => nav('/devices')}>管理</Button>}
          >
            <List
              size="small"
              dataSource={devices.slice(0, 8)}
              locale={{ emptyText: '暂无设备' }}
              renderItem={(d) => (
                <List.Item>
                  <Space>
                    <Tag
                      color={
                        { ssh: 'blue', telnet: 'orange', serial: 'purple', mock: 'cyan', outband: 'geekblue' }[
                          d.protocol
                        ] || 'default'
                      }
                    >
                      {d.protocol}
                    </Tag>
                    <Typography.Text strong>{d.name}</Typography.Text>
                    <Typography.Text type="secondary">{d.host || d.serial_port}</Typography.Text>
                  </Space>
                  <Tag>{d.vendor}</Tag>
                </List.Item>
              )}
            />
          </Card>
        </Col>
      </Row>

      <Card size="small" title="快捷开始">
        <Space wrap>
          <Button type="primary" onClick={() => nav('/workbench')}>
            打开终端工作台
          </Button>
          <Button onClick={() => nav('/devices')}>添加设备</Button>
          <Button onClick={() => nav('/backups')}>立即备份</Button>
          {!aiReady && (
            <Button danger onClick={() => nav('/settings')}>
              补全 AI 配置（缺 {aiMissing.join('、') || '…'}）→
            </Button>
          )}
        </Space>
      </Card>
    </Space>
  );
}
