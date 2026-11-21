import React, { useEffect, useState } from 'react';
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
  SaveOutlined,
} from '@ant-design/icons';
import {
  Button,
  Input,
  Modal,
  Popconfirm,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import { api } from '../api';

const EMPTY_FORM = { label: '', cat: '自定义', cmd_display: '', cmd_show: '', enabled: true, sort: 100 };

/**
 * 检测项管理：内置项与自定义项同表，可增删改、启用停用、恢复内置。
 * 自定义项 = 用户自己填展示名 + 查看命令（华为/H3C 一条、DCN/Cisco 一条）。
 */
export default function DetectItemModal({ open, onClose, onChanged }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);

  const load = async () => {
    setLoading(true);
    try {
      const list = await api.get('/api/detect/items');
      setItems(list);
    } catch (e) {
      message.error('加载检测项失败: ' + e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) {
      load();
      setEditingId(null);
      setForm(EMPTY_FORM);
    }
  }, [open]);

  const submit = async () => {
    if (!form.label.trim()) {
      message.warning('请填写检测项名称');
      return;
    }
    if (!form.cmd_display.trim() && !form.cmd_show.trim()) {
      message.warning('至少填写一条查看命令');
      return;
    }
    try {
      if (editingId) {
        await api.put(`/api/detect/items/${editingId}`, form);
        message.success('已保存');
      } else {
        await api.post('/api/detect/items', form);
        message.success('已添加');
      }
      setEditingId(null);
      setForm(EMPTY_FORM);
      await load();
      onChanged?.();
    } catch (e) {
      message.error(e.message);
    }
  };

  const toggleEnabled = async (row, checked) => {
    try {
      await api.put(`/api/detect/items/${row.id}`, {
        label: row.label,
        cat: row.cat,
        cmd_display: row.cmd_display,
        cmd_show: row.cmd_show,
        enabled: checked,
        sort: row.sort,
      });
      await load();
      onChanged?.();
    } catch (e) {
      message.error(e.message);
    }
  };

  const remove = async (id) => {
    try {
      await api.del(`/api/detect/items/${id}`);
      message.success('已删除');
      await load();
      onChanged?.();
    } catch (e) {
      message.error(e.message);
    }
  };

  const resetBuiltin = async () => {
    try {
      const r = await api.post('/api/detect/items/reset', {});
      message.success(`已恢复内置检测项${r.restored ? `（补齐 ${r.restored} 项）` : ''}`);
      await load();
      onChanged?.();
    } catch (e) {
      message.error(e.message);
    }
  };

  const columns = [
    {
      title: '分类',
      dataIndex: 'cat',
      width: 92,
      render: (v) => <Tag>{v}</Tag>,
    },
    {
      title: '名称',
      dataIndex: 'label',
      width: 120,
      render: (v, r) => (
        <Space size={4}>
          <span>{v}</span>
          {r.builtin ? <Tag color="blue">内置</Tag> : <Tag color="purple">自定义</Tag>}
        </Space>
      ),
    },
    {
      title: '华为 / H3C 命令',
      dataIndex: 'cmd_display',
      ellipsis: true,
      render: (v) => (v ? <Typography.Text code>{v}</Typography.Text> : <Typography.Text type="secondary">—</Typography.Text>),
    },
    {
      title: 'DCN / Cisco 命令',
      dataIndex: 'cmd_show',
      ellipsis: true,
      render: (v) => (v ? <Typography.Text code>{v}</Typography.Text> : <Typography.Text type="secondary">—</Typography.Text>),
    },
    {
      title: '启用',
      dataIndex: 'enabled',
      width: 70,
      render: (v, r) => <Switch size="small" checked={v} onChange={(c) => toggleEnabled(r, c)} />,
    },
    {
      title: '操作',
      width: 110,
      render: (_, r) => (
        <Space size={2}>
          <Button
            size="small"
            type="text"
            icon={<EditOutlined />}
            onClick={() => {
              setEditingId(r.id);
              setForm({
                label: r.label,
                cat: r.cat,
                cmd_display: r.cmd_display,
                cmd_show: r.cmd_show,
                enabled: r.enabled,
                sort: r.sort,
              });
            }}
          />
          <Popconfirm title="删除该检测项？" onConfirm={() => remove(r.id)}>
            <Button size="small" type="text" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Modal
      open={open}
      title="检测项管理 · 自定义协议与查看命令"
      width={860}
      onCancel={onClose}
      footer={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={resetBuiltin}>恢复内置</Button>
          <Button type="primary" onClick={onClose}>完成</Button>
        </Space>
      }
    >
      {/* 新增 / 编辑 行 */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '100px 120px 1fr 1fr auto',
          gap: 8,
          marginBottom: 10,
          padding: 10,
          border: '1px solid rgba(47,129,247,0.28)',
          borderRadius: 8,
          background: 'rgba(47,129,247,0.06)',
        }}
      >
        <Input
          size="small"
          placeholder="分类"
          value={form.cat}
          onChange={(e) => setForm({ ...form, cat: e.target.value })}
        />
        <Input
          size="small"
          placeholder="名称*"
          value={form.label}
          onChange={(e) => setForm({ ...form, label: e.target.value })}
        />
        <Input
          size="small"
          placeholder="华为/H3C 命令，如 display version"
          value={form.cmd_display}
          onChange={(e) => setForm({ ...form, cmd_display: e.target.value })}
        />
        <Input
          size="small"
          placeholder="DCN/Cisco 命令，如 show version"
          value={form.cmd_show}
          onChange={(e) => setForm({ ...form, cmd_show: e.target.value })}
          onPressEnter={submit}
        />
        <Space>
          <Button size="small" type="primary" icon={editingId ? <SaveOutlined /> : <PlusOutlined />} onClick={submit}>
            {editingId ? '保存' : '添加'}
          </Button>
          {editingId && (
            <Button
              size="small"
              onClick={() => {
                setEditingId(null);
                setForm(EMPTY_FORM);
              }}
            >
              取消
            </Button>
          )}
        </Space>
      </div>

      <Table
        size="small"
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={items}
        pagination={false}
        scroll={{ y: 320 }}
      />
    </Modal>
  );
}
