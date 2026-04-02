// Split into separate configuration file/module
const CONFIG = {
  CHAT_URL: '__CHAT_WIDGET_HOST__',
  API_URL: '__ROWBOAT_HOST__/api/widget/v1',
  STORAGE_KEYS: {
    MINIMIZED: 'rowboat_chat_minimized',
    SESSION: 'rowboat_session_id'
  },
  IFRAME_STYLES: {
    MINIMIZED: {
      width: '48px',
      height: '48px',
      borderRadius: '50%'
    },
    MAXIMIZED: {
      width: '400px',
      height: 'min(calc(100vh - 32px), 600px)',
      borderRadius: '10px'
    },
    BASE: {
      position: 'fixed',
      bottom: '20px',
      right: '20px',
      border: 'none',
      boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
      zIndex: '999999',
      transition: 'all 0.1s ease-in-out'
    }
  }
};

// New SessionManager class to handle session-related operations
class SessionManager {
  static async createGuestSession() {
    try {
      const response = await fetch(`${CONFIG.API_URL}/session/guest`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-client-id': window.ROWBOAT_CONFIG.clientId
        },
      });
      
      if (!response.ok) throw new Error('Failed to create session');
      
      const data = await response.json();
      CookieManager.setCookie(CONFIG.STORAGE_KEYS.SESSION, data.sessionId);
      return true;
    } catch (error) {
      console.error('Failed to create chat session:', error);
      return false;
    }
  }
}

// New CookieManager class for cookie operations
class CookieManager {
  static getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return null;
  }

  static setCookie(name, value) {
    document.cookie = `${name}=${value}; path=/`;
  }

  static deleteCookie(name) {
    document.cookie = `${name}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
  }
}

// New IframeManager class to handle iframe-specific operations
class IframeManager {
  static createIframe(url, isMinimized) {
    const iframe = document.createElement('iframe');
    iframe.hidden = true;
    iframe.src = url.toString();
    
    Object.assign(iframe.style, CONFIG.IFRAME_STYLES.BASE);
    IframeManager.updateSize(iframe, isMinimized);
    
    return iframe;
  }

  static updateSize(iframe, isMinimized) {
    const styles = isMinimized ? CONFIG.IFRAME_STYLES.MINIMIZED : CONFIG.IFRAME_STYLES.MAXIMIZED;
    Object.assign(iframe.style, styles);
  }

  static removeIframe(iframe) {
    if (iframe && iframe.parentNode) {
      iframe.parentNode.removeChild(iframe);
    }
  }
}

// Refactored main ChatWidget class
class ChatWidget {
  constructor() {
    this.iframe = null;
    this.messageHandlers = {
      chatLoaded: () => this.iframe.hidden = false,
      chatStateChange: (data) => this.handleStateChange(data),
      sessionExpired: () => this.handleSessionExpired()
    };
    
    this.init();
  }

  async init() {
    const sessionId = CookieManager.getCookie(CONFIG.STORAGE_KEYS.SESSION);
    if (!sessionId && !(await SessionManager.createGuestSession())) {
      console.error('Chat widget initialization failed: Could not create session');
      return;
    }
    
    this.createAndMountIframe();
    this.setupEventListeners();
  }

  createAndMountIframe() {
    const url = this.buildUrl();
    const isMinimized = this.getStoredMinimizedState();
    this.iframe = IframeManager.createIframe(url, isMinimized);
    document.body.appendChild(this.iframe);
  }

  buildUrl() {
    const sessionId = CookieManager.getCookie(CONFIG.STORAGE_KEYS.SESSION);
    const isMinimized = this.getStoredMinimizedState();
    
    const url = new URL(`${CONFIG.CHAT_URL}/`);
    url.searchParams.append('session_id', sessionId);
    url.searchParams.append('minimized', isMinimized);
    
    return url;
  }

  setupEventListeners() {
    window.addEventListener('message', (event) => this.handleMessage(event));
  }

  handleMessage(event) {
    if (event.origin !== CONFIG.CHAT_URL) return;

    if (this.messageHandlers[event.data.type]) {
      this.messageHandlers[event.data.type](event.data);
    }
  }

  async handleSessionExpired() {
    console.log("Session expired");
    IframeManager.removeIframe(this.iframe);
    CookieManager.deleteCookie(CONFIG.STORAGE_KEYS.SESSION);
    
    const sessionCreated = await SessionManager.createGuestSession();
    if (!sessionCreated) {
      console.error('Failed to recreate session after expiry');
      return;
    }
    
    this.createAndMountIframe();
    document.body.appendChild(this.iframe);
  }

  handleStateChange(data) {
    localStorage.setItem(CONFIG.STORAGE_KEYS.MINIMIZED, data.isMinimized);
    IframeManager.updateSize(this.iframe, data.isMinimized);
  }

  getStoredMinimizedState() {
    return localStorage.getItem(CONFIG.STORAGE_KEYS.MINIMIZED) !== 'false';
  }
}

// Initialize when DOM is ready
if (document.readyState === 'complete') {
  new ChatWidget();
} else {
  window.addEventListener('load', () => new ChatWidget());
}