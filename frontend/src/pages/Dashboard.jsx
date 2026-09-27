import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getMe } from '../api/client';
import { useAuth } from '../context/AuthContext';
import {
  MdOutlineFactCheck, MdOutlineCode, MdOutlineLanguage,
  MdOutlineAutoAwesome, MdOutlineRadar, MdOutlineAssessment,
  MdArrowForward, MdOutlineChat, MdOutlineTrendingUp,
  MdOutlineSpeed, MdOutlineVerified, MdOutlineIntegrationInstructions,
  MdSend,
} from 'react-icons/md';
import {
  RiRobot2Line, RiShieldCheckLine, RiCodeSSlashLine,
  RiTestTubeLine, RiBarChartBoxLine, RiGlobalLine, RiBrainLine,
} from 'react-icons/ri';

const features = [
  {
    to: '/test-review', icon: RiTestTubeLine, color: 'bg-blue-600', light: 'bg-blue-50 text-blue-700 border-blue-200',
    title: 'Test Case Review', desc: 'AI analyzes your manual test cases for completeness, clarity, missing edge cases, and ambiguity — then rewrites them better.',
    tags: ['Completeness Check', 'Edge Cases', 'AI Rewrite'],
  },
  {
    to: '/website-testing', icon: RiGlobalLine, color: 'bg-cyan-600', light: 'bg-cyan-50 text-cyan-700 border-cyan-200',
    title: 'Website Testing', desc: 'Launches a real browser via Playwright, scans forms, buttons, and inputs, then generates functional and UI test cases automatically.',
    tags: ['Playwright', 'UI Tests', 'Auto-Generated'],
  },
  {
    to: '/autonomous-qa', icon: RiRobot2Line, color: 'bg-emerald-600', light: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    title: 'Autonomous QA', desc: 'AI autonomously understands requirements, generates tests, executes browser flows, analyzes failures, predicts risks, and creates a report.',
    tags: ['AI Orchestration', 'Self-Driven Testing', 'Smart Report'],
  },
  {
    to: '/test-generator', icon: MdOutlineAutoAwesome, color: 'bg-indigo-600', light: 'bg-indigo-50 text-indigo-700 border-indigo-200',
    title: 'Test Generator', desc: 'Paste a requirement or user story and get positive, negative, boundary, and UI test cases in a structured table format.',
    tags: ['4 Test Types', 'Table Format', 'Excel Export'],
  },
  {
    to: '/smart-report', icon: RiBarChartBoxLine, color: 'bg-emerald-600', light: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    title: 'Smart Report', desc: 'Aggregates all your activity into an executive QA report with quality scores, coverage analysis, and actionable recommendations.',
    tags: ['Quality Score', 'Coverage', 'Excel Export'],
  },
];

const techStack = [
  { label: 'React.js',    color: 'bg-blue-100 text-blue-700' },
  { label: 'Flask',       color: 'bg-slate-100 text-slate-700' },
  { label: 'MySQL',       color: 'bg-orange-100 text-orange-700' },
  { label: 'Groq LLaMA', color: 'bg-violet-100 text-violet-700' },
  { label: 'Gemini AI',   color: 'bg-blue-100 text-blue-800' },
  { label: 'Playwright',  color: 'bg-green-100 text-green-700' },
  { label: 'JWT Auth',    color: 'bg-red-100 text-red-700' },
  { label: 'Tailwind CSS',color: 'bg-cyan-100 text-cyan-700' },
];

const highlights = [
  { icon: MdOutlineSpeed,                  label: 'Fast AI Responses',    desc: 'Groq LLaMA 3.3 delivers sub-second AI analysis' },
  { icon: RiShieldCheckLine,               label: 'Secure by Default',    desc: 'JWT auth, bcrypt passwords, per-user data isolation' },
  { icon: MdOutlineIntegrationInstructions,label: 'Multi-Agent System',   desc: '4 specialized AI agents working in parallel' },
  { icon: MdOutlineVerified,               label: 'Production Ready',     desc: 'MySQL persistence, error handling, Excel exports' },
];

