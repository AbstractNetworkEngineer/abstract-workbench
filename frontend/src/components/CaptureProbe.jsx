import React, { useEffect, useState } from 'react';
import { LoadingOutlined, WifiOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Input, InputNumber, Select, Space, Tag, Typography, message } from 'antd';
import { api } from '../api';
import { useStore } from '../lib/store';

const LEVEL_COLOR = { 高: 'error', 中: 'warning', 低: 'processing' };

/**
 * 内嵌抓包探测：在当前模块里直接起抓包 + 出包级发现，不跳页。
 *
 * 用在「智能巡检」「运维检测站」——这是 Wireshark 真正融入业务的地方，
 * 不是放个链接跳到抓包模块。
 *
 * storeKey 用于把结果持久化，换模块回来还在。
 */
export default function CaptureProbe({ storeKey, title = 'Wireshark 抓包审查', defaultDuration = 15 }) {
  const [ifs, setIfs] = useState([]);
  const [iface, setIface] = useState('');
  const [filter, setFilter] = useStore(`${storeKey}.filter`, '');
  const [duration, setDuration] = useState(defaultDuration);
  const [running, setRunning] = useState(false);
  const [findings, setFindings] = useStore(`${storeKey}.findings`, null);
  const [err, setErr] = useState('');

  const loadIfs = async () => {
    try {
      const r = await api.get('/api/capture/interfaces');
      const list = r.interfaces || [];
      setIfs(list);
      if (!iface && list.length) {
        const eth = list.find((x) => /以太网|ethernet|wlan|local/i.test(x.name));
        setIface((eth || list[0]).device);
      }
      if (!list.length) setErr('未检测到可抓包网卡（需安装 Npcap，抓包一般要管理员权限）');
      else setErr('');
    } catch (e) {
      setErr(`网卡列表加载失败：${e.message}`);
    }
  };

  useEffect(() => {
    loadIfs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const run = async () => {
    if (!iface) {
      message.warning('请先选择网卡');
      return;
    }
    setRunning(true);
    setErr('');
    try {
      // 1) 抓包（时长到了自动停）
      const s = await api.post('/api/capture/start', {
        iface,
        bpf_filter: filter,
        max_packets: 50000,
        duration,
        name: 'probe',
      });
      message.success(`抓包中，${duration} 秒后自动分析…`);
      await new Promise((r) => setTimeout(r, (duration + 2) * 1000));
      await api.post('/api/capture/stop', { id: s.id });
      // 2) 包级发现
      const f = await api.post('/api/capture/findings', { path: s.file });
      setFindings(f);
      message.success(`抓包审查完成：${f.total} 个包，${f.findings?.length || 0} 项发现`);
    } catch (e) {
      setErr(e.message);
      message.error(e.message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <Card
      size="small"
      title={
        <span>
          <WifiOutlined /> {title}
        </span>
      }
    >
      <Space wrap>
        <Select
          style={{ minWidth: 210 }}
          placeholder={ifs.length ? '选择网卡' : '（暂无网卡）'}
          value={iface || undefined}
          onChange={setIface}
          options={ifs.map((x) => ({ value: x.device, label: x.name }))}
          showSearch
          optionFilterProp="label"
          notFoundContent={ifs.length ? '无匹配' : '未检测到网卡'}
        />
        <Input
          style={{ width: 200 }}
          placeholder="过滤器，如 host 172.16.10.1"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          allowClear
        />
        <InputNumber
          addonBefore="时长"
          addonAfter="秒"
          min={3}
          max={180}
          value={duration}
          onChange={(v) => setDuration(v || 15)}
          style={{ width: 140 }}
        />
        <Button type="primary" loading={running} icon={running ? <LoadingOutlined /> : <WifiOutlined />} onClick={run}>
          运行抓包审查
        </Button>
        <Button onClick={loadIfs}>刷新网卡</Button>
      </Space>

      {err && <Alert type="warning" showIcon message={err} style={{ marginTop: 10 }} />}

      {findings && (
        <div style={{ marginTop: 12 }}>
          <Space wrap size={8} style={{ marginBottom: 10 }}>
            <Tag color="blue">{findings.total} 个包</Tag>
            <Tag>{findings.file?.duration ?? 0}s</Tag>
            <Tag>发现 {findings.findings?.length || 0} 项</Tag>
            {(findings.top_protocols || []).slice(0, 5).map((p) => (
              <Tag key={p.proto} color="geekblue">
                {p.proto} {(p.pct * 100).toFixed(0)}%
              </Tag>
            ))}
          </Space>
          {findings.findings?.length ? (
            findings.findings.map((f, i) => (
              <div
                key={i}
                style={{
                  borderLeft: `3px solid ${f.level === '高' ? '#ff4d4f' : f.level === '中' ? '#faad14' : '#1677ff'}`,
                  background: f.level === '高' ? 'rgba(255,77,79,0.10)' : 'rgba(127,127,127,0.07)',
                  borderRadius: 8,
                  padding: '9px 12px',
                  marginBottom: 8,
                }}
              >
                <Space size={8} wrap>
                  <Tag color={LEVEL_COLOR[f.level] || 'default'}>{f.level}危</Tag>
                  <Tag>{f.cat}</Tag>
                  <Tag>-{f.deduct} 分</Tag>
                  <b>{f.title}</b>
                </Space>
                <div style={{ fontSize: 12.5, marginTop: 5, lineHeight: 1.7 }}>{f.detail}</div>
                {f.evidence?.length > 0 && (
                  <Typography.Text code style={{ fontSize: 11, display: 'block', marginTop: 4 }}>
                    {f.evidence.join('  ·  ')}
                  </Typography.Text>
                )}
              </div>
            ))
          ) : (
            <Alert type="success" showIcon message="抓包中未发现明显异常" />
          )}
        </div>
      )}
    </Card>
  );
}
