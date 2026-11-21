import React, { useEffect, useState } from 'react';
import { Select, Space, Table, Tag, Typography, message } from 'antd';
import { api } from '../api';

const KINDS = [
  { value: '', label: '全部类型' },
  { value: 'backup', label: '备份' },
  { value: 'change', label: '变更' },
  { value: 'ai', label: 'AI' },
  { value: 'connection', label: '连接' },
  { value: 'system', label: '系统' },
];

const KIND_COLOR = {
  backup: 'blue',
  change: 'purple',
  ai: 'magenta',
  connection: 'cyan',
  system: 'default',
};

export default function Audit() {
  const [list, setList] = useState([]);
  const [kind, setKind] = useState('');
  const [loading, setLoading] = useState(false);

  const load = async (k = kind) => {
    setLoading(true);
    try {
      const q = k ? `?kind=${k}` : '';
      setList(await api.get(`/api/audits${q}`));
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(kind);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind]);

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    {
      title: '类型',
      dataIndex: 'kind',
      width: 90,
      render: (k) => <Tag color={KIND_COLOR[k] || 'default'}>{k}</Tag>,
    },
    { title: '动作', dataIndex: 'action', ellipsis: true },
    { title: '设备', dataIndex: 'device_name', width: 140 },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (s) => (
        <Tag color={s === 'ok' ? 'success' : s === 'failed' ? 'error' : 'processing'}>{s}</Tag>
      ),
    },
    {
      title: '详情',
      dataIndex: 'detail',
      ellipsis: true,
      render: (d) => (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {d}
        </Typography.Text>
      ),
    },
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 170,
      render: (t) => (t ? new Date(t + 'Z').toLocaleString() : ''),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 12 }}>
        <Select style={{ width: 160 }} value={kind} onChange={setKind} options={KINDS} />
        <Typography.Text type="secondary">
          所有备份、AI 调用、变更执行都会留痕，供事后审计
        </Typography.Text>
      </Space>
      <Table
        rowKey="id"
        size="middle"
        loading={loading}
        dataSource={list}
        columns={columns}
        pagination={{ pageSize: 15 }}
      />
    </div>
  );
}
