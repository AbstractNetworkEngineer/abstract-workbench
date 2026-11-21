import React from 'react';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  DatabaseOutlined,
  MinusCircleOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Card, Collapse, Progress, Space, Table, Tag, Typography } from 'antd';

const STATUS_META = {
  ok: { color: '#3fb950', icon: <CheckCircleOutlined />, text: '正常', tag: 'success' },
  warn: { color: '#d29922', icon: <WarningOutlined />, text: '关注', tag: 'warning' },
  error: { color: '#f5222d', icon: <CloseCircleOutlined />, text: '异常', tag: 'error' },
  na: { color: '#8b949e', icon: <MinusCircleOutlined />, text: '不支持', tag: 'default' },
};

const TONE_COLOR = {
  ok: '#3fb950',
  warn: '#d29922',
  error: '#ff7b72',
  info: '#c9d1d9',
  muted: '#6e7681',
};

function toneStyle(tone) {
  const c = TONE_COLOR[tone] || TONE_COLOR.info;
  return { color: c, fontWeight: tone === 'ok' || tone === 'error' ? 600 : 400 };
}

/* ---------------- 表格视图 ---------------- */
function TableView({ struct }) {
  const cols = struct.columns || [];
  const rows = (struct.rows || []).map((r, i) => ({ key: i, cells: r }));
  const columns = cols.map((name, ci) => ({
    title: name,
    key: 'c' + ci,
    onCell: (rec) => ({ style: { ...toneStyle(rec.cells[ci]?.tone), whiteSpace: 'nowrap' } }),
    render: (_, rec) => rec.cells[ci]?.text || '—',
  }));
  return (
    <Table
      size="small"
      pagination={false}
      columns={columns}
      dataSource={rows}
      scroll={{ x: 'max-content', y: 320 }}
      style={{ fontSize: 12 }}
    />
  );
}

/* ---------------- 键值视图 ---------------- */
function KvView({ struct }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))',
        gap: 8,
      }}
    >
      {(struct.pairs || []).map((p, i) => (
        <div
          key={i}
          style={{
            padding: '7px 10px',
            borderRadius: 6,
            background: 'rgba(127,127,127,0.07)',
            border: '1px solid rgba(127,127,127,0.12)',
          }}
        >
          <div style={{ fontSize: 11, opacity: 0.6 }}>{p.k}</div>
          <div style={{ fontSize: 13, ...toneStyle(p.tone), wordBreak: 'break-all' }}>{p.v}</div>
        </div>
      ))}
    </div>
  );
}

/* ---------------- 仪表盘视图 ---------------- */
function BarsView({ struct }) {
  return (
    <Space direction="vertical" style={{ width: '100%' }} size={12}>
      {(struct.bars || []).map((b, i) => {
        const color = b.tone === 'error' ? '#ff4d4f' : b.tone === 'warn' ? '#faad14' : '#3fb950';
        return (
          <div key={i}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 2 }}>
              <span>{b.label}</span>
              <span style={{ color, fontWeight: 700 }}>{b.value}%</span>
            </div>
            <Progress
              percent={Math.max(0, Math.min(100, b.value))}
              showInfo={false}
              strokeColor={color}
              trailColor="rgba(127,127,127,0.15)"
              size="small"
            />
          </div>
        );
      })}
    </Space>
  );
}

/* ---------------- 日志 / 行列表视图 ---------------- */
function LinesView({ struct }) {
  return (
    <div
      style={{
        maxHeight: 300,
        overflow: 'auto',
        fontFamily: 'Cascadia Code, Consolas, monospace',
        fontSize: 11.5,
        lineHeight: 1.7,
      }}
    >
      {(struct.rows || []).map((r, i) => (
        <div
          key={i}
          style={{
            ...toneStyle(r.tone),
            padding: '1px 8px',
            borderLeft: `2px solid ${TONE_COLOR[r.tone] || 'transparent'}`,
            background: r.tone === 'error' ? 'rgba(255,77,79,0.08)' : undefined,
            wordBreak: 'break-all',
          }}
        >
          {r.text}
        </div>
      ))}
    </div>
  );
}

/**
 * 检测结果卡：结构化状态视图（表格/键值/仪表盘/日志）+ 源文可展开。
 * struct = { type, columns, rows, pairs, bars, summary, bad }
 */
export default function DetectResultCard({ item }) {
  const meta = STATUS_META[item.status] || STATUS_META.na;
  const struct = item.structured || { type: 'lines', rows: [] };
  const showSummary = struct.summary || item.note;

  return (
    <Card
      size="small"
      className="detect-card"
      title={
        <Space>
          <span style={{ color: meta.color, fontSize: 15 }}>{meta.icon}</span>
          <span style={{ fontWeight: 700 }}>{item.label}</span>
          <Tag color={meta.tag}>{meta.text}</Tag>
          {item.custom && <Tag color="purple">自定义</Tag>}
        </Space>
      }
      extra={<Tag>{item.cat}</Tag>}
    >
      {/* 汇总条 */}
      {showSummary && (
        <div className="detect-summary">
          {struct.summary && (
            <span className="detect-summary-main">
              <DatabaseOutlined style={{ marginRight: 5, opacity: 0.7 }} />
              {struct.summary}
            </span>
          )}
          {item.note && <span className="detect-summary-note">{item.note}</span>}
        </div>
      )}

      {/* 结构化视图 */}
      <div style={{ marginTop: 10 }}>
        {struct.type === 'table' && struct.rows?.length > 0 && <TableView struct={struct} />}
        {struct.type === 'kv' && struct.pairs?.length > 0 && <KvView struct={struct} />}
        {struct.type === 'bars' && struct.bars?.length > 0 && <BarsView struct={struct} />}
        {(struct.type === 'logs' || struct.type === 'lines') && struct.rows?.length > 0 && (
          <LinesView struct={struct} />
        )}
        {(!struct.rows?.length && !struct.pairs?.length && !struct.bars?.length) && (
          <Typography.Text type="secondary">无可解析的结构化数据</Typography.Text>
        )}
      </div>

      {/* 源文 */}
      <Collapse
        ghost
        size="small"
        style={{ marginTop: 10 }}
        items={[
          {
            key: 'raw',
            label: (
              <span style={{ fontSize: 12, opacity: 0.72 }}>
                源文 · <code>{item.command}</code>
                {item.output ? `（${item.output.split('\n').length} 行）` : ''}
              </span>
            ),
            children: <pre className="detect-raw">{item.output || '(无输出)'}</pre>,
          },
        ]}
      />
    </Card>
  );
}
