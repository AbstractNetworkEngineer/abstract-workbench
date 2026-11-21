import React, { useCallback, useEffect, useRef, useState } from 'react';
import { RocketOutlined, WifiOutlined } from '@ant-design/icons';
import { Button, Card, Empty, Space, Typography, message } from 'antd';
import { useNavigate } from 'react-router-dom';
import { api, wsUrl } from '../api';
import { useStore } from '../lib/store';
import AiCopilot from '../components/AiCopilot';
import ChangeGateModal from '../components/ChangeGateModal';
import CliConsole from '../components/CliConsole';
import ConnectionTree from '../components/ConnectionTree';
import PanelLog from '../components/PanelLog';

const VENDOR_QUICK = {
  huawei: ['display version', 'display current-configuration', 'display ip interface brief'],
  h3c: ['display version', 'display current-configuration', 'display ip interface brief'],
  dcn: ['show version', 'show running-config', 'show ip interface brief', 'show vlan'],
  cisco: ['show version', 'show running-config', 'show ip interface brief'],
  generic: ['show version', 'show running-config'],
};

let logSeq = 0;
function now() {
  // 带毫秒：快速连敲时多条日志会落在同一秒，秒级时间戳分不清先后
  const d = new Date();
  const p = (n, w = 2) => String(n).padStart(w, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}`;
}

/** 媒体查询：窗口窄到一定程度时三栏变纵向堆叠。 */
function useMedia(query) {
  const [match, setMatch] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia(query).matches : false
  );
  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = (e) => setMatch(e.matches);
    setMatch(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, [query]);
  return match;
}

/**
 * 可拖拽分隔条：把面板尺寸存到 localStorage，下次进来还是自己调好的比例。
 * axis='x' 拖宽度（三栏并排），axis='y' 拖高度（窄窗口纵向堆叠）。
 * 两种模式都要能拖 —— 之前堆叠模式直接把分隔条隐藏了，等于废掉调大小。
 */
function useSplitter(key, initial, min, max, invert = false, axis = 'x') {
  const [size, setSize] = useState(() => {
    const v = Number(localStorage.getItem(key));
    return v >= min && v <= max ? v : initial;
  });
  const sizeRef = useRef(size);
  sizeRef.current = size;

  const onPointerDown = useCallback(
    (e) => {
      e.preventDefault();
      const start = axis === 'y' ? e.clientY : e.clientX;
      const s0 = sizeRef.current;
      const move = (ev) => {
        const cur = axis === 'y' ? ev.clientY : ev.clientX;
        const d = cur - start;
        const next = Math.min(max, Math.max(min, s0 + (invert ? -d : d)));
        setSize(next);
        sizeRef.current = next;
      };
      const up = () => {
        localStorage.setItem(key, String(sizeRef.current));
        window.removeEventListener('pointermove', move);
        window.removeEventListener('pointerup', up);
        document.body.classList.remove('is-resizing');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      };
      document.body.classList.add('is-resizing');
      document.body.style.cursor = axis === 'y' ? 'row-resize' : 'col-resize';
      document.body.style.userSelect = 'none';
      window.addEventListener('pointermove', move);
      window.addEventListener('pointerup', up);
    },
    [key, invert, min, max, axis]
  );

  return [size, onPointerDown];
}

function Splitter({ onPointerDown, label, axis = 'x' }) {
  return (
    <div
      className={axis === 'y' ? 'wb-splitter wb-splitter-y' : 'wb-splitter'}
      role="separator"
      aria-orientation={axis === 'y' ? 'horizontal' : 'vertical'}
      aria-label={label}
      title="拖拽调整面板大小"
      onPointerDown={onPointerDown}
    >
      <span className="wb-splitter-grip" />
    </div>
  );
}

export default function Workbench() {
  const nav = useNavigate();
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [connected, setConnected] = useState(false);
  const [streamMode, setStreamMode] = useState(false);
  const [active, setActive] = useState(null);
  const [gate, setGate] = useState(null);
  // 日志持久化：换模块再回来，会话记录不丢
  const [connLog, setConnLog] = useStore('workbench.connLog', []);
  const [termLog, setTermLog] = useStore('workbench.termLog', []);
  const wsRef = useRef(null);
  const termApi = useRef(null);
  const contextRef = useRef('');

  const [leftW, onLeftDrag] = useSplitter('netdeck_wb_left', 248, 180, 460, false, 'x');
  const [rightW, onRightDrag] = useSplitter('netdeck_wb_right', 356, 260, 620, true, 'x');
  // 窄窗口时三栏变纵向堆叠，此时用高度而不是宽度来分面板
  const stacked = useMedia('(max-width: 1100px)');
  const [topH, onTopDrag] = useSplitter('netdeck_wb_top', 260, 140, 620, false, 'y');
  const [midH, onMidDrag] = useSplitter('netdeck_wb_mid', 460, 260, 1200, false, 'y');
  // 当前生效的终端编码。必须自己持有，不能只读 active.encoding —— 没连设备时
  // active 是 null，下拉框会一直卡在 UTF-8（用户切换了界面也不跟着变）。
  const [termEncoding, setTermEncoding] = useState('utf-8');

  // 日志：带事件类型（kind）与补充说明（detail），条数上限放到 250
  const pushConnLog = (text, level = 'info', kind = 'sys', detail = '') =>
    setConnLog((l) => [...l.slice(-250), { id: ++logSeq, time: now(), text, level, kind, detail }]);
  const pushTermLog = (text, level = 'info', kind = 'sys', detail = '') =>
    setTermLog((l) => [...l.slice(-250), { id: ++logSeq, time: now(), text, level, kind, detail }]);

  // 流式模式下按键是逐个发的，要把它们聚成完整命令行才记日志
  const cmdBufRef = useRef('');
  // 输出摘要：攒够一小段再记，避免刷屏
  const outBufRef = useRef({ bytes: 0, head: '' });
  const outTimerRef = useRef(null);
  const connectAtRef = useRef(0);

  const flushOutput = useCallback(() => {
    if (outTimerRef.current) {
      clearTimeout(outTimerRef.current);
      outTimerRef.current = null;
    }
    const { bytes, head } = outBufRef.current;
    if (!bytes) return;
    outBufRef.current = { bytes: 0, head: '' };
    pushTermLog(
      `收到 ${bytes} B`,
      'info',
      'out',
      head ? head.replace(/\s+/g, ' ').slice(0, 72) : ''
    );
  }, []);

  const noteOutput = useCallback(
    (text) => {
      if (!text) return;
      outBufRef.current.bytes += text.length;
      if (!outBufRef.current.head) {
        outBufRef.current.head = text.replace(/[\r\n]+/g, ' ').trim().slice(0, 72);
      }
      if (outTimerRef.current) clearTimeout(outTimerRef.current);
      outTimerRef.current = setTimeout(flushOutput, 900);
    },
    [flushOutput]
  );

  const loadDevices = useCallback(async () => {
    try {
      const list = await api.get('/api/devices');
      setDevices(list);
    } catch (e) {
      message.error('加载设备失败: ' + e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDevices();
    // 载入全局默认编码（设备未单独指定时的生效值）
    api
      .get('/api/settings')
      .then((s) => setTermEncoding(s.term_encoding || 'utf-8'))
      .catch(() => {});
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, [loadDevices]);

  const appendBuffer = (text) => {
    termApi.current?.write(text);
    contextRef.current = (contextRef.current + text).slice(-8000);
    noteOutput(text);
  };

  const disconnect = useCallback(() => {
    flushOutput();
    if (wsRef.current) {
      try {
        wsRef.current.send(JSON.stringify({ type: 'disconnect' }));
        wsRef.current.close();
      } catch {
        /* ignore */
      }
      wsRef.current = null;
    }
    setConnected(false);
    cmdBufRef.current = '';
    pushConnLog('会话已断开', 'warn', 'link');
    pushTermLog('会话已断开', 'warn', 'link');
  }, [flushOutput]);

  const connect = useCallback(
    (device) => {
      disconnect();
      setActive(device);
      // 设备单独指定过编码就切过去；否则沿用当前（全局默认）值
      if (device.encoding) setTermEncoding(device.encoding);
      termApi.current?.clear();
      contextRef.current = '';
      cmdBufRef.current = '';
      connectAtRef.current = Date.now();
      const where = device.host || device.serial_port || device.protocol;
      pushConnLog(`连接 ${device.name}（${device.protocol}）…`, 'info', 'link', where);
      pushTermLog(
        `打开会话 ${device.name}`,
        'ok',
        'link',
        `${device.protocol}://${where} · 编码 ${device.encoding || '默认'}`
      );

      const ws = new WebSocket(wsUrl({ device_id: device.id }));
      wsRef.current = ws;

      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.type === 'stream') {
          appendBuffer(msg.data);
        } else if (msg.type === 'connected') {
          setConnected(true);
          setStreamMode(!!msg.stream);
          const ms = Date.now() - connectAtRef.current;
          pushConnLog(`已连接 ${msg.data}`, 'ok', 'link', `耗时 ${(ms / 1000).toFixed(1)}s`);
          pushTermLog(
            `已连接 ${msg.data}`,
            'ok',
            'link',
            `耗时 ${(ms / 1000).toFixed(1)}s · ${msg.stream ? '字符级流式' : '命令-回显'}`
          );
        } else if (msg.type === 'error') {
          appendBuffer(`\r\n[错误] ${msg.data}\r\n`);
          pushTermLog('连接/会话失败', 'error', 'link', msg.data);
          setConnected(false);
        } else if (msg.type === 'encoding') {
          pushTermLog(`编码已切换为 ${msg.data}`, 'warn', 'enc');
        }
      };
      ws.onclose = () => {
        setConnected(false);
      };
      ws.onerror = () => {
        appendBuffer('\r\n[错误] WebSocket 连接异常\r\n');
        pushTermLog('WebSocket 连接异常', 'error', 'link');
        setConnected(false);
      };
    },
    [disconnect]
  );

  const sendLine = (cmd) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    if (cmd.trim().toLowerCase() === 'clear') {
      termApi.current?.clear();
      pushTermLog('清屏', 'info', 'key');
      return;
    }
    flushOutput();
    wsRef.current.send(JSON.stringify({ type: 'input', data: cmd }));
    pushTermLog(`› ${cmd}`, 'info', 'cmd', '整行下发');
    cmdBufRef.current = '';
  };

  /**
   * 流式模式下按键逐个下发 —— 必须在这里把它们重新拼成命令行，
   * 否则日志里只剩「按键 回车」，用户敲的 show version 全丢。
   */
  const sendKey = (ch) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: 'key', data: ch }));

    if (ch === '\r' || ch === '\n') {
      const line = cmdBufRef.current.trim();
      cmdBufRef.current = '';
      flushOutput();
      if (line) pushTermLog(`› ${line}`, 'info', 'cmd', '用户输入');
      else pushTermLog('回车', 'info', 'key');
    } else if (ch === '\x03') {
      cmdBufRef.current = '';
      flushOutput();
      pushTermLog('Ctrl+C 中断', 'warn', 'key');
    } else if (ch === '\x04') {
      pushTermLog('Ctrl+D 退出', 'warn', 'key');
    } else if (ch === '\x7f' || ch === '\b') {
      cmdBufRef.current = cmdBufRef.current.slice(0, -1);
    } else if (ch === '\t') {
      pushTermLog(`Tab 补全${cmdBufRef.current ? ` · ${cmdBufRef.current}` : ''}`, 'info', 'key');
    } else if (ch.length === 1 && ch >= ' ') {
      cmdBufRef.current += ch;
    } else if (ch.charCodeAt(0) < 32) {
      pushTermLog(`控制键 0x${ch.charCodeAt(0).toString(16)}`, 'info', 'key');
    }
  };

  /** CliConsole 抛上来的事件（高危拦截、录制开关等）。 */
  const onConsoleEvent = useCallback((ev) => {
    if (!ev) return;
    if (ev.kind === 'risk') {
      pushTermLog(ev.text, ev.level || 'warn', 'risk', ev.detail || '');
    } else if (ev.kind === 'rec') {
      pushTermLog(ev.text, ev.level || 'info', 'rec', ev.detail || '');
    } else if (ev.kind === 'enc') {
      pushTermLog(ev.text, ev.level || 'warn', 'enc', ev.detail || '');
    } else if (ev.kind === 'snip') {
      pushTermLog(ev.text, ev.level || 'info', 'cmd', ev.detail || '');
    } else {
      pushTermLog(ev.text, ev.level || 'info', ev.kind || 'sys', ev.detail || '');
    }
  }, []);

  /** 切换终端字符编码：当前会话立即生效，并写回设备配置（下次进来记住）。 */
  const changeEncoding = useCallback(
    async (enc) => {
      // 0) 立刻更新界面，不能等接口回来（否则下拉框会卡在旧值）
      setTermEncoding(enc);
      // 1) 让正在跑的会话立刻用新编码解码后续字节
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'encoding', data: enc }));
      }
      // 2) 持久化：有设备写设备（每台独立），无设备写全局默认
      //    注意 /api/settings 是部分更新，只传 term_encoding 不会动 AI 配置
      try {
        if (active?.id) {
          await api.put(`/api/devices/${active.id}`, { ...active, encoding: enc });
          setActive((d) => (d ? { ...d, encoding: enc } : d));
          pushConnLog(`终端编码切换为 ${enc}（已写入设备配置）`, 'ok');
        } else {
          await api.put('/api/settings', { term_encoding: enc });
          pushConnLog(`终端默认编码切换为 ${enc}`, 'ok');
        }
        message.success(`终端编码已切换：${enc}`);
      } catch (e) {
        message.error('编码切换失败: ' + e.message);
      }
    },
    [active, pushConnLog]
  );

  const quickCommands = active ? VENDOR_QUICK[active.vendor] || VENDOR_QUICK.generic : [];

  return (
    <div className="workbench-grid">
      {/* 左：连接树 + 连接日志 */}
      <div
        className="wb-col"
        style={stacked ? { width: '100%', height: topH, flex: '0 0 auto' } : { width: leftW, flex: '0 0 auto' }}
      >
        <Card
          className="wb-panel"
          size="small"
          title={<span>🔗 连接树</span>}
          styles={{ body: { display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, overflow: 'hidden' } }}
        >
          <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
            <ConnectionTree
              devices={devices}
              loading={loading}
              onConnect={connect}
              connectedId={connected ? active?.id : null}
            />
            <Space.Compact block style={{ marginTop: 8 }}>
              <Button size="small" block onClick={loadDevices}>
                刷新设备列表
              </Button>
              <Button size="small" icon={<WifiOutlined />} onClick={() => nav('/capture')}>
                抓包分析
              </Button>
            </Space.Compact>
          </div>
          <PanelLog
            title="连接日志"
            entries={connLog}
            onClear={() => setConnLog([])}
            defaultCollapsed
            height={120}
          />
        </Card>
      </div>

      <Splitter
        axis={stacked ? 'y' : 'x'}
        onPointerDown={stacked ? onTopDrag : onLeftDrag}
        label={stacked ? '调整连接树高度' : '调整连接树宽度'}
      />

      {/* 中：真终端 + 会话日志 */}
      <div
        className="wb-col"
        style={stacked ? { width: '100%', height: midH, flex: '0 0 auto' } : { flex: 1, minWidth: 0 }}
      >
        <Card
          className="wb-panel"
          size="small"
          styles={{
            body: { flex: 1, minHeight: 0, padding: 8, display: 'flex', flexDirection: 'column', gap: 8, overflow: 'hidden' },
            header: { display: 'none' },
          }}
        >
          {devices.length === 0 && !loading ? (
            <Empty
              description={
                <Space direction="vertical">
                  <span>还没有设备 — 先添加一台（可选「模拟设备」零硬件体验）</span>
                  <Button type="primary" onClick={() => nav('/devices')}>
                    <RocketOutlined /> 去设备管理
                  </Button>
                </Space>
              }
              style={{ margin: 'auto' }}
            />
          ) : (
            <>
              <div style={{ flex: 1, minHeight: 0, display: 'flex' }}>
                <CliConsole
                  termRef={termApi}
                  streamMode={streamMode}
                  onSendData={sendKey}
                  onSendLine={sendLine}
                  onClear={() => {
                    contextRef.current = '';
                  }}
                  onDisconnect={disconnect}
                  connected={connected}
                  title={active ? `${active.name} · ${active.vendor} · ${active.protocol}` : ''}
                  quickCommands={quickCommands}
                  encoding={termEncoding}
                  onEncodingChange={changeEncoding}
                  onEvent={onConsoleEvent}
                />
              </div>
              <PanelLog
                title="会话日志"
                entries={termLog}
                onClear={() => setTermLog([])}
                height={158}
              />
            </>
          )}
        </Card>
      </div>

      <Splitter
        axis={stacked ? 'y' : 'x'}
        onPointerDown={stacked ? onMidDrag : onRightDrag}
        label={stacked ? '调整终端高度' : '调整 AI 接入模块宽度'}
      />

      {/* 右：AI 接入模块 */}
      <div
        className="wb-col"
        style={stacked ? { width: '100%', flex: '1 1 auto', minHeight: 260 } : { width: rightW, flex: '0 0 auto' }}
      >
        <Card
          className="wb-panel ai-module"
          size="small"
          title={
            <span className="ai-module-title">
              <span className="ai-led" />
              AI 接入模块
              <span className="ai-module-tag">AI BRIDGE</span>
            </span>
          }
          styles={{ body: { flex: 1, minHeight: 0, padding: 0, display: 'flex', overflow: 'hidden' } }}
        >
          <div className="ai-module-body">
            {!connected && (
              <Typography.Text type="secondary" style={{ fontSize: 11, padding: '4px 12px 0' }}>
                未连接设备：分析 / 配置写入能力受限
              </Typography.Text>
            )}
            <AiCopilot
              context={contextRef.current}
              deviceName={active?.name}
              deviceId={active?.id}
              onOpenGate={setGate}
            />
          </div>
        </Card>
      </div>

      <ChangeGateModal preview={gate} onClose={() => setGate(null)} />
    </div>
  );
}
