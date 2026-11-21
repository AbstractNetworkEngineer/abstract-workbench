import React, { useEffect, useRef, useState } from 'react';
import {
  BgColorsOutlined,
  CommentOutlined,
  MedicineBoxOutlined,
  RobotOutlined,
  SendOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons';
import { Button, Input, Select, Space, Tag, Typography, message } from 'antd';
import { api } from '../api';
import PanelLog from './PanelLog';

const MODES = [
  { value: 'chat', label: '对话', icon: <CommentOutlined /> },
  { value: 'analyze', label: '分析配置', icon: <BgColorsOutlined /> },
  { value: 'plan', label: '配置写入', icon: <ThunderboltOutlined /> },
  { value: 'trouble', label: '排障向导', icon: <MedicineBoxOutlined /> },
];

const MODE_HINT = {
  chat: '问它任何网络问题…（自动携带终端最近输出）',
  analyze: '粘贴配置文本，或直接回车用终端最近输出做多维分析',
  plan: '描述要写入设备的变更意图，如：把 GE0/0/2 划入 VLAN 100',
  trouble: '描述故障现象，如：VLAN10 用户无法获取地址',
};

let seq = 0;
function now() {
  const d = new Date();
  const p = (n, w = 2) => String(n).padStart(w, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}`;
}

export default function AiCopilot({ context, deviceName, deviceId, onOpenGate }) {
  const [mode, setMode] = useState('chat');
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [model, setModel] = useState('');
  const [log, setLog] = useState([]);
  const [trouble, setTrouble] = useState({ symptom: '', history: '', rounds: 0, commands: [] });
  const bottomRef = useRef(null);

  const pushLog = (text, level = 'info', detail = '') =>
    setLog((l) => [...l.slice(-200), { id: ++seq, time: now(), text, level, kind: 'ai', detail }]);

  const refreshModel = async () => {
    try {
      const c = await api.get('/api/ai/config');
      setModel(c.ai_model || '');
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    refreshModel();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const addMsg = (role, text, extra = {}) => {
    setMessages((m) => [...m, { id: ++seq, role, mode, text, ...extra }]);
  };

  const runTrouble = async (symptom, history, rounds) => {
    setLoading(true);
    const t0 = Date.now();
    pushLog(`排障向导 第${rounds + 1}轮`, 'info', `模型 ${model || '未配置'}`);
    try {
      const r = await api.post('/api/ai/troubleshoot', {
        device_id: deviceId,
        symptom,
        history,
        rounds,
      });
      addMsg('assistant', r.reply, { commands: r.commands });
      setTrouble((t) => ({ ...t, symptom, history, rounds: rounds + 1, commands: r.commands || [] }));
      const secs = ((Date.now() - t0) / 1000).toFixed(1);
      pushLog(`给出 ${r.commands?.length || 0} 条排查命令`, 'ok', `${secs}s`);
    } catch (e) {
      const secs = ((Date.now() - t0) / 1000).toFixed(1);
      addMsg('assistant', `⚠️ ${e.message}`);
      pushLog(`排障失败`, 'error', `${secs}s · ${e.message.slice(0, 50)}`);
    } finally {
      setLoading(false);
    }
  };

  const execTroubleCommands = async () => {
    if (!deviceId) {
      message.warning('请先连接设备');
      return;
    }
    if (!trouble.commands.length) return;
    setLoading(true);
    try {
      const r = await api.post('/api/changes/execute', {
        device_id: deviceId,
        commands: trouble.commands,
        note: '排障向导自动执行',
        intent: trouble.symptom,
      });
      const outputs = r.results
        .map((x) => `$ ${x.command}\n${(x.output || '(无输出)').slice(0, 2000)}`)
        .join('\n');
      const newHistory = (trouble.history ? trouble.history + '\n\n' : '') + outputs;
      pushLog(`执行排查命令 ${trouble.commands.length} 条`, 'ok');
      await runTrouble(trouble.symptom, newHistory, trouble.rounds);
    } catch (e) {
      message.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  const run = async () => {
    const text = input.trim();
    if (mode === 'trouble') {
      if (!text) {
        message.warning('请描述故障现象');
        return;
      }
      addMsg('user', text);
      setInput('');
      setTrouble((t) => ({ ...t, symptom: text, history: '', rounds: 0, commands: [] }));
      await runTrouble(text, '', 0);
      return;
    }

    if (!text && mode === 'chat') {
      message.warning('请输入内容');
      return;
    }
    if (mode === 'plan' && !deviceId) {
      message.warning('请先连接一台设备');
      return;
    }
    if (mode === 'plan' && !text) {
      message.warning('请描述配置写入意图');
      return;
    }

    addMsg('user', text || '(使用终端输出作为上下文)');
    setInput('');
    setLoading(true);
    const modeLabel = MODES.find((x) => x.value === mode).label;
    const t0 = Date.now();
    pushLog(`调用[${modeLabel}]`, 'info', `模型 ${model || '未配置'}`);

    try {
      let reply = '';
      if (mode === 'chat') {
        const history = messages.slice(-6).map((m) => ({
          role: m.role === 'user' ? 'user' : 'assistant',
          content: m.text,
        }));
        const r = await api.post('/api/ai/chat', {
          messages: [...history, { role: 'user', content: text }],
          context: context ? `【终端最近输出】\n${context.slice(-3000)}` : '',
          mode: 'chat',
        });
        reply = r.reply;
      } else if (mode === 'analyze') {
        const cfg = text || context || '';
        if (!cfg) {
          message.warning('请粘贴配置文本，或先在终端执行 display current-configuration / show running-config');
          setLoading(false);
          return;
        }
        const r = await api.post('/api/ai/analyze', { messages: [], context: cfg });
        reply = r.reply;
      } else {
        const r = await api.post('/api/changes/preview', {
          device_id: deviceId,
          intent: text,
          context: (context || '').slice(-4000),
        });
        const checks = r.command_checks || [];
        const unverified = checks.filter((c) => c.status === 'unverified');
        const partial = checks.filter((c) => c.status === 'partial');
        let verifyNote = '';
        if (checks.length) {
          const lines = [
            `━━━ 手册核验（对照设备操作手册逐条查证）━━━`,
            `✓ 已验证 ${checks.filter((c) => c.status === 'verified').length} 条 · 部分匹配 ${partial.length} 条 · 手册未找到 ${unverified.length} 条`,
          ];
          for (const c of [...unverified, ...partial]) {
            lines.push(`  ${c.status === 'unverified' ? '✗' : '△'} ${c.command} — ${c.note}`);
          }
          if (unverified.length) {
            lines.push(`⚠️ 上述命令手册中查无出处，可能是 AI 臆造或该型号不支持，执行前请务必人工确认。`);
          }
          verifyNote = `\n\n${lines.join('\n')}`;
        }
        const pre = r.precheck ? `\n\n━━━ AI 预检 ━━━\n${r.precheck}` : '';
        reply = `已生成配置写入方案（${r.commands?.length || 0} 条命令，风险 ${r.risk}）${verifyNote}${pre}\n\n${r.analysis || ''}`;
        onOpenGate(r);
        pushLog(
          `生成方案 ${r.commands?.length || 0} 条`,
          unverified.length ? 'warn' : 'ok',
          `风险 ${r.risk} · 手册未验证 ${unverified.length} 条`
        );
      }
      addMsg('assistant', reply);
      const secs = ((Date.now() - t0) / 1000).toFixed(1);
      pushLog(`回复 ${reply.length} 字`, 'ok', `${secs}s · ${model || '未配置'}`);
    } catch (e) {
      const secs = ((Date.now() - t0) / 1000).toFixed(1);
      addMsg('assistant', `⚠️ ${e.message}`);
      pushLog(`调用失败`, 'error', `${secs}s · ${e.message.slice(0, 60)}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div className="ai-topbar">
        <Select
          size="small"
          value={mode}
          onChange={setMode}
          style={{ width: 118 }}
          options={MODES.map((m) => ({ value: m.value, label: m.label }))}
        />
        <Tag icon={<RobotOutlined />} color={model ? 'geekblue' : 'default'} title="当前调用的 API 模型">
          {model ? model : '模型未配置'}
        </Tag>
        {deviceName && <Tag color="cyan">{deviceName}</Tag>}
      </div>

      <div className="ai-messages">
        {messages.length === 0 && (
          <div className="ai-empty">
            <RobotOutlined style={{ fontSize: 22, opacity: 0.5 }} />
            <div>选择模式开始智能协作</div>
            <div className="ai-empty-hint">
              · 对话：自由问答 · 分析配置：安全/规范/优化
              <br />
              · 配置写入：预检→确认→执行→后检
              <br />
              · 排障向导：现象→AI 给排查命令→一键执行→根因
            </div>
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`chat-msg ${m.role}`}>
            <div className="chat-msg-meta">
              {m.role === 'user' ? '我' : 'AI'} · {MODES.find((x) => x.value === m.mode)?.label}
            </div>
            <div className="chat-msg-body">{m.text}</div>
            {m.commands?.length > 0 && (
              <div className="chat-msg-cmds">
                {m.commands.map((c, i) => (
                  <Tag key={i} color="geekblue" style={{ fontFamily: 'Consolas, monospace' }}>
                    {c}
                  </Tag>
                ))}
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="chat-msg assistant">
            <div className="chat-msg-body ai-thinking">
              思考中<span className="thinking-dots"><i>.</i><i>.</i><i>.</i></span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {mode === 'trouble' && trouble.commands.length > 0 && !loading && (
        <Button
          type="primary"
          ghost
          block
          style={{ margin: '0 12px 6px' }}
          onClick={execTroubleCommands}
        >
          ▶ 执行 {trouble.commands.length} 条排查命令并继续分析
        </Button>
      )}

      <div className="ai-input">
        <Input.TextArea
          rows={3}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={MODE_HINT[mode]}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault();
              run();
            }
          }}
        />
        <Button
          type="primary"
          block
          icon={<SendOutlined />}
          loading={loading}
          onClick={run}
          style={{ marginTop: 6 }}
        >
          {mode === 'plan' ? '生成配置写入方案' : mode === 'analyze' ? '开始分析' : mode === 'trouble' ? '开始排障' : '发送'}
        </Button>
      </div>

      <PanelLog title="AI 调用日志" entries={log} onClear={() => setLog([])} height={128} />
    </div>
  );
}
