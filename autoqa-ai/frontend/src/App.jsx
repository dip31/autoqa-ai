import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import Sidebar from './components/Sidebar';
import Chatbot from './components/Chatbot';
import Dashboard from './pages/Dashboard';
import TestCaseReview from './pages/TestCaseReview';
import CodeReview from './pages/CodeReview';
import WebsiteTesting from './pages/WebsiteTesting';
import TestGenerator from './pages/TestGenerator';
import RiskPrediction from './pages/RiskPrediction';
import SmartReport from './pages/SmartReport';
import Login from './pages/Login';
import Register from './pages/Register';
import { MdMenu } from 'react-icons/md';

function ProtectedLayout() {
  const { user, loading } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="w-10 h-10 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin" />
      </div>
    );
  }

  if (!user) return <Navigate to="/login" replace />;

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      {sidebarOpen && (
        <div className="fixed inset-0 bg-black/40 z-30 lg:hidden" onClick={() => setSidebarOpen(false)} />
      )}
      <div className={`fixed lg:static inset-y-0 left-0 z-40 transition-transform duration-300 ${sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}>
        <Sidebar onClose={() => setSidebarOpen(false)} />
      </div>
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <div className="lg:hidden flex items-center gap-3 px-4 py-3 bg-white border-b border-slate-200 shrink-0">
          <button onClick={() => setSidebarOpen(true)} className="p-2 rounded-lg hover:bg-slate-100 transition-colors">
            <MdMenu className="text-slate-600 text-xl" />
          </button>
          <p className="text-sm font-semibold text-slate-800">AutoQA AI</p>
        </div>
        <main className="flex-1 overflow-y-auto">
          <Routes>
            <Route path="/"                element={<Dashboard />} />
            <Route path="/test-review"     element={<TestCaseReview />} />
            <Route path="/code-review"     element={<CodeReview />} />
            <Route path="/website-testing" element={<WebsiteTesting />} />
            <Route path="/test-generator"  element={<TestGenerator />} />
            <Route path="/risk-prediction" element={<RiskPrediction />} />
            <Route path="/smart-report"    element={<SmartReport />} />
          </Routes>
        </main>
      </div>
      <Chatbot />
    </div>
  );
}

function AuthRedirect({ children }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (user) return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login"    element={<AuthRedirect><Login /></AuthRedirect>} />
          <Route path="/register" element={<AuthRedirect><Register /></AuthRedirect>} />
          <Route path="/*"        element={<ProtectedLayout />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
