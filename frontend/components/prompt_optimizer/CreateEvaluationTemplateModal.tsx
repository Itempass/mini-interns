'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { X, Loader2, Download, AlertTriangle, CheckSquare, Square } from 'lucide-react';
import { listDataSources, getDataSourceConfigSchema, listThreads, exportThreadsDataset, collectThreadIds, startExportJob, getExportJobStatus, getExportJobProgress, downloadExportJob, DataSource, ThreadListFilters, ThreadListItem, ThreadListResponse } from '../../services/promptoptimizer_api';




interface CreateEvaluationTemplateModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const CreateEvaluationTemplateModal: React.FC<CreateEvaluationTemplateModalProps> = ({ isOpen, onClose }) => {
  const [step, setStep] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');

  // Step 1
  const [dataSources, setDataSources] = useState<DataSource[]>([]);
  const [selectedDataSource, setSelectedDataSource] = useState<string>('');

  // Step 2: Filters and list
  const [configSchema, setConfigSchema] = useState<Record<string, any> | null>(null);
  const [filters, setFilters] = useState<ThreadListFilters>({ folder_names: [], filter_by_labels: [] });
  const [threads, setThreads] = useState<ThreadListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [selectedUids, setSelectedUids] = useState<Set<string>>(new Set());
  const [selectAllOnPage, setSelectAllOnPage] = useState(false);
  const [isTableLoading, setIsTableLoading] = useState(false);
  const [isSelectingAll, setIsSelectingAll] = useState(false);
  const [exportJobId, setExportJobId] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [exportProgress, setExportProgress] = useState<{total: number, completed: number}>({ total: 0, completed: 0 });

  const steps = [
    { name: 'Select Source' },
    { name: 'Select Threads' },
    { name: 'Review & Export' },
  ];

  useEffect(() => {
    if (!isOpen) return;
      setStep(1);
    setIsLoading(true);
      setErrorMessage('');
      Promise.all([
      listDataSources()
    ]).then(([sources]) => {
        setDataSources(sources);
        if (sources.length > 0) {
          setSelectedDataSource(sources[0].id);
        }
      }).catch(err => {
      setErrorMessage('Failed to load data sources.');
        console.error(err);
    }).finally(() => setIsLoading(false));
  }, [isOpen]);

  const loadSchemaAndFirstPage = async () => {
    if (!selectedDataSource) return;
    setIsLoading(true);
    setErrorMessage('');
    try {
      const schema = await getDataSourceConfigSchema(selectedDataSource);
      setConfigSchema(schema);
      // Initialize filters with defaults if present
      const initialFolders = Array.isArray(schema?.properties?.folder_names?.options) ? [] : [];
      setFilters({ folder_names: initialFolders, filter_by_labels: [] });
      setPage(1);
      await fetchThreads(1, pageSize, { folder_names: initialFolders, filter_by_labels: [] });
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to load configuration schema.');
    } finally {
      setIsLoading(false);
    }
  };

  const fetchThreads = async (p: number, ps: number, f?: ThreadListFilters) => {
    // Clear current rows and show loading before fetching new page
    setIsTableLoading(true);
    setThreads([]);
    setSelectAllOnPage(false);
    setIsLoading(true);
    try {
      const res: ThreadListResponse = await listThreads(selectedDataSource, f ?? filters, p, ps);
      setThreads(res.items);
      setTotal(res.total);
      // maintain selectAllOnPage flag based on page contents
      const pageAllSelected = res.items.length > 0 && res.items.every(i => selectedUids.has((i as any).uid || ''));
      setSelectAllOnPage(pageAllSelected);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to load threads.');
    } finally {
      setIsLoading(false);
      setIsTableLoading(false);
    }
  };

  const handleNext = async () => {
    setErrorMessage('');
    if (step === 1) {
      await loadSchemaAndFirstPage();
        setStep(2);
    } else if (step === 2) {
      setStep(3);
    }
  };
  
