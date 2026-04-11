import axios from 'axios';

const api = axios.create({
  baseURL: process.env.REACT_APP_API_URL || 'http://localhost:5000',
  headers: { 'Content-Type': 'application/json' },
  timeout: 60000,
});

export const axiosInstance = api;

// Attach JWT token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// Auto logout on 401
api.interceptors.response.use(
  res => res,
  err => {
    const isAuthError = err.response?.status === 401 || err.response?.status === 403;
    const isLoginPath = window.location.pathname === '/login' || window.location.pathname === '/register';
    
    if (isAuthError && !isLoginPath) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      // Use replace to avoid back-button loops
      window.location.replace('/login');
    }
    return Promise.reject(err);
  }
);

// Auth
export const register = (data) => api.post('/auth/register', data);
export const login    = (data) => api.post('/auth/login', data);
export const getMe    = ()     => api.get('/auth/me');

// Features
export const reviewTestCase   = (testcase)           => api.post('/review-testcase', { testcase });
export const reviewCode       = (code, language)     => api.post('/review-code', { code, language });
export const testWebsite      = (url)                => api.post('/website-test', { url });
export const generateTestCases= (requirement)        => api.post('/generate-testcase', { requirement });
export const predictRisk      = (content, input_type)=> api.post('/predict-risk', { content, input_type });
export const generateReport   = ()                   => api.get('/generate-report');
export const generateReportImage = (report)          => api.post('/generate-report-image', { report });

// Autonomous QA
export const runAutonomousQA       = (data)   => api.post('/api/autonomous-qa/run', data);
export const getAutonomousRuns     = ()       => api.get('/api/autonomous-qa/runs');
export const getAutonomousRunDetails = (id)   => api.get(`/api/autonomous-qa/run/${id}`);

// QA-to-Dev Bridge
export const analyzeQADevBridge    = (qa_data, system_mode) =>
  api.post('/api/qa-dev-bridge/analyze', { qa_data, system_mode });

// Developer Portal — Projects
export const devListProjects   = ()      => api.get('/api/dev/projects');
export const devCreateProject  = (data)  => api.post('/api/dev/projects', data);
export const devGetProject     = (id)    => api.get(`/api/dev/projects/${id}`);
export const devUpdateProject  = (id, d) => api.put(`/api/dev/projects/${id}`, d);
export const devDeleteProject  = (id)    => api.delete(`/api/dev/projects/${id}`);

// Developer Portal — Diagrams
export const devGenerateDiagram = (pid, data) => api.post(`/api/dev/projects/${pid}/diagrams`, data);
export const devAllDiagrams     = ()           => api.get('/api/dev/diagrams');

// Developer Portal — Code
export const devGenerateCode  = (pid, data) => api.post(`/api/dev/projects/${pid}/code`, data);
export const devReviewCode    = (data)       => api.post('/api/dev/code/review', data);
export const devProjectRisk   = (pid, data)  => api.post(`/api/dev/projects/${pid}/risk`, data);

// Messaging
export const getTeamUsers      = ()         => api.get('/api/users/team');
export const getMessages       = (box)      => api.get(`/api/messages?box=${box||'inbox'}`);
export const sendMessage       = (data)     => api.post('/api/messages', data);
export const replyMessage      = (mid, body)=> api.post(`/api/messages/${mid}/reply`, { body });
export const markRead          = (mid)      => api.patch(`/api/messages/${mid}/read`);
export const getUnreadCount    = ()         => api.get('/api/messages/unread-count');

// Chat
export const sendChatMessage  = (messages, session_id) => api.post('/chat', { messages, session_id });
export const getChatSessions  = ()                     => api.get('/chat/sessions');
export const createChatSession= (title)                => api.post('/chat/sessions', { title });
export const deleteChatSession= (id)                   => api.delete(`/chat/sessions/${id}`);
export const getSessionMessages=(id)                   => api.get(`/chat/sessions/${id}/messages`);
