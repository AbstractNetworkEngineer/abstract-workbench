import React from 'react';

/**
 * 放射状拓扑图（SVG）：自身在中心，邻居沿圆周排布，连线标两端标识。
 * 主动发现（LLDP/CDP CLI）与被动发现（抓包）共用同一渲染。
 *
 * data = { self: {label, ip}, nodes: [{id,label,kind,ip}], links: [{from,to,local_if,remote_if,proto}] }
 */
export default function TopologySvg({ data, height = 520 }) {
  const nodes = data.nodes || [];
  const links = data.links || [];
  const W = 860;
  const H = height;
  const cx = W / 2;
  const cy = H / 2;
  const R = Math.min(W, H) * 0.34;

  const others = nodes.filter((n) => n.kind !== 'self');
  const pos = { __self__: { x: cx, y: cy } };
  others.forEach((n, i) => {
    const a = (i / Math.max(others.length, 1)) * Math.PI * 2 - Math.PI / 2;
    pos[n.id] = { x: cx + R * Math.cos(a), y: cy + R * Math.sin(a) };
  });

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      width="100%"
      style={{ display: 'block', background: 'rgba(11,18,32,0.5)', borderRadius: 10 }}
    >
      <defs>
        <radialGradient id="selfGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#2f81f7" stopOpacity="0.42" />
          <stop offset="100%" stopColor="#2f81f7" stopOpacity="0" />
        </radialGradient>
        <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
          <path d="M0,0 L8,4 L0,8 Z" fill="#58a6ff" />
        </marker>
      </defs>

      <circle cx={cx} cy={cy} r={R * 0.85} fill="url(#selfGlow)" />

      {links.map((l, i) => {
        const a = pos[l.from] || pos.__self__;
        const b = pos[l.to];
        if (!b) return null;
        const mx = (a.x + b.x) / 2;
        const my = (a.y + b.y) / 2;
        return (
          <g key={i}>
            <line
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke="#58a6ff"
              strokeWidth="1.6"
              strokeOpacity="0.75"
              markerEnd="url(#arrow)"
            />
            <text
              x={mx}
              y={my - 6}
              fill="#8fd3ff"
              fontSize="10"
              fontFamily="Consolas, monospace"
              textAnchor="middle"
            >
              {l.local_if}
              {l.remote_if ? ` ↔ ${l.remote_if}` : ''}
            </text>
            <text x={mx} y={my + 10} fill="#8b949e" fontSize="9" textAnchor="middle">
              {l.proto?.toUpperCase()}
            </text>
          </g>
        );
      })}

      <g>
        <circle cx={cx} cy={cy} r="38" fill="#2f81f7" fillOpacity="0.22" stroke="#2f81f7" strokeWidth="2" />
        <text x={cx} y={cy - 4} fill="#c9e0ff" fontSize="13" fontWeight="700" textAnchor="middle">
          {data.self?.label?.slice(0, 14) || '本机'}
        </text>
        <text x={cx} y={cy + 13} fill="#7ee787" fontSize="10" textAnchor="middle" fontFamily="Consolas, monospace">
          {data.self?.ip || '(采集点)'}
        </text>
      </g>

      {others.map((n) => {
        const p = pos[n.id];
        return (
          <g key={n.id}>
            <circle cx={p.x} cy={p.y} r="30" fill="rgba(126,231,135,0.14)" stroke="#7ee787" strokeWidth="1.6" />
            <text x={p.x} y={p.y - 3} fill="#d7e0ee" fontSize="11" fontWeight="600" textAnchor="middle">
              {n.label?.slice(0, 12)}
            </text>
            <text x={p.x} y={p.y + 12} fill="#8b949e" fontSize="9" textAnchor="middle" fontFamily="Consolas, monospace">
              {n.ip || n.vendor || '邻居'}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
