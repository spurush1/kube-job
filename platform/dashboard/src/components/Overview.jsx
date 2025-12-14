import React from 'react';
import { Layers, CheckCircle, Clock, Zap, Cpu, BarChart3, Activity } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';

export default function Overview({ metrics }) {
    if (!metrics) return null;

    // Simulation for chart data (since we only have instantaneous metrics, effectively)
    // In a real app we'd fetch a timeseries. For now, we can perhaps display static or just the current values in a nice way.
    // Or we can construct a small dummy history in the parent if we wanted. 
    // Let's stick to rich cards + simple visualizers for now.

    const cpuColor = metrics.cpu_percent > 80 ? 'text-red-500' : 'text-slate-700';
    const memColor = metrics.memory_percent > 80 ? 'text-red-500' : 'text-slate-700';

    return (
        <div className="space-y-6">
            {/* Top Row: Key Performance Indicators */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <Card title="Throughput" value={metrics.throughput} sub="Msgs / Minute" icon={Zap} color="text-yellow-500" />
                <Card title="Avg Latency" value={`${metrics.avg_latency || 0} ms`} sub="Processing Time" icon={Clock} color="text-indigo-500" />
                <Card title="Active Jobs" value={`${metrics.active_jobs}/${metrics.max_jobs || 50}`} sub="Workers" icon={Activity} color="text-blue-500" />
                <Card title="Total Consumed" value={metrics.total_consumed} sub="Lifetime Messages" icon={CheckCircle} color="text-green-500" />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Queue Health */}
                <div className="lg:col-span-2 bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
                    <div className="flex justify-between items-center mb-6">
                        <h3 className="font-bold text-slate-800 flex items-center gap-2"><Layers size={20} className="text-purple-600" /> Queue Health</h3>
                        <div className="text-2xl font-bold text-slate-900">{metrics.queue_depth} <span className="text-sm font-normal text-slate-400">pending</span></div>
                    </div>
                    {/* Visual Bar for Queue vs Capacity (Example) */}
                    <div className="space-y-6">
                        <div>
                            <div className="flex justify-between text-sm mb-1">
                                <span className="text-slate-500">Unacknowledged (Processing)</span>
                                <span className="font-mono">{metrics.unacked}</span>
                            </div>
                            <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
                                <div className="bg-orange-400 h-2.5 rounded-full" style={{ width: `${Math.min((metrics.unacked / 200) * 100, 100)}%` }}></div>
                            </div>
                        </div>
                        <div>
                            <div className="flex justify-between text-sm mb-1">
                                <span className="text-slate-500">Queue Pressure</span>
                                <span className="font-mono text-purple-600 font-bold">{metrics.queue_depth > 10000 ? 'Critical' : metrics.queue_depth > 5000 ? 'High' : 'Normal'}</span>
                            </div>
                            <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
                                <div className="bg-purple-600 h-2.5 rounded-full transition-all duration-500" style={{ width: `${Math.min((metrics.queue_depth / 20000) * 100, 100)}%` }}></div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* System Resources */}
                <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
                    <h3 className="font-bold text-slate-800 mb-6 flex items-center gap-2"><Cpu size={20} className="text-slate-600" /> Resource Usage</h3>

                    <div className="space-y-6">
                        <div className="flex justify-center items-center gap-4">
                            {/* Circular Progress Placeholder */}
                            <CircularProgress value={metrics.cpu_percent} label="CPU" color="#3b82f6" />
                            <CircularProgress value={metrics.memory_percent} label="RAM" color="#ec4899" />
                        </div>
                        <div className="border-t border-slate-100 pt-4">
                            <div className="flex justify-between items-center">
                                <span className="text-sm text-slate-500">Scaler Load</span>
                                <span className={`font-mono font-bold ${cpuColor}`}>{metrics.cpu_percent}%</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

function Card({ title, value, sub, icon: Icon, color }) {
    return (
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm hover:shadow-md transition-shadow">
            <div className="flex justify-between items-start mb-3">
                <div className="text-xs font-bold text-slate-400 uppercase tracking-widest">{title}</div>
                <div className={`p-2 rounded-lg bg-opacity-10 ${color.replace('text-', 'bg-')}`}>
                    <Icon size={20} className={color} />
                </div>
            </div>
            <div className="text-2xl font-bold text-slate-900">{value}</div>
            <div className="text-xs text-slate-400 font-medium mt-1">{sub}</div>
        </div>
    )
}

function CircularProgress({ value, label, color }) {
    const radius = 30;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference - (value / 100) * circumference;

    return (
        <div className="relative flex flex-col items-center">
            <svg width="80" height="80" className="transform -rotate-90">
                <circle cx="40" cy="40" r={radius} stroke="#e2e8f0" strokeWidth="6" fill="transparent" />
                <circle cx="40" cy="40" r={radius} stroke={color} strokeWidth="6" fill="transparent" strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="round" />
            </svg>
            <div className="absolute top-0 left-0 w-full h-full flex items-center justify-center font-bold text-sm text-slate-700">
                {value}%
            </div>
            <span className="text-xs font-semibold text-slate-500 mt-2">{label}</span>
        </div>
    )
}
