import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ClearOutlined,
  DisconnectOutlined,
  DownloadOutlined,
  EditOutlined,
  MinusOutlined,
  PlusOutlined,
  SaveOutlined,
  SearchOutlined,
  StopOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Button, Input, Modal, Select, Space, Tag, Tooltip, Typography, message } from 'antd';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import { api } from '../api';

// 高危命令护栏
const RISKY_PATTERNS = [
  'reload', 'write erase', 'erase', 'delete', 'format', 'reset', 'shutdown',
  'undo vlan', 'undo interface', 'undo port', 'undo ip', 'undo stp',
  'no vlan', 'no interface', 'no ip', 'factory', 'boot system',
];

function riskyOf(line) {
  const low = line.trim().toLowerCase();
  if (!low) return null;
  return RISKY_PATTERNS.find((p) => low === p || low.startsWith(p + ' ') || low.includes(' ' + p + ' ')) || null;
}

const FONT_MIN = 10;
const FONT_MAX = 24;
const DEFAULT_FONT = 13;

/* ---------------- 命令库（localStorage 持久化） ---------------- */
const SNIP_KEY = 'netdeck_snippets';
const DEFAULT_SNIPPETS = [
  { id: 's1', name: '查看版本', cmd: 'show version', cat: '查看' },
  { id: 's2', name: '查看配置', cmd: 'show running-config', cat: '查看' },
  { id: 's3', name: '接口状态', cmd: 'show ip interface brief', cat: '查看' },
  { id: 's4', name: '查看VLAN', cmd: 'show vlan', cat: '查看' },
  { id: 's5', name: '路由表', cmd: 'show ip route', cat: '查看' },
  { id: 's6', name: '保存配置', cmd: 'write', cat: '维护' },
];

function loadSnippets() {
  try {
    const raw = localStorage.getItem(SNIP_KEY);
    if (raw) {
      const arr = JSON.parse(raw);
      if (Array.isArray(arr) && arr.length) return arr;
    }
  } catch {
    /* ignore */
  }
  return DEFAULT_SNIPPETS;
}

function saveSnippets(list) {
  try {
    localStorage.setItem(SNIP_KEY, JSON.stringify(list));
  } catch {
    /* ignore */
  }
}

/* ---------------- 命令库管理弹窗 ---------------- */
function SnippetModal({ open, snippets, onChange, onClose, onSend }) {
  const [name, setName] = useState('');
  const [cmd, setCmd] = useState('');
  const [cat, setCat] = useState('自定义');

  const add = () => {
    if (!cmd.trim()) {
      message.warning('请填写命令');
      return;
    }
    const next = [
      ...snippets,
      { id: 'u' + Date.now(), name: name.trim() || cmd.trim().slice(0, 12), cmd: cmd.trim(), cat: cat.trim() || '自定义' },
    ];
    onChange(next);
    setName('');
    setCmd('');
    message.success('已加入命令库');
  };

  return (
    <Modal
      open={open}
      title="命令库 · 常用命令收藏"
      width={680}
      onCancel={onClose}
      footer={<Button type="primary" onClick={onClose}>完成</Button>}
    >
      <Space.Compact style={{ width: '100%', marginBottom: 10 }}>
        <Input placeholder="名称（可选）" value={name} onChange={(e) => setName(e.target.value)} style={{ width: 140 }} />
        <Input placeholder="分类，如 查看 / 配置 / 维护" value={cat} onChange={(e) => setCat(e.target.value)} style={{ width: 160 }} />
        <Input placeholder="命令，如 show version" value={cmd} onChange={(e) => setCmd(e.target.value)} onPressEnter={add} />
        <Button type="primary" icon={<SaveOutlined />} onClick={add}>添加</Button>
      </Space.Compact>
      <div style={{ maxHeight: 360, overflow: 'auto' }}>
        {snippets.map((s) => (
          <div
            key={s.id}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '6px 8px',
              borderBottom: '1px solid rgba(127,127,127,0.12)',
            }}
          >
            <Tag color="blue" style={{ minWidth: 52, textAlign: 'center' }}>{s.cat}</Tag>
            <Typography.Text style={{ width: 96 }} ellipsis>{s.name}</Typography.Text>
            <Typography.Text code style={{ flex: 1 }} ellipsis>{s.cmd}</Typography.Text>
            <Button size="small" onClick={() => onSend(s.cmd)}>发送</Button>
            <Button size="small" danger onClick={() => onChange(snippets.filter((x) => x.id !== s.id))}>
              删除
            </Button>
          </div>
        ))}
        {!snippets.length && <Typography.Text type="secondary">还没有命令，先在上面添加。</Typography.Text>}
      </div>
    </Modal>
  );
}

