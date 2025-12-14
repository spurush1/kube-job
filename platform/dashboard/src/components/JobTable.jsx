import React, { useState } from 'react';
import { Terminal, X } from 'lucide-react';
import axios from 'axios';
import SmartTable from './SmartTable';

export default function JobTable({ jobs, baseUrl }) {
    const [selectedJob, setSelectedJob] = useState(null);
    const [logs, setLogs] = useState('');
    const [loadingLogs, setLoadingLogs] = useState(false);

    // Auto-scroll ref
    const logContainerRef = React.useRef(null);

    const handleViewLogs = (jobName) => {
        setSelectedJob(jobName);
        setLogs('Connecting to log stream...');
    };

    // Columns Definition
    const columns = [
        { key: 'name', label: 'Job Name', width: 200, render: (row) => <span className="font-mono text-slate-700">{row.name}</span> },
        { key: 'type', label: 'Type', width: 120, render: (row) => <span className="text-slate-600">{row.type || 'generic'}</span> },
        { key: 'status', label: 'Status', width: 120, render: (row) => <StatusBadge status={row.status} /> },
        { key: 'start_time', label: 'Start Time', width: 120, render: (row) => <span className="text-slate-500">{row.start_time}</span> },
        { key: 'processed', label: 'Processed', width: 100, render: (row) => <span className="font-bold text-slate-700">{row.processed}</span> },
        {
            key: 'actions',
            label: 'Actions',
            width: 100,
            sortable: false,
            render: (row) => (
                <button
                    onClick={(e) => { e.stopPropagation(); handleViewLogs(row.name); }}
                    className="text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1"
                >
                    <Terminal size={14} /> Logs
                </button>
            )
        }
    ];

    // Poll logs when a job is selected
    React.useEffect(() => {
        if (!selectedJob) return;

        const fetchLogs = async () => {
            try {
                const res = await axios.get(`${baseUrl}/logs/${selectedJob}`);
                setLogs(res.data);
            } catch (e) {
                console.error("Log poll failed", e);
            }
        };

        fetchLogs();
        const interval = setInterval(fetchLogs, 1000); // 1s polling
        return () => clearInterval(interval);
    }, [selectedJob, baseUrl]);

    // Auto-scroll to bottom of logs
    React.useEffect(() => {
        if (logContainerRef.current) {
            logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
        }
    }, [logs]);

    return (
        <>
            <SmartTable
                columns={columns}
                data={jobs}
                showRowNumber={true}
            />

            {/* Log Modal */}
            {selectedJob && (
                <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
                    <LogViewer
                        jobName={selectedJob}
                        baseUrl={baseUrl}
                        onClose={() => setSelectedJob(null)}
                    />
                </div>
            )}
        </>
    );
}

function LogViewer({ jobName, baseUrl, onClose }) {
    const [rawLogs, setRawLogs] = useState('');
    const [filter, setFilter] = useState('');
    const [timeRange, setTimeRange] = useState(0); // 0 = All
    const [sortDesc, setSortDesc] = useState(false);
    const [status, setStatus] = useState('Connecting...');

    const logContainerRef = React.useRef(null);

    // Fetch Logic
    React.useEffect(() => {
        const fetchLogs = async () => {
            try {
                // Pass since_minutes
                const res = await axios.get(`${baseUrl}/logs/${jobName}?since_minutes=${timeRange}`);
                setRawLogs(res.data);
                setStatus('Live');
            } catch (e) {
                console.error(e);
                setStatus('Connection Failed');
            }
        };

        fetchLogs();
        const interval = setInterval(fetchLogs, 2000);
        return () => clearInterval(interval);
    }, [jobName, baseUrl, timeRange]);

    // Processing Logic (Filter & Sort)
    const processedLogs = React.useMemo(() => {
        if (!rawLogs) return [];
        let lines = rawLogs.split('\n');

        // Filter
        if (filter) {
            lines = lines.filter(l => l.toLowerCase().includes(filter.toLowerCase()));
        }

        // Sort (Default is Ascending/Oldest First, Toggle for Descending)
        if (sortDesc) {
            lines.reverse();
        }

        return lines;
    }, [rawLogs, filter, sortDesc]);

    // Auto-scroll (only if not sorted descending, otherwise stay at top)
    React.useEffect(() => {
        if (!sortDesc && logContainerRef.current) {
            logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
        }
    }, [processedLogs, sortDesc]);


    return (
        <div className="bg-white rounded-xl shadow-2xl w-full max-w-5xl h-[85vh] flex flex-col overflow-hidden">
            {/* Toolbar */}
            <div className="flex flex-col gap-4 p-4 border-b border-slate-200 bg-slate-50">
                <div className="flex justify-between items-center">
                    <div className="flex items-center gap-2">
                        <Terminal size={20} className="text-slate-600" />
                        <h3 className="font-bold text-lg text-slate-800">Logs: <span className="font-mono text-blue-600">{jobName}</span></h3>
                        <span className="px-2 py-0.5 rounded-full bg-green-100 text-green-700 text-xs font-bold flex items-center gap-1">
                            <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse"></span>
                            {status}
                        </span>
                    </div>
                    <button onClick={onClose} className="p-2 hover:bg-slate-200 rounded-full transition-colors"><X size={20} /></button>
                </div>

                <div className="flex gap-4 items-center">
                    {/* Search */}
                    <div className="relative flex-1">
                        <input
                            type="text"
                            placeholder="Filter logs (regex support)..."
                            className="w-full pl-3 pr-3 py-2 rounded-lg border border-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                            value={filter}
                            onChange={(e) => setFilter(e.target.value)}
                        />
                    </div>

                    {/* Time Range */}
                    <select
                        className="px-3 py-2 rounded-lg border border-slate-300 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                        value={timeRange}
                        onChange={(e) => setTimeRange(Number(e.target.value))}
                    >
                        <option value={0}>All Time</option>
                        <option value={5}>Last 5 Minutes</option>
                        <option value={15}>Last 15 Minutes</option>
                        <option value={60}>Last 1 Hour</option>
                    </select>

                    {/* Sort Toggle */}
                    <button
                        onClick={() => setSortDesc(!sortDesc)}
                        className={`px-3 py-2 rounded-lg text-sm font-medium border transition-colors ${sortDesc ? 'bg-blue-100 text-blue-700 border-blue-200' : 'bg-white text-slate-600 border-slate-300 hover:bg-slate-50'}`}
                    >
                        {sortDesc ? 'Newest First' : 'Oldest First'}
                    </button>
                </div>
            </div>

            {/* Log Content */}
            <div ref={logContainerRef} className="bg-[#1e1e1e] text-slate-300 p-4 font-mono text-sm overflow-auto flex-1 leading-relaxed">
                {processedLogs.length > 0 ? (
                    processedLogs.map((line, i) => (
                        <div key={i} className="hover:bg-white/5 px-2 -mx-2 rounded pointer-events-none">
                            {line}
                        </div>
                    ))
                ) : (
                    <div className="text-slate-500 italic p-4">No logs match your filter or range.</div>
                )}
            </div>
        </div>
    );
}

function StatusBadge({ status }) {
    const styles = {
        Running: "bg-blue-100 text-blue-700",
        Succeeded: "bg-green-100 text-green-700",
        Failed: "bg-red-100 text-red-700",
        Terminating: "bg-orange-100 text-orange-700",
        Pending: "bg-yellow-100 text-yellow-700"
    };
    return (
        <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold ${styles[status] || "bg-gray-100 text-gray-700"}`}>
            {status}
        </span>
    )
}
