import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { format } from 'date-fns';
import { XCircle } from 'lucide-react';
import SmartTable from './SmartTable';

export default function AuditView({ baseUrl }) {
    const [audits, setAudits] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedAudit, setSelectedAudit] = useState(null);

    const fetchAudit = async () => {
        try {
            const res = await axios.get(`${baseUrl}/audit?limit=100`);
            setAudits(res.data);
        } catch (e) {
            console.error("Failed audit fetch", e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchAudit();
        const interval = setInterval(fetchAudit, 5000); // Poll slower for audit
        return () => clearInterval(interval);
    }, []);

    const columns = [
        { key: 'message_id', label: 'Message ID', width: 220, render: (row) => <span className="font-mono text-slate-600 hover:text-blue-600 font-bold" title={row.message_id}>{row.message_id}</span> },
        { key: 'job_type', label: 'Job Type', width: 140 },
        { key: 'worker_pod', label: 'Worker Pod', width: 180, render: (row) => <span className="font-mono text-xs">{row.worker_pod}</span> },
        { key: 'queued_at', label: 'Queued At', width: 120, render: (row) => <span className="text-slate-500">{formatDate(row.queued_at)}</span> },
        { key: 'processed_at', label: 'Processed At', width: 120, render: (row) => <span className="text-slate-500">{formatDate(row.processed_at)}</span> },
        { key: 'duration_ms', label: 'Duration', width: 100, render: (row) => <span className="font-bold text-slate-700">{row.duration_ms}ms</span> },
        { key: 'status', label: 'Status', width: 100, render: () => <span className="bg-green-100 text-green-700 px-2 py-0.5 rounded-full text-xs font-bold">Done</span> }
    ];

    if (loading && audits.length === 0) return <div className="p-6 text-center text-slate-400">Loading audit trail...</div>;

    return (
        <div className="space-y-4">
            <div className="flex justify-between items-center">
                <h2 className="text-lg font-bold text-slate-800">Message Audit Trail</h2>
                <button onClick={fetchAudit} className="text-sm text-blue-600 hover:underline">Refresh</button>
            </div>

            <SmartTable
                columns={columns}
                data={audits}
                onRowClick={setSelectedAudit}
                showRowNumber={true}
            />

            {/* Drill Down Modal */}
            {selectedAudit && (
                <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
                    <AuditDetailModal audit={selectedAudit} baseUrl={baseUrl} onClose={() => setSelectedAudit(null)} />
                </div>
            )}
        </div>
    );
}

function AuditDetailModal({ audit, baseUrl, onClose }) {
    const [logContent, setLogContent] = useState('Loading historical logs...');

    useEffect(() => {
        const fetchLog = async () => {
            if (!audit.log_file) {
                setLogContent("No log file associated with this record.");
                return;
            }
            try {
                // Encode the path just in case
                const res = await axios.get(`${baseUrl}/audit/log?file_path=${encodeURIComponent(audit.log_file)}`);
                setLogContent(res.data);
            } catch (e) {
                setLogContent(`Failed to retrieve log file: ${audit.log_file}\nError: ${e.message}`);
            }
        };
        fetchLog();
    }, [audit, baseUrl]);

    return (
        <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden">
            <div className="flex justify-between items-center p-4 border-b border-slate-100 bg-slate-50">
                <div>
                    <h3 className="font-bold text-lg text-slate-800">Audit Detail</h3>
                    <div className="text-xs text-slate-500 font-mono">{audit.message_id}</div>
                </div>
                <button onClick={onClose} className="p-2 hover:bg-slate-200 rounded-full"><XCircle size={20} /></button>
            </div>

            <div className="p-4 grid grid-cols-2 gap-4 bg-white border-b border-slate-100">
                <DetailItem label="Job Type" value={audit.job_type} />
                <DetailItem label="Worker Pod" value={audit.worker_pod} />
                <DetailItem label="Queued At" value={formatDate(audit.queued_at)} />
                <DetailItem label="Processed At" value={formatDate(audit.processed_at)} />
                <DetailItem label="Duration" value={`${audit.duration_ms} ms`} />
                <DetailItem label="Log File Path" value={audit.log_file} mono />
            </div>

            <div className="flex-1 bg-[#1e1e1e] p-4 overflow-auto">
                <div className="text-xs text-slate-400 mb-2 uppercase tracking-wider font-bold">Historical Log Content</div>
                <pre className="font-mono text-sm text-slate-300 whitespace-pre-wrap">{logContent}</pre>
            </div>
        </div>
    )
}

function DetailItem({ label, value, mono }) {
    return (
        <div>
            <div className="text-xs text-slate-400 uppercase tracking-wider font-semibold">{label}</div>
            <div className={`text-sm text-slate-700 font-medium ${mono ? 'font-mono' : ''}`}>{value}</div>
        </div>
    )
}

function LegacyAuditView({ baseUrl }) {
    // keeping old code? No, we replaced the export default. Only imports need check.
    // We need to add X import
}

function formatDate(isoStr) {
    if (!isoStr) return "-";
    try {
        // Postgres returns ISO string or maybe not? usually standard
        return format(new Date(isoStr), "HH:mm:ss.SSS");
    } catch { return isoStr; }
}
