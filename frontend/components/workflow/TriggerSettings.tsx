import React from 'react';
import { TriggerModel } from '../../services/workflows_api';
import EditNewEmailTrigger from './editors/EditNewEmailTrigger';

interface TriggerSettingsProps {
  trigger: TriggerModel;
  onSave: (triggerData: any) => void;
  onCancel: () => void;
  isLoading?: boolean;
}

const TriggerSettings: React.FC<TriggerSettingsProps> = ({ trigger, onSave, onCancel, isLoading = false }) => {
  // For now, we only have one trigger type (new_email)
  // This can be extended when we add more trigger types
  const triggerType = 'new_email'; // We can derive this from trigger.initial_data_description if needed
  
  switch (triggerType) {
    case 'new_email':
      return (
        <EditNewEmailTrigger 
          trigger={trigger}
          onSave={onSave}
          onCancel={onCancel}
          isLoading={isLoading}
        />
      );
    default:
      return (
        <div className="p-4 text-center text-gray-500">
          Unknown trigger type
        </div>
      );
  }
};

export default TriggerSettings; 