  const handlePrevious = () => {
    setStep(prev => prev - 1);
  };

  const toggleSelect = (uid: string) => {
    setSelectedUids(prev => {
      const next = new Set(prev);
      if (next.has(uid)) next.delete(uid); else next.add(uid);
      return next;
    });
  };

  const toggleSelectAllOnThisPage = () => {
    const uidsOnPage = threads.map((t: any) => t.uid || '');
    setSelectedUids(prev => {
      const next = new Set(prev);
      const allSelected = uidsOnPage.length > 0 && uidsOnPage.every(uid => next.has(uid));
      if (allSelected) {
        uidsOnPage.forEach(uid => next.delete(uid));
      } else {
        uidsOnPage.forEach(uid => next.add(uid));
      }
      return next;
    });
    setSelectAllOnPage(!selectAllOnPage);
  };

  const clearSelections = () => setSelectedUids(new Set());

  const handleFilterChange = (key: 'folder_names' | 'filter_by_labels', values: string[]) => {
    const newFilters = { ...filters, [key]: values };
    setFilters(newFilters);
  };

  const applyFilters = async () => {
    setPage(1);
    await fetchThreads(1, pageSize, filters);
  };

  const handlePageChange = async (newPage: number) => {
    setPage(newPage);
    await fetchThreads(newPage, pageSize);
  };

  const handlePageSizeChange = async (newSize: number) => {
    setPageSize(newSize);
    setPage(1);
    await fetchThreads(1, newSize);
  };

