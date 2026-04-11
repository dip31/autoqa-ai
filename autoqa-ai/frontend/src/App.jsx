import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Sidebar from './components/Sidebar';
import DevSidebar from './components/DevSidebar';
import Chatbot from './components/Chatbot';
import Dashboard from './pages/Dashboard';
import TestCaseReview from './pages/TestCaseReview';
import WebsiteTesting from './pages/WebsiteTesting';
import TestGenerator from './pages/TestGenerator';
import SmartReport from './pages/SmartReport';
import Login from './pages/Login';
import Register from './pages/Register';
import AutonomousQA from './pages/AutonomousQA';
import DevDashboard from './pages/dev/DevDashboard';
import DevProjects from './pages/dev/DevProjects';
import DevDiagrams from './pages/dev/DevDiagrams';
import DevCodeGen from './pages/dev/DevCodeGen';
import DevMessages from './pages/dev/DevMessages';
import QAMessages from './pages/QAMessages';
import GithubIntelligence from './pages/GithubIntelligence';
import { MdMenu } from 'react-icons/md';

/* ── QA Layout (existing) ────────────────────────────────────────────────── */
function QALayout() {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      {open && <div className="fixed inset-0 bg-black/40 z-30 lg:hidden" onClick={() => setOpen(false)} />}
      <div className={`fixed lg:static inset-y-0 left-0 z-40 transition-transform duration-300 ${open ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}>
        <Sidebar onClose={() => setOpen(false)} />
      </div>
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <div className="lg:hidden flex items-center gap-3 px-4 py-3 bg-white border-b border-slate-200 shrink-0">
          <button onClick={() => setOpen(true)} className="p-2 rounded-lg hover:bg-slate-100">
            <MdMenu className="text-slate-600 text-xl" />
          </button>
          <p className="text-sm font-semibold text-slate-800">AutoQA AI</p>
        </div>
        <main className="flex-1 overflow-y-auto">
          <Routes>
            <Route path="/"                element={<Dashboard />} />
            <Route path="/test-review"     element={<TestCaseReview />} />
            <Route path="/website-testing" element={<WebsiteTesting />} />
            <Route path="/test-generator"  element={<TestGenerator />} />
            <Route path="/smart-report"    element={<SmartReport />} />
            <Route path="/autonomous-qa"   element={<AutonomousQA />} />
            <Route path="/messages"         element={<QAMessages />} />
            <Route path="/github-intelligence" element={<GithubIntelligence />} />
          </Routes>
        </main>
      </div>
      <Chatbot />
    </div>
  );
}

/* ── Developer Layout ────────────────────────────────────────────────────── */
function DevLayout() {
  const [open, setOpen] = useState(false);
  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      {open && <div className="fixed inset-0 bg-black/40 z-30 lg:hidden" onClick={() => setOpen(false)} />}
      <div className={`fixed lg:static inset-y-0 left-0 z-40 transition-transform duration-300 ${open ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}>
        <DevSidebar onClose={() => setOpen(false)} />
      </div>
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <div className="lg:hidden flex items-center gap-3 px-4 py-3 bg-white border-b border-slate-200 shrink-0">
          <button onClick={() => setOpen(true)} className="p-2 rounded-lg hover:bg-slate-100">
            <MdMenu className="text-slate-600 text-xl" />
          </button>
          <p className="text-sm font-semibold text-slate-800">DevPortal</p>
        </div>
        <main className="flex-1 overflow-y-auto">
          <Routes>
            <Route path="/dev"           element={<DevDashboard />} />
            <Route path="/dev/projects"  element={<DevProjects />} />
            <Route path="/dev/diagrams"  element={<DevDiagrams />} />
            <Route path="/dev/code"      element={<DevCodeGen />} />
            <Route path="/dev/messages"  element={<DevMessages />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

/* ── Protected Router — role-aware ───────────────────────────────────────── */
function ProtectedRouter() {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="w-10 h-10 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  if (user.role === 'developer') return <DevLayout />;
  return <QALayout />;
}

function AuthRedirect({ children }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (user) return <Navigate to={user.role === 'developer' ? '/dev' : '/'} replace />;
  return children;
}

export default function App() {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AuthProvider>
        <Routes>
          <Route path="/login"    element={<AuthRedirect><Login /></AuthRedirect>} />
          <Route path="/register" element={<AuthRedirect><Register /></AuthRedirect>} />
          <Route path="/*"        element={<ProtectedRouter />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
