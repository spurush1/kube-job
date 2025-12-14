import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Cpu, Activity, AlertCircle, Layers } from 'lucide-react';

export default function ClusterView({ baseUrl }) {
    const [info, setInfo] = useState({ nodes: [], events: [], pods: [] });
    const [loading, setLoading] = useState(true);

    const fetchInfo = async () => {
        try {
            const res = await axios.get(`${baseUrl}/cluster-info`);
            setInfo(res.data);
        } catch (e) {
            console.error(e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchInfo();
        const interval = setInterval(fetchInfo, 5000);
        return () => clearInterval(interval);
    }, []);

    if (loading) return <div>Loading cluster info...</div>;

    return (
        <div className="space-y-6">

            {/* Error Banner */}
            {info.error && (
                <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl flex items-center gap-2">
                    <AlertCircle size={20} />
                    <div>
                        <div className="font-bold">Failed to load cluster info</div>
                        <div className="text-xs font-mono mt-1 whitespace-pre-wrap">{info.error}</div>
                    </div>
                </div>
            )}

            {/* Nodes Section */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {info.nodes.map(node => (
                    <div key={node.name} className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm flex items-start gap-4">
                        <div className={`p-3 rounded-lg ${node.status === 'Ready' ? 'bg-green-100 text-green-600' : 'bg-red-100 text-red-600'}`}>
                            <Cpu size={24} />
                        </div>
                        <div>
                            <h3 className="font-bold text-lg text-slate-800">{node.name}</h3>
                            <div className="flex gap-2 mt-1 mb-3">
                                <Badge label={node.status} color={node.status === 'Ready' ? 'green' : 'red'} />
                                <Badge label={node.os} color="blue" />
                            </div>
                            <div className="text-sm text-slate-500 grid grid-cols-2 gap-x-8 gap-y-1">
                                <span>CPU Cap: <span className="font-mono text-slate-700">{node.cpu}</span></span>
                                <span>Mem Cap: <span className="font-mono text-slate-700">{node.memory}</span></span>
                                <span className="col-span-2 text-xs mt-1 truncate" title={node.kernel}>{node.kernel}</span>
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            {/* Layout: Pods Left, Events Right */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

                {/* Pods List */}
                <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                    <div className="p-4 border-b border-slate-100 flex justify-between items-center bg-slate-50">
                        <h3 className="font-bold flex items-center gap-2 text-slate-700"><Layers size={18} /> Pod Inventory ({info.pods.length})</h3>
                    </div>
                    <div className="overflow-auto max-h-[500px]">
                        <table className="w-full text-sm text-left">
                            <thead className="bg-white sticky top-0 z-10 text-slate-500 font-semibold border-b shadow-sm">
                                <tr>
                                    <th className="px-4 py-3">Name</th>
                                    <th className="px-4 py-3">Status</th>
                                    <th className="px-4 py-3">Restarts</th>
                                    <th className="px-4 py-3">IP</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                                {info.pods.map(pod => (
                                    <tr key={pod.name} className="hover:bg-slate-50">
                                        <td className="px-4 py-3 font-mono text-xs text-slate-700">{pod.name}</td>
                                        <td className="px-4 py-3"><StatusDot status={pod.status} /> {pod.status}</td>
                                        <td className={`px-4 py-3 font-mono ${pod.restarts > 0 ? 'text-orange-600 font-bold' : 'text-slate-400'}`}>{pod.restarts}</td>
                                        <td className="px-4 py-3 text-slate-500 font-mono text-xs">{pod.ip}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>

                {/* Events Feed */}
                <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col h-[500px]">
                    <div className="p-4 border-b border-slate-100 bg-slate-50">
                        <h3 className="font-bold flex items-center gap-2 text-slate-700"><Activity size={18} /> Cluster Events</h3>
                    </div>
                    <div className="flex-1 overflow-auto p-0">
                        {info.events.length === 0 ? (
                            <div className="p-8 text-center text-slate-400 italic">No recent events</div>
                        ) : (
                            <div className="divide-y divide-slate-100">
                                {info.events.map((evt, i) => (
                                    <div key={i} className={`p-3 text-xs border-l-4 ${evt.type === 'Warning' ? 'border-orange-400 bg-orange-50/50' : 'border-blue-400 hover:bg-slate-50'}`}>
                                        <div className="flex justify-between items-start mb-1">
                                            <span className={`font-bold ${evt.type === 'Warning' ? 'text-orange-700' : 'text-blue-700'}`}>{evt.reason}</span>
                                            <span className="text-slate-400 font-mono text-[10px]">{evt.time}</span>
                                        </div>
                                        <div className="text-slate-600 mb-1">{evt.message}</div>
                                        <div className="text-slate-400 font-mono text-[10px]">{evt.object}</div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>

            </div>
        </div>
    );
}

function Badge({ label, color }) {
    const colors = {
        green: 'bg-green-100 text-green-700',
        red: 'bg-red-100 text-red-700',
        blue: 'bg-blue-100 text-blue-700',
        gray: 'bg-slate-100 text-slate-700'
    };
    return (
        <span className={`px-2 py-0.5 rounded text-xs font-bold ${colors[color] || colors.gray}`}>
            {label}
        </span>
    );
}

function StatusDot({ status }) {
    const color = status === 'Running' ? 'bg-green-500' : status === 'Pending' ? 'bg-yellow-500' : 'bg-red-500';
    return <span className={`inline-block w-2 h-2 rounded-full mr-1 ${color}`}></span>;
}
