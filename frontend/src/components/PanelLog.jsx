import React, { useState } from 'react';
import {
  CaretDownOutlined,
  CaretRightOutlined,
  ClearOutlined,
  CopyOutlined,
} from '@ant-design/icons';
import { Button, Space, Tooltip, Typography, message } from 'antd';

/**
 * 面板活动日志。
 *
 * entries: [{ id, time, kind, text, detail, level }]
 *   kind  决定图标与配色（link/cmd/out/key/enc/risk/rec/ai/sys）
 *   level 兜底着色（info/ok/warn/error）
 */
const KIND_META = {
  link: { icon: '⇅', color: '#58a6ff', label: '连接' },
  cmd: { icon: '›', color: '#7ee787', label: '命令' },
  out: { icon: '⏎', color: '#8b949e', label: '输出' },
  key: { icon: '⌨', color: '#8b949e', label: '按键' },
  enc: { icon: '文', color: '#d29922', label: '编码' },
  risk: { icon: '⚠', color: '#f5222d', label: '高危' },
  rec: { icon: '●', color: '#ff7b72', label: '录制' },
  ai: { icon: '✦', color: '#a371f7', label: 'AI' },
  sys: { icon: '·', color: '#8b949e', label: '系统' },
};

const LEVEL_COLOR = {
  ok: '#3fb950',
  warn: '#d29922',
  error: '#ff7b72',
  info: '#c9d1d9',
};

export default function PanelLog({
  title = '活动日志',
  entries = [],
  onClear,
  max = 200,
  collapsible = true,
  defaultCollapsed = false,
  height = 132,
}) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const shown = entries.slice(-max);

  const copyAll = () => {
    if (!entries.length) {
      message.warning('没有可复制的日志');
      return;
    }
    const text = entries
      .map((e) => `${e.time}  [${(KIND_META[e.kind] || KIND_META.sys).label}] ${e.text}${e.detail ? '  ' + e.detail : ''}`)
      .join('\n');
    navigator.clipboard?.writeText(text).then(
      () => message.success(`已复制 ${entries.length} 条日志`),
      () => message.error('复制失败')
    );
  };

  return (
    <div className="panel-log" style={collapsed ? { maxHeight: 34 } : { maxHeight: height }}>
      <div className="panel-log-head">
        {collapsible && (
          <span
            className="panel-log-caret"
            onClick={() => setCollapsed((v) => !v)}
            title={collapsed ? '展开' : '收起'}
          >
            {collapsed ? <CaretRightOutlined /> : <CaretDownOutlined />}
          </span>
        )}
        <span className="panel-log-dot" />
        {title}
        <span className="panel-log-count">{entries.length}</span>
        <Space size={2} style={{ marginLeft: 'auto' }}>
          <Tooltip title="复制全部">
            <Button
              size="small"
              type="text"
              icon={<CopyOutlined />}
              className="panel-log-btn"
              onClick={copyAll}
            />
          </Tooltip>
          {onClear && (
            <Tooltip title="清空">
              <Button
                size="small"
                type="text"
                icon={<ClearOutlined />}
                className="panel-log-btn"
                onClick={onClear}
              />
            </Tooltip>
          )}
        </Space>
      </div>
      {!collapsed && (
        <div className="panel-log-body">
          {shown.length === 0 && <div className="panel-log-empty">暂无事件</div>}
          {shown.map((e) => {
            const k = KIND_META[e.kind] || KIND_META.sys;
            const color = LEVEL_COLOR[e.level] || k.color;
            return (
              <div key={e.id} className="panel-log-line" style={{ color }}>
                <span className="panel-log-time">{e.time}</span>
                <span className="panel-log-kind" style={{ color: k.color }} title={k.label}>
                  {k.icon}
                </span>
                <span className="panel-log-text">{e.text}</span>
                {e.detail && <span className="panel-log-detail">{e.detail}</span>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
