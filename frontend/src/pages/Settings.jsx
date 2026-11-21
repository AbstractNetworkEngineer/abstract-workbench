import React, { useEffect, useState } from 'react';
import { DeleteOutlined, ImportOutlined, SaveOutlined, UploadOutlined } from '@ant-design/icons';
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  List,
  Select,
  Space,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd';
import { api, upload } from '../api';

export default function Settings() {
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [keySet, setKeySet] = useState(false);
  const [saving, setSaving] = useState(false);
  const [manuals, setManuals] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [encList, setEncList] = useState([]);
  const [aiSt, setAiSt] = useState(null);

  const loadManuals = async () => {
    try {
      setManuals(await api.get('/api/manuals'));
    } catch (e) {
      /* ignore */
    }
  };

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const s = await api.get('/api/settings');
        form.setFieldsValue(s);
        const c = await api.get('/api/ai/config');
        setKeySet(c.key_set);
        setAiSt(c);
        await loadManuals();
        const enc = await api.get('/api/settings/encodings');
        setEncList(enc || []);
      } catch (e) {
        message.error(e.message);
      } finally {
        setLoading(false);
      }
    })();
  }, [form]);

  const save = async () => {
    const v = await form.validateFields();
    setSaving(true);
    try {
      await api.put('/api/settings', v);
      message.success('设置已保存');
      const c = await api.get('/api/ai/config');
      setKeySet(c.key_set);
      setAiSt(c);
    } catch (e) {
      message.error(e.message);
    } finally {
      setSaving(false);
    }
  };

  const doUpload = async (file) => {
    setUploading(true);
    try {
      const r = await upload('/api/manuals/upload', file);
      message.success(`${r.filename}：${r.message}`);
      await loadManuals();
    } catch (e) {
      message.error(e.message);
    } finally {
      setUploading(false);
    }
  };

  const removeManual = async (id) => {
    try {
      await api.del(`/api/manuals/${id}`);
      message.success('已删除');
      await loadManuals();
    } catch (e) {
      message.error(e.message);
    }
  };

  return (
    <Space direction="vertical" size={16} style={{ width: '100%', maxWidth: 860 }}>
      <Card title="🤖 AI API 接入" loading={loading}>
        {aiSt && (
          <Alert
            type={aiSt.ready ? 'success' : 'warning'}
            showIcon
            style={{ marginBottom: 12 }}
            message={
              aiSt.ready
                ? 'AI 接入已就绪'
                : `AI 接入未就绪 — 缺 ${aiSt.missing?.join('、') || '配置'}`
            }
            description={
              <span style={{ fontSize: 12 }}>
                <span style={{ color: aiSt.has_base_url ? '#3fb950' : '#faad14' }}>
                  Base URL {aiSt.has_base_url ? '✓' : '✗'}
                </span>
                {' · '}
                <span style={{ color: aiSt.has_api_key ? '#3fb950' : '#faad14' }}>
                  API Key {aiSt.has_api_key ? '✓' : '✗'}
                </span>
                {' · '}
                <span style={{ color: aiSt.has_model ? '#3fb950' : '#faad14' }}>
                  模型名 {aiSt.has_model ? '✓' : '✗'}
                </span>
                {aiSt.missing?.length > 0 && (
                  <span style={{ marginLeft: 8, color: '#faad14' }}>
                    待补全
                  </span>
                )}
              </span>
            }
          />
        )}
        <Form form={form} layout="vertical">
          <Form.Item
            name="ai_base_url"
            label="Base URL"
            rules={[{ required: true, message: '请填写 API 地址' }]}
          >
            <Input placeholder="https://your-api-endpoint/v1" />
          </Form.Item>
          <Form.Item
            name="ai_api_key"
            label={
              <Space>
                API Key
                {keySet && <Typography.Text type="success">已配置（留空则不修改）</Typography.Text>}
              </Space>
            }
          >
            <Input.Password placeholder={keySet ? '••••••••（已保存，留空保持不变）' : 'sk-...'} />
          </Form.Item>
          <Form.Item
            name="ai_model"
            label="模型名称"
            rules={[{ required: true, message: '请填写模型名' }]}
          >
            <Input placeholder="如 mimo-v2.5-pro / qwen-plus" />
          </Form.Item>
          <Form.Item name="ai_manual" label="补充摘录（可选，随手册一起注入 AI）">
            <Input.TextArea rows={3} placeholder="少量要点、规范约定等；大段手册请直接上传文件" />
          </Form.Item>
          <Form.Item name="env_memory" label="环境记忆（AI 会记住你的网络环境）">
            <Input.TextArea
              rows={3}
              placeholder={'例：\n- 核心交换机 CS6200 在 3 楼机房，VLAN20/200 属于 VRF internet\n- 命名规范：SW-{楼号}-{序号}\n- 变更窗口：工作日 22:00 后'}
            />
          </Form.Item>
          <Form.Item
            name="term_encoding"
            label="终端默认字符编码（设备未单独指定时生效）"
            tooltip="国产设备（华为/H3C/神州数码）常输出 GBK/GB18030，乱码时切到这里。单台设备可在设备管理里单独指定，也可在终端工具栏实时切换。"
          >
            <Select
              showSearch
              optionFilterProp="label"
              placeholder="UTF-8（默认）"
              options={encList.map((e) => ({ value: e.value, label: e.label }))}
            />
          </Form.Item>
          <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={save}>
            保存设置
          </Button>
        </Form>
      </Card>

      <Card
        title={
          <Space>
            <ImportOutlined />
            设备操作手册导入
            <Tag color="blue">AI 上下文自动注入</Tag>
          </Space>
        }
      >
        <Alert
          type="success"
          showIcon
          style={{ marginBottom: 12 }}
          message="支持 PDF / Word(.docx) / TXT / MD，大小与份数不限"
          description="导入后自动提取文字，AI 对话、配置分析、变更生成都会带上手册内容（按厂商方言输出命令）。超大手册会按章节自动节选注入。"
        />
        <Upload.Dragger
          accept=".pdf,.docx,.txt,.md,.log,.cfg,.conf"
          showUploadList={false}
          beforeUpload={(file) => {
            doUpload(file);
            return false; // 阻止默认上传，走自定义请求
          }}
          disabled={uploading}
        >
          <p className="ant-upload-drag-icon">
            <UploadOutlined />
          </p>
          <p className="ant-upload-text">{uploading ? '正在导入…' : '点击或拖拽文件到这里导入'}</p>
          <p className="ant-upload-hint">华为 / 神州数码等设备的配置手册、命令手册均可</p>
        </Upload.Dragger>

        {manuals.length > 0 && (
          <List
            style={{ marginTop: 12 }}
            size="small"
            header={<Typography.Text strong>已导入 {manuals.length} 份手册</Typography.Text>}
            dataSource={manuals}
            renderItem={(m) => (
              <List.Item
                actions={[
                  <Button
                    key="del"
                    size="small"
                    danger
                    icon={<DeleteOutlined />}
                    onClick={() => removeManual(m.id)}
                  >
                    删除
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={
                    <Space>
                      <Tag>{m.kind.toUpperCase()}</Tag>
                      {m.filename}
                    </Space>
                  }
                  description={`提取 ${m.chars.toLocaleString()} 字符${
                    m.created_at ? ' · ' + new Date(m.created_at).toLocaleString() : ''
                  }`}
                />
              </List.Item>
            )}
          />
        )}
      </Card>

      <Card title="🔌 连接方式说明">
        <Typography.Paragraph style={{ marginBottom: 8 }}>
          <strong>SSH</strong>：主流设备默认方式，支持旧算法协商。
        </Typography.Paragraph>
        <Typography.Paragraph style={{ marginBottom: 8 }}>
          <strong>Telnet</strong>：老设备开局用，明文传输，仅限实验/内网环境。
        </Typography.Paragraph>
        <Typography.Paragraph style={{ marginBottom: 8 }}>
          <strong>Serial</strong>：Console 口直连，需本机插着 USB-Console 线，用于设备无 IP 的开局与救砖。
        </Typography.Paragraph>
        <Typography.Paragraph style={{ marginBottom: 8 }}>
          <strong>带外</strong>：管理口地址 + SSH 进入（一期）；Redfish/IPMI 电源级操作规划二期。
        </Typography.Paragraph>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
          <strong>模拟设备</strong>：内置类华为命令行模拟器，零硬件体验完整流程。
        </Typography.Paragraph>
      </Card>
    </Space>
  );
}
