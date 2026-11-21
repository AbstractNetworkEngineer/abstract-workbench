import React, { useEffect, useMemo, useState } from 'react';
import {
  CheckCircleOutlined,
  CopyOutlined,
  ExclamationCircleOutlined,
  FileProtectOutlined,
  LoadingOutlined,
  MonitorOutlined,
  ThunderboltOutlined,
  WarningOutlined,
  WifiOutlined,
} from '@ant-design/icons';
import { Alert, Button, Card, Collapse, Select, Space, Tag, Typography, message } from 'antd';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import { useStore } from '../lib/store';
import CaptureProbe from '../components/CaptureProbe';

const LEVEL_META = {
  高: { color: '#ff4d4f', bg: 'rgba(255,77,79,0.12)', border: 'rgba(255,77,79,0.45)', icon: <ExclamationCircleOutlined />, label: '高' },
  中: { color: '#faad14', bg: 'rgba(250,173,20,0.12)', border: 'rgba(250,173,20,0.45)', icon: <WarningOutlined />, label: '中' },
  低: { color: '#1677ff', bg: 'rgba(22,119,255,0.12)', border: 'rgba(22,119,255,0.4)', icon: <WarningOutlined />, label: '低' },
};

const CAT_COLOR = { 安全: 'red', 规范: 'blue', 容量: 'purple', 稳定: 'green' };

function scoreColor(n) {
  return n >= 85 ? '#3fb950' : n >= 70 ? '#d29922' : '#ff4d4f';
}

