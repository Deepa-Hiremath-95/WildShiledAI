/**
 * WildShield AI — Frontend Runtime Configuration
 *
 * This configuration allows the deployed frontend to communicate with your
 * FastAPI backend in production.
 *
 * CONFIGURATION OPTIONS:
 *
 * 1. Automatic Localhost:
 *    When opening on localhost or 127.0.0.1, the frontend automatically connects
 *    to http://localhost:8000/api.
 *
 * 2. Production Deployed Backend:
 *    Once your backend is deployed (e.g. on Render, Railway, Fly.io, or AWS),
 *    paste your backend API URL below:
 *    Example:
 *      API_BASE_URL: 'https://wildshield-ai-backend.onrender.com/api'
 *
 * 3. Zero-Redeploy URL Override (Instant testing):
 *    You can test any backend URL instantly in your browser without redeploying:
 *      https://your-site.vercel.app/?api=https://wildshield-ai-backend.onrender.com/api
 *    This will persist to localStorage automatically.
 *
 * 4. Automatic Resilient Fallback:
 *    If the backend is waking up or offline, the frontend gracefully falls back
 *    to simulated telemetry so the dashboard remains fully operational.
 */
window.__WILDSHIELD_CONFIG__ = {
  // Set your FastAPI backend URL (defaults to http://localhost:8000/api)
  API_BASE_URL: 'http://localhost:8000/api',

  // Strict Phase 4 rule: Never introduce fake or fabricated live detection data
  AUTO_FALLBACK_ON_ERROR: false
};
