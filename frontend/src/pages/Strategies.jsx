import React, { useEffect, useState } from 'react';
import { PlusOutlined } from '@ant-design/icons';
import {
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { api } from '../api';

export default function Strategies() {
  const [list, setList] = useState([]);
  const [devices, setDevices] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form] = Form.useForm();

  const load = async () => {
    try {
      const [s, d] = await Promise.all([api.get('/api/strategies'), api.get('/api/devices')]);
      setList(s);
      setDevices(d);
    } catch (e) {
      message.error(e.message);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ backup_type: 'running', interval_hours: 24, enabled: true, device_ids: [] });
    setOpen(true);
  };

  const openEdit = (r) => {
    setEditing(r);
    form.setFieldsValue({
      ...r,
      device_ids: JSON.parse(r.device_ids || '[]'),
    });
    setOpen(true);
  };

  const submit = async () => {
    const v = await form.validateFields();
    try {
      if (editing) await api.put(`/api/strategies/${editing.id}`, v);
      else await api.post('/api/strategies', v);
      message.success('已保存');
      setOpen(false);
      load();
    } catch (e) {
      message.error(e.message);
    }
  };

  const remove = async (id) => {
    try {
      await api.del(`/api/strategies/${id}`);
      message.success('已删除');
      load();
    } catch (e) {
      message.error(e.message);
    }
  };

  const columns = [
    { title: '策略名', dataIndex: 'name', render: (v) => <strong>{v}</strong> },
    {
      title: '设备',
      dataIndex: 'device_ids',
      render: (s) => {
        const ids = JSON.parse(s || '[]');
        return ids.map((id) => devices.find((d) => d.id === id)?.name || `#${id}`).join(', ') || '—';
      },
    },
    { title: '类型', dataIndex: 'backup_type', width: 90, render: (t) => <Tag>{t}</Tag> },
    { title: '周期', dataIndex: 'interval_hours', width: 100, render: (h) => `每 ${h} 小时` },
    {
      title: '状态',
      dataIndex: 'enabled',
      width: 90,
      render: (e) => <Tag color={e ? 'success' : 'default'}>{e ? '启用' : '停用'}</Tag>,
    },
    {
      title: '下次执行',
      dataIndex: 'next_run',
      width: 170,
      render: (t) => (t ? new Date(t + 'Z').toLocaleString() : '—'),
    },
    {
      title: '操作',
      width: 150,
      render: (_, r) => (
        <Space size={4}>
          <Button size="small" onClick={() => openEdit(r)}>
            编辑
          </Button>
          <Popconfirm title="删除策略？" onConfirm={() => remove(r.id)}>
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
      <Space style={{ marginBottom: 12 }}>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          新建策略
        </Button>
        <Typography.Text type="secondary">
          调度器每 30 秒检查一次到期任务，自动通过对应连接方式拉取配置
        </Typography.Text>
      </Space>

      <Table rowKey="id" size="middle" dataSource={list} columns={columns} pagination={false} />

      <Modal
        open={open}
        title={editing ? '编辑策略' : '新建策略'}
        onCancel={() => setOpen(false)}
        onOk={submit}
        okText="保存"
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="策略名称" rules={[{ required: true }]}>
            <Input placeholder="如 核心交换机每日备份" />
          </Form.Item>
          <Form.Item name="device_ids" label="目标设备" rules={[{ required: true, type: 'array', min: 1 }]}>
            <Select
              mode="multiple"
              placeholder="选择多台设备"
              options={devices.map((d) => ({ value: d.id, label: d.name }))}
            />
          </Form.Item>
          <Space.Compact block>
            <Form.Item name="backup_type" label="备份类型" style={{ width: '40%', marginRight: 8 }}>
              <Select
                options={[
                  { value: 'running', label: 'running-config' },
                  { value: 'version', label: '版本信息' },
                ]}
              />
            </Form.Item>
            <Form.Item name="interval_hours" label="间隔（小时）" style={{ width: '30%', marginRight: 8 }}>
              <InputNumber min={1} max={720} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="enabled" label="启用" valuePropName="checked" style={{ width: '30%' }}>
              <Switch />
            </Form.Item>
          </Space.Compact>
        </Form>
      </Modal>
    </div>
  );
}
