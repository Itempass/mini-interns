'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { X, Loader2, Download, Edit, Plus, AlertTriangle, Play, Copy } from 'lucide-react';
import { listDataSources, getDataSourceConfigSchema, fetchDataSourceSample, createEvaluationTemplate, DataSource, EvaluationTemplate, EvaluationTemplateCreate, listEvaluationTemplates, getEvaluationTemplate, EvaluationTemplateLight, updateEvaluationTemplate, runEvaluation, getEvaluationRun, EvaluationRun } from '../../services/promptoptimizer_api';
import { JsonSchemaForm } from './JsonSchemaForm';
import { StepSidebar } from './StepSidebar';
import { isEqual } from 'lodash';

interface CreateEvaluationTemplateModalProps {
  isOpen: boolean;
  onClose: () => void;
  prompt: string;
  model: string;
}

const CreateEvaluationTemplateModal: React.FC<CreateEvaluationTemplateModalProps> = ({ isOpen, onClose, prompt, model }) => {
  const [step, setStep] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [isDownloading, setIsDownloading] = useState<string | null>(null); // Store UUID of downloading template
  const [errorMessage, setErrorMessage] = useState('');

  // Mode state
  const [mode, setMode] = useState<'new' | 'edit'>('new');
  const [editingTemplate, setEditingTemplate] = useState<EvaluationTemplate | null>(null);
  const [isDirty, setIsDirty] = useState(false);
  const [dataSourceConfigDirty, setDataSourceConfigDirty] = useState(false);

  // Step 1 state
  const [dataSources, setDataSources] = useState<DataSource[]>([]);
  const [selectedDataSource, setSelectedDataSource] = useState<string>('');
  const [existingTemplates, setExistingTemplates] = useState<EvaluationTemplateLight[]>([]);

  // We define the steps here for the sidebar
  const steps = [
    { name: 'Select Source' },
    { name: 'Configure' },
    { name: 'Map Fields' },
    { name: 'Name & Save' },
    { name: 'Run Evaluation' },
    { name: 'Finish' },
  ];

  // Step 2 state
  const [configSchema, setConfigSchema] = useState<Record<string, any> | null>(null);
  const [configValues, setConfigValues] = useState<Record<string, any>>({});

  // Step 3 state
  const [sampleData, setSampleData] = useState<Record<string, any> | null>(null);
  const [sampleDataKeys, setSampleDataKeys] = useState<string[]>([]);
  const [inputField, setInputField] = useState<string>('');
  const [groundTruthField, setGroundTruthField] = useState<string>('');
  const [groundTruthTransform, setGroundTruthTransform] = useState<string>('none');
  
  // Step 4 state
  const [templateName, setTemplateName] = useState('');
  const [templateDescription, setTemplateDescription] = useState('');

  // New state for evaluation runs
  const [runningTemplate, setRunningTemplate] = useState<EvaluationTemplateLight | null>(null);
  const [currentRun, setCurrentRun] = useState<EvaluationRun | null>(null);
  const [isPolling, setIsPolling] = useState(false);

  // New state for data snapshot polling
  const [pollingTemplateUuid, setPollingTemplateUuid] = useState<string | null>(null);
  const [isPollingData, setIsPollingData] = useState(false);


  // Step 5 state (Success)
  const [createdTemplate, setCreatedTemplate] = useState<EvaluationTemplate | null>(null);

  const transformations = [
    { id: 'none', name: 'None' },
    { id: 'join_comma', name: 'Join array with comma' },
    { id: 'first_element', name: 'Extract first element from array' },
  ];

  const applyTransform = (value: any, transform: string): any => {
    if (value === undefined || value === null) return value;

    switch (transform) {
        case 'join_comma':
            if (Array.isArray(value)) {
                return value.join(', ');
            }
            return value;
        case 'first_element':
            if (Array.isArray(value) && value.length > 0) {
                return value[0];
            }
            return value;
        case 'none':
        default:
            return value;
    }
  };

  // Function to check for changes
  const checkForChanges = useCallback(() => {
    if (mode !== 'edit' || !editingTemplate) return;

    // Check if data source config (tool or params) has changed
    const originalDataSourceConfig = editingTemplate.data_source_config;
    const currentDataSourceConfig = { tool: selectedDataSource, params: configValues };
    const dataSourceChanged = !isEqual(originalDataSourceConfig, currentDataSourceConfig);
    setDataSourceConfigDirty(dataSourceChanged);

    const currentConfig = {
      name: templateName,
      description: templateDescription,
      data_source_config: {
        tool: selectedDataSource,
        params: configValues
      },
      field_mapping_config: {
        input_field: inputField,
        ground_truth_field: groundTruthField,
        ground_truth_transform: groundTruthTransform === 'none' ? undefined : groundTruthTransform
      }
    };

    const originalConfig = {
        name: editingTemplate.name,
        description: editingTemplate.description || '',
        data_source_config: editingTemplate.data_source_config,
        field_mapping_config: editingTemplate.field_mapping_config
    };

    // Use a deep comparison to check if anything has changed.
    if (!isEqual(currentConfig, originalConfig)) {
        setIsDirty(true);
    } else {
        setIsDirty(false);
    }
  }, [mode, editingTemplate, templateName, templateDescription, selectedDataSource, configValues, inputField, groundTruthField, groundTruthTransform]);

  // Effect to run the check whenever a dependency changes
  useEffect(() => {
    checkForChanges();
  }, [checkForChanges]);


  useEffect(() => {
    if (isOpen) {
      // Reset state when modal is opened
      setStep(1);
      setMode('new');
      setIsDirty(false);
      setDataSourceConfigDirty(false);
      setIsLoading(false);
      setErrorMessage('');
      setConfigSchema(null);
      setSampleData(null);
      setCreatedTemplate(null);
      setGroundTruthTransform('none');

      setIsLoading(true);
      Promise.all([
        listDataSources(),
        listEvaluationTemplates()
      ]).then(([sources, templates]) => {
        setDataSources(sources);
        if (sources.length > 0) {
          setSelectedDataSource(sources[0].id);
        }
        setExistingTemplates(templates);
      }).catch(err => {
        setErrorMessage('Failed to load initial data. Please try again.');
        console.error(err);
      }).finally(() => {
        setIsLoading(false);
      });
    }
  }, [isOpen]);

  const handleStepClick = (stepIndex: number) => {
    // Allow jumping back to any previously completed step
    if (stepIndex < step) {
      setStep(stepIndex);
    }
  };

  // When opening in edit mode, we need to fetch the full template and populate state
  const handleEditClick = async (templateToEdit: EvaluationTemplateLight) => {
    setIsLoading(true);
    setErrorMessage('');
    try {
      const fullTemplate = await getEvaluationTemplate(templateToEdit.uuid);
      setMode('edit');
      setEditingTemplate(fullTemplate);

      // Pre-populate all the state needed for the steps
      setSelectedDataSource(fullTemplate.data_source_config.tool);
      setConfigValues(fullTemplate.data_source_config.params);
      setTemplateName(fullTemplate.name);
      setTemplateDescription(fullTemplate.description || '');
      setInputField(fullTemplate.field_mapping_config.input_field);
      setGroundTruthField(fullTemplate.field_mapping_config.ground_truth_field);
      setGroundTruthTransform(fullTemplate.field_mapping_config.ground_truth_transform || 'none');
      
      // Need to fetch the config schema to be able to render the config step
      const schema = await getDataSourceConfigSchema(fullTemplate.data_source_config.tool);
      setConfigSchema(schema);

      // Use the first record from the existing cached_data as the sample.
      // This avoids refetching and ensures consistency.
      if (fullTemplate.cached_data && fullTemplate.cached_data.length > 0) {
        const sample = fullTemplate.cached_data[0];
        setSampleData(sample);
        setSampleDataKeys(Object.keys(sample));
      } else {
        // If there's no cached data for some reason, fetch a sample as a fallback.
        const sample = await fetchDataSourceSample(fullTemplate.data_source_config.tool, fullTemplate.data_source_config.params);
        setSampleData(sample);
        setSampleDataKeys(Object.keys(sample));
      }

      setIsDirty(false); // Reset dirty flag when loading an item to edit
      setDataSourceConfigDirty(false);
      // Jump to the second step (Configure)
      setStep(2);

    } catch(err) {
      setErrorMessage("Failed to load template data for editing.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleRunEvaluation = async (template: EvaluationTemplateLight) => {
    setIsLoading(true);
    setErrorMessage('');
    setRunningTemplate(template);
    
    try {
      // The API now returns the created run object immediately
      const newRun = await runEvaluation(template.uuid, prompt, model);
      setCurrentRun(newRun);
      setIsPolling(true);
      setStep(6); // Move to the "Running" step
    } catch (err) {
      setErrorMessage(err.message || 'Failed to start evaluation.');
      setIsLoading(false);
    }
  };


  useEffect(() => {
    if (!isPolling || !currentRun) return;

    const interval = setInterval(async () => {
      try {
        const run = await getEvaluationRun(currentRun.uuid);
        if (run.status === 'completed' || run.status === 'failed') {
          setIsPolling(false);
          setIsLoading(false);
          setCurrentRun(run);
          setStep(7); // Move to results step
          clearInterval(interval);
        } else {
          // Keep polling, maybe update some state to show progress
          setCurrentRun(run);
        }
      } catch (error) {
        console.error("Polling failed", error);
        setErrorMessage('Failed to get evaluation status.');
        setIsPolling(false);
        clearInterval(interval);
        setStep(1);
      }
    }, 3000); // Poll every 3 seconds

    return () => clearInterval(interval);
  }, [isPolling, currentRun, getEvaluationRun]);


  // Effect for polling template creation status
  useEffect(() => {
    if (!isPollingData || !pollingTemplateUuid) return;

    const interval = setInterval(async () => {
      try {
        const template = await getEvaluationTemplate(pollingTemplateUuid);
        if (template.status === 'completed') {
          setIsPollingData(false);
          setCreatedTemplate(template);
          setIsLoading(false);
          setStep(5); // Move to success step
          clearInterval(interval);
        } else if (template.status === 'failed') {
          setIsPollingData(false);
          setIsLoading(false);
          setErrorMessage(template.processing_error || 'Data processing failed. Please check the logs.');
          setStep(4); // Go back to the save step to show the error
          clearInterval(interval);
        }
        // If status is "processing", we just continue polling.
      } catch (error) {
        console.error("Template status polling failed", error);
        setErrorMessage('Failed to get template creation status.');
        setIsPollingData(false);
        setIsLoading(false);
        clearInterval(interval);
        setStep(4);
      }
    }, 3000); // Poll every 3 seconds

    return () => clearInterval(interval);
  }, [isPollingData, pollingTemplateUuid, getEvaluationTemplate]);


  const handleCreateNewClick = async () => {
    setMode('new');
    setStep(1); // Ensure we are on the correct step before proceeding
    await handleNext();
  };


  const handleNext = async () => {
    setErrorMessage('');
    setIsLoading(true);

    if (step === 1) {
      // Step 1 -> 2: Fetch config schema for selected data source
      try {
        const schema = await getDataSourceConfigSchema(selectedDataSource);
        setConfigSchema(schema);
        // Set default values from the schema, including for the multi-select arrays
        const defaultValues: Record<string, any> = {};
        for (const key in schema.properties) {
            defaultValues[key] = schema.properties[key].default ?? (schema.properties[key].type === 'array' ? [] : undefined);
        }
        setConfigValues(defaultValues);
        setStep(2);
      } catch (err) {
        setErrorMessage(err.message || 'An unknown error occurred');
      }
    } else if (step === 2) {
      // Step 2 -> 3: In edit mode, check for changes. If dirty, warn user. Otherwise, proceed.
      if (mode === 'edit' && dataSourceConfigDirty) {
        // The user is now warned in Step 4, so no confirmation is needed here.
        // We just proceed with fetching the new sample.
      }

      // Only fetch a new sample if the config is dirty in edit mode, or if we're in new mode.
      if (mode === 'new' || dataSourceConfigDirty) {
        try {
          const sample = await fetchDataSourceSample(selectedDataSource, configValues);
          setSampleData(sample);
          const keys = Object.keys(sample);
          setSampleDataKeys(keys);
          if (mode === 'new' || !inputField || !groundTruthField) {
              setInputField(keys[0] || '');
              setGroundTruthField(keys[0] || '');
          }
        } catch (err) {
          setErrorMessage(err.message || 'An unknown error occurred');
          setIsLoading(false);
          return;
        }
      }
      
      setStep(3);

    } else if (step === 3) {
      // Step 3 -> 4: Simple transition, no async logic
      setStep(4);
    }
    
    setIsLoading(false);
  };
  
  const handlePrevious = () => {
    setStep(prev => prev - 1);
    setErrorMessage('');
  };

  const handleSave = async () => {
    if (!templateName.trim()) {
        setErrorMessage("Template name is required.");
        return;
    }
    setIsLoading(true);
    setErrorMessage('');

    const templateData: EvaluationTemplateCreate = {
        name: templateName,
        description: templateDescription,
        data_source_config: {
            tool: selectedDataSource,
            params: configValues
        },
        field_mapping_config: {
            input_field: inputField,
            ground_truth_field: groundTruthField,
            ground_truth_transform: groundTruthTransform === 'none' ? undefined : groundTruthTransform,
        }
    };

    // Only include the data_source_config if we are creating new, or if it has changed in edit mode.
    // This prevents the backend from refetching data unnecessarily.
    if (mode === 'new' || (mode === 'edit' && dataSourceConfigDirty)) {
        templateData.data_source_config = {
            tool: selectedDataSource,
            params: configValues
        };
    }

    try {
        let savedTemplate;
        if (mode === 'edit' && editingTemplate) {
            if (isDirty) {
                 savedTemplate = await updateEvaluationTemplate(editingTemplate.uuid, templateData);
            } else {
                 savedTemplate = editingTemplate; // No changes, so no-op
            }
        } else {
            savedTemplate = await createEvaluationTemplate(templateData as EvaluationTemplateCreate);
        }

        // When creating a new template, always go to the processing step to await the background job.
        // For edits, the status determines the next step.
        if (mode === 'new' || savedTemplate.status === 'processing') {
            setPollingTemplateUuid(savedTemplate.uuid);
            setIsPollingData(true);
            setStep(8); // Move to the new "processing" step
        } else if (savedTemplate.status === 'completed') {
            setCreatedTemplate(savedTemplate);
            setStep(5); // This handles edits where data wasn't refetched
        } else { // status === 'failed' or something unexpected
            setErrorMessage(savedTemplate.processing_error || "An unknown error occurred during template creation.");
        }
    } catch (err) {
        console.error("DEBUG: Error in handleSave:", err);
        setErrorMessage(err.message || 'An unknown error occurred');
    } finally {
        setIsLoading(false);
    }
  };

  const handleDownloadSnapshot = async (template: EvaluationTemplateLight) => {
    setIsDownloading(template.uuid);
    try {
      // Fetch the full template data on-demand
      const fullTemplate = await getEvaluationTemplate(template.uuid);
      const snapshotJson = JSON.stringify(fullTemplate.cached_data, null, 2);
      const blob = new Blob([snapshotJson], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${fullTemplate.name.replace(/\s+/g, '_').toLowerCase()}_snapshot.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (error) {
        console.error("Download failed", error);
        setErrorMessage("Failed to download snapshot.");
    } finally {
        setIsDownloading(null);
    }
  };

  const handleDownloadSuccessSnapshot = () => {
    if (!createdTemplate) return;

    const snapshotJson = JSON.stringify(createdTemplate.cached_data, null, 2);
    const blob = new Blob([snapshotJson], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${createdTemplate.name.replace(/\s+/g, '_').toLowerCase()}_snapshot.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const renderStepContent = () => {
    if (isLoading && step === 1) {
      return <div className="flex justify-center items-center p-8"><Loader2 className="animate-spin" /></div>;
    }
    
    switch (step) {
      case 1: // Select Path: Create New or Edit Existing
        return (
          <div>
            <div className="p-4 border border-gray-200 rounded-lg hover:bg-gray-50">
                <button onClick={handleCreateNewClick} className="w-full text-left">
                    <div className="flex items-center">
                        <span className="p-2 bg-blue-100 text-blue-600 rounded-lg"><Plus size={20}/></span>
                        <div className="ml-4">
                            <h3 className="text-lg font-medium text-gray-900">Create New Template</h3>
                            <p className="mt-1 text-sm text-gray-600">Start from scratch by choosing a data source.</p>
                        </div>
                    </div>
                </button>
            </div>

            <div className="mt-6">
                <h4 className="text-lg font-medium text-gray-800">Or, Edit an Existing Template</h4>
                <div className="mt-2 border border-gray-200 rounded-md max-h-60 overflow-y-auto">
                    {existingTemplates.length > 0 ? (
                        <ul className="divide-y divide-gray-200">
                            {existingTemplates.map(template => (
                                <li key={template.uuid} className="px-3 py-2 flex justify-between items-center text-sm">
                                    <div>
                                        <p className="font-medium text-gray-700">{template.name}</p>
                                        <p className="text-gray-500 text-xs">Last updated: {new Date(template.updated_at).toLocaleDateString()}</p>
                                    </div>
                                    <div>
                                        <button
                                            onClick={() => handleDownloadSnapshot(template)}
                                            className="p-1 text-gray-500 rounded-md hover:bg-gray-100 hover:text-gray-800 disabled:opacity-50"
                                            title={`Download snapshot for ${template.name}`}
                                            disabled={isDownloading === template.uuid}
                                        >
                                            {isDownloading === template.uuid ? <Loader2 size={18} className="animate-spin" /> : <Download size={18} />}
                                        </button>
                                        <button
                                            onClick={() => handleEditClick(template)}
                                            className="p-1 ml-2 text-gray-500 rounded-md hover:bg-gray-100 hover:text-gray-800"
                                            title={`Edit ${template.name}`}
                                        >
                                            <Edit size={18} />
                                        </button>
                                        <button
                                            onClick={() => handleRunEvaluation(template)}
                                            className="p-1 ml-2 text-green-600 rounded-md hover:bg-green-100"
                                            title={`Run evaluation with ${template.name}`}
                                        >
                                            <Play size={18} />
                                        </button>
                                    </div>
                                </li>
                            ))}
                        </ul>
                    ) : (
                        <p className="p-4 text-sm text-gray-500">{isLoading ? "Loading templates..." : "No existing templates found."}</p>
                    )}
                </div>
            </div>
          </div>
        );
      case 2: // Configure Data Source
        return (
            <div>
                <h3 className="text-lg font-medium text-gray-900">Step 2: Configure Data Source</h3>
                <p className="mt-2 text-sm text-gray-600">Set the parameters for fetching your data.</p>
                {isLoading ? <div className="flex justify-center items-center p-8"><Loader2 className="animate-spin" /></div> : 
                    (configSchema && <JsonSchemaForm schema={configSchema} formData={configValues} onChange={setConfigValues} />)
                }
            </div>
        );
      case 3: // Map Fields
        return (
          <div>
            <h3 className="text-lg font-medium text-gray-900">Step 3: Map Data Fields</h3>
            <p className="mt-2 text-sm text-gray-600">
                We fetched a sample record. Tell us which fields to use for the evaluation.
            </p>
            {isLoading ? <div className="flex justify-center items-center p-8"><Loader2 className="animate-spin" /></div> : 
                (sampleData && Object.keys(sampleData).length > 0 ?
                    <div className="space-y-4 mt-4">
                        <pre className="bg-gray-100 p-4 rounded-md text-xs overflow-auto max-h-48">
                            {JSON.stringify(sampleData, null, 2)}
                        </pre>
                        <div>
                            <label className="block text-sm font-medium">Prompt Input</label>
                            <select value={inputField} onChange={e => setInputField(e.target.value)} className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md">
                                {sampleDataKeys.map(key => <option key={key} value={key}>{key}</option>)}
                            </select>
                        </div>
                        <div>
                            <label className="block text-sm font-medium">Ground Truth</label>
                            <select value={groundTruthField} onChange={e => setGroundTruthField(e.target.value)} className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md">
                                {sampleDataKeys.map(key => <option key={key} value={key}>{key}</option>)}
                            </select>
                        </div>
                        <div>
                          <label className="block text-sm font-medium">Ground Truth Post-processing</label>
                          <select value={groundTruthTransform} onChange={e => setGroundTruthTransform(e.target.value)} className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md">
                              {transformations.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                          </select>
                        </div>
                         <div className="mt-4 p-3 bg-gray-50 border border-gray-200 rounded-md">
                             <h4 className="text-sm font-medium text-gray-600">Preview</h4>
                             <div className="mt-2 space-y-1 text-xs bg-white p-2 rounded overflow-auto max-h-28">
                                 <p className="break-words">
                                     <span className="font-semibold text-gray-500">Original:</span>
                                     <span> {JSON.stringify(sampleData[groundTruthField])}</span>
                                 </p>
                                 <p className="break-words">
                                     <span className="font-semibold text-gray-500">Transformed:</span>
                                     <span> {JSON.stringify(applyTransform(sampleData[groundTruthField], groundTruthTransform))}</span>
                                 </p>
                             </div>
                         </div>
                    </div>
                : <p className="text-sm text-gray-600 mt-4">No sample data found for this configuration. Try adjusting your parameters in the previous step.</p>)
            }
          </div>
        );
      case 4: // Save
        return (
            <div>
                <h3 className="text-lg font-medium text-gray-900">Step 4: Name and Save</h3>
                <p className="mt-2 text-sm text-gray-600">Give your evaluation template a name.</p>

                {mode === 'edit' && dataSourceConfigDirty && (
                     <div className="mt-4 p-3 bg-red-100 border border-red-300 rounded-md flex items-start">
                         <AlertTriangle className="h-5 w-5 text-red-500 mr-3 flex-shrink-0" />
                         <div>
                             <h4 className="font-bold text-red-800">Warning: Dataset Will Be Replaced</h4>
                             <p className="text-sm text-red-700 mt-1">You changed the data source configuration. Saving will permanently discard the original dataset and create a new one based on your new settings.</p>
                         </div>
                     </div>
                )}

                {mode === 'edit' && isDirty && !dataSourceConfigDirty && (
                    <div className="mt-4 p-3 bg-yellow-50 border border-yellow-300 rounded-md flex items-center">
                        <AlertTriangle className="h-5 w-5 text-yellow-500 mr-2" />
                        <p className="text-sm text-yellow-700">You have unsaved changes. Saving will update the template's details.</p>
                    </div>
                )}

                <div className="space-y-4 mt-4">
                    <div>
                        <label htmlFor="template-name" className="block text-sm font-medium">Template Name</label>
                        <input
                            type="text"
                            id="template-name"
                            value={templateName}
                            onChange={(e) => setTemplateName(e.target.value)}
                            className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md"
                            placeholder="e.g., Email Categorization Test"
                        />
                    </div>
                    <div>
                        <label htmlFor="template-desc" className="block text-sm font-medium">Description (Optional)</label>
                        <textarea
                            id="template-desc"
                            value={templateDescription}
                            onChange={(e) => setTemplateDescription(e.target.value)}
                            rows={3}
                            className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md"
                        />
                    </div>
                </div>
            </div>
        );
      case 5: // Run Evaluation
        return (
          <div>
            <h3 className="text-lg font-medium text-green-700">Template Ready for Evaluation</h3>
            <p className="mt-2 text-sm text-gray-600">
              Your template "{createdTemplate?.name}" has been created with {createdTemplate?.cached_data?.length || 0} records. You can now run an evaluation or download the data snapshot.
            </p>
            <div className="mt-6 border-t pt-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <button
                      onClick={() => createdTemplate && handleRunEvaluation(createdTemplate)}
                      disabled={!createdTemplate || isLoading}
                      className="w-full flex items-center justify-center px-4 py-3 text-sm font-medium text-white bg-green-600 border border-transparent rounded-md hover:bg-green-700 disabled:bg-green-300 disabled:cursor-not-allowed"
                  >
                      <X className="mr-2 h-4 w-4" />
                      Run Evaluation
                  </button>
                  <button
                      onClick={handleDownloadSuccessSnapshot}
                      disabled={!createdTemplate}
                      className="w-full flex items-center justify-center px-4 py-3 text-sm font-medium text-blue-700 bg-blue-100 border border-transparent rounded-md hover:bg-blue-200 disabled:bg-gray-100 disabled:text-gray-400 disabled:cursor-not-allowed"
                  >
                      <Download className="mr-2 h-4 w-4" />
                      Download Snapshot
                  </button>
              </div>
            </div>
          </div>
        );
      case 6: // Running Evaluation
        return (
            <div className="text-center p-8">
                <Loader2 className="h-12 w-12 text-blue-600 animate-spin mx-auto" />
                <h3 className="mt-4 text-lg font-medium text-gray-900">Running Evaluation...</h3>
                <p className="mt-2 text-sm text-gray-600">
                    Evaluating <span className="font-semibold">{runningTemplate?.name}</span>. This may take a few minutes.
                </p>
            </div>
        );
      case 7: // Results
        return <EvaluationResultsView run={currentRun} onClose={onClose} />;
      case 8: // Processing Data Snapshot
        return (
            <div className="text-center p-8">
                <Loader2 className="h-12 w-12 text-blue-600 animate-spin mx-auto" />
                <h3 className="mt-4 text-lg font-medium text-gray-900">Processing Dataset...</h3>
                <p className="mt-2 text-sm text-gray-600">
                    We're fetching and preparing your data. This may take a few minutes.
                </p>
            </div>
        );
      default:
        return null;
    }
  };

  if (!isOpen) {
    return null;
  }

  // Map internal step state to the visual step in the sidebar
  let displayStep = step;
  if (step === 6) displayStep = 5; // "Running..." loader should keep "Run Evaluation" active
  if (step === 7) displayStep = 6; // "Results" view is the "Finish" step
  if (step === 8) displayStep = 4; // "Processing..." loader should keep "Name & Save" active


  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl transform transition-all">
        <div className="p-6">
          <div className="flex items-start justify-between">
            <div>
                <h2 className="text-xl font-semibold text-gray-800">
                    {mode === 'edit' && editingTemplate ? 'Editing Template' : 'Create Evaluation Template'}
                </h2>
                {mode === 'edit' && editingTemplate && (
                    <p className="text-sm text-gray-500 mt-1">
                        Editing: <span className="font-medium">{editingTemplate.name}</span>
                    </p>
                )}
            </div>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
              <X size={24} />
            </button>
          </div>
          {errorMessage && <div className="mt-4 bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative" role="alert">
            <strong className="font-bold">Error:</strong>
            <span className="block sm:inline"> {errorMessage}</span>
          </div>}
          <div className="mt-6 flex space-x-8">
            <div className="w-1/4">
              <StepSidebar steps={steps} currentStep={displayStep} onStepClick={handleStepClick} />
            </div>
            <div className="w-3/4 pr-4">
                <div className="min-h-[400px]">
            {renderStepContent()}
                </div>
            </div>
          </div>
        </div>
        <div className="bg-gray-50 px-6 py-4 flex justify-between items-center rounded-b-lg">
          <div className="flex items-center gap-4">
            <span className="px-2 py-0.5 text-xs font-semibold text-purple-800 bg-purple-100 rounded-full">
                Experimental
            </span>
            {step > 1 && step < 5 && (
              <button
                onClick={handlePrevious}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
                disabled={isLoading}
              >
                Previous
              </button>
            )}
          </div>
          <div>
            {step < 4 ? (
              <button
                onClick={handleNext}
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md hover:bg-blue-700 disabled:bg-blue-300 flex items-center"
                disabled={isLoading || (step === 1 && !selectedDataSource) || (step === 3 && !sampleData)}
              >
                {isLoading ? <Loader2 className="animate-spin h-5 w-5" /> : "Next"}
              </button>
            ) : step === 4 ? (
              <button
                onClick={handleSave}
                className="px-4 py-2 text-sm font-medium text-white bg-green-600 border border-transparent rounded-md hover:bg-green-700 disabled:bg-green-300 flex items-center"
                disabled={isLoading || !templateName.trim()}
              >
                {isLoading ? <Loader2 className="animate-spin h-5 w-5" /> : (mode === 'edit' ? 'Save Changes' : 'Create Template')}
              </button>
            ) : (
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm font-medium text-white bg-gray-600 border border-transparent rounded-md hover:bg-gray-700"
              >
                Finish
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};


const EvaluationResultsView: React.FC<{ run: EvaluationRun | null, onClose: () => void }> = ({ run, onClose }) => {
    const [promptCopied, setPromptCopied] = useState(false);

    if (!run) {
        return (
            <div className="text-center p-8">
                <h3 className="text-lg font-medium text-red-700">Error</h3>
                <p className="mt-2 text-sm text-gray-600">Could not load evaluation results.</p>
            </div>
        );
    }

    if (run.status === 'failed') {
        return (
            <div className="text-center p-8">
                <h3 className="text-lg font-medium text-red-700">Evaluation Failed</h3>
                <p className="mt-2 text-sm text-gray-600">Something went wrong during the evaluation. Please check the system logs for more details.</p>
            </div>
        )
    }

    const v1_accuracy = run.summary_report?.v1_accuracy ?? 0;
    const v2_accuracy = run.summary_report?.v2_accuracy ?? 0;
    const refined_prompt = run.detailed_results?.refined_prompt_v2 ?? "No prompt generated.";

    const handleCopyPrompt = () => {
        navigator.clipboard.writeText(refined_prompt);
        setPromptCopied(true);
        setTimeout(() => setPromptCopied(false), 2000);
    };

    return (
        <div>
            <h3 className="text-lg font-medium text-gray-900">Evaluation Complete</h3>
            <div className="mt-4 grid grid-cols-2 gap-4 text-center">
                <div className="p-4 bg-gray-100 rounded-lg">
                    <p className="text-sm font-medium text-gray-600">Original Prompt (V1)</p>
                    <p className="text-3xl font-bold text-gray-800 mt-1">{(v1_accuracy * 100).toFixed(1)}%</p>
                    <p className="text-xs text-gray-500">Accuracy</p>
                </div>
                <div className="p-4 bg-green-100 rounded-lg border border-green-300">
                    <p className="text-sm font-medium text-green-700">Refined Prompt (V2)</p>
                    <p className="text-3xl font-bold text-green-800 mt-1">{(v2_accuracy * 100).toFixed(1)}%</p>
                    <p className="text-xs text-green-500">Accuracy</p>
                </div>
            </div>
            <div className="mt-6">
                <label className="block text-sm font-medium text-gray-700">Refined Prompt (V2)</label>
                <div className="relative mt-1">
                    <textarea
                        readOnly
                        value={refined_prompt}
                        rows={8}
                        className="w-full p-2 border border-gray-300 rounded-md bg-gray-50 text-sm font-mono"
                    />
                    <button
                        onClick={handleCopyPrompt}
                        className="absolute top-2 right-2 p-1 text-gray-500 rounded hover:bg-gray-200"
                    >
                        {promptCopied ? <span className="text-xs text-green-600">Copied!</span> : <Copy size={16} />}
                    </button>
                </div>
            </div>
        </div>
    );
};


export default CreateEvaluationTemplateModal; 