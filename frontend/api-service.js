(function (global) {
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  const mockState = {
    detections: [
      {
        id: 'det-001',
        type: 'animal',
        species: 'Lion',
        classification: 'Lion',
        confidence: 0.96,
        location: 'Forest Boundary - Zone A',
        movementDirection: 'South-East',
        boundaryCrossing: true,
        riskLevel: 'critical',
        affectedVillage: 'Village 1',
        sirenStatus: 'on',
        timestamp: '2026-08-01T06:42:00',
        imageLabel: 'Detection image'
      },
      {
        id: 'det-002',
        type: 'animal',
        species: 'Elephant',
        classification: 'Elephant',
        confidence: 0.91,
        location: 'Riverline Trail',
        movementDirection: 'North',
        boundaryCrossing: false,
        riskLevel: 'high',
        affectedVillage: 'Village 2',
        sirenStatus: 'on',
        timestamp: '2026-08-01T05:18:00',
        imageLabel: 'Detection image'
      },
      {
        id: 'det-003',
        type: 'human',
        species: 'Human',
        classification: 'Human',
        confidence: 0.95,
        location: 'North Ridge Access Point',
        movementDirection: 'Northwest',
        boundaryCrossing: true,
        riskLevel: 'critical',
        affectedVillage: 'Village 1',
        sirenStatus: 'on',
        timestamp: '2026-08-01T06:42:00',
        imageLabel: 'Detection image'
      },
      {
        id: 'det-004',
        type: 'animal',
        species: 'Wild Boar',
        classification: 'Wild Boar',
        confidence: 0.72,
        location: 'South Loop',
        movementDirection: 'South',
        boundaryCrossing: false,
        riskLevel: 'low',
        affectedVillage: 'Village 4',
        sirenStatus: 'off',
        timestamp: '2026-07-31T19:14:00',
        imageLabel: 'Detection image'
      }
    ],
    activeAlerts: [
      {
        id: 'A-204',
        title: 'Lion movement near boundary',
        riskLevel: 'critical',
        status: 'active',
        detectedObject: 'Lion',
        speciesOrHuman: 'Animal • Lion',
        location: 'Forest Boundary - Zone A',
        zone: 'Zone A',
        village: 'Village 1',
        movementDirection: 'South-East',
        actionTaken: 'Village siren ON • Forest officer alerted',
        timestamp: '2026-08-01T06:42:00',
        recipients: ['Forest Officers', 'Police', 'Rescue/Security Team']
      },
      {
        id: 'A-203',
        title: 'Elephant intrusion detected',
        riskLevel: 'high',
        status: 'active',
        detectedObject: 'Elephant',
        speciesOrHuman: 'Animal • Elephant',
        location: 'Riverline Trail',
        zone: 'Zone B',
        village: 'Village 2',
        movementDirection: 'North',
        actionTaken: 'Siren active • Rescue team notified',
        timestamp: '2026-08-01T05:18:00',
        recipients: ['Forest Officers', 'Rescue/Security Team']
      },
      {
        id: 'A-202',
        title: 'Human activity near sensor line',
        riskLevel: 'medium',
        status: 'resolved',
        detectedObject: 'Human',
        speciesOrHuman: 'Human • Group of 2',
        location: 'East Ridge',
        zone: 'Zone C',
        village: 'Village 3',
        movementDirection: 'West',
        actionTaken: 'Forest team notified • Monitoring continued',
        timestamp: '2026-07-31T22:05:00',
        recipients: ['Rangers', 'Forest Officers', 'Police']
      }
    ],
    villages: [
      { id: 'v1', name: 'Village 1', zone: 'Zone A', status: 'at-risk', sirenId: 's1', sirenStatus: 'on' },
      { id: 'v2', name: 'Village 2', zone: 'Zone B', status: 'safe', sirenId: 's2', sirenStatus: 'off' },
      { id: 'v3', name: 'Village 3', zone: 'Zone C', status: 'safe', sirenId: 's3', sirenStatus: 'off' }
    ],
    sirens: [
      { id: 's1', name: 'Siren 1', currentStatus: 'on', zoneStatus: 'At Risk', village: 'Village 1', connected: true, lastActivatedAt: '2026-08-01T06:42:00', activationReason: 'Lion moving toward Village 1' },
      { id: 's2', name: 'Siren 2', currentStatus: 'off', zoneStatus: 'Safe', village: 'Village 2', connected: true, lastActivatedAt: '2026-07-31T17:10:00', activationReason: 'No active threat' },
      { id: 's3', name: 'Siren 3', currentStatus: 'off', zoneStatus: 'Safe', village: 'Village 3', connected: true, lastActivatedAt: '2026-07-30T21:05:00', activationReason: 'No active threat' }
    ],
    mapData: {
      threat: {
        animal: 'Lion',
        confidence: '96.3%',
        currentLocation: 'Forest Boundary - Zone A',
        movingToward: 'Village 1',
        distance: '850 meters',
        riskLevel: 'CRITICAL',
        siren: 'Village 1 ON'
      },
      zones: [
        { name: 'Zone C', incidents: 24 },
        { name: 'Zone B', incidents: 19 },
        { name: 'Zone A', incidents: 16 },
        { name: 'Boundary Ridge', incidents: 11 }
      ]
    },
    analytics: {
      speciesCounts: [
        { label: 'Lion', value: 14 },
        { label: 'Leopard', value: 11 },
        { label: 'Elephant', value: 16 },
        { label: 'Wild Boar', value: 13 },
        { label: 'Deer', value: 15 }
      ],
      wildlifeIntrusions: [9, 11, 14, 13, 16, 18],
      humanIntrusions: [2, 3, 4, 3, 4, 5],
      riskLevels: [
        { label: 'Low', value: 8 },
        { label: 'Medium', value: 12 },
        { label: 'High', value: 14 },
        { label: 'Critical', value: 7 }
      ],
      movementDirections: [
        { label: 'South-East', value: 28 },
        { label: 'Northwest', value: 22 },
        { label: 'North', value: 18 },
        { label: 'South', value: 16 },
        { label: 'West', value: 16 }
      ],
      sirenActivations: [9, 11, 14, 13, 16, 18],
      falseAlarmStats: { falseAlarms: 6, confirmedIntrusions: 35 }
    },
    zones: [
      { id: 'z1', name: 'Village 1 — Zone A', status: 'at-risk', lat: 11.685, lng: 76.620, latitude: 11.685, longitude: 76.620, incidents: 16, village: 'Village 1' },
      { id: 'z2', name: 'Village 2 — Zone B', status: 'safe', lat: 11.692, lng: 76.635, latitude: 11.692, longitude: 76.635, incidents: 19, village: 'Village 2' },
      { id: 'z3', name: 'Core Reserve — Zone C', status: 'safe', lat: 11.678, lng: 76.610, latitude: 11.678, longitude: 76.610, incidents: 24, village: 'Core Reserve' }
    ],
    cameras: [
      { id: 'cam-01', name: 'Camera 01', zone: 'Zone A', status: 'online', lastSeenMinutesAgo: 0 },
      { id: 'cam-02', name: 'Camera 02', zone: 'Zone B', status: 'online', lastSeenMinutesAgo: 2 },
      { id: 'cam-03', name: 'Camera 03', zone: 'Zone C', status: 'offline', lastSeenMinutesAgo: 47 },
      { id: 'cam-04', name: 'Camera 04', zone: 'Boundary Ridge', status: 'online', lastSeenMinutesAgo: 1 }
    ]
  };
  const service = {
    _customBaseUrl: null,
    get baseUrl() {
      if (this._customBaseUrl) return this._customBaseUrl;
      return this.resolveBaseUrl();
    },
    set baseUrl(val) {
      this._customBaseUrl = val;
    },
    resolveBaseUrl() {
      // 1. Explicit window override (injected or config.js)
      if (typeof window !== 'undefined' && window.__WILDSHIELD_API_URL__) {
        return window.__WILDSHIELD_API_URL__.replace(/\/+$/, '');
      }
      if (typeof window !== 'undefined' && window.__WILDSHIELD_CONFIG__ && window.__WILDSHIELD_CONFIG__.API_BASE_URL) {
        return window.__WILDSHIELD_CONFIG__.API_BASE_URL.replace(/\/+$/, '');
      }
      // 2. URL parameter override: ?api=https://...
      if (typeof window !== 'undefined' && window.location) {
        const p = new URLSearchParams(window.location.search);
        const apiParam = p.get('api');
        if (apiParam) {
          try { localStorage.setItem('wildshield_api_url', apiParam); } catch (_) {}
          return apiParam.replace(/\/+$/, '');
        }
      }
      // 3. LocalStorage override
      try {
        const stored = localStorage.getItem('wildshield_api_url');
        if (stored) return stored.replace(/\/+$/, '');
      } catch (_) {}
      // 4. Localhost / local development
      if (typeof window !== 'undefined' && window.location) {
        const host = window.location.hostname;
        if (host === 'localhost' || host === '127.0.0.1' || host === '') {
          return 'http://localhost:8000/api';
        }
      }
      // 5. Production default (same-origin / reverse proxy via Vercel)
      return '/api';
    },
    // Flip to true any time you want to demo the UI with canned data and no backend running.
    // Also auto-enabled when ?demo=1 or ?mock=1 is in the URL.
    useMock: (function() {
      const p = new URLSearchParams(window.location.search);
      return p.get('demo') === '1' || p.get('mock') === '1';
    })(),
    tokenKey: 'wildshield_token',
    getToken() {
      return sessionStorage.getItem(this.tokenKey);
    },
    setToken(token) {
      sessionStorage.setItem(this.tokenKey, token);
    },
    clearToken() {
      sessionStorage.removeItem(this.tokenKey);
    },
    isAuthenticated() {
      return Boolean(this.getToken());
    },
    async login(username, password) {
      const body = new URLSearchParams();
      body.set('username', username);
      body.set('password', password);

      const response = await fetch(`${this.baseUrl}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body
      });

      if (!response.ok) {
        throw new Error(response.status === 401 ? 'Invalid username or password' : `Login failed (${response.status})`);
      }

      const data = await response.json();
      this.setToken(data.access_token);
      return data;
    },
    logout() {
      this.clearToken();
    },
    async request(path, options = {}) {
      if (this.useMock) {
        await wait(80);
        return this.handleMock(path, options);
      }

      const token = this.getToken();
      const headers = { Accept: 'application/json', ...(options.headers || {}) };
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }

      try {
        const response = await fetch(`${this.baseUrl}${path}`, {
          ...options,
          headers
        });

        if (!response.ok) {
          const error = new Error(`Request failed: ${response.status}`);
          error.status = response.status;
          throw error;
        }

        if (response.status === 204) return null;
        return response.json();
      } catch (err) {
        const autoFallback = typeof window !== 'undefined' &&
          window.__WILDSHIELD_CONFIG__ &&
          window.__WILDSHIELD_CONFIG__.AUTO_FALLBACK_ON_ERROR;

        if (autoFallback) {
          console.warn(`[WildShield] Backend at "${this.baseUrl}" unreachable (${err.message}). Serving simulated preview telemetry.`);
          await wait(50);
          return this.handleMock(path, options);
        }
        throw err;
      }
    },
    handleMock(path, options = {}) {
      const method = (options.method || 'GET').toUpperCase();

      if (path === '/detections') {
        return Promise.resolve(mockState.detections);
      }

      if (path === '/active-alerts') {
        return Promise.resolve(mockState.activeAlerts);
      }

      if (path === '/villages') {
        return Promise.resolve(mockState.villages);
      }

      if (path === '/sirens') {
        return Promise.resolve(mockState.sirens);
      }

      if (path === '/map-data') {
        return Promise.resolve(mockState.mapData);
      }

      if (path === '/analytics') {
        return Promise.resolve(mockState.analytics);
      }

      if (path === '/zones') {
        return Promise.resolve(mockState.zones);
      }

      if (path === '/cameras' || path.startsWith('/cameras?')) {
        return Promise.resolve(mockState.cameras);
      }

      if (path === '/health/summary') {
        const cams = mockState.cameras;
        const onlineCams = cams.filter(c => c.status === 'online').length;
        const activeAlerts = mockState.activeAlerts.filter(a => a.status === 'active').length;
        const sirensOn = mockState.sirens.filter(s => s.currentStatus === 'on').length;
        const latestDet = mockState.detections[0];
        return Promise.resolve({
          cameras_online: onlineCams,
          cameras_total: cams.length,
          cameras: `${onlineCams}/${cams.length}`,
          active_alerts: activeAlerts,
          sirens_on: sirensOn,
          last_detection_time: latestDet ? latestDet.timestamp : null
        });
      }

      if (path === '/detections' && method === 'POST') {
        const body = options.body ? JSON.parse(options.body) : {};
        const newDet = {
          id: `det-${Date.now()}`,
          type: body.type || 'animal',
          species: body.species || 'Unknown',
          classification: body.species || 'Unknown',
          confidence: body.confidence || 0.9,
          location: body.location || 'Forest Boundary',
          movementDirection: body.movement_direction || 'South',
          boundaryCrossing: body.boundary_crossing !== undefined ? body.boundary_crossing : true,
          riskLevel: body.risk_level || 'high',
          affectedVillage: body.affected_village || 'Village 1',
          sirenStatus: 'off',
          timestamp: new Date().toISOString(),
          snapshotUrl: null
        };
        mockState.detections.unshift(newDet);
        // Also create a matching alert
        const alert = {
          id: `A-${Date.now()}`,
          title: newDet.type === 'human' ? 'Human intrusion detected' : `${newDet.species} movement detected`,
          riskLevel: newDet.riskLevel,
          status: 'active',
          detectedObject: newDet.species,
          speciesOrHuman: newDet.type === 'human' ? 'Human' : `Animal • ${newDet.species}`,
          location: newDet.location,
          zone: 'Zone A',
          village: newDet.affectedVillage,
          movementDirection: newDet.movementDirection,
          actionTaken: 'Pending response',
          timestamp: newDet.timestamp,
          recipients: newDet.type === 'human' ? ['Rangers', 'Forest Officers', 'Police'] : ['Forest Officers', 'Rescue/Security Team'],
          type: newDet.type
        };
        mockState.activeAlerts.unshift(alert);
        return Promise.resolve(newDet);
      }

      if (path.startsWith('/sirens/') && method === 'POST') {
        const sirenId = path.split('/')[2];
        const siren = mockState.sirens.find((entry) => entry.id === sirenId);
        if (!siren) {
          return Promise.reject(new Error('Siren not found'));
        }

        const action = path.includes('/activate') ? 'on' : 'off';
        siren.currentStatus = action;
        siren.zoneStatus = action === 'on' ? 'At Risk' : 'Safe';
        return Promise.resolve(siren);
      }

      if (path === '/users/me') {
        if (!mockState.userProfile) {
          mockState.userProfile = {
            id: 'u-admin',
            username: 'admin',
            role: 'admin',
            full_name: 'Forest Officer',
            email: 'officer@wildshield.ai',
            location: 'Central Forest Command',
            two_factor_enabled: true,
            last_login_at: new Date().toISOString()
          };
        }
        if (method === 'PUT' || method === 'PATCH') {
          const body = options.body ? JSON.parse(options.body) : {};
          Object.assign(mockState.userProfile, body);
        }
        return Promise.resolve(mockState.userProfile);
      }

      if (path === '/security/settings') {
        return Promise.resolve({
          two_factor_enabled: mockState.userProfile ? mockState.userProfile.two_factor_enabled : true,
          authorized_devices_count: 1,
          last_login: new Date().toISOString(),
          events: [
            { title: 'Recent login', detail: 'Successful authentication via command center', time: 'Just now' },
            { title: 'Device verification', detail: 'Active browser session', time: 'Approved' },
            { title: 'Role verification', detail: 'Access granted under admin privilege', time: 'Verified' }
          ]
        });
      }

      if (path === '/security/toggle-2fa' && method === 'POST') {
        const curr = mockState.userProfile ? mockState.userProfile.two_factor_enabled : true;
        if (!mockState.userProfile) mockState.userProfile = {};
        mockState.userProfile.two_factor_enabled = !curr;
        return Promise.resolve({
          two_factor_enabled: mockState.userProfile.two_factor_enabled,
          status: mockState.userProfile.two_factor_enabled ? 'enabled' : 'disabled'
        });
      }

      if (path.startsWith('/alerts/') && path.endsWith('/read')) {
        const id = path.split('/')[2];
        const alert = mockState.activeAlerts.find((a) => a.id === id);
        if (alert) alert.read = !alert.read;
        return Promise.resolve({ id, read: alert ? alert.read : true, status: 'ok' });
      }

      if (path.startsWith('/alerts/') && path.endsWith('/resolve') && method === 'POST') {
        const id = path.split('/')[2];
        const alert = mockState.activeAlerts.find((a) => a.id === id);
        if (alert) {
          alert.status = 'resolved';
          alert.actionTaken = 'Resolved by operator';
        }
        return Promise.resolve(alert || { id, status: 'resolved' });
      }

      if (path === '/alerts/mark-all-read' && method === 'POST') {
        mockState.activeAlerts.forEach((a) => { a.read = true; });
        return Promise.resolve({ updated: mockState.activeAlerts.length, status: 'ok' });
      }

      return Promise.reject(new Error(`No mock handler for ${path}`));
    },
    async getDetections() {
      return this.request('/detections');
    },
    async getActiveAlerts() {
      return this.request('/active-alerts');
    },
    async getVillages() {
      return this.request('/villages');
    },
    async getSirens() {
      return this.request('/sirens');
    },
    async getMapData() {
      return this.request('/map-data');
    },
    async getAnalytics() {
      return this.request('/analytics');
    },
    async activateSiren(sirenId) {
      return this.request(`/sirens/${sirenId}/activate`, { method: 'POST' });
    },
    async deactivateSiren(sirenId) {
      return this.request(`/sirens/${sirenId}/deactivate`, { method: 'POST' });
    },
    async resolveAlert(alertId) {
      return this.request(`/alerts/${alertId}/resolve`, { method: 'POST' });
    },
    async toggleAlertRead(alertId, readState) {
      const options = {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
      };
      if (readState !== undefined) {
        options.body = JSON.stringify({ read: Boolean(readState) });
      }
      return this.request(`/alerts/${alertId}/read`, options);
    },
    async markAllAlertsRead() {
      return this.request('/alerts/mark-all-read', { method: 'POST' });
    },
    async getUserProfile() {
      return this.request('/users/me');
    },
    async updateUserProfile(data) {
      return this.request('/users/me', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
    },
    async getSecuritySettings() {
      return this.request('/security/settings');
    },
    async toggle2FA() {
      return this.request('/security/toggle-2fa', { method: 'POST' });
    },
    async getZones() {
      return this.request('/zones');
    },
    async getCameras(zoneId) {
      const qs = zoneId ? `?zone_id=${encodeURIComponent(zoneId)}` : '';
      return this.request(`/cameras${qs}`);
    },
    async postDetection(payload) {
      return this.request('/detections', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
    },
    async getHealthSummary() {
      return this.request('/health/summary');
    }
  };

  global.WildShieldApi = service;

})(window);
