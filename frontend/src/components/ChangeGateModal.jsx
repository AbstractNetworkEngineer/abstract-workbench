import React, { useEffect, useState } from 'react';
import { ExclamationCircleOutlined, SaveOutlined } from '@ant-design/icons';
import { Alert, Button, Input, Modal, Space, Tag, Typography, message } from 'antd';
import { api } from '../api';

const CHECK_BADGE = {
  verified: { color: 'success', label: '手册已验证' },
  partial: { color: 'warning', label: '部分匹配' },
  unverified: { color: 'error', label: '手册未找到' },
};

/**
 * 配置写入：AI 生成的命令必须经人工确认才下发设备。
 * preview = { device: {id,name,vendor}, commands: [], command_checks: [], risk, analysis }
 */
export default function ChangeGateModal({ preview, onClose }) {
  const [cmds, setCmds] = useState('');
  const [note, setNote] = useState('');
  const [executing, setExecuting] = useState(false);
  const [results, setResults] = useState(null);

  useEffect(() => {
    if (preview) {
      setCmds((preview.commands || []).join('\n'));
      setNote('');
      setResults(null);
    }
  }, [preview]);

  if (!preview) return null;

  const riskColor = preview.risk === '高' ? 'error' : preview.risk === '中' ? 'warning' : 'success';
  const checks = preview.command_checks || [];
  const checkOf = (cmd) => checks.find((c) => c.command === cmd);
  const unverified = checks.filter((c) => c.status === 'unverified');

  const execute = async () => {
    const list = cmds.split('\n').map((s) => s.trim()).filter(Boolean);
    if (!list.length) {
      message.warning('没有可写入的命令');
      return;
    }
    setExecuting(true);
    try {
      const r = await api.post('/api/changes/execute', {
        device_id: preview.device.id,
        commands: list,
        note,
        intent: preview.intent || '',
      });
      setResults(r);
      const failed = (r.results || []).filter((x) => !x.ok).length;
      if (r.status === 'ok') message.success('配置写入完成，设备已接受全部命令');
      else message.error(`写入失败：${failed} 条命令被设备拒绝`);
    } catch (e) {
      message.error(e.message);
    } finally {
      setExecuting(false);
    }
  };

  return (
    <Modal
      open
      title={
        <Space>
          <SaveOutlined />
          配置写入 — {preview.device?.name}
          <Tag color={riskColor}>风险 {preview.risk || '中'}</Tag>
        </Space>
      }
      width={760}
      onCancel={onClose}
      footer={
        results ? (
          <Button type="primary" onClick={onClose}>
            完成
          </Button>
        ) : (
          <>
            <Button onClick={onClose}>取消</Button>
            <Button type="primary" danger loading={executing} onClick={execute}>
              确认写入 {cmds.split('\n').filter((s) => s.trim()).length} 条命令
            </Button>
          </>
        )
      }
    >
      {!results && (
        <>
          <Alert
            type="warning"
            showIcon
            icon={<ExclamationCircleOutlined />}
            message="命令将实际下发到设备并写入配置"
            description="若设备正通过终端会话连接（尤其串口），命令会经该活动会话执行并实时回显在终端；无活动会话时新建连接执行。写入全程记录审计日志。"
            style={{ marginBottom: 12 }}
          />
          {unverified.length > 0 && (
            <Alert
              type="error"
              showIcon
              message={`${unverified.length} 条命令在设备操作手册中查无出处`}
              description={
                <span style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>
                  {unverified.map((c) => `✗ ${c.command}\n`).join('')}
                  这些命令可能是 AI 臆造或该型号不支持。执行前请先在设备 `?` 提示下核实关键字。
                </span>
              }
              style={{ marginBottom: 12 }}
            />
          )}
          {preview.precheck && (
            <Alert
              type={preview.precheck.includes('【预检通过】') ? 'success' : 'info'}
              showIcon
              message="AI 预检"
              description={<span style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{preview.precheck}</span>}
              style={{ marginBottom: 12 }}
            />
          )}
          {preview.analysis && (
            <Typography.Paragraph
              type="secondary"
              style={{ whiteSpace: 'pre-wrap', maxHeight: 140, overflow: 'auto', fontSize: 12 }}
            >
              {preview.analysis}
            </Typography.Paragraph>
          )}
          <Input.TextArea
            rows={10}
            value={cmds}
            onChange={(e) => setCmds(e.target.value)}
            style={{ fontFamily: 'Consolas, monospace' }}
          />
          {checks.length > 0 && (
            <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {checks.map((c, i) => {
                const b = CHECK_BADGE[c.status] || CHECK_BADGE.unverified;
                return (
                  <Tag key={i} color={b.color} title={c.note}>
                    {b.label} · {c.command}
                  </Tag>
                );
              })}
            </div>
          )}
          <Input
            style={{ marginTop: 10 }}
            placeholder="写入备注（可选，写入审计日志）"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </>
      )}
      {results && (
        <div style={{ maxHeight: 420, overflow: 'auto' }}>
          <Alert
            type={results.status === 'ok' ? 'success' : 'error'}
            showIcon
            message={
              results.status === 'ok'
                ? results.via === 'live-session'
                  ? '已通过活动终端会话执行，设备已接受全部命令'
                  : '已通过新建连接执行，设备已接受全部命令'
                : '设备拒绝了部分命令，本次写入未完全生效'
            }
            description={
              results.status !== 'ok'
                ? '请查看下方逐条结果中的「设备判定」，被拒绝的命令不会写入配置。'
                : undefined
            }
            style={{ marginBottom: 10 }}
          />
          {results.postcheck && (
            <Alert
              type="info"
              showIcon
              message="AI 后检（以设备真实回显为准）"
              description={<span style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{results.postcheck}</span>}
              style={{ marginBottom: 10 }}
            />
          )}
          {results.results.map((r, i) => (
            <div key={i} style={{ marginBottom: 10 }}>
              <Typography.Text code strong type={r.ok ? undefined : 'danger'}>
                {r.ok ? '✓ 设备接受' : '✗ 设备拒绝'} {r.command}
              </Typography.Text>
              {r.error && (
                <Tag color="error" style={{ marginLeft: 8 }}>
                  {r.error}
                </Tag>
              )}
              <pre
                style={{
                  background: r.ok ? 'rgba(127,127,127,0.08)' : 'rgba(255,77,79,0.10)',
                  padding: 8,
                  borderRadius: 6,
                  fontSize: 12,
                  whiteSpace: 'pre-wrap',
                  margin: '4px 0 0',
                }}
              >
                {r.output || '(无输出)'}
              </pre>
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}