export default function Dashboard() {
  const { user } = useAuth();
  const [stats, setStats] = useState({ test_cases: 0, code_reviews: 0, website_tests: 0 });

  useEffect(() => {
    getMe().then(res => setStats(res.data.stats || {})).catch(() => {});
  }, []);

  return (
    <div className="w-full">
      {/* ── Hero ── */}
      <div className="bg-gradient-to-br from-slate-900 via-blue-950 to-violet-950 px-6 sm:px-10 py-12 sm:py-16 relative overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-blue-600/10 rounded-full blur-3xl" />
        <div className="absolute bottom-0 left-0 w-96 h-96 bg-violet-600/10 rounded-full blur-3xl" />
        <div className="relative z-10 max-w-4xl">
          <div className="inline-flex items-center gap-2 bg-blue-500/20 border border-blue-400/30 rounded-full px-4 py-1.5 mb-5">
            <span className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse" />
            <span className="text-blue-200 text-xs font-medium">Multi-Agent AI QA Platform</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-bold text-white leading-tight mb-4">
            Welcome back, <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-violet-400">{user?.username}</span>
          </h1>
          <p className="text-slate-400 text-base sm:text-lg max-w-2xl leading-relaxed mb-8">
            AutoQA AI is your intelligent QA automation platform — review test cases, test websites, and generate reports using cutting-edge AI.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link to="/test-review"
              className="flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-xl transition-colors shadow-lg">
              Get Started <MdArrowForward />
            </Link>
            <button
              onClick={() => document.querySelector('[title="AutoQA Assistant"]')?.click()}
              className="flex items-center gap-2 px-5 py-2.5 bg-white/10 hover:bg-white/20 border border-white/20 text-white text-sm font-semibold rounded-xl transition-colors">
              <MdOutlineChat /> Ask AI Assistant
            </button>
          </div>
        </div>
      </div>

      <div className="p-4 sm:p-6 lg:p-8 w-full space-y-8">

        {/* ── User Activity Stats ── */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div className="flex-1">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Your Activity</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label: 'Test Cases Reviewed', value: stats.test_cases,    icon: RiTestTubeLine,    color: 'text-blue-600',    bg: 'bg-blue-50' },
                { label: 'Website Tests',        value: stats.website_tests, icon: RiGlobalLine,      color: 'text-cyan-600',    bg: 'bg-cyan-50' },
                { label: 'AI Agents Active',     value: 6,                   icon: RiBrainLine,       color: 'text-emerald-600', bg: 'bg-emerald-50' },
              ].map(({ label, value, icon: Icon, color, bg }) => (
                <div key={label} className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex items-center gap-3">
                  <div className={`w-10 h-10 ${bg} rounded-lg flex items-center justify-center shrink-0`}>
                    <Icon className={`${color} text-xl`} />
                  </div>
                  <div>
                    <p className="text-xl font-bold text-slate-800">{value}</p>
                    <p className="text-xs text-slate-500 leading-tight">{label}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <Link to="/smart-report"
            className="flex items-center gap-2 px-6 py-3 bg-amber-500 hover:bg-amber-600 text-white text-sm font-bold rounded-xl transition-all shadow-lg shadow-amber-200 shrink-0">
            <MdSend className="text-lg" /> Share Reports with Developers
          </Link>
        </div>

        {/* ── Feature Cards ── */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Platform Features</p>
            <span className="text-xs text-slate-400">4 AI-powered tools</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {features.map(({ to, icon: Icon, color, light, title, desc, tags }) => (
              <Link key={to} to={to}
                className="bg-white border border-slate-200 rounded-xl p-5 hover:shadow-md hover:-translate-y-0.5 transition-all group flex flex-col">
                <div className={`w-10 h-10 ${color} rounded-xl flex items-center justify-center mb-4 shadow-sm`}>
                  <Icon className="text-white text-xl" />
                </div>
                <h3 className="text-sm font-semibold text-slate-800 mb-2">{title}</h3>
                <p className="text-xs text-slate-500 leading-relaxed flex-1 mb-4">{desc}</p>
                <div className="flex flex-wrap gap-1.5 mb-4">
                  {tags.map(tag => (
                    <span key={tag} className={`text-xs px-2 py-0.5 rounded-full border font-medium ${light}`}>{tag}</span>
                  ))}
                </div>
                <div className="flex items-center gap-1 text-xs text-blue-600 font-semibold group-hover:gap-2 transition-all">
                  Open tool <MdArrowForward />
                </div>
              </Link>
            ))}
          </div>
        </div>

        {/* ── Why AutoQA AI ── */}
        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Why AutoQA AI</p>
          <h2 className="text-lg font-bold text-slate-800 mb-5">Built for modern QA teams</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {highlights.map(({ icon: Icon, label, desc }) => (
              <div key={label} className="flex flex-col gap-3 p-4 bg-slate-50 rounded-xl border border-slate-200">
                <div className="w-9 h-9 bg-blue-100 rounded-lg flex items-center justify-center">
                  <Icon className="text-blue-600 text-lg" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-800">{label}</p>
                  <p className="text-xs text-slate-500 mt-1 leading-relaxed">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ── How It Works ── */}
        <div className="bg-gradient-to-r from-slate-800 to-slate-900 rounded-2xl p-6 sm:p-8">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">How It Works</p>
          <h2 className="text-lg font-bold text-white mb-6">Three steps to better QA</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            {[
              { step: '01', title: 'Input your content', desc: 'Paste test cases, code, a URL, or a requirement description into any tool.' },
              { step: '02', title: 'AI analyzes instantly', desc: 'Our multi-agent system processes your input using Groq LLaMA 3.3 for fast, accurate results.' },
              { step: '03', title: 'Get actionable output', desc: 'Receive scores, issues, suggestions, optimized code, and exportable reports.' },
            ].map(({ step, title, desc }) => (
              <div key={step} className="flex gap-4">
                <div className="w-10 h-10 bg-blue-600/20 border border-blue-500/30 rounded-xl flex items-center justify-center shrink-0 text-blue-400 font-bold text-sm">{step}</div>
                <div>
                  <p className="text-white text-sm font-semibold mb-1">{title}</p>
                  <p className="text-slate-400 text-xs leading-relaxed">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ── Tech Stack ── */}
        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
          <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-4">Technology Stack</p>
          <div className="flex flex-wrap gap-2">
            {techStack.map(({ label, color }) => (
              <span key={label} className={`text-xs font-semibold px-3 py-1.5 rounded-full ${color}`}>{label}</span>
            ))}
          </div>
        </div>

        {/* ── Chatbot CTA ── */}
        <div className="bg-gradient-to-r from-blue-600 to-violet-600 rounded-2xl p-6 sm:p-8 flex flex-col sm:flex-row items-start sm:items-center gap-5 shadow-lg">
          <div className="w-14 h-14 bg-white/20 rounded-2xl flex items-center justify-center shrink-0 ring-2 ring-white/30">
            <RiRobot2Line className="text-white text-3xl" />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-white font-bold text-base sm:text-lg">AutoQA Assistant is ready to help</p>
            <p className="text-blue-100 text-sm mt-1">Ask anything about QA best practices, test strategies, code quality, or how to use any feature — powered by Gemini AI with full chat history.</p>
          </div>
          <button
            onClick={() => document.querySelector('[title="AutoQA Assistant"]')?.click()}
            className="flex items-center gap-2 bg-white hover:bg-blue-50 text-blue-700 font-semibold px-5 py-3 rounded-xl text-sm transition-colors shadow-md shrink-0 w-full sm:w-auto justify-center">
            <MdOutlineChat className="text-lg" /> Start Chatting
          </button>
        </div>

      </div>
    </div>
  );
}