/* ---------------- 终端控制台（含查找/缩放/录制/命令库） ---------------- */
export default function CliConsole({
  termRef,
  streamMode,
  onSendData,
  onSendLine,
  onClear,
  onDisconnect,
  connected,
  title,
  quickCommands = [],
  encoding = '',
  onEncodingChange,
  onEvent,
}) {
  const containerRef = useRef(null);
  const xtermRef = useRef(null);
  const fitRef = useRef(null);
  const lineRef = useRef('');
  const logBufRef = useRef([]);
  const recordingRef = useRef(false);
  const [focused, setFocused] = useState(false);
  const [pendingRisk, setPendingRisk] = useState(null);
  const [fontSize, setFontSize] = useState(DEFAULT_FONT);
  const [dims, setDims] = useState({ cols: 0, rows: 0 });
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQ, setSearchQ] = useState('');
  const [searchInfo, setSearchInfo] = useState('');
  const [recording, setRecording] = useState(false);
  const [snippets, setSnippets] = useState(loadSnippets);
  const [snippetOpen, setSnippetOpen] = useState(false);
  const [encList, setEncList] = useState([]);
  const searchInputRef = useRef(null);

  // 加载可用字符编码清单（Python 内置 codec，无需下载字体包）
  useEffect(() => {
    api
      .get('/api/settings/encodings')
      .then((list) =>
        setEncList(
          (list || []).map((e) => ({ value: e.value, label: e.label }))
        )
      )
      .catch(() => {
        setEncList([
          { value: 'utf-8', label: 'UTF-8（默认）' },
          { value: 'gbk', label: 'ANSI/OEM 简体中文 GBK' },
          { value: 'gb18030', label: 'GB18030 简体中文' },
        ]);
      });
  }, []);

  // ---- xterm 初始化 ----
  useEffect(() => {
    const term = new Terminal({
      convertEol: true,
      cursorBlink: true,
      fontSize: DEFAULT_FONT,
      // 中文必须在字体栈里：Cascadia/Consolas 无中文字形，缺了会显示成方块
      fontFamily:
        "'Cascadia Code', 'JetBrains Mono', Consolas, 'NSimSun', 'SimSun', 'Microsoft YaHei', 'SimHei', monospace",
      theme: {
        background: '#0b1220',
        foreground: '#d7e0ee',
        cursor: '#7ee787',
        selectionBackground: 'rgba(47,129,247,0.35)',
      },
      scrollback: 20000,
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(containerRef.current);
    try {
      fit.fit();
    } catch {
      /* ignore */
    }
    xtermRef.current = term;
    fitRef.current = fit;
    setDims({ cols: term.cols, rows: term.rows });

    if (termRef) {
      termRef.current = {
        write: (d) => {
          term.write(d);
          if (recordingRef.current) logBufRef.current.push(d);
        },
        clear: () => term.clear(),
        focus: () => term.focus(),
      };
    }

    // xterm 6.0.0 移除了公开的 onFocus/onBlur，改用 DOM focusin/focusout（跨版本稳定）
    const container = containerRef.current;
    const onFocusIn = () => setFocused(true);
    const onFocusOut = () => setFocused(false);
    container.addEventListener('focusin', onFocusIn);
    container.addEventListener('focusout', onFocusOut);

    const ro = new ResizeObserver(() => {
      try {
        fit.fit();
        setDims({ cols: term.cols, rows: term.rows });
      } catch {
        /* ignore */
      }
    });
    ro.observe(containerRef.current);
    return () => {
      ro.disconnect();
      container.removeEventListener('focusin', onFocusIn);
      container.removeEventListener('focusout', onFocusOut);
      term.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  recordingRef.current = recording;

  // ---- 字号缩放 ----
  const applyFont = useCallback((size) => {
    const s = Math.max(FONT_MIN, Math.min(FONT_MAX, size));
    const t = xtermRef.current;
    if (!t) return;
    t.options.fontSize = s;
    setFontSize(s);
    try {
      fitRef.current?.fit();
      setDims({ cols: t.cols, rows: t.rows });
    } catch {
      /* ignore */
    }
  }, []);

  // ---- 查找 ----
  const runSearch = useCallback(() => {
    const t = xtermRef.current;
    const q = searchQ.trim();
    if (!t || !q) {
      setSearchInfo('');
      return;
    }
    const buf = t.buffer.active;
    const total = buf.length;
    let hits = 0;
    let first = null;
    for (let i = 0; i < total; i++) {
      const line = buf.getLine(i);
      if (!line) continue;
      const text = line.translateToString(true);
      if (text.toLowerCase().includes(q.toLowerCase())) {
        hits++;
        if (first === null) first = i;
      }
    }
    if (first === null) {
      setSearchInfo('未找到');
      return;
    }
    t.scrollToLine(first);
    try {
      const vy = t.buffer.active.viewportY;
      const rel = first - vy;
      const lineObj = buf.getLine(first);
      const text = lineObj ? lineObj.translateToString(true) : '';
      const col = Math.max(0, text.toLowerCase().indexOf(q.toLowerCase()));
      if (rel >= 0 && rel < t.rows) t.select(col, rel, q.length);
    } catch {
      /* ignore */
    }
    setSearchInfo(`命中 ${hits} 处，已定位首处`);
  }, [searchQ]);

  // ---- 会话录制下载 ----
  const downloadLog = () => {
    const text = logBufRef.current.join('');
    if (!text.trim()) {
      message.warning('暂无会话内容可下载');
      return;
    }
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `session_${new Date().toISOString().replace(/[:.]/g, '-')}.log`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  // ---- 快捷键：Ctrl+F 查找 / Ctrl+= 缩放 ----
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onKey = (e) => {
      if (e.ctrlKey && e.key === 'f') {
        e.preventDefault();
        setSearchOpen(true);
        setTimeout(() => searchInputRef.current?.focus(), 30);
      } else if (e.ctrlKey && (e.key === '=' || e.key === '+')) {
        e.preventDefault();
        applyFont(fontSize + 1);
      } else if (e.ctrlKey && e.key === '-') {
        e.preventDefault();
        applyFont(fontSize - 1);
      } else if (e.ctrlKey && e.key === '0') {
        e.preventDefault();
        applyFont(DEFAULT_FONT);
      }
    };
    el.addEventListener('keydown', onKey);
    return () => el.removeEventListener('keydown', onKey);
  }, [applyFont, fontSize]);

  // 连接变化时聚焦
  useEffect(() => {
    if (connected) xtermRef.current?.focus();
  }, [connected]);

  const handleData = (data) => {
    if (!connected || pendingRisk) return;

    // 行跟踪（高危识别）
    if (data === '\r' || data === '\n') {
      const hit = riskyOf(lineRef.current);
      if (hit) {
        setPendingRisk(lineRef.current.trim());
        onEvent?.({
          kind: 'risk',
          level: 'warn',
          text: `拦截高危命令 ${hit}`,
          detail: lineRef.current.trim(),
        });
        return; // 拦截回车，等确认
      }
      lineRef.current = '';
    } else if (data === '\x7f' || data === '\b') {
      lineRef.current = lineRef.current.slice(0, -1);
    } else if (data.length === 1 && data >= ' ') {
      lineRef.current += data;
    }

    if (streamMode) {
      // 网络设备控制台约定 Backspace=BS(0x08)；xterm 默认发 DEL(0x7F)，此处转换
      const out = data === '\x7f' ? '\x08' : data;
      onSendData(out);
    } else {
      // 模拟设备：本地行编辑 + 本地回显
      if (data === '\r' || data === '\n') {
        xtermRef.current?.write('\r\n');
        onSendLine(lineRef.current);
        lineRef.current = '';
      } else if (data === '\x7f' || data === '\b') {
        if (lineRef.current) xtermRef.current?.write('\b \b');
      } else if (data.length === 1 && data >= ' ') {
        xtermRef.current?.write(data);
      }
    }
  };

  useEffect(() => {
    const term = xtermRef.current;
    if (!term) return;
    const d = term.onData(handleData);
    return () => d.dispose();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connected, streamMode, pendingRisk]);

  const confirmRisk = () => {
    const cmd = pendingRisk;
    setPendingRisk(null);
    lineRef.current = '';
    if (streamMode) onSendData('\r');
    else xtermRef.current?.write('\r\n');
    onEvent?.({ kind: 'risk', level: 'warn', text: '高危命令已放行', detail: cmd });
  };

  const cancelRisk = () => {
    const cmd = pendingRisk;
    setPendingRisk(null);
    lineRef.current = '';
    if (streamMode) onSendData('\x03');
    onEvent?.({ kind: 'risk', level: 'error', text: '高危命令已取消', detail: cmd });
  };

  const sendSnippet = (cmd) => {
    if (!connected) {
      message.warning('请先连接设备');
      return;
    }
    onSendLine(cmd);
    onEvent?.({ kind: 'snip', level: 'info', text: `› ${cmd}`, detail: '命令库/快捷命令' });
  };

  const cats = [...new Set(snippets.map((s) => s.cat))];

  return (
    <div className="cli-console">
      <div className="cli-toolbar">
        <Space size={6}>
          <Tag color={connected ? 'success' : 'default'}>{connected ? '已连接' : '未连接'}</Tag>
          <Typography.Text style={{ color: '#8b949e', fontSize: 12 }} ellipsis>
            {title || '选择左侧设备建立会话'}
          </Typography.Text>
          <Tooltip title="终端字符编码 — 国产设备常需 GBK/GB18030，乱码时切换它">
            <Select
              size="small"
              value={encoding || 'utf-8'}
              style={{ width: 178 }}
              popupMatchSelectWidth={false}
              options={encList}
              showSearch
              optionFilterProp="label"
              onChange={(v) => onEncodingChange?.(v)}
            />
          </Tooltip>
        </Space>
        <Space wrap size={4}>
          <Tooltip title="查找 (Ctrl+F)">
            <Button
              size="small"
              type="text"
              icon={<SearchOutlined />}
              style={{ color: searchOpen ? '#2f81f7' : '#8b949e' }}
              onClick={() => {
                setSearchOpen((v) => !v);
                setTimeout(() => searchInputRef.current?.focus(), 30);
              }}
            />
          </Tooltip>
          <Tooltip title="复制全部">
            <Button
              size="small"
              type="text"
              icon={<EditOutlined />}
              style={{ color: '#8b949e' }}
              onClick={() => {
                const t = xtermRef.current;
                if (!t) return;
                const buf = t.buffer.active;
                const lines = [];
                for (let i = 0; i < buf.length; i++) {
                  const l = buf.getLine(i);
                  if (l) lines.push(l.translateToString(true));
                }
                navigator.clipboard?.writeText(lines.join('\n')).then(
                  () => message.success('已复制终端内容'),
                  () => message.error('复制失败')
                );
              }}
            />
          </Tooltip>
          <Tooltip title="缩小字号 (Ctrl+-)">
            <Button size="small" type="text" icon={<MinusOutlined />} style={{ color: '#8b949e' }} onClick={() => applyFont(fontSize - 1)} />
          </Tooltip>
          <span style={{ color: '#8b949e', fontSize: 11, minWidth: 34, textAlign: 'center' }}>{fontSize}px</span>
          <Tooltip title="放大字号 (Ctrl+=)">
            <Button size="small" type="text" icon={<PlusOutlined />} style={{ color: '#8b949e' }} onClick={() => applyFont(fontSize + 1)} />
          </Tooltip>
          <Tooltip title={recording ? '停止录制并可下载' : '录制会话输出'}>
            <Button
              size="small"
              type="text"
              icon={<SaveOutlined />}
              style={{ color: recording ? '#ff7b72' : '#8b949e' }}
              onClick={() => {
                if (recording) {
                  setRecording(false);
                  const n = logBufRef.current.join('').length;
                  message.success('已停止录制');
                  onEvent?.({ kind: 'rec', level: 'warn', text: '停止录制', detail: `已录 ${n} 字符` });
                } else {
                  logBufRef.current = [];
                  setRecording(true);
                  message.success('开始录制会话输出');
                  onEvent?.({ kind: 'rec', level: 'info', text: '开始录制会话输出' });
                }
              }}
            />
          </Tooltip>
          <Tooltip title="下载会话日志">
            <Button size="small" type="text" icon={<DownloadOutlined />} style={{ color: '#8b949e' }} onClick={downloadLog} />
          </Tooltip>
          <Tooltip title="中断（Ctrl+C）">
            <Button
              size="small"
              type="text"
              icon={<StopOutlined />}
              style={{ color: '#f5222d' }}
              disabled={!connected}
              onClick={() => onSendData('\x03')}
            />
          </Tooltip>
          <Tooltip title="清屏">
            <Button
              size="small"
              type="text"
              icon={<ClearOutlined />}
              style={{ color: '#8b949e' }}
              onClick={() => {
                xtermRef.current?.clear();
                onClear?.();
              }}
            />
          </Tooltip>
          <Tooltip title="断开">
            <Button
              size="small"
              type="text"
              icon={<DisconnectOutlined />}
              style={{ color: '#8b949e' }}
              disabled={!connected}
              onClick={onDisconnect}
            />
          </Tooltip>
        </Space>
      </div>

      {searchOpen && (
        <div className="cli-searchbar">
          <Input
            ref={searchInputRef}
            size="small"
            placeholder="在终端输出中查找…"
            value={searchQ}
            onChange={(e) => setSearchQ(e.target.value)}
            onPressEnter={runSearch}
            style={{ width: 220 }}
            allowClear
          />
          <Button size="small" type="primary" onClick={runSearch}>查找</Button>
          {searchInfo && <Typography.Text style={{ fontSize: 11, color: '#8b949e' }}>{searchInfo}</Typography.Text>}
          <Button size="small" type="text" onClick={() => setSearchOpen(false)} style={{ marginLeft: 'auto' }}>关闭</Button>
        </div>
      )}

      {pendingRisk && (
        <div className="cli-risk-bar">
          <WarningOutlined style={{ color: '#faad14' }} />
          <span>
            检测到高危命令 <code>{pendingRisk}</code> — 确认后才会执行
          </span>
          <Space style={{ marginLeft: 'auto' }}>
            <Button size="small" danger onClick={confirmRisk}>
              确认执行
            </Button>
            <Button size="small" onClick={cancelRisk}>
              取消
            </Button>
          </Space>
        </div>
      )}

      {/* 命令库 / 快捷命令条 */}
      <div className="cli-snippetbar">
        <Button size="small" className="cli-chip" icon={<SaveOutlined />} onClick={() => setSnippetOpen(true)}>
          命令库
        </Button>
        <span className="cli-snippet-div" />
        {cats.map((c) => (
          <span key={c} style={{ display: 'contents' }}>
            {snippets
              .filter((s) => s.cat === c)
              .map((s) => (
                <Tooltip key={s.id} title={`${s.name} — ${s.cmd}`}>
                  <Button size="small" className="cli-chip" disabled={!connected} onClick={() => sendSnippet(s.cmd)}>
                    {s.cmd}
                  </Button>
                </Tooltip>
              ))}
          </span>
        ))}
        {quickCommands.map((c) => (
          <Tooltip key={'q' + c} title="厂商快捷命令">
            <Button size="small" className="cli-chip cli-chip-quick" disabled={!connected} onClick={() => sendSnippet(c)}>
              {c}
            </Button>
          </Tooltip>
        ))}
      </div>

      <div
        ref={containerRef}
        className="cli-xterm"
        onClick={() => xtermRef.current?.focus()}
      />

      <div className="cli-statusbar">
        {focused ? (
          <span className="cli-status-live">● 键盘已接入终端</span>
        ) : (
          <span>点击终端区域获取键盘焦点</span>
        )}
        <span style={{ opacity: 0.65 }}>Ctrl+F 查找 · Ctrl+= 缩放 · --More-- 空格/q · 高危命令需确认</span>
        <span style={{ marginLeft: 'auto', opacity: 0.75, fontFamily: 'Consolas, monospace' }}>
          {dims.cols}×{dims.rows}
          {recording && <Tag color="red" style={{ marginLeft: 8, fontSize: 10 }}>REC</Tag>}
        </span>
      </div>

      <SnippetModal
        open={snippetOpen}
        snippets={snippets}
        onChange={(l) => {
          setSnippets(l);
          saveSnippets(l);
        }}
        onClose={() => setSnippetOpen(false)}
        onSend={sendSnippet}
      />
    </div>
  );
}
