import React from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import Shell from './layout/Shell';
import Dashboard from './pages/Dashboard';
import Workbench from './pages/Workbench';
import Devices from './pages/Devices';
import Backups from './pages/Backups';
import Strategies from './pages/Strategies';
import Inspect from './pages/Inspect';
import Topology from './pages/Topology';
import Capture from './pages/Capture';
import Drift from './pages/Drift';
import Detect from './pages/Detect';
import Audit from './pages/Audit';
import Settings from './pages/Settings';

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/workbench" element={<Workbench />} />
        <Route path="/devices" element={<Devices />} />
        <Route path="/backups" element={<Backups />} />
        <Route path="/strategies" element={<Strategies />} />
        <Route path="/inspect" element={<Inspect />} />
        <Route path="/topology" element={<Topology />} />
        <Route path="/capture" element={<Capture />} />
        <Route path="/drift" element={<Drift />} />
        <Route path="/detect" element={<Detect />} />
        <Route path="/audit" element={<Audit />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
