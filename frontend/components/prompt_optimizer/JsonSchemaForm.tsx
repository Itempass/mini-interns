
'use client';

import React from 'react';
import { Check } from 'lucide-react';

interface JsonSchemaFormProps {
  schema: Record<string, any>;
  formData: Record<string, any>;
  onChange: (data: Record<string, any>) => void;
}

const CustomMultiSelect: React.FC<{
    title: string;
    description: string;
    options: string[];
    selected: string[];
    onChange: (selected: string[]) => void;
}> = ({ title, description, options, selected, onChange }) => {

    const handleToggle = (option: string) => {
        const newSelected = selected.includes(option)
            ? selected.filter(item => item !== option)
            : [...selected, option];
        onChange(newSelected);
    };

    return (
        <div>
            <label className="block text-sm font-medium text-gray-700">{title}</label>
            <div className="mt-1 border border-gray-300 rounded-md h-40 overflow-y-auto">
                {options.map(option => (
                    <div
                        key={option}
                        onClick={() => handleToggle(option)}
                        className={`px-3 py-2 flex items-center justify-between cursor-pointer hover:bg-gray-50 ${selected.includes(option) ? 'bg-blue-50' : ''}`}
                    >
                        <span>{option}</span>
                        {selected.includes(option) && <Check className="h-5 w-5 text-blue-600" />}
                    </div>
                ))}
            </div>
            <p className="mt-2 text-sm text-gray-500">{description}</p>
        </div>
    );
};


export const JsonSchemaForm: React.FC<JsonSchemaFormProps> = ({ schema, formData, onChange }) => {
  const handleChange = (key: string, value: any) => {
    onChange({ ...formData, [key]: value });
  };

  const renderField = (key: string, fieldSchema: any) => {
    const { type, title, description, default: defaultValue, options } = fieldSchema;

    switch (type) {
      case 'string':
        return (
          <div key={key}>
            <label className="block text-sm font-medium text-gray-700">{title}</label>
            <input
              type="text"
              value={formData[key] || defaultValue || ''}
              onChange={e => handleChange(key, e.target.value)}
              className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm"
            />
            <p className="mt-2 text-sm text-gray-500">{description}</p>
          </div>
        );
      case 'integer':
        return (
          <div key={key}>
            <label className="block text-sm font-medium text-gray-700">{title}</label>
            <input
              type="number"
              value={formData[key] || defaultValue || 0}
              onChange={e => handleChange(key, parseInt(e.target.value, 10))}
              className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm"
            />
            <p className="mt-2 text-sm text-gray-500">{description}</p>
          </div>
        );
       case 'array':
        if (fieldSchema.items.type === 'string' && options) {
          return (
            <CustomMultiSelect
                key={key}
                title={title}
                description={description}
                options={options}
                selected={formData[key] || []}
                onChange={(selected) => handleChange(key, selected)}
            />
          );
        }
        return null;
      default:
        return null;
    }
  };

  return (
    <div className="space-y-4 mt-4">
      {Object.entries(schema.properties || {}).map(([key, fieldSchema]) =>
        renderField(key, fieldSchema)
      )}
    </div>
  );
}; 