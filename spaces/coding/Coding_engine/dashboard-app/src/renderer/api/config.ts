/**
 * API Configuration
 *
 * Centralized configuration for API endpoints.
 */

// Base URL for the backend API
export const API_BASE_URL = 'http://localhost:8000';

// Full API path prefix
export const API_V1_PREFIX = `${API_BASE_URL}/api/v1`;

// Dashboard API endpoints
export const DASHBOARD_API = `${API_V1_PREFIX}/dashboard`;

// Vision API endpoints
export const VISION_API = `${API_V1_PREFIX}/vision`;
