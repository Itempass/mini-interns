'use client';
import React from 'react';
import { Copy, X } from 'lucide-react';

interface GoogleAppPasswordHelpProps {
  onClose: () => void;
}

const GoogleAppPasswordHelp: React.FC<GoogleAppPasswordHelpProps> = ({ onClose }) => {

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {}, (err) => {
      console.error('Failed to copy text: ', err);
    });
  };

  const settingsSectionClasses = "border border-gray-300 p-4 mb-5 rounded-lg bg-gray-50";
  const copyButtonStyle = "bg-gray-100 border border-gray-300 rounded-full w-6 h-6 flex items-center justify-center cursor-pointer ml-2";

  return (
    <div className="p-10 max-w-4xl mx-auto font-sans">
        <div className="flex justify-between items-center mb-8">
            <h1 className="text-3xl font-bold">How to get your Google App Password</h1>
            <button onClick={onClose} className="p-2 rounded-full hover:bg-gray-200">
                <X size={24} />
            </button>
        </div>

      <div className={settingsSectionClasses}>
        <h2 className="text-2xl font-bold mb-3">Why we need an App Password</h2>
        <p className="mb-3">
          To connect to your Gmail account and process emails, our application uses a standard email protocol called IMAP. A full, direct integration with Google is a very complex and time-consuming process for developers. Using IMAP with an App Password is a secure and reliable way for us to provide you with our services right now.
        </p>
        <p className="font-bold text-red-600">
          Your App Password is encrypted and stored locally inside the Docker container on your own computer. It is never sent to our servers or any third party.
        </p>
      </div>

      <div className={settingsSectionClasses}>
        <h2 className="text-2xl font-bold mb-3">Step 1: Turn On 2-Step Verification</h2>
        <p className="mb-3">
          Before you can create an App Password, you need to have 2-Step Verification enabled on your Google Account. This adds an extra layer of security.
        </p>
        <p>
          If you don't have it enabled, please go to your Google Account settings to turn it on.
        </p>
        <a href="https://myaccount.google.com/security" target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">
          Go to Google Security Settings
        </a>
      </div>

      <div className={settingsSectionClasses}>
        <h2 className="text-2xl font-bold mb-3">Step 2: Create your App Password</h2>
        <ol className="list-decimal list-inside space-y-2">
          <li>Go to your Google Account's <a href="https://myaccount.google.com/security" target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">Security settings</a>.</li>
          <li>Under "How you sign in to Google," find and click on "2-Step Verification". You might need to sign in again.</li>
          <li>Scroll down to the bottom and click on "App passwords".</li>
          <li>
            When asked to "Select app", choose "Other (Custom name)" and give it a name you'll remember, like "My AI Agent".
          </li>
          <li>Click "Generate". Google will show you a 16-character password.</li>
          <li className="font-bold">Copy this password immediately. Google won't show it to you again. Do not store it anywhere, only paste it into the settings page.</li>
        </ol>
      </div>

      <div className={settingsSectionClasses}>
          <h2 className="text-2xl font-bold mb-3">Step 3: Use Your New Password and Settings</h2>
          <p className="mb-3">
              Now, go back to the settings page in our application and enter the password and server details.
          </p>
          <div className="flex items-center mb-3">
              <span className="font-bold w-48 text-right mr-2">IMAP Username:</span>
              <span>Your full email address (e.g., example@gmail.com or example@workspacedomain.com)</span>
          </div>
          <div className="flex items-center mb-3">
              <span className="font-bold w-48 text-right mr-2">IMAP Password:</span>
              <span>Use the 16-character password you just generated.</span>
          </div>
          <div className="flex items-center">
              <label className="font-bold w-48 text-right mr-2">IMAP Server:</label>
              <div className="flex-1">
                  <div className="flex items-center">
                  <code className="p-2 rounded border border-gray-200 bg-gray-100 text-gray-800">imap.gmail.com</code>
                  <button onClick={() => handleCopy('imap.gmail.com')} className={copyButtonStyle} title="Copy">
                      <Copy size={14} />
                  </button>
                  </div>
              </div>
          </div>
      </div>
    </div>
  );
};

export default GoogleAppPasswordHelp; 