import React from 'react';
import { DragDropContext, Droppable, Draggable, DropResult } from 'react-beautiful-dnd';
import { McpTool } from '../services/api';
import { GripVertical, HelpCircle } from 'lucide-react';
import { Tooltip } from 'react-tooltip';
import 'react-tooltip/dist/react-tooltip.css';

export interface UiTool extends McpTool {
  id: string;
  serverName: string;
  enabled: boolean;
  required: boolean;
  order?: number;
}

interface ToolListProps {
  tools: UiTool[];
  onToolsChange: (tools: UiTool[]) => void;
}

const ToggleSwitch = ({ enabled, onChange, disabled }: { enabled: boolean; onChange: () => void, disabled?: boolean }) => (
  <label className="relative inline-flex items-center cursor-pointer">
    <input type="checkbox" checked={enabled} onChange={onChange} className="sr-only peer" disabled={disabled} />
    <div className={`w-11 h-6 bg-gray-200 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:bg-gray-600 peer-checked:bg-green-500 ${disabled ? 'cursor-not-allowed opacity-50' : ''}`}></div>
  </label>
);

const ToolList: React.FC<ToolListProps> = ({ tools, onToolsChange }) => {

  const onDragEnd = (result: DropResult) => {
    if (!result.destination) {
      return;
    }

    const sortedToolsForDrag = sortTools(tools);
    const reorderedTools = Array.from(sortedToolsForDrag);
    const [movedItem] = reorderedTools.splice(result.source.index, 1);
    reorderedTools.splice(result.destination.index, 0, movedItem);

    const updatedTools = reorderedTools.map(tool => {
      if (tool.required) {
        const newOrder = reorderedTools.filter(t => t.required).findIndex(t => t.id === tool.id);
        return { ...tool, order: newOrder };
      }
      return tool;
    });
    
    onToolsChange(updatedTools);
  };

  const toggleEnabled = (id: string) => {
    const newTools = tools.map(tool => {
      if (tool.id === id) {
        if (tool.required) {
          return { ...tool, enabled: true };
        }
        return { ...tool, enabled: !tool.enabled };
      }
      return tool;
    });
    onToolsChange(sortTools(newTools));
  };
  
  const toggleRequired = (id: string) => {
    const newTools = tools.map(tool => {
      if (tool.id === id) {
        const isRequired = !tool.required;
        const newOrder = isRequired 
          ? (tools.filter(t => t.required).length) 
          : undefined;
        return { ...tool, required: isRequired, enabled: isRequired || tool.enabled, order: newOrder };
      }
      return tool;
    });
    
    const reorderedTools = sortTools(newTools).map(tool => {
      if (tool.required) {
        const newOrder = sortTools(newTools).filter(t => t.required).findIndex(t => t.id === tool.id);
        return { ...tool, order: newOrder };
      }
      return tool;
    });

    onToolsChange(reorderedTools);
  };

  const sortTools = (toolList: UiTool[]): UiTool[] => {
    const required = toolList.filter(t => t.required).sort((a, b) => (a.order ?? Infinity) - (b.order ?? Infinity));
    const enabled = toolList.filter(t => !t.required && t.enabled).sort((a, b) => a.name.localeCompare(b.name));
    const disabled = toolList.filter(t => !t.required && !t.enabled).sort((a, b) => a.name.localeCompare(b.name));
    return [...required, ...enabled, ...disabled];
  };

  const sortedTools = sortTools(tools);

  const ToolItem = ({ tool, draggableProps, dragHandleProps, innerRef }: { tool: UiTool, draggableProps?: any, dragHandleProps?: any, innerRef?: any }) => {
    
    let badge = null;
    if (tool.required) {
        const requiredTools = sortedTools.filter(t => t.required);
        const currentToolIndexInRequired = requiredTools.findIndex(t => t.id === tool.id);
        const subsequentTools = requiredTools.slice(currentToolIndexInRequired + 1);
        
        let badgeText = `Order: ${currentToolIndexInRequired + 1}.`;
        if (subsequentTools.length > 0) {
            const subsequentToolNames = subsequentTools.map(t => t.name).join(', ');
            badgeText += ` This tool needs to be called before ${subsequentToolNames}.`;
        } else {
            badgeText += ' This will be the last toolcall. Use the drag handle to reorder the tools.';
        }

        badge = (
            <div className="mt-2 text-xs text-red-700 bg-red-100 p-2 rounded-md">
                {badgeText}
            </div>
        );
    } else if (tool.enabled) {
        badge = (
            <div className="mt-2 text-xs text-gray-700 bg-gray-100 p-2 rounded-md">
                The Agent will use this tool upon its own initiative.
            </div>
        );
    }

    return (
        <div
            ref={innerRef}
            {...draggableProps}
            className="grid grid-cols-[auto_1fr_100px_100px] items-start gap-x-4 p-4 mb-3 bg-white border border-gray-200 rounded-lg shadow-sm"
        >
            <div {...dragHandleProps} className="flex justify-center pt-1">
              {tool.required ? <GripVertical className="text-gray-400 cursor-grab" /> : <div className="w-6 h-6"></div>}
            </div>
            <div>
                <p className="font-semibold">{tool.serverName.toUpperCase()}: {tool.name}</p>
                <p className="text-sm text-gray-500">{tool.description}</p>
                {badge}
            </div>
            <div className="flex justify-center items-center h-full">
                <ToggleSwitch enabled={tool.enabled} onChange={() => toggleEnabled(tool.id)} disabled={tool.required}/>
            </div>
            <div className="flex justify-center items-center h-full">
                <input
                    type="checkbox"
                    checked={tool.required}
                    onChange={() => toggleRequired(tool.id)}
                    className="h-5 w-5 rounded accent-red-500 focus:ring-red-500 cursor-pointer"
                />
            </div>
        </div>
    );
  };

  return (
    <div className="w-full">
        {/* Header */}
        <div className="grid grid-cols-[auto_1fr_100px_100px] items-center gap-x-4 px-4 pb-2 border-b border-gray-200 mb-3">
            <div className="w-6"></div> {/* Placeholder for drag handle */}
            <div>
                <p className="font-bold text-gray-700">Tool</p>
            </div>
            <div className="text-center flex items-center justify-center">
                <p className="font-bold text-gray-700 mr-1">Enabled</p>
                <a data-tooltip-id="enabled-tooltip" data-tooltip-content="Add this tool to the agent. It can decide when to use it.">
                    <HelpCircle className="w-4 h-4 text-gray-500 cursor-help" />
                </a>
                <Tooltip id="enabled-tooltip" />
            </div>
            <div className="text-center flex items-center justify-center">
                <p className="font-bold text-gray-700 mr-1">Required</p>
                <a data-tooltip-id="required-tooltip" data-tooltip-content="The agent must use this tool before finishing. You can drag required rows to define the order in which the tools must be used">
                    <HelpCircle className="w-4 h-4 text-gray-500 cursor-help" />
                </a>
                <Tooltip id="required-tooltip" />
            </div>
        </div>

        <DragDropContext onDragEnd={onDragEnd}>
            <Droppable droppableId="tools">
            {(provided) => (
                <div {...provided.droppableProps} ref={provided.innerRef}>
                {sortedTools.map((tool, index) => (
                    <Draggable key={tool.id} draggableId={tool.id} index={index} isDragDisabled={!tool.required}>
                    {(provided) => (
                        <ToolItem
                            tool={tool}
                            innerRef={provided.innerRef}
                            draggableProps={provided.draggableProps}
                            dragHandleProps={provided.dragHandleProps}
                        />
                    )}
                    </Draggable>
                ))}
                {provided.placeholder}
                </div>
            )}
            </Droppable>
        </DragDropContext>
    </div>
  );
};

export default ToolList; 