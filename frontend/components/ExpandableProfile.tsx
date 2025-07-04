import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface ExpandableProfileProps {
  language: string;
  profile: string;
}

const ExpandableProfile: React.FC<ExpandableProfileProps> = ({ language, profile }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const toggleExpansion = () => {
    setIsExpanded(!isExpanded);
  };

  const lines = profile.split('\n');
  const isExpandable = lines.length > 5;
  const displayText = isExpanded ? profile : lines.slice(0, 5).join('\n');

  return (
    <div className="mb-6">
      <h3 className="text-lg font-bold uppercase border-b border-gray-300 pb-2 mb-3">{language}</h3>
      <div className="prose prose-sm max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {displayText}
        </ReactMarkdown>
        {isExpandable && (
          <button onClick={toggleExpansion} className="text-blue-500 hover:underline text-sm mt-2 cursor-pointer no-underline bg-transparent border-none p-0">
            {isExpanded ? 'Show less' : 'Show more...'}
          </button>
        )}
      </div>
    </div>
  );
};

export default ExpandableProfile; 