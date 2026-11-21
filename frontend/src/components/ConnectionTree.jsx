import React from 'react';
import {
  ApiOutlined,
  CloudServerOutlined,
  DesktopOutlined,
  LinkOutlined,
  UsbOutlined,
  WifiOutlined,
} from '@ant-design/icons';
import { Badge, Empty, Spin, Tag, Tree } from 'antd';

const PROTO_META = {
  ssh: { icon: <LinkOutlined />, label: 'SSH' },
  telnet: { icon: <ApiOutlined />, label: 'Telnet' },
  serial: { icon: <UsbOutlined />, label: 'Serial' },
  mock: { icon: <DesktopOutlined />, label: '模拟' },
  outband: { icon: <WifiOutlined />, label: '带外' },
};

const VENDOR_COLOR = {
  huawei: 'red',
  h3c: 'green',
  dcn: 'geekblue',
  cisco: 'blue',
  generic: 'default',
};

export default function ConnectionTree({ devices, loading, onConnect, connectedId }) {
  if (loading) return <Spin style={{ margin: 24 }} />;
  if (!devices.length)
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="暂无设备，先到设备管理添加"
        style={{ margin: '32px 8px' }}
      />
    );

  const groups = {};
  devices.forEach((d) => {
    const p = d.protocol || 'ssh';
    (groups[p] = groups[p] || []).push(d);
  });

  const treeData = Object.entries(groups).map(([proto, list]) => {
    const meta = PROTO_META[proto] || PROTO_META.ssh;
    return {
      key: `proto-${proto}`,
      title: (
        <span style={{ fontWeight: 600 }}>
          {meta.icon} {meta.label}
          <span style={{ opacity: 0.5, marginLeft: 6, fontSize: 12 }}>{list.length}</span>
        </span>
      ),
      selectable: false,
      children: list.map((d) => ({
        key: `dev-${d.id}`,
        isLeaf: true,
        title: (
          <span>
            {connectedId === d.id && <Badge status="processing" style={{ marginRight: 6 }} />}
            {d.name}
            <Tag
              color={VENDOR_COLOR[d.vendor] || 'default'}
              style={{ marginLeft: 6, transform: 'scale(0.85)' }}
            >
              {d.vendor}
            </Tag>
          </span>
        ),
        device: d,
      })),
    };
  });

  return (
    <Tree
      showIcon={false}
      defaultExpandedKeys={treeData.map((t) => t.key)}
      treeData={treeData}
      titleRender={(node) => node.title}
      onSelect={(_, info) => {
        const node = info.node;
        if (node.device) onConnect(node.device);
      }}
    />
  );
}
