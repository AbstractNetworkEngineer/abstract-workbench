import React, { useEffect, useMemo, useState } from 'react';
import {
  ExperimentOutlined,
  LoadingOutlined,
  MonitorOutlined,
  RobotOutlined,
  SettingOutlined,
  WifiOutlined,
} from '@ant-design/icons';
import {
  Button,
  Card,
  Checkbox,
  Empty,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
  message,
} from 'antd';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import { useStore } from '../lib/store';
import CaptureProbe from '../components/CaptureProbe';
import DetectItemModal from '../components/DetectItemModal';
import DetectResultCard from '../components/DetectResultCard';

export default function Detect() {
  const nav = useNavigate();
  const [devices, setDevices] = useState([]);
  const [catalog, setCatalog] = useState([]);
  // 结果用 useStore：切换模块再回来不丢（React Router 卸载组件不会清掉它）
  const [deviceId, setDeviceId] = useStore('detect.deviceId', null);
  const [checked, setChecked] = useStore('detect.checked', []);
  const [result, setResult] = useStore('detect.result', null);
  const [aiText, setAiText] = useStore('detect.aiText', '');
  const [running, setRunning] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [manageOpen, setManageOpen] = useState(false);

  const loadCatalog = async () => {
    try {
      const c = await api.get('/api/detect/catalog');
      setCatalog(c);
      setChecked((prev) => {
        // 保留用户已勾选项，新增项默认勾上
        const keys = c.map((i) => i.key);
        const kept = prev.filter((k) => keys.includes(k));
        const added = keys.filter((k) => !prev.includes(k));
        return [...kept, ...added];
      });
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    api.get('/api/devices').then(setDevices).catch(() => {});
    loadCatalog();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const grouped = useMemo(() => {
    const g = {};
    catalog.forEach((i) => {
      (g[i.cat] = g[i.cat] || []).push(i);
    });
    return g;
  }, [catalog]);

  const run = async () => {
    if (!deviceId) {
      message.warning('请选择设备');
      return;
    }
    if (!checked.length) {
      message.warning('请至少勾选一个检测项');
      return;
    }
    setRunning(true);
    setResult(null);
    setAiText('');
    try {
      const r = await api.post('/api/detect/run', { device_id: deviceId, items: checked });
      setResult(r);
      const bad = r.results.filter((x) => x.status === 'warn' || x.status === 'error').length;
      message.success(`检测完成：${r.results.length} 项 · 耗时 ${r.elapsed}s · ${bad} 项需关注`);
    } catch (e) {
      message.error(e.message);
    } finally {
      setRunning(false);
    }
  };

  const aiExplain = async () => {
    if (!result) return;
    setAiLoading(true);
    setAiText('');
    try {
      const ctx = result.results
        .map((x) => `## ${x.label}（${x.status}）\n${(x.output || '').slice(0, 1500)}`)
        .join('\n\n');
      const r = await api.post('/api/ai/chat', {
        messages: [
          {
            role: 'user',
            content:
              `请对设备 ${result.device.name} 的运维检测结果做整体解读：运行是否健康、协议状态是否正常、有无隐患，最后给一个 0-100 的健康分（格式：健康分：NN）。`,
          },
        ],
        context: ctx,
        mode: 'analyze',
      });
      setAiText(r.reply);
    } catch (e) {
      message.error(e.message);
    } finally {
      setAiLoading(false);
    }
  };

  const summary = result
    ? {
        ok: result.results.filter((r) => r.status === 'ok').length,
        warn: result.results.filter((r) => r.status === 'warn').length,
        error: result.results.filter((r) => r.status === 'error').length,
        na: result.results.filter((r) => r.status === 'na').length,
      }
    : null;

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card
        size="small"
        title={
          <span>
            <MonitorOutlined /> 设备运维检测站 — 配置 · 协议 · 状态 · 数据
          </span>
        }
      >
        <Space wrap>
          <Select
            style={{ minWidth: 220 }}
            placeholder="选择设备"
            value={deviceId}
            onChange={setDeviceId}
            options={devices.map((d) => ({ value: d.id, label: `${d.name}（${d.protocol}）` }))}
          />
          <Button type="primary" loading={running} icon={running ? <LoadingOutlined /> : <ExperimentOutlined />} onClick={run}>
            开始检测
          </Button>
          <Button
            icon={<RobotOutlined />}
            loading={aiLoading}
            disabled={!result}
            onClick={aiExplain}
          >
            AI 解读检测结果
          </Button>
          <Button icon={<SettingOutlined />} onClick={() => setManageOpen(true)}>
            管理检测项
          </Button>
          <Typography.Text type="secondary">
            自动经活动会话采集；检测项可自定义名称与命令
          </Typography.Text>
        </Space>

        <div style={{ marginTop: 12 }}>
          <Space style={{ marginBottom: 6 }}>
            <Button size="small" onClick={() => setChecked(catalog.map((i) => i.key))}>
              全选
            </Button>
            <Button size="small" onClick={() => setChecked([])}>
              清空
            </Button>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              已勾选 {checked.length}/{catalog.length} 项
            </Typography.Text>
          </Space>
          <div>
            {Object.entries(grouped).map(([cat, items]) => (
              <span key={cat} style={{ marginRight: 16, display: 'inline-block' }}>
                <Typography.Text strong style={{ fontSize: 12, marginRight: 6 }}>{cat}</Typography.Text>
                {items.map((i) => (
                  <Checkbox
                    key={i.key}
                    checked={checked.includes(i.key)}
                    onChange={(e) =>
                      setChecked((c) =>
                        e.target.checked ? [...c, i.key] : c.filter((k) => k !== i.key)
                      )
                    }
                  >
                    {i.label}
                    {i.builtin === false && (
                      <Tag color="purple" style={{ marginLeft: 4, fontSize: 10 }}>自定义</Tag>
                    )}
                  </Checkbox>
                ))}
              </span>
            ))}
          </div>
        </div>
      </Card>

      <DetectItemModal
        open={manageOpen}
        onClose={() => setManageOpen(false)}
        onChanged={loadCatalog}
      />

      {/* Wireshark 真实融入：在检测站里直接起抓包，出包级发现 */}
      <CaptureProbe
        storeKey="detect.probe"
        title="Wireshark 抓包检测 — 广播风暴 / ARP 泛洪 / 明文协议"
        defaultDuration={15}
      />

      {running && (
        <Card size="small">
          <Spin tip="正在采集设备协议与状态数据…" />
        </Card>
      )}

      {summary && (
        <Card size="small">
          <Space size={16}>
            <Tag color="success">正常 {summary.ok}</Tag>
            <Tag color="warning">关注 {summary.warn}</Tag>
            <Tag color="error">异常 {summary.error}</Tag>
            <Tag>不支持 {summary.na}</Tag>
            <Tag color="blue">采集通道：{result.via === 'live-session' ? '活动会话' : '新建连接'}</Tag>
            <Tag>耗时 {result.elapsed}s</Tag>
          </Space>
        </Card>
      )}

      {aiText && (
        <Card size="small" title={<span><RobotOutlined /> AI 检测解读</span>}>
          <pre className="report-text">{aiText}</pre>
        </Card>
      )}

      {result && (
        <div className="detect-grid">
          {result.results.map((r) => (
            <DetectResultCard key={r.key} item={r} />
          ))}
        </div>
      )}

      {!result && !running && (
        <Card size="small">
          <Empty description="选择设备后点击「开始检测」，一键查看配置/协议/状态/数据" />
        </Card>
      )}
    </Space>
  );
}
