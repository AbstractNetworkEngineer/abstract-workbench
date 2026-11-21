import React, { useEffect, useState } from 'react';
import { PlusOutlined, ThunderboltOutlined } from '@ant-design/icons';
import {
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';

const VENDORS = [
  { value: 'huawei', label: '华为 Huawei' },
  { value: 'h3c', label: '新华三 H3C' },
  { value: 'dcn', label: '神州数码 DCN' },
  { value: 'cisco', label: '思科 Cisco' },
  { value: 'generic', label: '通用' },
];

const PROTOCOLS = [
  { value: 'ssh', label: 'SSH' },
  { value: 'telnet', label: 'Telnet' },
  { value: 'serial', label: 'Serial 串口' },
  { value: 'outband', label: '带外管理口' },
  { value: 'mock', label: '模拟设备（演示）' },
];

const PROTO_COLOR = {
  ssh: 'blue',
  telnet: 'orange',
  serial: 'purple',
  mock: 'cyan',
  outband: 'geekblue',
};

export default function Devices() {
  const nav = useNavigate();
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [testing, setTesting] = useState(false);
  const [encList, setEncList] = useState([]);
  const [form] = Form.useForm();
  const protocol = Form.useWatch('protocol', form) || 'ssh';

  useEffect(() => {
    api
      .get('/api/settings/encodings')
      .then((l) => setEncList(l || []))
      .catch(() => setEncList([]));
  }, []);

  const load = async () => {
    setLoading(true);
    try {
      setList(await api.get('/api/devices'));
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ protocol: 'ssh', vendor: 'huawei', port: 22, baudrate: 9600 });
    setOpen(true);
  };

  const openEdit = (record) => {
    setEditing(record);
    form.setFieldsValue(record);
    setOpen(true);
  };

  const test = async () => {
    const values = await form.validateFields();
    setTesting(true);
    try {
      const r = await api.post('/api/devices/test', values);
      if (r.ok) message.success('连接成功！\n' + (r.version || '').slice(0, 200));
      else message.error(r.message);
    } catch (e) {
      message.error(e.message);
    } finally {
      setTesting(false);
    }
  };

  const submit = async () => {
    const values = await form.validateFields();
    try {
      if (editing) await api.put(`/api/devices/${editing.id}`, values);
      else await api.post('/api/devices', values);
      message.success('已保存');
      setOpen(false);
      load();
    } catch (e) {
      message.error(e.message);
    }
  };

  const remove = async (id) => {
    try {
      await api.del(`/api/devices/${id}`);
      message.success('已删除');
      load();
    } catch (e) {
      message.error(e.message);
    }
  };

  const columns = [
    { title: '名称', dataIndex: 'name', width: 160, render: (v) => <strong>{v}</strong> },
    {
      title: '连接方式',
      dataIndex: 'protocol',
      width: 110,
      render: (p) => <Tag color={PROTO_COLOR[p]}>{p.toUpperCase()}</Tag>,
    },
    {
      title: '地址 / 串口',
      width: 180,
      render: (_, r) => r.protocol === 'serial' ? `${r.serial_port} @${r.baudrate}` : `${r.host}:${r.port}`,
    },
    {
      title: '编码',
      dataIndex: 'encoding',
      width: 90,
      render: (v) => (v ? <Tag color="geekblue">{v}</Tag> : <Typography.Text type="secondary">默认</Typography.Text>),
    },
    { title: '厂商', dataIndex: 'vendor', width: 100 },
    { title: '用户', dataIndex: 'username', width: 100 },
    { title: '备注', dataIndex: 'notes', ellipsis: true },
    {
      title: '操作',
      width: 220,
      render: (_, r) => (
        <Space size={4}>
          <Button size="small" type="primary" onClick={() => nav('/workbench')}>
            工作台
          </Button>
          <Button size="small" onClick={() => openEdit(r)}>
            编辑
          </Button>
          <Popconfirm title="确认删除该设备？" onConfirm={() => remove(r.id)}>
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
          添加设备
        </Button>
        <Typography.Text type="secondary">
          支持 SSH / Telnet / Serial / 带外；无硬件可先用「模拟设备」体验全流程
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

      <Modal
        open={open}
        title={editing ? `编辑设备 ${editing.name}` : '添加设备'}
        width={640}
        onCancel={() => setOpen(false)}
        onOk={submit}
        okText="保存"
        extra={
          <Button icon={<ThunderboltOutlined />} loading={testing} onClick={test}>
            测试连接
          </Button>
        }
      >
        <Form form={form} layout="vertical">
          <Space.Compact block>
            <Form.Item name="name" label="设备名称" rules={[{ required: true }]} style={{ width: '50%', marginRight: 8 }}>
              <Input placeholder="如 CORE-SW-01" />
            </Form.Item>
            <Form.Item name="vendor" label="厂商方言" rules={[{ required: true }]} style={{ width: '50%' }}>
              <Select options={VENDORS} />
            </Form.Item>
          </Space.Compact>

          <Form.Item name="protocol" label="连接方式" rules={[{ required: true }]}>
            <Select options={PROTOCOLS} />
          </Form.Item>

          {protocol !== 'serial' && protocol !== 'mock' && (
            <Space.Compact block>
              <Form.Item name="host" label="IP / 主机名" rules={[{ required: true }]} style={{ width: '70%', marginRight: 8 }}>
                <Input placeholder="192.168.1.10" />
              </Form.Item>
              <Form.Item name="port" label="端口" style={{ width: '30%' }}>
                <InputNumber min={1} max={65535} style={{ width: '100%' }} />
              </Form.Item>
            </Space.Compact>
          )}

          {protocol === 'serial' && (
            <Space.Compact block>
              <Form.Item name="serial_port" label="串口号" rules={[{ required: true }]} style={{ width: '60%', marginRight: 8 }}>
                <Input placeholder="COM3 或 /dev/ttyUSB0" />
              </Form.Item>
              <Form.Item name="baudrate" label="波特率" style={{ width: '40%' }}>
                <Select
                  options={[9600, 19200, 38400, 57600, 115200].map((b) => ({ value: b, label: String(b) }))}
                />
              </Form.Item>
            </Space.Compact>
          )}

          {protocol !== 'mock' && (
            <Space.Compact block>
              <Form.Item name="username" label="用户名" style={{ width: '50%', marginRight: 8 }}>
                <Input placeholder="admin" />
              </Form.Item>
              <Form.Item name="password" label="密码" style={{ width: '50%' }}>
                <Input.Password placeholder="登录密码 / Console 密码" />
              </Form.Item>
            </Space.Compact>
          )}

          <Form.Item
            name="encoding"
            label="终端字符编码"
            tooltip="设备回显的编码。国产设备常为 GBK/GB18030；留空则用全局默认（设置页可改）。"
          >
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="默认（UTF-8）"
              options={encList.map((e) => ({ value: e.value, label: e.label }))}
            />
          </Form.Item>

          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} placeholder="机房位置、用途等" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
