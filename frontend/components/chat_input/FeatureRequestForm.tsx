'use client';

import React, { useState, useEffect } from 'react';

interface FeatureRequestFormProps {
  request: {
    tool_call_id: string;
    data: {
      name: string;
      description: string;
    };
  };
  onSubmit: (formData: { name: string; description: string }) => Promise<void>;
  isSubmitting: boolean;
}

const FeatureRequestForm: React.FC<FeatureRequestFormProps> = ({ request, onSubmit, isSubmitting }) => {
  const [name, setName] = useState(request.data.name || '');
  const [description, setDescription] = useState(request.data.description || '');

  useEffect(() => {
    setName(request.data.name || '');
    setDescription(request.data.description || '');
  }, [request.data]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !description.trim()) {
      // You could add a more robust validation message here
      alert('Both name and description are required.');
      return;
    }
    onSubmit({ name, description });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <h4 className="font-semibold text-lg text-gray-800">Feature Proposal</h4>
        <p className="text-sm text-gray-600">
          Submit a feature request to the team.
        </p>
      </div>
      <div>
        <label htmlFor="feature-name" className="block text-sm font-medium text-gray-700">
          Feature Name
        </label>
        <input
          type="text"
          id="feature-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="mt-1 block w-full px-3 py-2 bg-white border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
          placeholder="e.g., Automatic Email Summarizer"
          disabled={isSubmitting}
        />
      </div>
      <div>
        <label htmlFor="feature-description" className="block text-sm font-medium text-gray-700">
          Description
        </label>
        <textarea
          id="feature-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={4}
          className="mt-1 block w-full px-3 py-2 bg-white border border-gray-300 rounded-md shadow-sm placeholder-gray-400 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
          placeholder="Describe what this feature should do."
          disabled={isSubmitting}
        />
      </div>
      <div className="flex justify-end">
        <button
          type="submit"
          className="inline-flex justify-center py-2 px-4 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:bg-gray-400"
          disabled={isSubmitting || !name.trim() || !description.trim()}
        >
          {isSubmitting ? 'Submitting...' : 'Submit Feature Request'}
        </button>
      </div>
    </form>
  );
};

export default FeatureRequestForm; 