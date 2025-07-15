import React, { useState, useEffect } from 'react';
import { TriggerModel } from '../../../services/workflows_api';

interface EditNewEmailTriggerProps {
  trigger: TriggerModel;
  onSave: (triggerData: any) => void;
  onCancel: () => void;
  isLoading?: boolean;
}

const EditNewEmailTrigger: React.FC<EditNewEmailTriggerProps> = ({ trigger, onSave, onCancel, isLoading = false }) => {
  const [filterRuleStrings, setFilterRuleStrings] = useState({
    email_blacklist: '',
    email_whitelist: '',
    domain_blacklist: '',
    domain_whitelist: '',
  });
  
  const [filterErrors, setFilterErrors] = useState({
    email_blacklist: '',
    email_whitelist: '',
    domain_blacklist: '',
    domain_whitelist: '',
  });
  
  const [isDirty, setIsDirty] = useState(false);

  // Initialize filter rules from trigger
  useEffect(() => {
    const filterRules = trigger?.filter_rules || {};
    const newFilterRuleStrings = {
      email_blacklist: filterRules.email_blacklist?.join(', ') || '',
      email_whitelist: filterRules.email_whitelist?.join(', ') || '',
      domain_blacklist: filterRules.domain_blacklist?.join(', ') || '',
      domain_whitelist: filterRules.domain_whitelist?.join(', ') || '',
    };
    setFilterRuleStrings(newFilterRuleStrings);
    setFilterErrors({
      email_blacklist: '',
      email_whitelist: '',
      domain_blacklist: '',
      domain_whitelist: '',
    });
    setIsDirty(false);
  }, [trigger]);

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

  // Handle filter rule changes
  const handleFilterRuleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFilterRuleStrings(prev => ({
      ...prev,
      [name]: value,
    }));
    validateFilterInput(name, value);
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

    console.log('[EditNewEmailTrigger] Saving with filter rules:', finalFilterRules);
    onSave(finalFilterRules);
  };

  return (
    <div className="mt-4 p-6 bg-white border border-gray-300 rounded-lg">
      <div className="flex justify-between items-center mb-4">
        <h4 className="text-lg font-semibold">Email Trigger Settings</h4>
        <button
          onClick={onCancel}
          className="text-gray-400 hover:text-gray-600 w-6 h-6 flex items-center justify-center"
        >
          ×
        </button>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700">Email Blacklist (comma-separated)</label>
          <textarea 
            name="email_blacklist" 
            value={filterRuleStrings.email_blacklist} 
            onChange={handleFilterRuleChange} 
            rows={2} 
            className="mt-1 block w-full rounded-md border-gray-400 shadow-sm sm:text-sm p-2 border" 
          />
          <p className="text-xs text-gray-600 mt-1">Stop processing emails from these specific addresses. Ex: spam@example.com, junk@mail.net</p>
          {filterErrors.email_blacklist && <p className="text-xs text-red-600 mt-1">{filterErrors.email_blacklist}</p>}
        </div>
        
        <div>
          <label className="block text-sm font-medium text-gray-700">Email Whitelist (comma-separated)</label>
          <textarea 
            name="email_whitelist" 
            value={filterRuleStrings.email_whitelist} 
            onChange={handleFilterRuleChange} 
            rows={2} 
            className="mt-1 block w-full rounded-md border-gray-400 shadow-sm sm:text-sm p-2 border" 
          />
          <p className="text-xs text-gray-600 mt-1">If used, only emails from these addresses will proceed. Ex: boss@mycompany.com</p>
          {filterErrors.email_whitelist && <p className="text-xs text-red-600 mt-1">{filterErrors.email_whitelist}</p>}
        </div>
        
        <div>
          <label className="block text-sm font-medium text-gray-700">Domain Blacklist (comma-separated)</label>
          <textarea 
            name="domain_blacklist" 
            value={filterRuleStrings.domain_blacklist} 
            onChange={handleFilterRuleChange} 
            rows={2} 
            className="mt-1 block w-full rounded-md border-gray-400 shadow-sm sm:text-sm p-2 border" 
          />
          <p className="text-xs text-gray-600 mt-1">Stop processing emails from these domains. Ex: evil-corp.com, bad-actors.org</p>
          {filterErrors.domain_blacklist && <p className="text-xs text-red-600 mt-1">{filterErrors.domain_blacklist}</p>}
        </div>
        
        <div>
          <label className="block text-sm font-medium text-gray-700">Domain Whitelist (comma-separated)</label>
          <textarea 
            name="domain_whitelist" 
            value={filterRuleStrings.domain_whitelist} 
            onChange={handleFilterRuleChange} 
            rows={2} 
            className="mt-1 block w-full rounded-md border-gray-400 shadow-sm sm:text-sm p-2 border" 
          />
          <p className="text-xs text-gray-600 mt-1">If used, only emails from these domains will proceed. Ex: mycompany.com</p>
          {filterErrors.domain_whitelist && <p className="text-xs text-red-600 mt-1">{filterErrors.domain_whitelist}</p>}
        </div>
      </div>
      
      <div className="flex justify-end space-x-3 mt-6">
        <button
          onClick={onCancel}
          className="px-4 py-2 text-gray-600 bg-gray-100 rounded-md hover:bg-gray-200"
        >
          Cancel
        </button>
        <button
          onClick={handleSave}
          disabled={isLoading || !isDirty}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
        >
          {isLoading ? 'Saving...' : 'Save Settings'}
        </button>
      </div>
    </div>
  );
};

export default EditNewEmailTrigger; 