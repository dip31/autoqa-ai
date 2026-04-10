import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:5000',
  headers: { 'Content-Type': 'application/json' },
  timeout: 60000,
});

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
    if (err.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
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

// Chat
export const sendChatMessage  = (messages, session_id) => api.post('/chat', { messages, session_id });
export const getChatSessions  = ()                     => api.get('/chat/sessions');
export const createChatSession= (title)                => api.post('/chat/sessions', { title });
export const deleteChatSession= (id)                   => api.delete(`/chat/sessions/${id}`);
export const getSessionMessages=(id)                   => api.get(`/chat/sessions/${id}/messages`);