/** 四维评分条 */
function DimBar({ label, value, color }) {
  return (
    <div style={{ minWidth: 120 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 3 }}>
        <span style={{ opacity: 0.8 }}>{label}</span>
        <span style={{ color, fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>{value}</span>
      </div>
      <div style={{ height: 6, borderRadius: 3, background: 'rgba(127,127,127,0.18)', overflow: 'hidden' }}>
        <div
          style={{
            width: `${Math.max(0, Math.min(100, value))}%`,
            height: '100%',
            borderRadius: 3,
            background: `linear-gradient(90deg, ${color}cc, ${color})`,
            transition: 'width .5s ease',
          }}
        />
      </div>
    </div>
  );
}

/** 整改命令块（可复制） */
function FixBlock({ commands }) {
  if (!commands?.length) return null;
  const copy = () => {
    navigator.clipboard?.writeText(commands.join('\n')).then(
      () => message.success('已复制整改命令'),
      () => message.error('复制失败')
    );
  };
  return (
    <div className="fix-block">
      <div className="fix-block-head">
        <span>整改命令</span>
        <Button size="small" type="text" icon={<CopyOutlined />} className="panel-log-btn" onClick={copy} />
      </div>
      <pre className="fix-block-code">{commands.join('\n')}</pre>
    </div>
  );
}

/** 单条发现卡片 */
function FindingCard({ f }) {
  const m = LEVEL_META[f.level] || LEVEL_META.低;
  return (
    <div className="finding-card" style={{ borderLeft: `3px solid ${m.color}`, background: m.bg }}>
      <div className="finding-head">
        <span style={{ color: m.color }}>{m.icon}</span>
        <Tag color={CAT_COLOR[f.cat] || 'default'}>{f.cat}</Tag>
        <Tag color={f.level === '高' ? 'error' : f.level === '中' ? 'warning' : 'processing'}>
          {m.label}危
        </Tag>
        <Tag>-{f.deduct} 分</Tag>
        <span className="finding-title">{f.title}</span>
      </div>
      <div className="finding-detail">{f.detail}</div>
      {f.evidence?.length > 0 && (
        <Collapse
          ghost
          size="small"
          items={[
            {
              key: 'ev',
              label: <span style={{ fontSize: 11, opacity: 0.7 }}>设备证据 · {f.evidence.length} 条</span>,
              children: (
                <pre className="finding-evidence">
                  {f.evidence.map((e, i) => `· ${e}`).join('\n')}
                </pre>
              ),
            },
          ]}
        />
      )}
      <FixBlock commands={f.fix} />
    </div>
  );
}

export default function Inspect() {
  const nav = useNavigate();
  const [devices, setDevices] = useState([]);
  // 巡检结果持久化：换模块回来报告还在
  const [deviceId, setDeviceId] = useStore('inspect.deviceId', null);
  const [report, setReport] = useStore('inspect.report', '');
  const [score, setScore] = useStore('inspect.score', null);
  const [via, setVia] = useStore('inspect.via', '');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get('/api/devices').then(setDevices).catch(() => {});
  }, []);

  const run = async () => {
    if (!deviceId) {
      message.warning('请选择设备');
      return;
    }
    setLoading(true);
    setReport('');
    setScore(null);
    try {
      const r = await api.post('/api/inspect', { device_id: deviceId });
      setReport(r.report);
      setScore(r.score);
      setVia(r.via);
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  const grouped = useMemo(() => {
    const g = { 高: [], 中: [], 低: [] };
    (score?.findings || []).forEach((f) => {
      (g[f.level] = g[f.level] || []).push(f);
    });
    return g;
  }, [score]);

  const total = score?.total ?? null;
  const totalColor = total !== null ? scoreColor(total) : '#8b949e';

  return (
    <Space direction="vertical" size={16} style={{ width: '100%', maxWidth: 1080 }}>
      <Card
        size="small"
        title={
          <span>
            <MonitorOutlined /> 智能巡检 — 设备运行状态检测
          </span>
        }
      >
        <Space wrap>
          <Select
            style={{ minWidth: 240 }}
            placeholder="选择设备"
            value={deviceId}
            onChange={setDeviceId}
            options={devices.map((d) => ({ value: d.id, label: `${d.name}（${d.protocol}）` }))}
          />
          <Button type="primary" loading={loading} icon={loading ? <LoadingOutlined /> : <FileProtectOutlined />} onClick={run}>
            一键巡检
          </Button>
          <Button icon={<WifiOutlined />} onClick={() => nav('/capture')}>
            抓包审查
          </Button>
          <Typography.Text type="secondary">
            自动采集 版本 / 接口 / 运行配置 → 安全审查
          </Typography.Text>
        </Space>
      </Card>

      {score && (
        <Card
          size="small"
          title={
            <Space>
              状态检测报告
              {via === 'live-session' && <Tag color="success">活动会话采集</Tag>}
              <Tag>发现 {score.findings?.length || 0} 项</Tag>
            </Space>
          }
          extra={
            <Button
              size="small"
              icon={<CopyOutlined />}
              onClick={() => {
                navigator.clipboard?.writeText(report);
                message.success('已复制完整报告');
              }}
            >
              复制报告
            </Button>
          }
        >
          {/* 评分总览 */}
          <div className="score-overview">
            <div className="score-ring" style={{ borderColor: totalColor, color: totalColor }}>
              <div className="score-num">{total}</div>
              <div className="score-label">运行状态</div>
            </div>
            <div className="dim-grid">
              <DimBar label="安全" value={score.dims?.安全 ?? 0} color="#ff4d4f" />
              <DimBar label="规范" value={score.dims?.规范 ?? 0} color="#1677ff" />
              <DimBar label="容量" value={score.dims?.容量 ?? 0} color="#9254de" />
              <DimBar label="稳定" value={score.dims?.稳定 ?? 0} color="#3fb950" />
            </div>
            <div className="score-verdict" style={{ color: totalColor }}>
              {total >= 85 ? (
                <>
                  <CheckCircleOutlined /> 状态良好
                </>
              ) : total >= 70 ? (
                <>
                  <WarningOutlined /> 存在隐患，建议整改
                </>
              ) : (
                <>
                  <ExclamationCircleOutlined /> 风险较高，需优先处理
                </>
              )}
            </div>
          </div>

          {/* 发现分级展示 */}
          {['高', '中', '低'].map((lv) => {
            const list = grouped[lv] || [];
            if (!list.length) return null;
            const meta = LEVEL_META[lv];
            return (
              <div key={lv} className="finding-group">
                <div className="finding-group-head" style={{ color: meta.color }}>
                  {meta.icon} {lv}危 · {list.length} 项
                </div>
                {list.map((f, i) => (
                  <FindingCard key={f.id || i} f={f} />
                ))}
              </div>
            );
          })}

          {(!score.findings || score.findings.length === 0) && (
            <Alert
              type="success"
              showIcon
              message="未发现明显问题"
              description="按规则引擎逐条检查，配置中未命中已知风险项。"
            />
          )}
        </Card>
      )}

      {report && (
        <Card
          size="small"
          title={
            <Space>
              <ThunderboltOutlined /> AI 分析与整改建议
            </Space>
          }
        >
          <pre className="report-text">{report.replace(/^## (总评分|四维评分)[\s\S]*?(?=\n## )/, '')}</pre>
        </Card>
      )}

      {/* Wireshark 真实融入：在巡检里直接跑抓包，出包级发现 */}
      <CaptureProbe
        storeKey="inspect.probe"
        title="Wireshark 抓包审查 — 配置之外的链路实况"
        defaultDuration={15}
      />
    </Space>
  );
}
