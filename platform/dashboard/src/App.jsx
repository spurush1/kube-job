import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { LayoutDashboard, List, FileText, Activity, LogOut } from 'lucide-react';
import JobTable from './components/JobTable';
import AuditView from './components/AuditView';
import Overview from './components/Overview';
import ClusterView from './components/ClusterView';
import LoginPage from './components/LoginPage';

const SCALER_URL = "http://localhost:8080"; // Correct Port Mapping

function App() {
  const [tab, setTab] = useState('overview');
  const [stats, setStats] = useState(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [token, setToken] = useState(localStorage.getItem('auth_token'));

  // Initialize Auth
  useEffect(() => {
    if (token) {
      setIsAuthenticated(true);
      // Setup default header
      axios.defaults.headers.common['Authorization'] = `Basic ${token}`;
    }
  }, [token]);

  // Login Handler
  const handleLogin = async (username, password) => {
    const credentials = btoa(`${username}:${password}`); // Basic Auth Base64
    const basicHeader = `Basic ${credentials}`;

    try {
      // Test connection with credentials
      // Use stats endpoint which is now protected
      await axios.get(`${SCALER_URL}/stats`, {
        headers: { 'Authorization': basicHeader }
      });

      // If success, save state
      localStorage.setItem('auth_token', credentials);
      setToken(credentials);
      setIsAuthenticated(true);
      axios.defaults.headers.common['Authorization'] = basicHeader;
    } catch (e) {
      console.error("Login failed", e);
      alert("Invalid credentials / API unavailable");
    }
  };

  const handleLogout = () => {
    localStorage.removeItem('auth_token');
    setIsAuthenticated(false);
    setToken(null);
    delete axios.defaults.headers.common['Authorization'];
  };

  // Poll stats globally (only if authenticated)
  useEffect(() => {
    if (!isAuthenticated) return;

    const fetchStats = async () => {
      try {
        const res = await axios.get(`${SCALER_URL}/stats`);
        setStats(res.data);
      } catch (e) {
        console.error("Failed to fetch stats (check console for 401)", e);
        if (e.response && e.response.status === 401) {
          handleLogout();
        }
      }
    };
    fetchStats();
    const interval = setInterval(fetchStats, 2000);
    return () => clearInterval(interval);
  }, [isAuthenticated]);

  if (!isAuthenticated) {
    return <LoginPage onLogin={handleLogin} />;
  }

  if (!stats) return <div className="flex items-center justify-center h-screen">Loading Platform...</div>;

  return (
    <div className="min-h-screen bg-slate-50 pb-20">
      {/* Header */}
      <div className="bg-white border-b border-slate-200 sticky top-0 z-30">
        <div className="container mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold">K</div>
            <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-600 to-indigo-600">KubeJob Fabric</h1>
          </div>
          {/* Tabs */}
          <div className="flex gap-4 items-center">
            <div className="flex gap-1 bg-slate-100 p-1 rounded-lg">
              <Tab active={tab === 'overview'} onClick={() => setTab('overview')} label="Overview" />
              <Tab active={tab === 'jobs'} onClick={() => setTab('jobs')} label="Active Jobs" />
              <Tab active={tab === 'audit'} onClick={() => setTab('audit')} label="Audit Trail" />
              <Tab active={tab === 'cluster'} onClick={() => setTab('cluster')} label="Cluster Info" />
            </div>
            <button onClick={handleLogout} className="text-slate-400 hover:text-red-600 transition-colors" title="Logout">
              <LogOut size={20} />
            </button>
          </div>
        </div>
      </div>

      <main className="container mx-auto px-6 py-8">
        {tab === 'overview' && <Overview metrics={stats?.metrics} />}
        {tab === 'jobs' && <JobTable jobs={stats?.jobs} baseUrl={SCALER_URL} />}
        {tab === 'audit' && <AuditView baseUrl={SCALER_URL} />}
        {tab === 'cluster' && <ClusterView baseUrl={SCALER_URL} />}
      </main>
    </div>
  );
}

// New Tab component based on the instruction's usage
function Tab({ active, onClick, label }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${active ? 'bg-white text-blue-600 shadow' : 'text-slate-600 hover:text-slate-800 hover:bg-slate-200'
        }`}
    >
      {label}
    </button>
  );
}

// The original TabButton component is no longer used but kept as per instruction's implicit request
function TabButton({ id, label, icon: Icon, active, onClick }) {
  return (
    <button
      onClick={() => onClick(id)}
      className={`flex items-center gap-2 px-4 py-2 border-b-2 transition-colors ${active === id ? 'border-blue-600 text-blue-600 font-medium' : 'border-transparent text-slate-500 hover:text-slate-700'
        }`}
    >
      <Icon size={18} />
      {label}
    </button>
  )
}

export default App;
