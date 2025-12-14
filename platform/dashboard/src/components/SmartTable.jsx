import React, { useState, useRef, useEffect } from 'react';
import { ArrowUpDown, ArrowUp, ArrowDown, Settings, Eye, EyeOff, MoveUp, MoveDown, GripVertical } from 'lucide-react';

export default function SmartTable({ columns, data, onRowClick, showRowNumber = false }) {
    // State
    const [tableColumns, setTableColumns] = useState([]);
    const [localData, setLocalData] = useState([]);
    const [sortConfig, setSortConfig] = useState({ key: null, direction: null });
    const [isConfigOpen, setIsConfigOpen] = useState(false);
    const [columnWidths, setColumnWidths] = useState({});

    // Initialize
    useEffect(() => {
        // Merge provided columns with existing state if possible, or init new
        if (tableColumns.length === 0) {
            const initialCols = columns.map(c => ({
                ...c,
                visible: true,
                width: c.width || 150 // Default width
            }));
            setTableColumns(initialCols);
        }
    }, [columns]);

    useEffect(() => {
        setLocalData(data);
    }, [data]);

    // Sorting Logic
    const handleSort = (key) => {
        let direction = 'asc';
        if (sortConfig.key === key && sortConfig.direction === 'asc') {
            direction = 'desc';
        } else if (sortConfig.key === key && sortConfig.direction === 'desc') {
            direction = null;
        }
        setSortConfig({ key: direction ? key : null, direction });
    };

    const sortedData = React.useMemo(() => {
        if (!sortConfig.key || !sortConfig.direction) return localData;

        return [...localData].sort((a, b) => {
            const aVal = a[sortConfig.key];
            const bVal = b[sortConfig.key];

            if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
            if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
            return 0;
        });
    }, [localData, sortConfig]);

    // Resizing Logic
    const resizingRef = useRef(null);

    const startResize = (e, colKey) => {
        e.preventDefault();
        resizingRef.current = {
            key: colKey,
            startX: e.clientX,
            startWidth: columnWidths[colKey] || tableColumns.find(c => c.key === colKey)?.width || 150
        };
        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);
    };

    const handleMouseMove = (e) => {
        if (!resizingRef.current) return;
        const { key, startX, startWidth } = resizingRef.current;
        const diff = e.clientX - startX;
        setColumnWidths(prev => ({
            ...prev,
            [key]: Math.max(50, startWidth + diff) // Min width 50
        }));
    };

    const handleMouseUp = () => {
        resizingRef.current = null;
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
    };


    // Column Config Logic
    const toggleVisibility = (key) => {
        setTableColumns(cols => cols.map(c => c.key === key ? { ...c, visible: !c.visible } : c));
    };

    const moveColumn = (index, direction) => {
        if (direction === 'up' && index > 0) {
            const newCols = [...tableColumns];
            [newCols[index], newCols[index - 1]] = [newCols[index - 1], newCols[index]];
            setTableColumns(newCols);
        } else if (direction === 'down' && index < tableColumns.length - 1) {
            const newCols = [...tableColumns];
            [newCols[index], newCols[index + 1]] = [newCols[index + 1], newCols[index]];
            setTableColumns(newCols);
        }
    };

    const visibleCols = tableColumns.filter(c => c.visible);

    return (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col">
            {/* Toolbar */}
            <div className="p-2 border-b border-slate-100 flex justify-end bg-slate-50/50 rounded-t-xl">
                <button
                    onClick={() => setIsConfigOpen(true)}
                    className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-slate-600 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 hover:text-blue-600 transition-colors"
                >
                    <Settings size={14} /> Configure Columns
                </button>
            </div>

            {/* Table Container */}
            <div className="overflow-auto relative">
                <table className="w-full text-left border-collapse table-fixed">
                    <thead className="bg-slate-50 text-slate-500 font-semibold text-sm sticky top-0 z-10 shadow-sm">
                        <tr>
                            {showRowNumber && <th className="px-4 py-3 w-16 border-r border-slate-200/50 bg-slate-50">Sl. No</th>}
                            {visibleCols.map(col => (
                                <th
                                    key={col.key}
                                    className="relative px-4 py-3 group border-r border-transparent hover:border-slate-200 transition-colors select-none"
                                    style={{ width: columnWidths[col.key] || col.width }}
                                >
                                    <div className="flex items-center justify-between gap-2">
                                        <span className="truncate" title={col.label}>{col.label}</span>
                                        {col.sortable !== false && (
                                            <button onClick={() => handleSort(col.key)} className="p-1 hover:bg-slate-200 rounded">
                                                {sortConfig.key === col.key ? (
                                                    sortConfig.direction === 'asc' ? <ArrowUp size={14} className="text-blue-600" /> : <ArrowDown size={14} className="text-blue-600" />
                                                ) : (
                                                    <ArrowUpDown size={14} className="text-slate-300 opacity-0 group-hover:opacity-100" />
                                                )}
                                            </button>
                                        )}
                                    </div>
                                    {/* Resize Handle */}
                                    <div
                                        className="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-blue-400 z-20"
                                        onMouseDown={(e) => startResize(e, col.key)}
                                    />
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 text-sm">
                        {sortedData.map((row, idx) => (
                            <tr
                                key={idx}
                                onClick={() => onRowClick && onRowClick(row)}
                                className={`group transition-colors ${onRowClick ? 'cursor-pointer hover:bg-blue-50/50' : 'hover:bg-slate-50'}`}
                            >
                                {showRowNumber && <td className="px-4 py-3 font-mono text-xs text-slate-400 border-r border-slate-100 bg-slate-50/30">{idx + 1}</td>}
                                {visibleCols.map(col => (
                                    <td key={col.key} className="px-4 py-3 truncate border-r border-transparent group-hover:border-slate-200/50" title={typeof row[col.key] === 'string' ? row[col.key] : ''}>
                                        {col.render ? col.render(row) : row[col.key]}
                                    </td>
                                ))}
                            </tr>
                        ))}
                        {sortedData.length === 0 && (
                            <tr>
                                <td colSpan={visibleCols.length + (showRowNumber ? 1 : 0)} className="px-6 py-12 text-center text-slate-400 italic">
                                    No data available
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>

            {/* Config Modal */}
            {isConfigOpen && (
                <div className="fixed inset-0 bg-black/20 z-50 flex items-center justify-center p-4 backdrop-blur-sm" onClick={() => setIsConfigOpen(false)}>
                    <div className="bg-white rounded-xl shadow-xl border border-slate-200 w-full max-w-sm overflow-hidden flex flex-col max-h-[80vh]" onClick={e => e.stopPropagation()}>
                        <div className="p-4 border-b border-slate-100 flex justify-between items-center bg-slate-50">
                            <h3 className="font-bold text-slate-800 flex items-center gap-2"><Settings size={16} /> Configure Columns</h3>
                            <button onClick={() => setIsConfigOpen(false)} className="text-slate-400 hover:text-slate-600"><Settings size={16} className="rotate-45" /></button>
                        </div>
                        <div className="p-2 overflow-y-auto flex-1 space-y-1">
                            {tableColumns.map((col, idx) => (
                                <div key={col.key} className="flex items-center justify-between p-2 rounded hover:bg-slate-50 border border-transparent hover:border-slate-100 group">
                                    <div className="flex items-center gap-3">
                                        <button onClick={() => toggleVisibility(col.key)} className={`p-1 rounded ${col.visible ? 'text-blue-600 bg-blue-50' : 'text-slate-400 bg-slate-100'}`}>
                                            {col.visible ? <Eye size={16} /> : <EyeOff size={16} />}
                                        </button>
                                        <span className={`text-sm font-medium ${col.visible ? 'text-slate-700' : 'text-slate-400'}`}>{col.label}</span>
                                    </div>
                                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                        <button disabled={idx === 0} onClick={() => moveColumn(idx, 'up')} className="p-1 hover:bg-slate-200 rounded disabled:opacity-30"><MoveUp size={14} /></button>
                                        <button disabled={idx === tableColumns.length - 1} onClick={() => moveColumn(idx, 'down')} className="p-1 hover:bg-slate-200 rounded disabled:opacity-30"><MoveDown size={14} /></button>
                                    </div>
                                </div>
                            ))}
                        </div>
                        <div className="p-3 border-t border-slate-100 bg-slate-50 text-right">
                            <button onClick={() => setIsConfigOpen(false)} className="px-4 py-2 bg-slate-900 text-white text-sm font-medium rounded-lg hover:bg-slate-800">Done</button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