  const downloadDataset = async () => {
    if (selectedUids.size === 0) return;
    setIsLoading(true);
    setErrorMessage('');
    try {
      // Start export job and poll
      setIsExporting(true);
      const job = await startExportJob(selectedDataSource, Array.from(selectedUids));
      setExportJobId(job.job_id);
      // Poll every 2s up to a max duration (e.g., 2 minutes)
      const start = Date.now();
      const timeoutMs = 15 * 60 * 1000; // 15 minutes
      while (true) {
        const prog = await getExportJobProgress(job.job_id);
        setExportProgress({ total: prog.total || 0, completed: prog.completed || 0 });
        if (prog.status === 'completed') {
          break; // show Download button instead of auto-downloading
        } else if (prog.status === 'failed') {
          setErrorMessage('Export failed. Please try again.');
          break;
        }
        if (Date.now() - start > timeoutMs) {
          setErrorMessage('Export is taking longer than expected. Please try again later.');
          break;
        }
        await new Promise(res => setTimeout(res, 2000));
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to download dataset.');
    } finally {
      setIsExporting(false);
      setIsLoading(false);
    }
  };
  const handleDownloadReady = async () => {
    if (!exportJobId) return;
    try {
      const blob = await downloadExportJob(exportJobId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `dataset_${selectedDataSource}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      setErrorMessage('Failed to download dataset.');
    }
  };

  if (!isOpen) return null;

  const renderStepContent = () => {
    if (isLoading && step === 1) {
      return <div className="flex justify-center items-center p-8"><Loader2 className="animate-spin" /></div>;
    }
    
    switch (step) {
      case 1:
        return (
          <div>
            <div className="mt-6">
              <h3 className="text-lg font-medium text-gray-900">Select Source</h3>
              <p className="mt-1 text-sm text-gray-600">Choose the data source to build your dataset.</p>
              <div className="mt-3" />
              <label className="block text-sm font-medium">Data Source</label>
              <select
                value={selectedDataSource}
                onChange={e => setSelectedDataSource(e.target.value)}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md"
              >
                {dataSources.map(ds => <option key={ds.id} value={ds.id}>{ds.name}</option>)}
              </select>
            </div>
          </div>
        );
      case 2:
        return (
          <div>
            <h3 className="text-lg font-medium text-gray-900">Step 2: Select Threads</h3>
            <p className="mt-2 text-sm text-gray-600">Use filters to narrow results. Your selections persist across pages and filters.</p>

            {/* Filters */}
            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                <label className="block text-sm font-medium">Folders</label>
                <select
                  multiple
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md h-32"
                  value={filters.folder_names || []}
                  onChange={(e) => {
                    const options = Array.from(e.target.selectedOptions).map(o => o.value);
                    handleFilterChange('folder_names', options);
                  }}
                >
                  {(configSchema?.properties?.folder_names?.options || []).map((opt: string) => (
                    <option key={opt} value={opt}>{opt}</option>
                  ))}
                            </select>
                        </div>
                        <div>
                <label className="block text-sm font-medium">Labels</label>
                <select
                  multiple
                  className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md h-32"
                  value={filters.filter_by_labels || []}
                  onChange={(e) => {
                    const options = Array.from(e.target.selectedOptions).map(o => o.value);
                    handleFilterChange('filter_by_labels', options);
                  }}
                >
                  {(configSchema?.properties?.filter_by_labels?.options || []).map((opt: string) => (
                    <option key={opt} value={opt}>{opt}</option>
                  ))}
                            </select>
                        </div>
                        </div>
            <div className="mt-3 flex items-center gap-2">
              <button onClick={applyFilters} className="px-3 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700">Apply Filters</button>
              <button onClick={clearSelections} className="px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50">Clear Selections</button>
          </div>

            {/* Table */}
            <div className="mt-4 border border-gray-200 rounded-md overflow-hidden">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      <button onClick={toggleSelectAllOnThisPage} className="flex items-center gap-2">
                        {selectAllOnPage ? <CheckSquare size={16}/> : <Square size={16}/>} Select Page
                      </button>
                    </th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Subject</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">From</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Date</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Labels</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {threads.map(item => (
                    <tr key={item.id} className="hover:bg-gray-50">
                      <td className="px-4 py-2">
                        <button onClick={() => toggleSelect(item.id)} className="text-gray-700">
                          {selectedUids.has(item.id) ? <CheckSquare size={18}/> : <Square size={18}/>}
                        </button>
                      </td>
                      <td className="px-4 py-2 text-sm text-gray-900 break-words">{item.subject}</td>
                      <td className="px-4 py-2 text-sm text-gray-600 break-words">{item.from}</td>
                      <td className="px-4 py-2 text-sm text-gray-600">{new Date(item.date).toLocaleString()}</td>
                      <td className="px-4 py-2 text-xs text-gray-500">{(item.labels || []).join(', ')}</td>
                    </tr>
                  ))}
                  {threads.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-6 text-center text-sm text-gray-500">No results. Adjust filters and try again.</td>
                    </tr>
                  )}
                </tbody>
              </table>
                    </div>

            {/* Pagination */}
            <div className="mt-3 flex items-center justify-between">
              <div className="text-sm text-gray-600">Total available: {total}</div>
              <div className="flex items-center gap-2">
                <button disabled={page <= 1} onClick={() => handlePageChange(page - 1)} className="px-3 py-1 border rounded disabled:opacity-50">Prev</button>
                <span className="text-sm">Page {page}</span>
                <button disabled={(page * pageSize) >= total} onClick={() => handlePageChange(page + 1)} className="px-3 py-1 border rounded disabled:opacity-50">Next</button>
                <select value={pageSize} onChange={(e) => handlePageSizeChange(parseInt(e.target.value))} className="ml-2 border rounded px-2 py-1 text-sm">
                  {[25, 50, 100].map(sz => <option key={sz} value={sz}>{sz}/page</option>)}
                </select>
                </div>
            </div>

            </div>
        );
      case 3:
        return (
          <div>
            <h3 className="text-lg font-medium text-gray-900">Step 3: Review & Export</h3>
            <p className="mt-2 text-sm text-gray-600">You have selected <span className="font-semibold">{selectedUids.size}</span> thread(s) for your dataset.</p>
            {selectedUids.size > 500 && (
              <div className="mt-4 p-3 bg-yellow-50 border border-yellow-300 rounded-md flex items-start">
                <AlertTriangle className="h-5 w-5 text-yellow-600 mr-3" />
                <p className="text-sm text-yellow-800">Large datasets may take longer to prepare. Consider narrowing your selection if you encounter delays.</p>
              </div>
            )}
            <div className="mt-6 space-y-3">
              {isExporting && (
                <div>
                  <div className="w-full bg-gray-200 rounded h-2 overflow-hidden">
                    <div className="bg-blue-600 h-2" style={{ width: `${exportProgress.total ? Math.min(100, Math.round((exportProgress.completed / exportProgress.total) * 100)) : 0}%` }} />
                  </div>
                  <p className="mt-1 text-xs text-gray-600">{exportProgress.completed} / {exportProgress.total} processed</p>
                </div>
              )}
              {!exportJobId || exportProgress.completed < exportProgress.total ? (
                <button
                  onClick={downloadDataset}
                  disabled={selectedUids.size === 0 || isLoading || isExporting}
                  className="w-full md:w-auto flex items-center justify-center px-4 py-3 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md hover:bg-blue-700 disabled:bg-blue-300"
                >
                  {(isLoading || isExporting) ? <Loader2 className="animate-spin h-5 w-5 mr-2" /> : <Download className="mr-2 h-4 w-4" />}
                  {isExporting ? 'Preparing...' : 'Start Export'}
                </button>
              ) : (
                <button
                  onClick={handleDownloadReady}
                  className="w-full md:w-auto flex items-center justify-center px-4 py-3 text-sm font-medium text-white bg-green-600 border border-transparent rounded-md hover:bg-green-700"
                >
                  <Download className="mr-2 h-4 w-4" />
                  Download Dataset
                </button>
              )}
            </div>
            </div>
        );
      default:
        return null;
    }
  };

  const displayStep = step;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="bg-white rounded-lg shadow-xl w-[90vw] h-[90vh] flex flex-col transform transition-all">
        {/* Modal Header */}
        <div className="p-6 border-b border-gray-200 shrink-0">
          <div className="flex items-start justify-between">
            <div>
              <h2 className="text-xl font-semibold text-gray-800">Create Dataset</h2>
            </div>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <X size={24} />
            </button>
          </div>
          {errorMessage && <div className="mt-4 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded" role="alert">
            <strong className="font-bold">Error:</strong>
            <span className="block sm:inline"> {errorMessage}</span>
          </div>}
        </div>
        {/* Modal Body */}
        <div className="flex-1 overflow-hidden p-6">
          <div className="flex space-x-6 h-full">
            {/* Sidebar */}
            <div className="w-56 shrink-0">
              <ol className="space-y-2">
                {steps.map((s, idx) => (
                  <li key={s.name} className={`px-3 py-2 rounded ${displayStep === idx+1 ? 'bg-blue-50 text-blue-700' : 'text-gray-600'}`}>{idx+1}. {s.name}</li>
                ))}
              </ol>
            </div>
            {/* Content */}
            <div className="flex-1 min-w-0 pr-2 min-h-0 flex flex-col">
              {step === 2 ? (
                <div className="h-full min-h-0 flex flex-col">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-lg font-medium text-gray-900">Step 2: Select Threads</h3>
                      <p className="mt-1 text-sm text-gray-600">Your selections persist across pages and filters.</p>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="inline-flex items-center px-3 py-2 text-sm font-medium text-purple-800 bg-purple-100 border border-purple-200 rounded-md">Selected entries for dataset: {selectedUids.size}</span>
                      <button onClick={clearSelections} className="px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50">Clear Selections</button>
                    </div>
                  </div>

                  <div className="mt-4 h-full min-h-0 flex gap-4">
                    {/* Table Column */}
                    <div className="flex-1 min-h-0 min-w-0 flex flex-col">
                      <div className="border border-gray-200 rounded-md flex-1 min-h-0 overflow-y-auto overflow-x-hidden">
                        {isTableLoading ? (
                          <div className="flex items-center justify-center h-full py-10">
                            <Loader2 className="h-6 w-6 text-blue-600 animate-spin" />
                          </div>
                        ) : (
                          <table className="min-w-full table-fixed divide-y divide-gray-200">
                            <thead className="bg-gray-50 sticky top-0 z-10">
                              <tr>
                                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider bg-gray-50">
                                  <button onClick={toggleSelectAllOnThisPage} className="flex items-center gap-2">
                                    {selectAllOnPage ? <CheckSquare size={16}/> : <Square size={16}/>} Select Page
                                  </button>
                                </th>
                                <th className="px-4 py-2 w-[45%] text-left text-xs font-medium text-gray-500 uppercase tracking-wider bg-gray-50">Subject</th>
                                <th className="px-4 py-2 w-[25%] text-left text-xs font-medium text-gray-500 uppercase tracking-wider bg-gray-50">From</th>
                                <th className="px-4 py-2 w-[15%] text-left text-xs font-medium text-gray-500 uppercase tracking-wider bg-gray-50">Date</th>
                                <th className="px-4 py-2 w-[15%] text-left text-xs font-medium text-gray-500 uppercase tracking-wider bg-gray-50">Labels</th>
                              </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-gray-200">
                              {threads.map((item: any) => (
                                <tr key={item.uid || item.id} className="hover:bg-gray-50">
                                  <td className="px-4 py-2">
                                    <button onClick={() => toggleSelect(item.uid || '')} className="text-gray-700">
                                      {selectedUids.has(item.uid || '') ? <CheckSquare size={18}/> : <Square size={18}/>}
                                    </button>
                                  </td>
                                  <td className="px-4 py-2 text-sm text-gray-900 truncate">{item.subject}</td>
                                  <td className="px-4 py-2 text-sm text-gray-600 truncate">{item.from}</td>
                                  <td className="px-4 py-2 text-sm text-gray-600 whitespace-nowrap">{new Date(item.date).toLocaleString()}</td>
                                  <td className="px-4 py-2 text-xs text-gray-500 truncate">{(item.labels || []).join(', ')}</td>
                                </tr>
                              ))}
                              {threads.length === 0 && (
                                <tr>
                                  <td colSpan={5} className="px-4 py-6 text-center text-sm text-gray-500">No results. Adjust filters and try again.</td>
                                </tr>
                              )}
                            </tbody>
                          </table>
                        )}
                      </div>

                      {/* Pagination and totals - always visible */}
                      <div className="mt-3 flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <span className="text-sm text-gray-600">Total available: {total}</span>
                          <div className="relative group inline-block">
                            <button
                              type="button"
                              disabled={total > 500 || isSelectingAll}
                              onClick={async () => {
                                setIsSelectingAll(true);
                                try {
                                  const ids = await collectThreadIds(selectedDataSource, filters, Math.min(total, 500));
                                  setSelectedUids(prev => {
                                    const next = new Set(prev);
                                    ids.forEach(uid => next.add(uid));
                                    return next;
                                  });
                                  setSelectAllOnPage(true);
                                } catch (e) {
                                  console.error('Select all failed', e);
                                } finally {
                                  setIsSelectingAll(false);
                                }
                              }}
                              className="px-2 py-1 text-xs font-medium rounded border disabled:opacity-50 flex items-center gap-2"
                            >
                              {isSelectingAll ? <Loader2 className="h-3 w-3 animate-spin"/> : null}
                              {isSelectingAll ? 'Selecting...' : 'Select all'}
                            </button>
                            {total > 500 && (
                              <div className="absolute left-0 mt-1 w-56 invisible group-hover:visible bg-gray-800 text-white text-xs rounded py-2 px-3 shadow-lg">
                                Maximum dataset size is 500. Refine your filters to select fewer items.
                              </div>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <button disabled={page <= 1} onClick={() => handlePageChange(page - 1)} className="px-3 py-1 border rounded disabled:opacity-50">Prev</button>
                          <span className="text-sm">Page {page}</span>
                          <button disabled={(page * pageSize) >= total} onClick={() => handlePageChange(page + 1)} className="px-3 py-1 border rounded disabled:opacity-50">Next</button>
                          <select value={pageSize} onChange={(e) => handlePageSizeChange(parseInt(e.target.value))} className="ml-2 border rounded px-2 py-1 text-sm">
                            {[25, 50, 100].map(sz => <option key={sz} value={sz}>{sz}/page</option>)}
                          </select>
                        </div>
                      </div>
                    </div>

                    {/* Filters Sidebar */}
                    <div className="w-72 shrink-0 border border-gray-200 rounded-md p-3 flex flex-col overflow-y-auto">
                      <h4 className="text-sm font-medium text-gray-700">Filters</h4>
                      <div className="mt-3">
                        <p className="text-xs font-semibold text-gray-600 uppercase mb-2">Folders</p>
                        <div className="max-h-40 overflow-y-auto space-y-1">
                          {(configSchema?.properties?.folder_names?.options || []).map((opt: string) => {
                            const checked = (filters.folder_names || []).includes(opt);
                            return (
                              <label key={opt} className="flex items-center gap-2 text-sm text-gray-700">
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  onChange={() => {
                                    const current = new Set(filters.folder_names || []);
                                    if (current.has(opt)) current.delete(opt); else current.add(opt);
                                    handleFilterChange('folder_names', Array.from(current));
                                  }}
                                />
                                <span className="truncate">{opt}</span>
                              </label>
                            );
                          })}
                        </div>
                      </div>
                      <div className="mt-4">
                        <p className="text-xs font-semibold text-gray-600 uppercase mb-2">Labels</p>
                        <div className="max-h-40 overflow-y-auto space-y-1">
                          {(configSchema?.properties?.filter_by_labels?.options || []).map((opt: string) => {
                            const checked = (filters.filter_by_labels || []).includes(opt);
                            return (
                              <label key={opt} className="flex items-center gap-2 text-sm text-gray-700">
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  onChange={() => {
                                    const current = new Set(filters.filter_by_labels || []);
                                    if (current.has(opt)) current.delete(opt); else current.add(opt);
                                    handleFilterChange('filter_by_labels', Array.from(current));
                                  }}
                                />
                                <span className="truncate">{opt}</span>
                              </label>
                            );
                          })}
                        </div>
                      </div>
                      <div className="mt-4">
                        <button onClick={applyFilters} disabled={isLoading} className="w-full px-3 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:bg-blue-300 flex items-center justify-center gap-2">
                          {isLoading ? <Loader2 className="animate-spin h-4 w-4"/> : null}
                          {isLoading ? 'Applying...' : 'Apply Filters'}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="min-h-[200px]">{renderStepContent()}</div>
              )}
            </div>
          </div>
        </div>
        {/* Modal Footer */}
        <div className="bg-gray-50 px-6 py-4 flex justify-between items-center rounded-b-lg shrink-0">
          <div className="flex items-center gap-4">
            <span className="px-2 py-0.5 text-xs font-semibold text-purple-800 bg-purple-100 rounded-full">Experimental</span>
            {step > 1 && (
              <button onClick={handlePrevious} className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50" disabled={isLoading}>Previous</button>
            )}
          </div>
          <div>
            {step < 3 ? (
              <button onClick={handleNext} className="px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md hover:bg-blue-700 disabled:bg-blue-300 flex items-center" disabled={isLoading || (step === 1 && !selectedDataSource)}>
                {isLoading ? <Loader2 className="animate-spin h-5 w-5" /> : 'Next'}
              </button>
            ) : (
              <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-white bg-gray-600 border border-transparent rounded-md hover:bg-gray-700">Finish</button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default CreateEvaluationTemplateModal; 