import React, { useEffect, useState } from 'react';
import { DiffOutlined, RobotOutlined } from '@ant-design/icons';
import { Button, Card, Modal, Space, Table, Tag, Typography, message } from 'antd';
import { api } from '../api';

export default function Drift() {
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(false);
  const [diffOpen, setDiffOpen] = useState(null); // {device_name, diff}
  const [explaining, setExplaining] = useState(false);
  const [report, setReport] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      setList(await api.get('/api/drift'));
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const showDiff = async (row) => {
    try {
      const d = await api.get(`/api/drift/${row.device_id}/diff`);
      setDiffOpen(d);
      setReport('');
    } catch (e) {
      message.error(e.message);
    }
  };

  const explain = async () => {
    if (!diffOpen) return;
    setExplaining(true);
    try {
      const r = await api.post(`/api/drift/${diffOpen.device_id}/explain`, {});
      setReport(r.report);
    } catch (e) {
      message.error(e.message);
    } finally {
      setExplaining(false);
    }
  };

  const columns = [
    { title: '设备', dataIndex: 'device_name', render: (v) => <strong>{v}</strong> },
    {
      title: '漂移状态',
      dataIndex: 'state',
      width: 120,
      render: (s) =>
        s === 'changed' ? <Tag color="error">已漂移</Tag> : s === 'same' ? <Tag color="success">一致</Tag> : <Tag>数据不足</Tag>,
    },
    { title: '差异', dataIndex: 'message' },
    {
      title: '操作',
      width: 260,
      render: (_, r) =>
        r.changed ? (
          <Space>
            <Button size="small" icon={<DiffOutlined />} onClick={() => showDiff(r)}>
              查看差异
            </Button>
            <Button size="small" type="primary" icon={<RobotOutlined />} onClick={async () => { await showDiff(r); explain(); }}>
              AI 解读
            </Button>
          </Space>
        ) : (
          <Typography.Text type="secondary">—</Typography.Text>
        ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card size="small">
        <Table rowKey="device_id" size="middle" loading={loading} dataSource={list} columns={columns} pagination={false} />
      </Card>

      <Modal
        open={!!diffOpen}
        title={`配置差异 — ${diffOpen?.device_name || ''}`}
        width={860}
        onCancel={() => setDiffOpen(null)}
        footer={
          <>
            <Button onClick={() => setDiffOpen(null)}>关闭</Button>
            <Button type="primary" icon={<RobotOutlined />} loading={explaining} onClick={explain}>
              AI 解读风险
            </Button>
          </>
        }
      >
        {report && (
          <pre className="report-text" style={{ maxHeight: 260, overflow: 'auto', marginBottom: 12, background: 'rgba(47,129,247,0.06)', padding: 10, borderRadius: 8 }}>
            {report}
          </pre>
        )}
        <pre style={{ maxHeight: 420, overflow: 'auto', fontSize: 12, background: 'rgba(127,127,127,0.08)', padding: 10, borderRadius: 8 }}>
          {diffOpen?.diff}
        </pre>
      </Modal>
    </Space>
  );
}
