import React, { useState, useRef, useEffect, useCallback } from 'react';
import { WorkflowStep } from '../../../services/workflows_api';

interface PlaceholderTextEditorProps {
  value: string;
  onChange: (value: string) => void;
  onSave?: () => void;
  placeholder?: string;
  className?: string;
  hasTrigger?: boolean;
  precedingSteps?: WorkflowStep[];
  showSaveButton?: boolean;
  rows?: number;
}

const PlaceholderTextEditor: React.FC<PlaceholderTextEditorProps> = ({
  value,
  onChange,
  onSave,
  placeholder = '',
  className = '',
  hasTrigger = false,
  precedingSteps = [],
  showSaveButton = false,
  rows = 10
}) => {
  const editorRef = useRef<HTMLDivElement>(null);
  const [isDirty, setIsDirty] = useState(false);
  const initialValueRef = useRef(value);
  const skipNextEffect = useRef(false);

  const textToHtml = useCallback((text: string): string => {
    let html = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    
    html = html.replace(/&lt;&lt;trigger_output&gt;&gt;/g, 
      '<span contenteditable="false" class="inline-block px-2 py-1 mx-0.5 bg-green-100 text-green-800 text-xs font-medium rounded-full select-none cursor-default" data-placeholder="&lt;&lt;trigger_output&gt;&gt;">trigger output</span>'
    );

    html = html.replace(/&lt;&lt;CURRENT_DATE\.([^&]+)&gt;&gt;/g, (match, timezone) => {
      return `<span contenteditable="false" class="inline-block px-2 py-1 mx-0.5 bg-purple-100 text-purple-800 text-xs font-medium rounded-full select-none cursor-default" data-placeholder="${match}">current date (${timezone})</span>`;
    });

    html = html.replace(/&lt;&lt;step_output\.([a-f0-9-]+)&gt;&gt;/g, (match, uuid) => {
      const stepIndex = precedingSteps.findIndex(step => step.uuid === uuid);
      const text = stepIndex >= 0 ? `step ${stepIndex + 2} output` : 'unknown step';
      return `<span contenteditable="false" class="inline-block px-2 py-1 mx-0.5 bg-blue-100 text-blue-800 text-xs font-medium rounded-full select-none cursor-default" data-placeholder="${match}">${text}</span>`;
    });

    return html.replace(/\n/g, '<br>');
  }, [precedingSteps]);

  const htmlToText = useCallback((html: string): string => {
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = html;
    
    tempDiv.querySelectorAll('[data-placeholder]').forEach(badge => {
      const placeholder = badge.getAttribute('data-placeholder');
      if (placeholder) {
        const unescaped = placeholder.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
        badge.replaceWith(document.createTextNode(unescaped));
      }
    });

    // Explicitly replace <br> with newlines before getting text content
    tempDiv.querySelectorAll('br').forEach(br => {
      br.replaceWith(document.createTextNode('\n'));
    });

    return tempDiv.textContent || '';
  }, []);

  useEffect(() => {
    if (skipNextEffect.current) {
      skipNextEffect.current = false;
      return;
    }
    if (editorRef.current) {
      editorRef.current.innerHTML = textToHtml(value);
      initialValueRef.current = value;
      setIsDirty(false);
    }
  }, [value, textToHtml]);

  const handleInput = () => {
    if (!editorRef.current) return;
    const currentText = htmlToText(editorRef.current.innerHTML);
    
    skipNextEffect.current = true;
    onChange(currentText);
    
    setIsDirty(currentText !== initialValueRef.current);
  };

  const handlePaste = useCallback((e: React.ClipboardEvent) => {
    e.preventDefault();
    const text = e.clipboardData.getData('text/plain');
    if (!text) return;

    const html = textToHtml(text);
    const selection = window.getSelection();
    if (!selection?.rangeCount) return;

    selection.deleteFromDocument();
    const range = selection.getRangeAt(0);
    const fragment = range.createContextualFragment(html);
    const lastNode = fragment.lastChild;
    range.insertNode(fragment);

    if (lastNode) {
      range.setStartAfter(lastNode);
      range.collapse(true);
      selection.removeAllRanges();
      selection.addRange(range);
    }

    handleInput();
  }, [textToHtml, handleInput]);
  
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Backspace') {
      const selection = window.getSelection();
      if (selection && selection.isCollapsed) {
          const range = selection.getRangeAt(0);
          const container = range.startContainer;
          let nodeToDelete: Node | null = null;

          if (container.nodeType === Node.ELEMENT_NODE && range.startOffset > 0) {
              const nodeBefore = container.childNodes[range.startOffset - 1];
              if ((nodeBefore as HTMLElement).getAttribute?.('data-placeholder')) {
                  nodeToDelete = nodeBefore;
              }
          }
          
          else if (container.nodeType === Node.TEXT_NODE && range.startOffset === 0) {
              if (container.previousSibling && (container.previousSibling as HTMLElement).getAttribute?.('data-placeholder')) {
                 nodeToDelete = container.previousSibling;
              }
          }

          if (nodeToDelete && 'remove' in nodeToDelete) {
              e.preventDefault();
              (nodeToDelete as Element).remove();
              handleInput();
          }
      }
    }
  }, [handleInput]);

  const handleSave = () => {
    if (onSave) {
      onSave();
      if (editorRef.current) {
        initialValueRef.current = htmlToText(editorRef.current.innerHTML);
      }
      setIsDirty(false);
    }
  };
  
  const editorHeight = `${rows * 1.5}rem`;

  return (
    <div className="relative">
      <div
        ref={editorRef}
        contentEditable
        onInput={handleInput}
        onPaste={handlePaste}
        onKeyDown={handleKeyDown}
        className={`
          block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm 
          focus:outline-none focus:ring-blue-500 focus:border-blue-500 
          font-mono text-sm resize-none overflow-y-auto
          ${className}
        `}
        style={{ 
          minHeight: editorHeight,
          maxHeight: editorHeight,
          whiteSpace: 'pre-wrap'
        }}
        suppressContentEditableWarning={true}
      />
      
      {!value && (
        <div className="absolute top-2 left-3 text-gray-400 text-sm font-mono pointer-events-none select-none" style={{ paddingTop: '0.5rem' }}>
          {placeholder}
        </div>
      )}
      
      {showSaveButton && isDirty && (
        <button
          onClick={handleSave}
          className="absolute bottom-3 right-3 px-2 py-1 bg-black text-white text-xs rounded hover:bg-gray-800 z-10"
        >
          save
        </button>
      )}
    </div>
  );
};

export default PlaceholderTextEditor; 