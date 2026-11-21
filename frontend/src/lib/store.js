import { useCallback, useEffect, useState } from 'react';

/**
 * 跨路由状态存储。
 *
 * 问题：React Router 切换页面会卸载组件，`useState` 里的结果全部丢失 ——
 * 检测报告、巡检结果、抓包分析、拓扑图、日志，换个模块回来就没了。
 *
 * 这里用「内存缓存 + sessionStorage」双写：路由切走组件卸载，数据仍在；
 * 刷新页面后 sessionStorage 还能兜底恢复。
 */

const cache = new Map();
const listeners = new Map();
const PREFIX = 'netdeck::';

function read(key) {
  try {
    const raw = sessionStorage.getItem(PREFIX + key);
    return raw === null ? undefined : JSON.parse(raw);
  } catch {
    return undefined;
  }
}

export function getState(key, fallback = null) {
  if (!cache.has(key)) {
    const v = read(key);
    cache.set(key, v === undefined ? fallback : v);
  }
  return cache.get(key);
}

export function setState(key, value) {
  cache.set(key, value);
  try {
    sessionStorage.setItem(PREFIX + key, JSON.stringify(value ?? null));
  } catch {
    /* 超出配额时静默降级为仅内存 */
  }
  const set = listeners.get(key);
  if (set) set.forEach((fn) => fn(value));
}

export function clearState(key) {
  setState(key, null);
}

/** React 绑定：`const [v, setV] = useStore('detect.result', null)` */
export function useStore(key, fallback = null) {
  const [v, setV] = useState(() => getState(key, fallback));

  useEffect(() => {
    if (!listeners.has(key)) listeners.set(key, new Set());
    const fn = (nv) => setV(nv);
    listeners.get(key).add(fn);
    // 挂载时同步一次，防止别的地方改了而本组件没跟上
    setV(getState(key, fallback));
    return () => {
      const s = listeners.get(key);
      if (s) s.delete(fn);
    };
  }, [key, fallback]);

  const set = useCallback(
    (next) => {
      const val = typeof next === 'function' ? next(getState(key, fallback)) : next;
      setState(key, val);
    },
    [key, fallback]
  );

  return [v, set];
}
