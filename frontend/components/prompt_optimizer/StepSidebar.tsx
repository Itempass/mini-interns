
'use client';

import React from 'react';
import { Check } from 'lucide-react';

interface Step {
  name: string;
}

interface StepSidebarProps {
  steps: Step[];
  currentStep: number; // 1-based index
  onStepClick: (stepIndex: number) => void;
}

export const StepSidebar: React.FC<StepSidebarProps> = ({ steps, currentStep, onStepClick }) => {
  return (
    <nav className="space-y-1">
      {steps.map((step, index) => {
        const stepNumber = index + 1;
        const isCompleted = stepNumber < currentStep;
        const isActive = stepNumber === currentStep;

        let stateClasses = '';
        let StateIcon = <span className="w-5 h-5 flex items-center justify-center bg-gray-300 rounded-full text-xs text-white">{stepNumber}</span>;

        if (isCompleted) {
          stateClasses = 'text-blue-600';
          StateIcon = <span className="w-5 h-5 flex items-center justify-center bg-blue-600 rounded-full"><Check size={12} className="text-white" /></span>;
        } else if (isActive) {
          stateClasses = 'font-semibold text-blue-600';
          StateIcon = <span className="w-5 h-5 flex items-center justify-center border-2 border-blue-600 rounded-full text-xs text-blue-600">{stepNumber}</span>;
        } else {
          stateClasses = 'text-gray-500';
        }

        return (
          <button
            key={step.name}
            onClick={() => onStepClick(stepNumber)}
            disabled={!isCompleted}
            className={`w-full text-left px-3 py-2 flex items-center text-sm rounded-md transition-colors ${stateClasses} ${isCompleted ? 'hover:bg-gray-100' : 'cursor-not-allowed'}`}
          >
            <span className="mr-3">{StateIcon}</span>
            {step.name}
          </button>
        );
      })}
    </nav>
  );
}; 