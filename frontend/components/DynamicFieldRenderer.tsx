import React from 'react';
import { ParamSchemaField } from '../services/api';

interface DynamicFieldRendererProps {
  field: ParamSchemaField;
  value: any;
  onChange: (parameterKey: string, value: any) => void;
  path: string; // e.g., "labeling_rules.0.keyword"
}

const DynamicFieldRenderer: React.FC<DynamicFieldRendererProps> = ({ field, value, onChange, path }) => {
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { type, checked, value } = e.target as HTMLInputElement;
    onChange(path, type === 'checkbox' ? checked : value);
  };

  const handleAddItem = () => {
    const newValue = Array.isArray(value) ? [...value] : [];
    const newItem: { [key: string]: any } = {};
    field.item_schema?.forEach(itemField => {
      newItem[itemField.parameter_key] = ''; // Initialize with default values
    });
    newValue.push(newItem);
    onChange(path, newValue);
  };

  const handleRemoveItem = (index: number) => {
    const newValue = [...value];
    newValue.splice(index, 1);
    onChange(path, newValue);
  };

  const handleNestedChange = (nestedPath: string, nestedValue: any) => {
    onChange(nestedPath, nestedValue);
  };

  const renderField = () => {
    switch (field.type) {
      case 'text':
        return (
          <input
            type="text"
            value={value || ''}
            onChange={handleInputChange}
            className="mt-1 block w-full rounded-md border-gray-400 shadow-sm sm:text-sm p-2 border"
          />
        );
      case 'checkbox':
        return (
          <input
            type="checkbox"
            checked={!!value}
            onChange={handleInputChange}
            className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
          />
        );
      case 'list':
        return (
          <div className="space-y-4">
            {Array.isArray(value) && value.map((item, index) => (
              <div key={index} className="p-4 border rounded-lg bg-gray-50 relative">
                <button
                  type="button"
                  onClick={() => handleRemoveItem(index)}
                  className="absolute top-2 right-2 text-red-500 hover:text-red-700 font-bold"
                  aria-label="Remove item"
                >
                  &times;
                </button>
                <div className="space-y-4">
                  {field.item_schema?.map(itemField => (
                    <div key={itemField.parameter_key}>
                      <label className="block text-sm font-medium text-gray-700">{itemField.display_text}</label>
                      <DynamicFieldRenderer
                        field={itemField}
                        value={item[itemField.parameter_key]}
                        onChange={handleNestedChange}
                        path={`${path}.${index}.${itemField.parameter_key}`}
                      />
                    </div>
                  ))}
                </div>
              </div>
            ))}
            <button
              type="button"
              onClick={handleAddItem}
              className="mt-2 px-3 py-1 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700"
            >
              Add {field.display_text}
            </button>
          </div>
        );
      default:
        // Exhaustiveness check
        const _exhaustiveCheck: never = field.type;
        return <p>Unknown field type: {_exhaustiveCheck}</p>;
    }
  };

  return (
    <div>
      <label className="block text-sm font-medium text-gray-700">{field.display_text}</label>
      {renderField()}
    </div>
  );
};

export default DynamicFieldRenderer; 