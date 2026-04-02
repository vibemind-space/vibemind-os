'use client';

import { useEffect, useState } from 'react';
import { CheckCircle, XCircle } from 'lucide-react';

export default function OAuth2CallbackPage() {
  const [isVisible, setIsVisible] = useState(false);
  const [isError, setIsError] = useState(false);

  useEffect(() => {
    // Small delay for smooth animation
    const timer = setTimeout(() => setIsVisible(true), 100);
    
    // Check for error parameters in URL
    const urlParams = new URLSearchParams(window.location.search);
    const error = urlParams.get('error');
    const errorDescription = urlParams.get('error_description');
    
    if (error) {
      setIsError(true);
    }
    
    // Send message to parent window that OAuth is complete
    if (window.opener) {
      window.opener.postMessage({
        type: 'OAUTH_COMPLETE',
        success: !error,
        error: error || null,
        errorDescription: errorDescription || null,
        timestamp: Date.now()
      }, window.location.origin);
      
      // Close this window after a short delay
      setTimeout(() => {
        window.close();
      }, 3000);
    }
    
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
      <div className={`max-w-md w-full bg-white rounded-lg shadow-lg p-8 text-center transition-all duration-500 ${
        isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'
      }`}>
        <div className="mb-6">
          {isError ? (
            <XCircle className="w-16 h-16 text-red-500 mx-auto" />
          ) : (
            <CheckCircle className="w-16 h-16 text-green-500 mx-auto" />
          )}
        </div>
        
        <h1 className="text-2xl font-semibold text-gray-900 mb-4">
          {isError ? 'OAuth2 Flow Failed' : 'OAuth2 Flow Completed'}
        </h1>
        
        <p className="text-gray-600 mb-6">
          {isError 
            ? 'There was an issue with the authentication. Please try again.'
            : 'Your authentication was successful. You can safely close this page now.'
          }
        </p>
        
        <div className="text-sm text-gray-500">
          This window will automatically close in a few seconds...
        </div>
      </div>
    </div>
  );
}
