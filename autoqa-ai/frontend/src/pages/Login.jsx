import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { login } from '../api/client';
import { useAuth } from '../context/AuthContext';
import {
  MdOutlineEmail, MdLockOutline, MdErrorOutline,
  MdArrowForward, MdOutlineVisibility, MdOutlineVisibilityOff,
} from 'react-icons/md';
import {
  RiRobot2Line, RiShieldCheckLine, RiCodeSSlashLine,
  RiTestTubeLine, RiBarChartBoxLine, RiGithubFill,
} from 'react-icons/ri';

const features = [
  { icon: RiTestTubeLine,      label: 'AI Test Case Review',    desc: 'Analyze completeness & edge cases' },
  { icon: RiCodeSSlashLine,    label: 'Smart Code Review',      desc: 'Multi-language quality analysis' },
  { icon: RiShieldCheckLine,   label: 'Bug Risk Prediction',    desc: 'Predict & prevent failures early' },
  { icon: RiBarChartBoxLine,   label: 'Smart QA Reports',       desc: 'Export insights to Excel & PDF' },
];

export default function Login() {
  const [form, setForm]       = useState({ email: '', password: '' });
  const [error, setError]     = useState('');
  const [loading, setLoading] = useState(false);
  const [showPwd, setShowPwd] = useState(false);
  const { signIn }  = useAuth();
  const navigate    = useNavigate();
  const location    = useLocation();

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const token = params.get('token');
    if (token) {
      const user = {
        id: params.get('id'),
        username: params.get('username'),
        email: params.get('email'),
        role: params.get('role')
      };
      signIn(token, user);
      navigate('/');
    }
  }, [location, signIn, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(''); setLoading(true);
    try {
      const res = await login(form);
      signIn(res.data.token, res.data.user);
      navigate('/');
    } catch (err) {
      setError(err.response?.data?.error || 'Login failed. Please try again.');
    } finally { setLoading(false); }
  };

  const handleGithubLogin = () => {
    window.location.href = 'http://localhost:5001/auth/github/login';
  };

  return (
    <div className="min-h-screen flex">
      {/* ── Left panel ── */}
      <div className="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-slate-900 via-blue-950 to-violet-950 flex-col justify-between p-12 relative overflow-hidden">
        {/* Background blobs */}
        <div className="absolute top-0 left-0 w-96 h-96 bg-blue-600/20 rounded-full blur-3xl -translate-x-1/2 -translate-y-1/2" />
        <div className="absolute bottom-0 right-0 w-96 h-96 bg-violet-600/20 rounded-full blur-3xl translate-x-1/2 translate-y-1/2" />

        {/* Logo */}
        <div className="relative z-10 flex items-center gap-3">
          <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center shadow-lg">
            <RiRobot2Line className="text-white text-xl" />
          </div>
          <div>
            <p className="text-white font-bold text-lg leading-tight">AutoQA AI</p>
            <p className="text-blue-300 text-xs">Intelligent QA Platform</p>
          </div>
        </div>

        {/* Hero text */}
        <div className="relative z-10">
          <div className="inline-flex items-center gap-2 bg-blue-500/20 border border-blue-400/30 rounded-full px-4 py-1.5 mb-6">
            <span className="w-2 h-2 bg-emerald-400 rounded-full animate-pulse" />
            <span className="text-blue-200 text-xs font-medium">Powered by Groq LLaMA 3.3 & Gemini AI</span>
          </div>
          <h2 className="text-4xl font-bold text-white leading-tight mb-4">
            Automate your QA<br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-violet-400">
              with AI precision
            </span>
          </h2>
          <p className="text-slate-400 text-base leading-relaxed mb-10">
            Review test cases, analyze code quality, predict bug risks, and generate comprehensive reports — all in one intelligent platform.
          </p>

          {/* Feature list */}
          <div className="grid grid-cols-2 gap-4">
            {features.map(({ icon: Icon, label, desc }) => (
              <div key={label} className="flex items-start gap-3 bg-white/5 border border-white/10 rounded-xl p-4 backdrop-blur-sm">
                <div className="w-8 h-8 bg-blue-500/20 rounded-lg flex items-center justify-center shrink-0">
                  <Icon className="text-blue-400 text-base" />
                </div>
                <div>
                  <p className="text-white text-xs font-semibold">{label}</p>
                  <p className="text-slate-400 text-xs mt-0.5">{desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Bottom quote */}
        <div className="relative z-10 border-t border-white/10 pt-6">
          <p className="text-slate-400 text-sm italic">"AutoQA AI reduced our bug escape rate by 60% in the first month."</p>
          <p className="text-slate-500 text-xs mt-2">— QA Lead, Software Team</p>
        </div>
      </div>

      {/* ── Right panel ── */}
      <div className="flex-1 flex items-center justify-center p-6 bg-slate-50">
        <div className="w-full max-w-md">
          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-3 mb-8">
            <div className="w-9 h-9 bg-blue-600 rounded-xl flex items-center justify-center">
              <RiRobot2Line className="text-white text-lg" />
            </div>
            <p className="text-slate-800 font-bold text-lg">AutoQA AI</p>
          </div>

          <div className="mb-8">
            <h1 className="text-2xl font-bold text-slate-800">Sign in</h1>
            <p className="text-slate-500 text-sm mt-1">Welcome back — enter your credentials to continue</p>
          </div>

          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8">
            {error && (
              <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm mb-6">
                <MdErrorOutline className="text-red-500 shrink-0 text-lg" />
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">Email address</label>
                <div className="relative">
                  <MdOutlineEmail className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-lg" />
                  <input
                    type="email" required placeholder="you@example.com"
                    value={form.email}
                    onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                    className="w-full pl-11 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-800 placeholder-slate-400 focus:border-blue-400 focus:ring-2 focus:ring-blue-100 focus:outline-none transition"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">Password</label>
                <div className="relative">
                  <MdLockOutline className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-lg" />
                  <input
                    type={showPwd ? 'text' : 'password'} required placeholder="••••••••"
                    value={form.password}
                    onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                    className="w-full pl-11 pr-11 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-800 placeholder-slate-400 focus:border-blue-400 focus:ring-2 focus:ring-blue-100 focus:outline-none transition"
                  />
                  <button type="button" onClick={() => setShowPwd(s => !s)}
                    className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors">
                    {showPwd ? <MdOutlineVisibilityOff className="text-lg" /> : <MdOutlineVisibility className="text-lg" />}
                  </button>
                </div>
              </div>

              <button type="submit" disabled={loading}
                className="w-full flex items-center justify-center gap-2 py-3 bg-gradient-to-r from-blue-600 to-violet-600 hover:from-blue-700 hover:to-violet-700 disabled:opacity-50 text-white font-semibold rounded-xl text-sm transition-all shadow-md hover:shadow-lg mt-2">
                {loading ? (
                  <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Signing in...</>
                ) : (
                  <>Sign In <MdArrowForward /></>
                )}
              </button>
            </form>

            <div className="relative my-6">
              <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-slate-200" /></div>
              <div className="relative flex justify-center"><span className="bg-white px-3 text-xs text-slate-400">Or continue with</span></div>
            </div>

            <button
              onClick={handleGithubLogin}
              className="w-full flex items-center justify-center gap-2 py-3 border-2 border-slate-200 hover:border-slate-300 hover:bg-slate-50 text-slate-700 font-semibold rounded-xl text-sm transition-all"
            >
              <RiGithubFill className="text-xl" />
              Continue with GitHub
            </button>

            <div className="relative my-6">
              <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-slate-200" /></div>
              <div className="relative flex justify-center"><span className="bg-white px-3 text-xs text-slate-400">New to AutoQA AI?</span></div>
            </div>

            <Link to="/register"
              className="w-full flex items-center justify-center gap-2 py-3 border-2 border-slate-200 hover:border-blue-300 hover:bg-blue-50 text-slate-700 hover:text-blue-700 font-semibold rounded-xl text-sm transition-all">
              Create a free account <MdArrowForward />
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
