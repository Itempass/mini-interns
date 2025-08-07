import React, { useState, useEffect } from 'react';
import { TriggerModel, getAvailableLLMModels, LLMModel } from '../../../services/workflows_api';

interface EditNewEmailTriggerProps {
  trigger: TriggerModel;
  onSave: (triggerData: any) => void;
  isLoading?: boolean;
}

const EditNewEmailTrigger: React.FC<EditNewEmailTriggerProps> = ({ trigger, onSave, isLoading = false }) => {
  const [filterRuleStrings, setFilterRuleStrings] = useState({
    email_blacklist: '',
    email_whitelist: '',
    domain_blacklist: '',
    domain_whitelist: '',
  });

  const [triggerPrompt, setTriggerPrompt] = useState('');
  const [selectedModel, setSelectedModel] = useState('');
  const [availableModels, setAvailableModels] = useState<LLMModel[]>([]);
  const [isLoadingModels, setIsLoadingModels] = useState(true);
  
  const [filterErrors, setFilterErrors] = useState({
    email_blacklist: '',
    email_whitelist: '',
    domain_blacklist: '',
    domain_whitelist: '',
  });
  
  const [isDirty, setIsDirty] = useState(false);

  // Initialize from trigger
  useEffect(() => {
    const filterRules = trigger?.filter_rules || {};
    const newFilterRuleStrings = {
      email_blacklist: filterRules.email_blacklist?.join(', ') || '',
      email_whitelist: filterRules.email_whitelist?.join(', ') || '',
      domain_blacklist: filterRules.domain_blacklist?.join(', ') || '',
      domain_whitelist: filterRules.domain_whitelist?.join(', ') || '',
    };
    setFilterRuleStrings(newFilterRuleStrings);
    setTriggerPrompt(trigger?.trigger_prompt || '');
    setSelectedModel(trigger?.trigger_model || '');
    
    setFilterErrors({
      email_blacklist: '',
      email_whitelist: '',
      domain_blacklist: '',
      domain_whitelist: '',
    });
    setIsDirty(false);
  }, [trigger]);

  useEffect(() => {
    const fetchModels = async () => {
      setIsLoadingModels(true);
      const models = await getAvailableLLMModels();
      setAvailableModels(models);
      // The default model is now set on the backend.
      // We still need to select it if the trigger doesn't have one yet for some reason.
      if (!selectedModel && models.length > 0) {
        if (!trigger?.trigger_model) {
            setSelectedModel(models[0].id);
        }
      }
      setIsLoadingModels(false);
    };
    fetchModels();
  }, []);

  // Validate filter input
  const validateFilterInput = (name: string, value: string) => {
    const items = value.split(',').map(item => item.trim()).filter(Boolean);
    let error = '';

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    const domainRegex = /^([a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}$/;

    for (const item of items) {
      if (name.includes('email') && !emailRegex.test(item)) {
        error = `"${item}" is not a valid email.`;
        break;
      }
      if (name.includes('domain') && !domainRegex.test(item)) {
        error = `"${item}" is not a valid domain.`;
        break;
      }
    }
    setFilterErrors(prev => ({ ...prev, [name]: error }));
  };

  // Handle changes
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value } = e.target;

    if (name in filterRuleStrings) {
        setFilterRuleStrings(prev => ({ ...prev, [name]: value, }));
        validateFilterInput(name, value);
    } else if (name === 'trigger_prompt') {
        setTriggerPrompt(value);
    } else if (name === 'trigger_model') {
        setSelectedModel(value);
    }
    
    setIsDirty(true);
  };

  // Handle save
  const handleSave = () => {
    if (Object.values(filterErrors).some(err => err)) {
      alert('Please fix the validation errors before saving.');
      return;
    }

    const finalFilterRules = {
      email_blacklist: filterRuleStrings.email_blacklist.split(',').map(item => item.trim()).filter(Boolean),
      email_whitelist: filterRuleStrings.email_whitelist.split(',').map(item => item.trim()).filter(Boolean),
      domain_blacklist: filterRuleStrings.domain_blacklist.split(',').map(item => item.trim()).filter(Boolean),
      domain_whitelist: filterRuleStrings.domain_whitelist.split(',').map(item => item.trim()).filter(Boolean),
    };

    const triggerData = {
        filter_rules: finalFilterRules,
        trigger_prompt: triggerPrompt,
        trigger_model: selectedModel
    }

    console.log('[EditNewEmailTrigger] Saving with trigger data:', triggerData);
    onSave(triggerData);
    setIsDirty(false);
  };

  return (
    <div className="p-6">
        <div className="space-y-6">
            {/* Filter Rules Section */}
            <div>
                <h3 className="text-lg font-medium text-gray-900 mb-4">Simple Filters</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700">Email Blacklist</label>
                  <textarea 
                    name="email_blacklist" 
                    value={filterRuleStrings.email_blacklist} 
                    onChange={handleInputChange} 
                    rows={2} 
                    className="mt-1 block w-full rounded-md border-gray-400 shadow-sm sm:text-sm p-2 border" 
                    placeholder="e.g., spam@example.com, junk@mail.net"
                  />
                  <p className="text-xs text-gray-600 mt-1">Do not trigger for emails from these specific addresses.</p>
                  {filterErrors.email_blacklist && <p className="text-xs text-red-600 mt-1">{filterErrors.email_blacklist}</p>}
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700">Email Whitelist</label>
                  <textarea 
                    name="email_whitelist" 
                    value={filterRuleStrings.email_whitelist} 
                    onChange={handleInputChange} 
                    rows={2} 
                    className="mt-1 block w-full rounded-md border-gray-400 shadow-sm sm:text-sm p-2 border" 
                    placeholder="e.g., boss@mycompany.com"
                  />
                  <p className="text-xs text-gray-600 mt-1">If used, only emails from these addresses will trigger.</p>
                  {filterErrors.email_whitelist && <p className="text-xs text-red-600 mt-1">{filterErrors.email_whitelist}</p>}
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700">Domain Blacklist</label>
                  <textarea 
                    name="domain_blacklist" 
                    value={filterRuleStrings.domain_blacklist} 
                    onChange={handleInputChange} 
                    rows={2} 
                    className="mt-1 block w-full rounded-md border-gray-400 shadow-sm sm:text-sm p-2 border" 
                    placeholder="e.g., evil-corp.com, bad-actors.org"
                  />
                  <p className="text-xs text-gray-600 mt-1">Do not trigger for emails from these domains.</p>
                  {filterErrors.domain_blacklist && <p className="text-xs text-red-600 mt-1">{filterErrors.domain_blacklist}</p>}
                </div>
                
                <div>
                  <label className="block text-sm font-medium text-gray-700">Domain Whitelist</label>
                  <textarea 
                    name="domain_whitelist" 
                    value={filterRuleStrings.domain_whitelist} 
                    onChange={handleInputChange} 
                    rows={2} 
                    className="mt-1 block w-full rounded-md border-gray-400 shadow-sm sm:text-sm p-2 border"
                    placeholder="e.g., mycompany.com"
                  />
                  <p className="text-xs text-gray-600 mt-1">If used, only emails from these domains will trigger.</p>
                  {filterErrors.domain_whitelist && <p className="text-xs text-red-600 mt-1">{filterErrors.domain_whitelist}</p>}
                </div>
                </div>
            </div>

            {/* LLM-based Filter Section */}
            <div>
                <h3 className="text-lg font-medium text-gray-900 mb-4">Smart Filter</h3>
                <div className="space-y-4">
                     <div>
                        <label className="block text-sm font-medium text-gray-700">Trigger Prompt</label>
                        <textarea 
                            name="trigger_prompt" 
                            value={triggerPrompt} 
                            onChange={handleInputChange} 
                            rows={4} 
                            className="mt-1 block w-full rounded-md border-gray-400 shadow-sm sm:text-sm p-2 border" 
                            placeholder="e.g., Only trigger if the email is a customer inquiry and is written in English."
                        />
                        <p className="text-xs text-gray-600 mt-1">Use natural language to describe when the workflow should run. The full email content will be checked against this prompt.</p>
                    </div>
                    <div>
                        <label htmlFor="trigger-model" className="block text-sm font-medium text-gray-700">Language Model</label>
                        <select
                            id="trigger-model"
                            name="trigger_model"
                            value={selectedModel}
                            onChange={handleInputChange}
                            className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
                            disabled={isLoadingModels}
                        >
                            {isLoadingModels ? (
                                <option>Loading models...</option>
                            ) : (
                                availableModels.map(model => (
                                    <option key={model.id} value={model.id}>{model.name}</option>
                                ))
                            )}
                        </select>
                        <p className="text-xs text-gray-600 mt-1">The model that will evaluate the email against your prompt.</p>
                    </div>
                </div>
            </div>
        </div>
      
      <div className="flex justify-end space-x-3 mt-6">
        {isDirty && (
          <button
            onClick={handleSave}
            disabled={isLoading}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
          >
            {isLoading ? 'Saving...' : 'Save Settings'}
          </button>
        )}
      </div>
    </div>
  );
};

export default EditNewEmailTrigger; 