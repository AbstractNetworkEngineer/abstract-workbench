import React, { useEffect, useRef, useState } from 'react';
import {
  ApartmentOutlined,
  LoadingOutlined,
  NodeIndexOutlined,
  WarningOutlined,
  WifiOutlined,
} from '@ant-design/icons';
import { Alert, Button, Card, Empty, InputNumber, Select, Space, Table, Tag, Typography, message } from 'antd';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import { useStore } from '../lib/store';
import TopologySvg from '../components/TopologySvg';

export default function Topology() {
  const nav = useNavigate();
  const [devices, setDevices] = useState([]);
  // 拓扑结果持久化
  const [deviceId, setDeviceId] = useStore('topology.deviceId', null);
  const [data, setData] = useStore('topology.data', null);
  const [loading, setLoading] = useState(false);
  // 被动发现（抓包）：真实跑抓包并从中推断邻居，不是跳转链接
  const [passiveData, setPassiveData] = useStore('topology.passive', null);
  const [passiveRunning, setPassiveRunning] = useState(false);
  const [passiveDur, setPassiveDur] = useStore('topology.passiveDur', 20);
  const [pIface, setPIface] = useStore('topology.pIface', '');
  const [ifs, setIfs] = useState([]);

  useEffect(() => {
    api.get('/api/devices').then(setDevices).catch(() => {});
    api
      .get('/api/capture/interfaces')
      .then((r) => {
        const list = r.interfaces || [];
        setIfs(list);
        if (!pIface && list.length) {
          const eth = list.find((x) => /以太网|ethernet|wlan|local/i.test(x.name));
          setPIface((eth || list[0]).device);
        }
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** 被动拓扑发现：抓一段包，从 LLDP/CDP/STP 通告推断邻居。 */
  const runPassive = async () => {
    if (!pIface) {
      message.warning('请先在下方选择要抓包的网卡');
      return;
    }
    setPassiveRunning(true);
    try {
      const s = await api.post('/api/capture/start', {
        iface: pIface,
        bpf_filter: 'lldp or cdp or stp or pvst or rstp',
        max_packets: 50000,
        duration: passiveDur,
        name: 'passive_topo',
      });
      message.success(`抓包中（过滤邻居通告协议），${passiveDur} 秒后分析…`);
      await new Promise((r) => setTimeout(r, (passiveDur + 2) * 1000));
      await api.post('/api/capture/stop', { id: s.id });
      const t = await api.post('/api/capture/topology', { path: s.file });
      setPassiveData(t);
      message.success(`被动发现完成：${t.links?.length || 0} 条链路`);
    } catch (e) {
      message.error(e.message);
    } finally {
      setPassiveRunning(false);
    }
  };

  const discover = async () => {
    if (!deviceId) {
      message.warning('请选择设备');
      return;
    }
    setLoading(true);
    setData(null);
    try {
      const r = await api.post('/api/topology/discover', { device_id: deviceId });
      setData(r);
      const n = r.links?.length || 0;
      if (n) message.success(`发现 ${n} 条邻居链路`);
      else message.warning('未发现邻居，请确认设备已启用 LLDP/CDP');
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card
        size="small"
        title={
          <span>
            <ApartmentOutlined /> 拓扑发现 — 从 LLDP / CDP / ARP 推断网络拓扑
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
          <Button type="primary" loading={loading} icon={loading ? <LoadingOutlined /> : <NodeIndexOutlined />} onClick={discover}>
            发现拓扑
          </Button>
          <Button loading={passiveRunning} icon={<WifiOutlined />} onClick={runPassive}>
            被动发现（抓包 {passiveDur}s）
          </Button>
          <Button onClick={() => nav('/capture')}>
            完整抓包分析
          </Button>
          <Typography.Text type="secondary">
            自动采集 邻居发现 / ARP / 接口地址，推断出一跳邻居并画图
          </Typography.Text>
        </Space>
      </Card>

      {data && (
        <>
          {data.warnings?.length > 0 && (
            <Alert
              type="warning"
              showIcon
              icon={<WarningOutlined />}
              message={`有 ${data.warnings.length} 条提示`}
              description={
                <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12 }}>
                  {data.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              }
            />
          )}

          <Card
            size="small"
            title={
              <Space>
                网络拓扑图
                <Tag color="blue">{data.links?.length || 0} 条链路</Tag>
                <Tag>{(data.nodes?.length || 1) - 1} 台邻居</Tag>
                {data.via === 'live-session' && <Tag color="success">活动会话采集</Tag>}
              </Space>
            }
          >
            {data.links?.length ? (
              <TopologySvg data={data} />
            ) : (
              <Empty description="未发现邻居链路" />
            )}
          </Card>

          {data.links?.length > 0 && (
            <Card size="small" title="邻居明细">
              <Table
                size="small"
                rowKey={(r) => r.to + r.local_if}
                pagination={false}
                dataSource={data.links}
                columns={[
                  {
                    title: '本机接口',
                    dataIndex: 'local_if',
                    render: (v) => <Typography.Text code>{v}</Typography.Text>,
                  },
                  {
                    title: '对端设备',
                    dataIndex: 'to',
                    render: (v) => <span style={{ fontWeight: 600 }}>{v}</span>,
                  },
                  {
                    title: '对端接口',
                    dataIndex: 'remote_if',
                    render: (v) => (v ? <Typography.Text code>{v}</Typography.Text> : '—'),
                  },
                  {
                    title: '发现协议',
                    dataIndex: 'proto',
                    width: 110,
                    render: (v) => <Tag color={v === 'cdp' ? 'orange' : 'geekblue'}>{v?.toUpperCase()}</Tag>,
                  },
                ]}
              />
            </Card>
          )}
        </>
      )}

      {/* 被动拓扑发现（抓包）：不登设备，看线上的邻居通告 */}
      <Card
        size="small"
        title={
          <Space>
            <WifiOutlined /> 被动拓扑发现（抓包）
            {passiveData && <Tag color="blue">{passiveData.links?.length || 0} 条链路</Tag>}
          </Space>
        }
      >
        <Space wrap style={{ marginBottom: 10 }}>
          <Select
            style={{ minWidth: 200 }}
            placeholder={ifs.length ? '选择要抓包的网卡' : '（暂无网卡）'}
            value={pIface || undefined}
            onChange={setPIface}
            options={ifs.map((x) => ({ value: x.device, label: x.name }))}
            showSearch
            optionFilterProp="label"
            notFoundContent={ifs.length ? '无匹配' : '未检测到网卡'}
          />
          <InputNumber
            addonBefore="时长"
            addonAfter="秒"
            min={5}
            max={180}
            value={passiveDur}
            onChange={(v) => setPassiveDur(v || 20)}
            style={{ width: 140 }}
          />
          <Button loading={passiveRunning} icon={<WifiOutlined />} onClick={runPassive}>
            抓包并推断邻居
          </Button>
        </Space>
        {passiveData?.warnings?.length > 0 && (
          <Alert type="warning" showIcon message={passiveData.warnings.join('；')} style={{ marginBottom: 10 }} />
        )}
        {passiveData?.links?.length > 0 ? (
          <TopologySvg data={passiveData} height={400} />
        ) : (
          passiveData && <Empty description="抓包中未见 LLDP/CDP 通告，可换网卡或延长时长" />
        )}
      </Card>

      {!data && !loading && !passiveData && (
        <Card size="small">
          <Empty description="选择一台设备点击「发现拓扑」，即可推断出它的一跳邻居并生成拓扑图" />
        </Card>
      )}
    </Space>
  );
}
