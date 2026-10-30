import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { register } from '../api/client';
import { useAuth } from '../context/AuthContext';
import {
  MdOutlineEmail, MdLockOutline, MdPersonOutline,
  MdErrorOutline, MdCheckCircleOutline, MdArrowForward,
  MdOutlineVisibility, MdOutlineVisibilityOff,
} from 'react-icons/md';
import { RiRobot2Line, RiShieldCheckLine, RiGithubFill } from 'react-icons/ri';

const perks = [
  'AI-powered test case review & generation',
  'Multi-language code quality analysis',
  'Automated website testing with Playwright',
  'Bug risk prediction with reduction plans',
  'Smart QA reports with Excel export',
  'Personal AI assistant with chat history',
];

export default function Register() {
  const [form, setForm]       = useState({ username: '', email: '', password: '', confirm: '' });
  const [role, setRole]       = useState('qa_engineer');
  const [error, setError]     = useState('');
  const [loading, setLoading] = useState(false);
  const [showPwd, setShowPwd] = useState(false);
  const { signIn }  = useAuth();
  const navigate    = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    if (form.password !== form.confirm) { setError('Passwords do not match'); return; }
    if (form.password.length < 6)       { setError('Password must be at least 6 characters'); return; }
    setLoading(true);
    try {
      const res = await register({ username: form.username, email: form.email, password: form.password, role });
      signIn(res.data.token, res.data.user);
      navigate('/');
    } catch (err) {
      setError(err.response?.data?.error || 'Registration failed. Please try again.');
    } finally { setLoading(false); }
  };

  const handleGithubLogin = () => {
    window.location.href = 'http://localhost:5001/auth/github/login';
  };

  const strength = form.password.length === 0 ? 0 : form.password.length < 6 ? 1 : form.password.length < 10 ? 2 : 3;
  const strengthLabel = ['', 'Weak', 'Good', 'Strong'];
  const strengthColor = ['', 'bg-red-400', 'bg-amber-400', 'bg-emerald-500'];
  const strengthText  = ['', 'text-red-500', 'text-amber-500', 'text-emerald-600'];

  return (
    <div className="min-h-screen flex">
      {/* ── Left panel ── */}
      <div className="hidden lg:flex lg:w-5/12 bg-gradient-to-br from-slate-900 via-blue-950 to-violet-950 flex-col justify-between p-12 relative overflow-hidden">
        <div className="absolute top-0 right-0 w-80 h-80 bg-violet-600/20 rounded-full blur-3xl translate-x-1/2 -translate-y-1/2" />
        <div className="absolute bottom-0 left-0 w-80 h-80 bg-blue-600/20 rounded-full blur-3xl -translate-x-1/2 translate-y-1/2" />

        <div className="relative z-10 flex items-center gap-3">
          <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center shadow-lg">
            <RiRobot2Line className="text-white text-xl" />
          </div>
          <div>
            <p className="text-white font-bold text-lg leading-tight">AutoQA AI</p>
            <p className="text-blue-300 text-xs">Intelligent QA Platform</p>
          </div>
        </div>

        <div className="relative z-10">
          <h2 className="text-3xl font-bold text-white leading-tight mb-3">
            Everything you need<br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-violet-400">
              for smarter QA
            </span>
          </h2>
          <p className="text-slate-400 text-sm mb-8">Join thousands of QA engineers using AI to ship better software faster.</p>

          <div className="space-y-3">
            {perks.map((perk) => (
              <div key={perk} className="flex items-center gap-3">
                <div className="w-5 h-5 bg-emerald-500/20 rounded-full flex items-center justify-center shrink-0">
                  <MdCheckCircleOutline className="text-emerald-400 text-sm" />
                </div>
                <p className="text-slate-300 text-sm">{perk}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="relative z-10 flex items-center gap-3 bg-white/5 border border-white/10 rounded-xl p-4">
          <RiShieldCheckLine className="text-emerald-400 text-2xl shrink-0" />
          <div>
            <p className="text-white text-xs font-semibold">Secure & Private</p>
            <p className="text-slate-400 text-xs">Your data is encrypted and never shared</p>
          </div>
        </div>
      </div>

      {/* ── Right panel ── */}
      <div className="flex-1 flex items-center justify-center p-6 bg-slate-50 overflow-y-auto">
        <div className="w-full max-w-md py-8">
          <div className="lg:hidden flex items-center gap-3 mb-8">
            <div className="w-9 h-9 bg-blue-600 rounded-xl flex items-center justify-center">
              <RiRobot2Line className="text-white text-lg" />
            </div>
            <p className="text-slate-800 font-bold text-lg">AutoQA AI</p>
          </div>

          <div className="mb-8">
            <h1 className="text-2xl font-bold text-slate-800">Create your account</h1>
            <p className="text-slate-500 text-sm mt-1">Free forever — no credit card required</p>
          </div>

          <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8">
            {error && (
              <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 rounded-xl px-4 py-3 text-sm mb-6">
                <MdErrorOutline className="text-red-500 shrink-0 text-lg" />
                {error}
              </div>
            )}

            {/* Role picker */}
            <div className="mb-6">
              <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-3">I am a…</label>
              <div className="grid grid-cols-2 gap-3">
                {[
                  { value: 'qa_engineer', emoji: '🧪', label: 'QA Engineer', desc: 'Test, review & automate' },
                  { value: 'developer',   emoji: '💻', label: 'Developer',   desc: 'Build & generate code' },
                ].map(r => (
                  <button
                    key={r.value} type="button" onClick={() => setRole(r.value)}
                    className={`p-4 rounded-xl border-2 text-left transition-all ${
                      role === r.value
                        ? 'border-blue-500 bg-blue-50'
                        : 'border-slate-200 bg-slate-50 hover:border-slate-300'
                    }`}
                  >
                    <p className="text-xl mb-1">{r.emoji}</p>
                    <p className={`text-sm font-bold ${role === r.value ? 'text-blue-700' : 'text-slate-800'}`}>{r.label}</p>
                    <p className="text-[10px] text-slate-500 mt-0.5">{r.desc}</p>
                  </button>
                ))}
              </div>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">Username</label>
                <div className="relative">
                  <MdPersonOutline className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-lg" />
                  <input type="text" required placeholder="johndoe"
                    value={form.username}
                    onChange={e => setForm(f => ({ ...f, username: e.target.value }))}
                    className="w-full pl-11 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-800 placeholder-slate-400 focus:border-blue-400 focus:ring-2 focus:ring-blue-100 focus:outline-none transition"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">Email address</label>
                <div className="relative">
                  <MdOutlineEmail className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-lg" />
                  <input type="email" required placeholder="you@example.com"
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
                  <input type={showPwd ? 'text' : 'password'} required placeholder="Min. 6 characters"
                    value={form.password}
                    onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                    className="w-full pl-11 pr-11 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-800 placeholder-slate-400 focus:border-blue-400 focus:ring-2 focus:ring-blue-100 focus:outline-none transition"
                  />
                  <button type="button" onClick={() => setShowPwd(s => !s)}
                    className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors">
                    {showPwd ? <MdOutlineVisibilityOff className="text-lg" /> : <MdOutlineVisibility className="text-lg" />}
                  </button>
                </div>
                {form.password && (
                  <div className="mt-2 flex items-center gap-2">
                    <div className="flex gap-1 flex-1">
                      {[1,2,3].map(i => (
                        <div key={i} className={`h-1.5 flex-1 rounded-full transition-all ${i <= strength ? strengthColor[strength] : 'bg-slate-200'}`} />
                      ))}
                    </div>
                    <span className={`text-xs font-medium ${strengthText[strength]}`}>{strengthLabel[strength]}</span>
                  </div>
                )}
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-600 uppercase tracking-wide mb-2">Confirm Password</label>
                <div className="relative">
                  <MdLockOutline className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 text-lg" />
                  <input type="password" required placeholder="Repeat password"
                    value={form.confirm}
                    onChange={e => setForm(f => ({ ...f, confirm: e.target.value }))}
                    className="w-full pl-11 pr-11 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-800 placeholder-slate-400 focus:border-blue-400 focus:ring-2 focus:ring-blue-100 focus:outline-none transition"
                  />
                  {form.confirm && form.password === form.confirm && (
                    <MdCheckCircleOutline className="absolute right-3.5 top-1/2 -translate-y-1/2 text-emerald-500 text-lg" />
                  )}
                </div>
              </div>

              <button type="submit" disabled={loading}
                className="w-full flex items-center justify-center gap-2 py-3 bg-gradient-to-r from-blue-600 to-violet-600 hover:from-blue-700 hover:to-violet-700 disabled:opacity-50 text-white font-semibold rounded-xl text-sm transition-all shadow-md hover:shadow-lg mt-2">
                {loading ? (
                  <><div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Creating account...</>
                ) : (
                  <>Create Free Account <MdArrowForward /></>
                )}
              </button>
            </form>

            <div className="relative my-5">
              <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-slate-200" /></div>
              <div className="relative flex justify-center"><span className="bg-white px-3 text-xs text-slate-400">Or join with</span></div>
            </div>

            <button
              type="button"
              onClick={handleGithubLogin}
              className="w-full flex items-center justify-center gap-2 py-3 border-2 border-slate-200 hover:border-slate-300 hover:bg-slate-50 text-slate-700 font-semibold rounded-xl text-sm transition-all"
            >
              <RiGithubFill className="text-xl" />
              Continue with GitHub
            </button>

            <div className="relative my-5">
              <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-slate-200" /></div>
              <div className="relative flex justify-center"><span className="bg-white px-3 text-xs text-slate-400">Already have an account?</span></div>
            </div>

            <Link to="/login"
              className="w-full flex items-center justify-center gap-2 py-3 border-2 border-slate-200 hover:border-blue-300 hover:bg-blue-50 text-slate-700 hover:text-blue-700 font-semibold rounded-xl text-sm transition-all">
              Sign in instead <MdArrowForward />
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
