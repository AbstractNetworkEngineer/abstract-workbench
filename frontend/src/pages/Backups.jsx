import React, { useEffect, useState } from 'react';
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  Button,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { api } from '../api';

export default function Backups() {
  const [list, setList] = useState([]);
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const [b, d] = await Promise.all([api.get('/api/backups'), api.get('/api/devices')]);
      setList(b);
      setDevices(d);
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const devName = (id) => devices.find((d) => d.id === id)?.name || `#${id}`;

  const backupNow = async (deviceId) => {
    setBusyId(deviceId);
    try {
      const r = await api.post('/api/backups', { device_id: deviceId, backup_type: 'running' });
      if (r.status === 'success') message.success(`备份成功：${devName(deviceId)}`);
      else message.error(`备份失败：${r.message}`);
      load();
    } catch (e) {
      message.error(e.message);
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (id) => {
    try {
      await api.del(`/api/backups/${id}`);
      message.success('已删除');
      load();
    } catch (e) {
      message.error(e.message);
    }
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    { title: '设备', dataIndex: 'device_id', width: 160, render: devName },
    {
      title: '类型',
      dataIndex: 'backup_type',
      width: 90,
      render: (t) => <Tag>{t}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (s) => (
        <Tag color={s === 'success' ? 'success' : 'error'}>{s === 'success' ? '成功' : '失败'}</Tag>
      ),
    },
    {
      title: '大小',
      dataIndex: 'size',
      width: 90,
      render: (s) => `${(s / 1024).toFixed(1)} KB`,
    },
    { title: '说明', dataIndex: 'message', ellipsis: true },
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 170,
      render: (t) => (t ? new Date(t + 'Z').toLocaleString() : ''),
    },
    {
      title: '操作',
      width: 160,
      render: (_, r) => (
        <Space size={4}>
          {r.status === 'success' && (
            <Button
              size="small"
              icon={<DownloadOutlined />}
              href={`/api/backups/${r.id}/download`}
            >
              下载
            </Button>
          )}
          <Popconfirm title="删除该备份记录？" onConfirm={() => remove(r.id)}>
            <Button size="small" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 12 }} wrap>
        <Select
          style={{ minWidth: 260 }}
          placeholder="选择设备立即备份"
          options={devices.map((d) => ({ value: d.id, label: `${d.name}（${d.protocol}）` }))}
          onChange={(v) => backupNow(v)}
          loading={busyId !== null}
          disabled={busyId !== null}
        />
        <Button icon={<ReloadOutlined />} onClick={load}>
          刷新
        </Button>
        <Typography.Text type="secondary">
          备份文件保存在 data/backups/，可下载对比版本差异
        </Typography.Text>
      </Space>

      <Table
        rowKey="id"
        size="middle"
        loading={loading}
        dataSource={list}
        columns={columns}
        pagination={{ pageSize: 10 }}
      />
    </div>
  );
}
