import React, { useEffect, useMemo, useState } from 'react';
import {
  ApiOutlined,
  DeleteOutlined,
  FolderOpenOutlined,
  LoadingOutlined,
  PlayCircleOutlined,
  QuestionCircleOutlined,
  ReloadOutlined,
  StopOutlined,
 WifiOutlined,
} from '@ant-design/icons';
import {
  Alert,
  Button,
  Card,
  Collapse,
  Drawer,
  Empty,
  Input,
  InputNumber,
  Progress,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { api } from '../api';
import { useStore } from '../lib/store';
import TopologySvg from '../components/TopologySvg';

function fmtBytes(n) {
  if (!n && n !== 0) return '—';
  const u = ['B', 'KB', 'MB', 'GB'];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${u[i]}`;
}

/** 协议分层（缩进 + 占比条） */
function ProtoTree({ rows }) {
  const max = Math.max(1, ...rows.map((r) => r.frames));
  return (
    <div className="proto-tree">
      {rows.map((r, i) => (
        <div key={i} className="proto-row" style={{ paddingLeft: r.depth * 18 }}>
          <span className="proto-name">{r.proto}</span>
          <div className="proto-bar-wrap">
            <div
              className="proto-bar"
              style={{ width: `${(r.frames / max) * 100}%`, opacity: 1 - r.depth * 0.18 }}
            />
          </div>
          <span className="proto-num">{r.frames} 帧</span>
          <span className="proto-num">{fmtBytes(r.bytes)}</span>
        </div>
      ))}
    </div>
  );
}

export default function Capture() {
  // 抓包结果/设置持久化：换模块回来分析结果还在
  const [iface, setIface] = useStore('capture.iface', '');
  const [filter, setFilter] = useStore('capture.filter', '');
  const [duration, setDuration] = useStore('capture.duration', 30);
  const [maxPkts, setMaxPkts] = useStore('capture.maxPkts', 20000);
  const [session, setSession] = useStore('capture.session', null);
  const [files, setFiles] = useStore('capture.files', []);
  const [analysis, setAnalysis] = useStore('capture.analysis', null);
  const [topo, setTopo] = useStore('capture.topo', null);
  const [st, setSt] = useState(null);
  const [ifs, setIfs] = useState([]);
  const [busy, setBusy] = useState(false);
  const [analyzing, setAnalyzing] = useState('');
  const [loadErr, setLoadErr] = useState('');
  const [helpOpen, setHelpOpen] = useState(false);

  const loadAll = async () => {
    setLoadErr('');
    // 三个请求各自独立：之前用 Promise.all，任何一个失败就全都不更新 ——
    // 网卡下拉框空、文件列表空就是这么来的
    const [rs, ri, rf] = await Promise.allSettled([
      api.get('/api/capture/status'),
      api.get('/api/capture/interfaces'),
      api.get('/api/capture/files'),
    ]);

    if (rs.status === 'fulfilled') setSt(rs.value);
    if (rf.status === 'fulfilled') setFiles(rf.value.files || []);

    if (ri.status === 'fulfilled') {
      const list = ri.value.interfaces || [];
      setIfs(list);
      setLoadErr(list.length ? '' : '未检测到可抓包网卡（需要 Npcap 驱动，抓包一般要管理员权限）');
      if (!iface && list.length) {
        const eth = list.find((x) => /以太网|ethernet|wlan|local/i.test(x.name));
        setIface((eth || list[0]).device);
      }
    } else {
      setIfs([]);
      setLoadErr(`网卡列表加载失败：${ri.reason?.message || '未知错误'}`);
    }
    if (rs.status !== 'fulfilled' && ri.status !== 'fulfilled') {
      setLoadErr('Wireshark 接入检测失败，请确认已安装 Wireshark（含 Npcap）');
    }
  };

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 轮询当前会话状态（大小/是否跑完）
  useEffect(() => {
    if (!session?.id) return undefined;
    const t = setInterval(async () => {
      try {
        const r = await api.get('/api/capture/sessions');
        const cur = (r.sessions || []).find((x) => x.id === session.id);
        if (cur) setSession(cur);
      } catch {
        /* ignore */
      }
    }, 3000);
    return () => clearInterval(t);
  }, [session?.id]);

  const start = async () => {
    if (!iface) {
      message.warning('请选择网卡');
      return;
    }
    setBusy(true);
    try {
      const s = await api.post('/api/capture/start', {
        iface,
        bpf_filter: filter,
        max_packets: maxPkts,
        duration,
        name: 'capture',
      });
      setSession(s);
      message.success(`抓包已启动：${s.filename}`);
      setTimeout(() => {
        api.get('/api/capture/files').then((r) => setFiles(r.files || [])).catch(() => {});
      }, (duration + 2) * 1000);
    } catch (e) {
      message.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    if (!session?.id) return;
    setBusy(true);
    try {
      const s = await api.post('/api/capture/stop', { id: session.id });
      setSession(s);
      message.success(`抓包已停止，文件 ${fmtBytes(s.file_size)}`);
      const r = await api.get('/api/capture/files');
      setFiles(r.files || []);
    } catch (e) {
      message.error(e.message);
    } finally {
      setBusy(false);
    }
  };

  const analyze = async (path) => {
    setAnalyzing(path);
    setAnalysis(null);
    setTopo(null);
    try {
      const r = await api.post('/api/capture/analyze', { path });
      setAnalysis(r);
      message.success(`分析完成：${r.file?.packets ?? 0} 个包`);
    } catch (e) {
      message.error(e.message);
    } finally {
      setAnalyzing('');
    }
  };

  const passiveTopo = async (path) => {
    setAnalyzing(path);
    try {
      const r = await api.post('/api/capture/topology', { path });
      setTopo(r);
      message.success(`被动拓扑：${r.links?.length || 0} 条链路`);
    } catch (e) {
      message.error(e.message);
    } finally {
      setAnalyzing('');
    }
  };

  const openGui = async (path) => {
    try {
      await api.post('/api/capture/open', { path });
      message.success('已唤起 Wireshark GUI');
    } catch (e) {
      message.error(e.message);
    }
  };

  const fileColumns = [
    { title: '文件名', dataIndex: 'filename', ellipsis: true },
    { title: '大小', dataIndex: 'size', width: 100, render: fmtBytes },
    {
      title: '时间',
      dataIndex: 'mtime',
      width: 160,
      render: (v) => new Date(v * 1000).toLocaleString('zh-CN', { hour12: false }),
    },
    {
      title: '操作',
      width: 300,
      render: (_, r) => (
        <Space size={4}>
          <Button size="small" type="primary" loading={analyzing === r.path} onClick={() => analyze(r.path)}>
            分析
          </Button>
          <Button size="small" loading={analyzing === r.path} onClick={() => passiveTopo(r.path)}>
            被动拓扑
          </Button>
          <Button size="small" icon={<FolderOpenOutlined />} onClick={() => openGui(r.path)}>
            Wireshark
          </Button>
        </Space>
      ),
    },
  ];

  const ready = st?.ready;

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card
        size="small"
        title={
          <span>
            <WifiOutlined /> 抓包分析 — Wireshark 接入
          </span>
        }
        extra={
          <Space>
            {st && (
              <Tag color={st.ready ? 'success' : 'error'}>
                {st.ready ? `tshark ${st.version || ''}` : 'Wireshark 未就绪'}
              </Tag>
            )}
            <Button size="small" icon={<QuestionCircleOutlined />} onClick={() => setHelpOpen(true)}>
              使用说明
            </Button>
          </Space>
        }
      >
        {!ready && (
          <Alert
            type="warning"
            showIcon
            message={st?.hint || '未检测到 Wireshark'}
            description="需要安装 Wireshark（含 Npcap 抓包驱动）。本机已有安装时，可设置环境变量 WIRESHARK_HOME 指向其目录。"
          />
        )}
        {loadErr && (
          <Alert type="error" showIcon message={loadErr} style={{ marginTop: 12 }} />
        )}
        <Space wrap style={{ marginTop: ready && !loadErr ? 0 : 12 }}>
          <Select
            style={{ minWidth: 260 }}
            placeholder={ifs.length ? '选择网卡' : '（暂无可抓包网卡）'}
            value={iface || undefined}
            onChange={setIface}
            options={ifs.map((x) => ({ value: x.device, label: `${x.name}` }))}
            showSearch
            optionFilterProp="label"
            notFoundContent={ifs.length ? '无匹配' : '未检测到网卡'}
          />
          <Button icon={<ReloadOutlined />} onClick={loadAll}>
            刷新网卡
          </Button>
          <Input
            style={{ width: 240 }}
            placeholder="抓包过滤器，如 host 172.16.10.1"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            allowClear
          />
          <InputNumber
            addonBefore="时长"
            addonAfter="秒"
            min={3}
            max={600}
            value={duration}
            onChange={(v) => setDuration(v || 30)}
            style={{ width: 150 }}
          />
          <InputNumber
            addonBefore="包数"
            min={100}
            max={1000000}
            value={maxPkts}
            onChange={(v) => setMaxPkts(v || 20000)}
            style={{ width: 160 }}
          />
          {!session || session.status !== 'running' ? (
            <Button type="primary" loading={busy} disabled={!ready} icon={<PlayCircleOutlined />} onClick={start}>
              开始抓包
            </Button>
          ) : (
            <Button danger loading={busy} icon={<StopOutlined />} onClick={stop}>
              停止抓包
            </Button>
          )}
        </Space>

        {session && (
          <div style={{ marginTop: 14, display: 'flex', gap: 24, alignItems: 'center' }}>
            <Statistic
              title="状态"
              value={session.status === 'running' ? '抓包中' : '已停止'}
              valueStyle={{ fontSize: 16, color: session.status === 'running' ? '#3fb950' : '#8b949e' }}
            />
            <Statistic title="网卡" value={ifs.find((x) => x.device === session.iface)?.name || session.iface} valueStyle={{ fontSize: 14 }} />
            <Statistic title="文件" value={session.filename} valueStyle={{ fontSize: 13 }} />
            <Statistic title="大小" value={fmtBytes(session.file_size || 0)} valueStyle={{ fontSize: 16 }} />
            {session.status === 'running' && (
              <Progress
                type="circle"
                size={56}
                percent={Math.min(100, Math.round(((session.elapsed || 0) / (duration || 1)) * 100))}
              />
            )}
          </div>
        )}
      </Card>

      <Card size="small" title="抓包文件">
        <Table
          size="small"
          rowKey="path"
          columns={fileColumns}
          dataSource={files}
          pagination={{ pageSize: 8 }}
          locale={{ emptyText: <Empty description="还没有抓包文件，先开始一次抓包" /> }}
        />
      </Card>

      {analysis && (
        <>
          <Card
            size="small"
            title={
              <Space>
                <ApiOutlined /> 协议分析 · {analysis.file?.file}
                <Tag color="blue">{analysis.file?.packets ?? 0} 包</Tag>
                <Tag>{analysis.file?.duration ?? 0}s</Tag>
                <Tag>{fmtBytes(analysis.file?.size)}</Tag>
              </Space>
            }
          >
            {analysis.protocols?.length > 0 ? (
              <ProtoTree rows={analysis.protocols} />
            ) : (
              <Empty description="无协议数据" />
            )}
          </Card>

          <Card size="small" title={`IP 会话 · ${analysis.conversations?.length || 0} 条`}>
            <Table
              size="small"
              rowKey="pair"
              pagination={false}
              dataSource={analysis.conversations}
              columns={[
                { title: '通信对', dataIndex: 'pair', render: (v) => <Typography.Text code>{v}</Typography.Text> },
                { title: '帧数', dataIndex: 'frames', width: 100 },
                { title: '字节', dataIndex: 'bytes', width: 110, render: fmtBytes },
                { title: '时长(s)', dataIndex: 'duration', width: 100 },
              ]}
              locale={{ emptyText: '无会话' }}
            />
          </Card>

          <Card size="small" title={`IP 端点 · ${analysis.endpoints?.length || 0} 个`}>
            <Table
              size="small"
              rowKey="address"
              pagination={false}
              dataSource={analysis.endpoints}
              columns={[
                { title: '地址', dataIndex: 'address', render: (v) => <Typography.Text code>{v}</Typography.Text> },
                { title: '帧数', dataIndex: 'frames', width: 100 },
                { title: '字节', dataIndex: 'bytes', width: 110, render: fmtBytes },
              ]}
              locale={{ emptyText: '无端点' }}
            />
          </Card>

          {analysis.expert?.length > 0 && (
            <Card size="small" title="专家信息">
              {analysis.expert.map((e, i) => (
                <div key={i} style={{ padding: '3px 0', fontSize: 12.5 }}>
                  <Tag
                    color={
                      /error/i.test(e.level) ? 'error' : /warn/i.test(e.level) ? 'warning' : 'default'
                    }
                  >
                    {e.level}
                  </Tag>
                  <Typography.Text code>{e.raw}</Typography.Text>
                </div>
              ))}
            </Card>
          )}
        </>
      )}

      {topo && (
        <Card
          size="small"
          title={
            <Space>
              被动拓扑发现 · {topo.file}
              <Tag color="blue">{topo.links?.length || 0} 条链路</Tag>
            </Space>
          }
        >
          {topo.warnings?.length > 0 && (
            <Alert type="warning" showIcon message={topo.warnings.join('；')} style={{ marginBottom: 12 }} />
          )}
          {topo.links?.length ? (
            <TopologySvg data={topo} height={440} />
          ) : (
            <Empty description="抓包中未见 LLDP/CDP 通告" />
          )}
          {topo.stp_roots?.length > 0 && (
            <div style={{ marginTop: 12, fontSize: 12, opacity: 0.85 }}>
              STP 根桥：
              {topo.stp_roots.map((r, i) => (
                <Tag key={i}>{r.root || r.bridge_mac}</Tag>
              ))}
            </div>
          )}
        </Card>
      )}

      <Drawer
        title="抓包分析 · 使用说明"
        placement="right"
        width={520}
        open={helpOpen}
        onClose={() => setHelpOpen(false)}
      >
        <Typography.Paragraph>
          本模块通过 <b>Wireshark 的命令行内核</b>（tshark / dumpcap）抓包与分析，
          Wireshark GUI 仅用于「一键深挖」。
        </Typography.Paragraph>
        <Typography.Title level={5}>1. 选择网卡</Typography.Title>
        <Typography.Paragraph type="secondary">
          列表来自 <code>dumpcap -D</code>。抓<b>本地机器发出/收到</b>的流量选「以太网 / WLAN」；
          抓本机进程间流量选「Loopback」；VirtualBox / Mihomo 是虚拟网卡。
          过滤器为空 = 全抓，填写 <code>host 172.16.10.1</code> 只抓该设备。
        </Typography.Paragraph>
        <Typography.Title level={5}>2. 开始抓包</Typography.Title>
        <Typography.Paragraph type="secondary">
          时长与包数是<b>双保险上限</b>，先到先停；也可手动「停止抓包」。
          文件落盘 <code>data/captures/*.pcapng</code>。
        </Typography.Paragraph>
        <Typography.Title level={5}>3. 分析</Typography.Title>
        <ul style={{ paddingLeft: 18, fontSize: 13, lineHeight: 1.9 }}>
          <li><b>协议分层</b>：io,phs，按协议树展示帧数/字节占比</li>
          <li><b>IP 会话</b>：谁跟谁在说话，多少帧、持续多久</li>
          <li><b>IP 端点</b>：每个地址的收发量</li>
          <li><b>专家信息</b>：Wireshark 自带的异常/告警/重传标记</li>
        </ul>
        <Typography.Title level={5}>4. 被动拓扑</Typography.Title>
        <Typography.Paragraph type="secondary">
          从抓包里的 <code>LLDP</code> / <code>CDP</code> / <code>STP</code> 通告推断邻居，
          <b>不登设备</b>。需要抓到这些协议才行：端口镜像、或接在承载邻居通告的链路上。
        </Typography.Paragraph>
        <Typography.Title level={5}>5. Wireshark GUI</Typography.Title>
        <Typography.Paragraph type="secondary">
          分析只能给汇总统计。要看<b>逐包细节、跟随流、协议字段</b>，
          点「Wireshark」把文件交给本机 Wireshark 打开。
        </Typography.Paragraph>
        <Typography.Title level={5}>常见问题</Typography.Title>
        <ul style={{ paddingLeft: 18, fontSize: 13, lineHeight: 1.9 }}>
          <li><b>网卡列表为空</b>：装 Npcap；或以管理员运行本软件</li>
          <li><b>开始抓包失败</b>：抓包驱动通常要管理员权限</li>
          <li><b>抓到 0 个包</b>：过滤器太严，或网卡选错（试试 Loopback）</li>
          <li><b>被动拓扑无邻居</b>：链路上没有 LLDP/CDP 通告，或未镜像</li>
        </ul>
      </Drawer>
    </Space>
  );
}
