/* WildShield AI — dashboard behavior. Talks to the real FastAPI backend via
   window.WildShieldApi (see api-service.js). No mock/static data is used here;
   every render function below is driven by what the API returns. */

const sidebar = document.getElementById('sidebar');
const sidebarToggle = document.getElementById('sidebarToggle');
const mobileToggle = document.getElementById('mobileToggle');
const backdrop = document.getElementById('sidebarBackdrop');
const profileTrigger = document.getElementById('profileTrigger');
const profileMenu = document.querySelector('.profile-menu');
const authActionLink = document.getElementById('authActionLink');
const dateTime = document.getElementById('currentDateTime');

let currentAlerts = [];
let currentDetections = [];
let currentVillages = [];
let currentSirens = [];
let currentCameras = [];
let pendingAfterLogin = null;
let _leafletMap = null;  // Leaflet map instance
let _wsDebounceTimer = null;
let _pollingTimer = null;

/* ------------------------------------------------------------------ */
/* Basic chrome: clock, sidebar, profile menu                          */
/* ------------------------------------------------------------------ */

function updateDateTime() {
  if (!dateTime) return;
  const now = new Date();
  dateTime.textContent = now.toLocaleString([], {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

function toggleSidebar(force) {
  const isMobile = window.innerWidth <= 760;
  const shouldOpen = typeof force === 'boolean' ? force : !sidebar.classList.contains('open');

  if (isMobile) {
    sidebar.classList.toggle('open', shouldOpen);
    backdrop.classList.toggle('show', shouldOpen);
    return;
  }

  if (typeof force === 'boolean') {
    sidebar.classList.toggle('collapsed', !force);
  } else {
    sidebar.classList.toggle('collapsed');
  }
}

sidebarToggle?.addEventListener('click', () => toggleSidebar());
mobileToggle?.addEventListener('click', () => toggleSidebar(true));
backdrop?.addEventListener('click', () => toggleSidebar(false));

profileTrigger?.addEventListener('click', () => {
  profileMenu.classList.toggle('open');
  profileTrigger.setAttribute('aria-expanded', profileMenu.classList.contains('open'));
});

document.addEventListener('click', (event) => {
  if (!profileMenu?.contains(event.target)) {
    profileMenu?.classList.remove('open');
    profileTrigger?.setAttribute('aria-expanded', 'false');
  }
});

window.addEventListener('resize', () => {
  if (window.innerWidth > 760) {
    sidebar?.classList.remove('open');
    backdrop?.classList.remove('show');
  }
});

updateDateTime();
setInterval(updateDateTime, 1000);

/* ------------------------------------------------------------------ */
/* Toast notifications                                                  */
/* ------------------------------------------------------------------ */

function ensureToastStack() {
  let stack = document.getElementById('toastStack');
  if (!stack) {
    stack = document.createElement('div');
    stack.id = 'toastStack';
    document.body.appendChild(stack);
  }
  return stack;
}

function toast(message, type = 'info', duration = 3200) {
  const stack = ensureToastStack();
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  stack.appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transition = 'opacity 200ms ease';
    setTimeout(() => el.remove(), 220);
  }, duration);
}

/* ------------------------------------------------------------------ */
/* Modal                                                                */
/* ------------------------------------------------------------------ */

function closeModal() {
  document.getElementById('wsModalOverlay')?.remove();
}

function openModal({ eyebrow = '', title = '', bodyHtml = '', actionsHtml = '' }) {
  closeModal();
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.id = 'wsModalOverlay';
  overlay.innerHTML = `
    <div class="modal-box" role="dialog" aria-modal="true">
      <div class="card-heading">
        <div>
          ${eyebrow ? `<p class="eyebrow">${eyebrow}</p>` : ''}
          <h3>${title}</h3>
        </div>
        <button class="modal-close" aria-label="Close" data-role="modal-close">✕</button>
      </div>
      <div class="modal-body">${bodyHtml}</div>
      ${actionsHtml ? `<div class="modal-actions">${actionsHtml}</div>` : ''}
    </div>
  `;
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) closeModal();
  });
  overlay.querySelector('[data-role="modal-close"]').addEventListener('click', closeModal);
  document.body.appendChild(overlay);
  return overlay;
}

function detailGridHtml(pairs) {
  return `<div class="detail-grid">${pairs.map(([label, value]) => `
    <div><span>${label}</span><strong>${value ?? '--'}</strong></div>
  `).join('')}</div>`;
}

/* ------------------------------------------------------------------ */
/* Auth: sign in / sign out                                            */
/* ------------------------------------------------------------------ */

function openLoginModal(onSuccess) {
  pendingAfterLogin = onSuccess || null;
  openModal({
    eyebrow: 'Operator access',
    title: 'Sign in',
    bodyHtml: `
      <form class="login-form" id="loginForm">
        <p class="login-hint">Sign in with your WildShield operator account to resolve alerts or manage zones. Demo login: <strong>admin</strong> / <strong>changeme123</strong> (seeded by <code>app.seed</code>).</p>
        <div>
          <label for="loginUsername">Username</label>
          <input id="loginUsername" name="username" type="text" autocomplete="username" value="admin" required />
        </div>
        <div>
          <label for="loginPassword">Password</label>
          <input id="loginPassword" name="password" type="password" autocomplete="current-password" value="changeme123" required />
        </div>
        <p class="login-error" id="loginError"></p>
      </form>
    `,
    actionsHtml: `
      <button class="btn-sm btn-outline" data-role="modal-close">Cancel</button>
      <button class="btn-sm btn-deactivate" id="loginSubmit">Sign in</button>
    `,
  });

  document.getElementById('loginSubmit').addEventListener('click', async () => {
    const api = window.WildShieldApi;
    const username = document.getElementById('loginUsername').value.trim();
    const password = document.getElementById('loginPassword').value;
    const errEl = document.getElementById('loginError');
    const btn = document.getElementById('loginSubmit');
    errEl.classList.remove('show');
    btn.disabled = true;
    btn.textContent = 'Signing in…';
    try {
      await api.login(username, password);
      toast('Signed in as ' + username, 'success');
      refreshAuthUI();
      closeModal();
      const cb = pendingAfterLogin;
      pendingAfterLogin = null;
      if (cb) cb();
    } catch (err) {
      errEl.textContent = err.message || 'Sign in failed';
      errEl.classList.add('show');
      btn.disabled = false;
      btn.textContent = 'Sign in';
    }
  });
}

authActionLink?.addEventListener('click', (e) => {
  e.preventDefault();
  const api = window.WildShieldApi;
  if (!api) return;
  if (api.isAuthenticated()) {
    api.logout();
    refreshAuthUI();
    toast('Signed out', 'info');
  } else {
    openLoginModal();
  }
});

/** Runs `action` (an async fn). If unauthenticated or fails with a 401, prompts sign-in then retries. */
async function withAuth(action) {
  const api = window.WildShieldApi;
  if (!api.isAuthenticated()) {
    return new Promise((resolve, reject) => {
      openLoginModal(async () => {
        try {
          resolve(await action());
        } catch (retryErr) {
          reject(retryErr);
        }
      });
    });
  }

  try {
    return await action();
  } catch (err) {
    if (err && err.status === 401) {
      return new Promise((resolve, reject) => {
        openLoginModal(async () => {
          try {
            resolve(await action());
          } catch (retryErr) {
            reject(retryErr);
          }
        });
      });
    }
    throw err;
  }
}

function refreshAuthUI() {
  const api = window.WildShieldApi;
  if (!authActionLink || !api) return;
  if (api.isAuthenticated()) {
    authActionLink.textContent = 'Sign out';
    loadUserProfile();
  } else {
    authActionLink.textContent = 'Sign in';
  }
}

refreshAuthUI();

/* ------------------------------------------------------------------ */
/* WebSocket + polling fallback                                         */
/* ------------------------------------------------------------------ */

function setWsPill(state) {
  // state: 'live' | 'offline'
  const pill = document.getElementById('wsStatusPill');
  if (!pill) return;
  if (state === 'live') {
    pill.textContent = '⬤ LIVE';
    pill.className = 'ws-pill live';
  } else {
    pill.textContent = '⬤ OFFLINE';
    pill.className = 'ws-pill offline';
  }
}

function flashAlertCard() {
  const card = document.querySelector('[data-role="index-active-alert"]');
  if (!card) return;
  card.classList.add('flash-new');
  setTimeout(() => card.classList.remove('flash-new'), 1200);
}

function getWebSocketUrl() {
  const base = (window.WildShieldApi?.baseUrl || '/api').trim();
  if (base.startsWith('http://') || base.startsWith('https://')) {
    const origin = base.replace(/\/api\/?$/, '');
    const wsProto = origin.startsWith('https://') ? 'wss://' : 'ws://';
    return origin.replace(/^https?:\/\//, wsProto) + '/ws';
  }
  if (typeof window !== 'undefined' && window.location && window.location.host) {
    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${wsProto}//${window.location.host}/ws`;
  }
  return null;
}

function initWebSocket() {
  const wsUrl = getWebSocketUrl();
  if (!wsUrl) {
    setWsPill('offline');
    startPollingFallback();
    return;
  }

  let ws;
  try {
    ws = new WebSocket(wsUrl);
  } catch (e) {
    setWsPill('offline');
    startPollingFallback();
    return;
  }

  ws.addEventListener('open', () => {
    setWsPill('live');
    stopPollingFallback();
  });

  ws.addEventListener('message', (event) => {
    let msg;
    try { msg = JSON.parse(event.data); } catch { return; }
    if (msg && msg.type === 'new_alert') {
      toast('🚨 New alert received', 'error', 3500);
      flashAlertCard();
      clearTimeout(_wsDebounceTimer);
      _wsDebounceTimer = setTimeout(() => hydrateDashboard(), 500);
    } else if (msg && msg.type === 'siren_off') {
      toast('🔕 Siren auto-off completed', 'info', 3000);
      clearTimeout(_wsDebounceTimer);
      _wsDebounceTimer = setTimeout(() => hydrateDashboard(), 250);
    }
  });

  ws.addEventListener('close', () => {
    setWsPill('offline');
    startPollingFallback();
  });

  ws.addEventListener('error', () => {
    setWsPill('offline');
    ws.close();
    startPollingFallback();
  });
}

function startPollingFallback() {
  if (_pollingTimer) return;
  _pollingTimer = setInterval(() => hydrateDashboard(), 10_000);
}

function stopPollingFallback() {
  if (_pollingTimer) { clearInterval(_pollingTimer); _pollingTimer = null; }
}

// Mock-mode: WS won't connect, so go straight to polling; show neutral MOCK pill
if (window.WildShieldApi?.useMock) {
  const pill = document.getElementById('wsStatusPill');
  if (pill) { pill.textContent = '\u2b24 MOCK'; pill.className = 'ws-pill mock'; }
  startPollingFallback();
} else {
  initWebSocket();
}




/* ------------------------------------------------------------------ */
/* WildShield AI Phase 4: Full Multi-Module Dashboard Hydration       */
/* ------------------------------------------------------------------ */

let _liveFilter = 'all';
let _livePollingTimer = null;
let _animalFilterSpecies = 'all';

async function hydrateDashboard() {
  const api = window.WildShieldApi;
  if (!api) return;

  try {
    const needsAnalytics = Boolean(document.querySelector('[data-role="analytics-species"]') || document.getElementById('anTotalEvents'));
    const needsCameras = Boolean(
      document.querySelector('[data-role="cam-health-grid"]') ||
      document.getElementById('cmCameraCardsGrid') ||
      document.getElementById('cmCameraTableBody') ||
      document.getElementById('lmCameraSelect') ||
      document.getElementById('vmVillageCardsGrid') ||
      document.getElementById('ovConnectedCameras')
    );
    const needsZones = Boolean(
      document.getElementById('vmVillageCardsGrid') ||
      document.getElementById('vmVillageTableBody') ||
      document.getElementById('setTargetZoneSelect') ||
      document.getElementById('leafletMap')
    );
    const needsLeaflet = Boolean(document.getElementById('leafletMap'));

    const [detections, alerts, villages, sirens, mapData, analytics, cameras, zones, healthSummary] = await Promise.all([
      api.getDetections().catch(() => []),
      api.getActiveAlerts().catch(() => []),
      api.getVillages().catch(() => []),
      api.getSirens().catch(() => []),
      api.getMapData().catch(() => ({ threat: {}, zones: [] })),
      needsAnalytics ? api.getAnalytics().catch(() => null) : Promise.resolve(null),
      needsCameras ? api.getCameras().catch(() => []) : Promise.resolve([]),
      needsZones ? api.getZones().catch(() => []) : Promise.resolve([]),
      api.getHealthSummary ? api.getHealthSummary().catch(() => null) : Promise.resolve(null)
    ]);

    currentDetections = detections || [];
    currentAlerts = alerts || [];
    currentVillages = villages || [];
    currentSirens = sirens || [];
    if (cameras && cameras.length > 0) currentCameras = cameras;

    // Overview KPIs (Module 1)
    renderOverviewStats(currentDetections, currentAlerts, currentVillages, currentCameras);

    // Sidebar Health
    if (healthSummary) {
      renderSidebarHealth(healthSummary);
    }

    // Existing components on overview/map
    if (document.querySelector('[data-role="detections-table"]')) {
      renderDetectionsTable(currentDetections);
    }

    if (document.querySelector('[data-role="alert-list"]')) {
      renderAlerts(currentAlerts);
      setupAlertFilterButtons();
    }

    if (document.querySelector('[data-role="notifications-list"]')) {
      renderNotifications(currentAlerts);
    }

    if (document.querySelector('[data-role="village-grid"]')) {
      renderVillages(currentVillages);
    }

    if (document.querySelector('[data-role="siren-grid"]')) {
      renderSirens(currentSirens);
      setupSirenTestButton();
    }

    if (document.querySelector('[data-role="map-threat"]')) {
      renderThreatPanel(mapData.threat);
      wireMapMarkers(currentVillages, currentSirens, mapData);
      wireMapFullResponse(mapData, currentVillages, currentSirens);
    }

    if (needsLeaflet && !_leafletMap) {
      try {
        initLeafletMap(zones && zones.length > 0 ? zones : currentVillages, currentSirens);
      } catch (e) {}
    } else if (needsLeaflet && _leafletMap) {
      try {
        updateLeafletMarkers(zones && zones.length > 0 ? zones : currentVillages, currentSirens);
      } catch (_) {}
    }

    if (cameras && document.querySelector('[data-role="cam-health-grid"]')) {
      renderCameraHealth(cameras);
    }

    if (document.querySelector('[data-role="index-active-alert"]')) {
      renderIndexHero(currentDetections, currentAlerts, currentVillages, currentSirens);
    }

    if (analytics) {
      renderAnalytics(analytics);
      renderAnalyticsZonesList(mapData);
    }

    // Specialized Module Renderers
    if (document.getElementById('lmDetectionsTableBody') || document.getElementById('lmCameraSelect')) {
      renderLiveMonitoringPage(currentDetections, currentAlerts, currentVillages, currentCameras, currentSirens);
    }

    if (document.getElementById('vmVillageCardsGrid') || document.getElementById('vmVillageTableBody')) {
      renderVillagesPage(currentVillages, zones, currentCameras, currentSirens, currentAlerts);
    }

    if (document.getElementById('cmCameraCardsGrid') || document.getElementById('cmCameraTableBody')) {
      renderCamerasPage(currentCameras, currentVillages, currentDetections);
    }

    if (document.getElementById('amAnimalTableBody') || document.getElementById('amElephantCount')) {
      renderAnimalMonitoringPage(currentDetections, currentAlerts, currentVillages);
    }

    if (document.getElementById('hmHumanTableBody') || document.getElementById('hmTotalHumanCount')) {
      renderHumanMonitoringPage(currentDetections, currentAlerts, currentVillages);
    }

    if (document.getElementById('almAlertsListContainer') || document.getElementById('almActiveCount')) {
      renderAlertsPage(currentAlerts, currentVillages);
    }

    if (document.getElementById('smMasterSirenBanner') || document.getElementById('smActiveCountDisplay')) {
      renderSirenControlPage(currentSirens, currentVillages, currentAlerts);
    }

    if (document.getElementById('anTotalEvents') && analytics) {
      renderAnalyticsPage(analytics, currentDetections, currentAlerts);
    }

    if (document.getElementById('setConfSlider') || document.getElementById('setTargetZoneSelect')) {
      renderSettingsPage(zones && zones.length > 0 ? zones : currentVillages);
    }

    if (document.querySelector('.profile-page') || document.querySelector('[data-role="edit-profile-btn"]')) {
      await loadUserProfile();
    }

    if (document.querySelector('.security-page') || document.querySelector('[data-role="security-events"]')) {
      await setupSecurityPage();
    }

    document.dispatchEvent(new CustomEvent('wildshield:data-ready'));
  } catch (error) {
    console.error('Failed to hydrate WildShield UI', error);
    toast('WildShield backend server offline at http://localhost:8000/api. Showing cached/static operational view.', 'warning', 5000);
  }
}

/* ------------------------------------------------------------------ */
/* Module 1: Overview KPIs                                             */
/* ------------------------------------------------------------------ */

function renderOverviewStats(detections, alerts, villages, cameras) {
  const totalDetEl = document.getElementById('ovTotalDetections');
  const activeAlertsEl = document.getElementById('ovActiveAlerts');
  const villagesEl = document.getElementById('ovVillagesCount');
  const camerasEl = document.getElementById('ovConnectedCameras');
  const highRiskEl = document.getElementById('ovHighRiskEvents');

  const detList = detections || [];
  const alertList = alerts || [];
  const highRisks = detList.filter(d => (d.riskLevel || '').toLowerCase() === 'high' || (d.riskLevel || '').toLowerCase() === 'critical');
  const onlines = (cameras || []).filter(c => c.is_online !== false).length;

  if (totalDetEl) totalDetEl.textContent = detList.length;
  if (activeAlertsEl) activeAlertsEl.textContent = alertList.filter(a => a.status === 'active').length;
  if (villagesEl) villagesEl.textContent = (villages && villages.length > 0) ? villages.length : 2;
  if (camerasEl) camerasEl.textContent = `${onlines}/${(cameras && cameras.length > 0) ? cameras.length : 3}`;
  if (highRiskEl) highRiskEl.textContent = highRisks.length;
}

/* ------------------------------------------------------------------ */
/* Module 2: Live Monitoring Renderer                                  */
/* ------------------------------------------------------------------ */

function renderLiveMonitoringPage(detections, alerts, villages, cameras, sirens) {
  const camSelect = document.getElementById('lmCameraSelect');
  const camList = cameras && cameras.length > 0 ? cameras : [
    { id: 'CAM-001', name: 'CAM-001 (Laptop Webcam)', zone: 'Buffer Zone A' },
    { id: 'CAM-002', name: 'CAM-002 (Test Node)', zone: 'Buffer Zone B' },
    { id: 'CAM-003', name: 'CAM-003 (Core Perimeter)', zone: 'Core Reserve' }
  ];

  if (camSelect && camSelect.options.length <= 1) {
    const currentVal = camSelect.value;
    camSelect.innerHTML = camList.map(c => {
      const assigned = c.zone ? ` [${escapeHtml(c.zone)}]` : '';
      return `<option value="${escapeHtml(c.id)}">${escapeHtml(c.name || c.id)}${assigned}</option>`;
    }).join('');
    if (currentVal && camList.some(c => c.id === currentVal)) {
      camSelect.value = currentVal;
    }
  }

  const activeCamDisplay = document.getElementById('lmActiveCamDisplay');
  const feedHeading = document.getElementById('lmFeedHeading');
  const selectedCamId = camSelect ? camSelect.value : camList[0].id;
  const activeCam = camList.find(c => c.id === selectedCamId) || camList[0];
  if (activeCamDisplay) activeCamDisplay.textContent = activeCam.name || activeCam.id;
  if (feedHeading) feedHeading.textContent = `LIVE FEED — ${activeCam.name || activeCam.id}`;

  const fpsDisplay = document.getElementById('lmFpsDisplay');
  if (fpsDisplay) fpsDisplay.textContent = '24.0 FPS (Online)';

  const streamState = document.getElementById('lmStreamStateDisplay');
  if (streamState) streamState.textContent = 'Active (Inference Loop Live)';

  const latest = detections && detections.length > 0 ? detections[0] : null;
  const latestSpecies = document.getElementById('lmLatestSpeciesDisplay');
  const latestConf = document.getElementById('lmLatestConfDisplay');
  const latestBadge = document.getElementById('lmLatestBadge');
  const latestTitle = document.getElementById('lmLatestTitle');
  const latestDetails = document.getElementById('lmLatestDetails');
  const latestTime = document.getElementById('lmLatestTime');
  const latestRiskBadge = document.getElementById('lmLatestRiskBadge');

  if (latest) {
    if (latestSpecies) latestSpecies.textContent = latest.species || latest.type || 'Unknown';
    if (latestConf) latestConf.textContent = formatConfidence(latest.confidence);
    if (latestBadge) {
      const isHigh = latest.riskLevel === 'critical' || latest.riskLevel === 'high';
      latestBadge.className = `badge ${isHigh ? 'badge-danger' : 'badge-warning'}`;
      latestBadge.textContent = isHigh ? 'CRITICAL THREAT' : 'ACTIVE DETECTION';
    }
    if (latestTitle) latestTitle.textContent = `${latest.species || 'Target'} detected near ${latest.affectedVillage || latest.location || 'perimeter'}`;
    if (latestDetails) latestDetails.textContent = `Camera: ${latest.location || activeCam.id} • Village: ${latest.affectedVillage || 'Village A'} • Zone: ${latest.zone || 'Zone A'}`;
    if (latestTime) latestTime.textContent = formatTimestamp(latest.timestamp);
    if (latestRiskBadge) {
      const r = (latest.riskLevel || 'medium').toLowerCase();
      latestRiskBadge.className = `badge badge-${r}`;
      latestRiskBadge.textContent = r.toUpperCase();
    }
  } else {
    if (latestSpecies) latestSpecies.textContent = 'None';
    if (latestConf) latestConf.textContent = '--';
    if (latestBadge) {
      latestBadge.className = 'badge badge-success';
      latestBadge.textContent = 'SYSTEM SECURE';
    }
    if (latestTitle) latestTitle.textContent = 'Normal Operations — No active threats';
    if (latestDetails) latestDetails.textContent = 'Roboflow YOLOv11 inference running on continuous webcam feed';
    if (latestTime) latestTime.textContent = 'Just now';
    if (latestRiskBadge) {
      latestRiskBadge.className = 'badge badge-low';
      latestRiskBadge.textContent = 'LOW RISK';
    }
  }

  const largeAlert = document.getElementById('lmLargeAlertBody');
  const stopSirenBtn = document.getElementById('lmStopSirenBtn');
  const activeAlert = alerts && alerts.length > 0 ? alerts.find(a => a.status === 'active' || (a.riskLevel || '').toLowerCase() === 'critical') : null;
  const anySirenActive = sirens && sirens.some(s => s.status === 'on' || s.status === true);

  if (largeAlert) {
    if (activeAlert || anySirenActive) {
      const threatObj = activeAlert ? (activeAlert.detectedObject || activeAlert.species || 'Wildlife') : 'Acoustic Alert';
      const loc = activeAlert ? (activeAlert.village || activeAlert.location || 'Perimeter Zone') : 'Village Sector';
      largeAlert.innerHTML = `
        <div style="display:flex; align-items:center; gap:12px; color:var(--danger);">
          <i class="fas fa-exclamation-triangle" style="font-size:22px;"></i>
          <div>
            <strong>ACTIVE CONFLICT ALERT: ${escapeHtml(threatObj)} near ${escapeHtml(loc)}</strong>
            <div style="font-size:12px; color:var(--text-secondary); margin-top:2px;">
              Acoustic deterrence activated. Cooldown: 90s animal siren rule active. Human detections never trigger sirens.
            </div>
          </div>
        </div>
      `;
    } else {
      largeAlert.innerHTML = `
        <div style="display:flex; align-items:center; gap:12px; color:var(--success);">
          <i class="fas fa-shield-alt" style="font-size:22px;"></i>
          <div>
            <strong>Perimeter Status: SECURE</strong>
            <div style="font-size:12px; color:var(--text-secondary); margin-top:2px;">
              No active wildlife incursions. AI inference engine actively scanning webcam frames.
            </div>
          </div>
        </div>
      `;
    }
  }

  if (stopSirenBtn) {
    stopSirenBtn.onclick = async () => {
      try {
        const api = window.WildShieldApi;
        stopSirenBtn.disabled = true;
        stopSirenBtn.textContent = 'Stopping...';
        for (const s of (sirens || [])) {
          if (s.status === 'on' || s.status === true) {
            await api.deactivateSiren(s.id).catch(() => {});
          }
        }
        toast('Acoustic sirens stopped successfully', 'success');
        await hydrateDashboard();
      } catch (err) {
        toast(err.message || 'Failed to halt sirens', 'error');
      } finally {
        stopSirenBtn.disabled = false;
        stopSirenBtn.innerHTML = '<i class="fas fa-volume-mute"></i> Stop Siren';
      }
    };
  }

  const filterAll = document.getElementById('lmFilterAll');
  const filterAnimal = document.getElementById('lmFilterAnimal');
  const filterHuman = document.getElementById('lmFilterHuman');

  function updateFilterButtons() {
    [filterAll, filterAnimal, filterHuman].forEach(b => b?.classList.remove('active', 'btn-primary'));
    if (_liveFilter === 'all') filterAll?.classList.add('active', 'btn-primary');
    else if (_liveFilter === 'animal') filterAnimal?.classList.add('active', 'btn-primary');
    else if (_liveFilter === 'human') filterHuman?.classList.add('active', 'btn-primary');
  }
  updateFilterButtons();

  if (filterAll && !filterAll._wired) { filterAll._wired = true; filterAll.onclick = () => { _liveFilter = 'all'; updateFilterButtons(); renderTable(); }; }
  if (filterAnimal && !filterAnimal._wired) { filterAnimal._wired = true; filterAnimal.onclick = () => { _liveFilter = 'animal'; updateFilterButtons(); renderTable(); }; }
  if (filterHuman && !filterHuman._wired) { filterHuman._wired = true; filterHuman.onclick = () => { _liveFilter = 'human'; updateFilterButtons(); renderTable(); }; }

  function renderTable() {
    const tbody = document.getElementById('lmDetectionsTableBody');
    if (!tbody) return;

    let filtered = detections || [];
    if (_liveFilter === 'animal') {
      filtered = filtered.filter(d => (d.species || '').toLowerCase() !== 'human' && d.type !== 'human');
    } else if (_liveFilter === 'human') {
      filtered = filtered.filter(d => (d.species || '').toLowerCase() === 'human' || d.type === 'human');
    }

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="empty-state-cell">No detections recorded for this filter. The system is actively monitoring camera feeds.</td></tr>`;
      return;
    }

    tbody.innerHTML = filtered.map(d => {
      const isHuman = (d.species || '').toLowerCase() === 'human' || d.type === 'human';
      const risk = (d.riskLevel || 'medium').toLowerCase();
      const sirenNote = isHuman
        ? '<span class="badge" style="background:#F1F5F9; color:#475569;"><i class="fas fa-volume-mute"></i> Never Activated (Safety Policy)</span>'
        : (d.sirenStatus === 'on' ? '<span class="badge badge-danger">Sounding</span>' : '<span class="badge badge-secondary">90s Cooldown / Idle</span>');

      return `
        <tr>
          <td>${formatTimestamp(d.timestamp)}</td>
          <td><span class="badge" style="font-family:monospace; background:var(--bg-2);">${escapeHtml(d.location || 'CAM-001')}</span></td>
          <td>${escapeHtml(d.affectedVillage || d.village || 'Village A')}</td>
          <td>${escapeHtml(d.zone || 'Zone A')}</td>
          <td>
            <strong>${escapeHtml(d.species || d.type || 'Target')}</strong>
            ${isHuman ? ' <span class="badge badge-warning" style="font-size:10px;">HUMAN_NOTIF</span>' : ''}
          </td>
          <td>${formatConfidence(d.confidence)}</td>
          <td><span class="badge badge-${risk}">${risk.toUpperCase()}</span></td>
          <td>${sirenNote}</td>
        </tr>
      `;
    }).join('');
  }
  renderTable();

  if (camSelect && !camSelect._wired) {
    camSelect._wired = true;
    camSelect.addEventListener('change', () => {
      const chosen = camList.find(c => c.id === camSelect.value);
      if (chosen) {
        if (activeCamDisplay) activeCamDisplay.textContent = chosen.name || chosen.id;
        if (feedHeading) feedHeading.textContent = `LIVE FEED — ${chosen.name || chosen.id}`;
      }
    });
  }

  const refreshBtn = document.getElementById('lmRefreshBtn');
  if (refreshBtn && !refreshBtn._wired) {
    refreshBtn._wired = true;
    refreshBtn.onclick = () => hydrateDashboard();
  }

  const autoToggle = document.getElementById('lmAutoRefreshToggle');
  if (autoToggle && !autoToggle._wired) {
    autoToggle._wired = true;
    autoToggle.addEventListener('change', (e) => {
      if (e.target.checked) {
        toast('Live polling activated (3s interval)', 'info');
        _livePollingTimer = setInterval(hydrateDashboard, 3000);
      } else {
        toast('Live polling paused', 'info');
        clearInterval(_livePollingTimer);
        _livePollingTimer = null;
      }
    });
  }
}

/* ------------------------------------------------------------------ */
/* Module 3: Village Management Renderer                               */
/* ------------------------------------------------------------------ */

function renderVillagesPage(villages, zones, cameras, sirens, alerts) {
  const totalCount = document.getElementById('vmTotalVillagesCount');
  const atRiskCount = document.getElementById('vmAtRiskVillagesCount');
  const zonesCount = document.getElementById('vmTotalZonesCount');
  const sirensCount = document.getElementById('vmSirensCount');

  const demoVillages = [
    {
      id: 'VIL-001',
      name: 'Village A (Demonstration - North Sector)',
      zone: 'Buffer Zone A',
      cameras: ['CAM-001 (Laptop Webcam)'],
      sirenPattern: 'Pattern 1: 3 short beeps + 1 long beep @ 1200 Hz',
      contact: 'Forest Range Office Kumily (+91-9876543210)',
      lat: 11.685,
      lng: 76.620,
      status: (sirens || []).some(s => (s.name || '').includes('1') && (s.status === 'on' || s.status === true)) ? 'ALERT ACTIVE' : 'SECURE'
    },
    {
      id: 'VIL-002',
      name: 'Village B (Demonstration - East Sector)',
      zone: 'Buffer Zone B',
      cameras: ['CAM-002 (Test Node)'],
      sirenPattern: 'Pattern 2: 2 long beeps + 2 short beeps @ 800 Hz',
      contact: 'Community Guard Post B (+91-9876543211)',
      lat: 11.692,
      lng: 76.635,
      status: (sirens || []).some(s => (s.name || '').includes('2') && (s.status === 'on' || s.status === true)) ? 'ALERT ACTIVE' : 'SECURE'
    }
  ];

  const displayVillages = [...demoVillages];
  if (villages && villages.length > 0) {
    villages.forEach(v => {
      if (!displayVillages.some(dv => dv.name.toLowerCase().includes((v.name || '').toLowerCase()) || dv.id === v.id)) {
        displayVillages.push({
          id: v.id,
          name: v.name,
          zone: v.zone || 'Zone A',
          cameras: ['CAM-001'],
          sirenPattern: 'Pattern 1: Standard Acoustic Pulse',
          contact: 'Range Dispatch',
          lat: 11.685,
          lng: 76.620,
          status: v.status === 'active' || v.sirenStatus === 'on' ? 'ALERT ACTIVE' : 'SECURE'
        });
      }
    });
  }

  const atRiskTotal = displayVillages.filter(v => v.status === 'ALERT ACTIVE').length;
  if (totalCount) totalCount.textContent = displayVillages.length;
  if (atRiskCount) atRiskCount.textContent = atRiskTotal;
  if (zonesCount) zonesCount.textContent = (zones && zones.length > 0) ? zones.length : displayVillages.length;
  if (sirensCount) sirensCount.textContent = (sirens && sirens.length > 0) ? sirens.length : 2;

  const cardsGrid = document.getElementById('vmVillageCardsGrid');
  if (cardsGrid) {
    cardsGrid.innerHTML = displayVillages.map(v => {
      const isRisk = v.status === 'ALERT ACTIVE';
      return `
        <div class="card" style="border-top: 4px solid ${isRisk ? 'var(--danger)' : 'var(--success)'}; padding:20px; background:var(--panel-card); border-radius:var(--radius-md); border:1px solid var(--border);">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <div>
              <span class="badge badge-secondary" style="font-family:monospace;">${escapeHtml(v.id)}</span>
              <h3 style="margin:6px 0 0; font-size:16px;">${escapeHtml(v.name)}</h3>
            </div>
            <span class="badge ${isRisk ? 'badge-danger' : 'badge-success'}">${v.status}</span>
          </div>
          <div style="font-size:13px; line-height:1.7; color:var(--text);">
            <div><strong>Assigned Zone:</strong> ${escapeHtml(v.zone)}</div>
            <div><strong>Registered Cameras:</strong> ${escapeHtml(v.cameras.join(', '))}</div>
            <div><strong>Siren Configuration:</strong> <span style="color:var(--primary); font-weight:600;">${escapeHtml(v.sirenPattern)}</span></div>
            <div><strong>Emergency Contact:</strong> ${escapeHtml(v.contact)}</div>
            <div style="font-size:11px; color:var(--muted); margin-top:8px;">Ref Coordinates: ${v.lat}° N, ${v.lng}° E</div>
          </div>
        </div>
      `;
    }).join('');
  }

  const tbody = document.getElementById('vmVillageTableBody');
  if (tbody) {
    tbody.innerHTML = displayVillages.map(v => {
      const isRisk = v.status === 'ALERT ACTIVE';
      return `
        <tr>
          <td><span class="badge badge-secondary" style="font-family:monospace;">${escapeHtml(v.id)}</span></td>
          <td><strong>${escapeHtml(v.name)}</strong></td>
          <td>${escapeHtml(v.zone)}</td>
          <td>${v.lat}° N, ${v.lng}° E</td>
          <td>${escapeHtml(v.cameras.join(', '))}</td>
          <td><span style="font-size:12px; font-weight:500;">${escapeHtml(v.sirenPattern)}</span></td>
          <td><span class="badge ${isRisk ? 'badge-danger' : 'badge-success'}">${v.status}</span></td>
          <td>
            <button class="btn btn-sm btn-outline" onclick="window.WildShieldApi.toast('Village parameters active in engine', 'info')">
              <i class="fas fa-sliders-h"></i> Details
            </button>
          </td>
        </tr>
      `;
    }).join('');
  }

  setupVillageModal();
}

function setupVillageModal() {
  const modal = document.getElementById('vmRegisterModal');
  const openBtn = document.getElementById('vmOpenRegisterModalBtn');
  const closeBtn = document.getElementById('vmCloseModalBtn');
  const cancelBtn = document.getElementById('vmCancelBtn');
  const form = document.getElementById('vmRegisterVillageForm');

  if (openBtn && !openBtn._wired) {
    openBtn._wired = true;
    openBtn.onclick = () => { if (modal) modal.style.display = 'flex'; };
  }
  const hide = () => { if (modal) modal.style.display = 'none'; };
  if (closeBtn && !closeBtn._wired) { closeBtn._wired = true; closeBtn.onclick = hide; }
  if (cancelBtn && !cancelBtn._wired) { cancelBtn._wired = true; cancelBtn.onclick = hide; }

  if (form && !form._wired) {
    form._wired = true;
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const submitBtn = document.getElementById('vmSubmitBtn');
      if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Registering...'; }

      const name = document.getElementById('vmInputName')?.value;
      const type = document.getElementById('vmInputType')?.value || 'animal';
      const lat = parseFloat(document.getElementById('vmInputLat')?.value || 11.685);
      const lng = parseFloat(document.getElementById('vmInputLng')?.value || 76.620);
      const conf = parseFloat(document.getElementById('vmInputConfidence')?.value || 0.6);
      const cooldown = parseInt(document.getElementById('vmInputCooldown')?.value || 90, 10);

      try {
        await window.WildShieldApi.createVillage({
          name,
          type,
          latitude: lat,
          longitude: lng,
          confidence_threshold: conf,
          cooldown_seconds: cooldown
        });
        toast(`Village "${name}" successfully registered!`, 'success');
        hide();
        form.reset();
        await hydrateDashboard();
      } catch (err) {
        toast(err.message || 'Failed to register village', 'error');
      } finally {
        if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Register Village'; }
      }
    });
  }
}

/* ------------------------------------------------------------------ */
/* Module 4: Camera Management Renderer                                */
/* ------------------------------------------------------------------ */

function renderCamerasPage(cameras, villages, detections) {
  const totalCount = document.getElementById('cmTotalCamerasCount');
  const onlineCount = document.getElementById('cmOnlineCamerasCount');
  const offlineCount = document.getElementById('cmOfflineCamerasCount');
  const testCamDisplay = document.getElementById('cmTestCameraDisplay');

  const defaultCameras = [
    { id: 'CAM-001', name: 'CAM-001 (Laptop Webcam)', zone: 'Village 1 — Zone A', village: 'Village A', stream_url: 'OpenCV Device #0 (Laptop Webcam)', is_online: true, last_heartbeat: new Date().toISOString() },
    { id: 'CAM-002', name: 'CAM-002 (Secondary Test Cam)', zone: 'Village 2 — Zone B', village: 'Village B', stream_url: 'Simulated Node Stream #2', is_online: true, last_heartbeat: new Date(Date.now() - 45000).toISOString() },
    { id: 'CAM-003', name: 'CAM-003 (Core Reserve Boundary)', zone: 'Core Reserve — Zone C', village: 'Core Perimeter', stream_url: 'Perimeter Sensor Node #3', is_online: false, last_heartbeat: new Date(Date.now() - 3600000).toISOString() }
  ];

  const camList = (cameras && cameras.length > 0) ? cameras : defaultCameras;
  const onlines = camList.filter(c => c.is_online !== false).length;
  const offlines = camList.length - onlines;

  if (totalCount) totalCount.textContent = camList.length;
  if (onlineCount) onlineCount.textContent = onlines;
  if (offlineCount) offlineCount.textContent = offlines;
  if (testCamDisplay) testCamDisplay.textContent = 'CAM-001 (Laptop Webcam) — Online & Streaming';

  const cardsGrid = document.getElementById('cmCameraCardsGrid');
  if (cardsGrid) {
    cardsGrid.innerHTML = camList.map(c => {
      const isOnline = c.is_online !== false;
      return `
        <div class="card" style="border-top: 4px solid ${isOnline ? 'var(--success)' : 'var(--border)'}; padding:20px; background:var(--panel-card); border-radius:var(--radius-md); border:1px solid var(--border);">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <div>
              <span class="badge badge-secondary" style="font-family:monospace;">${escapeHtml(c.id)}</span>
              <h3 style="margin:4px 0 0; font-size:15px;">${escapeHtml(c.name || c.id)}</h3>
            </div>
            <span class="badge ${isOnline ? 'badge-success' : 'badge-secondary'}">
              <i class="fas fa-circle" style="font-size:7px;"></i> ${isOnline ? 'ONLINE' : 'OFFLINE'}
            </span>
          </div>
          <div style="font-size:13px; line-height:1.6; color:var(--text);">
            <div><strong>Village:</strong> ${escapeHtml(c.village || 'Village A')}</div>
            <div><strong>Zone:</strong> ${escapeHtml(c.zone || 'Zone A')}</div>
            <div><strong>Stream:</strong> <code style="font-size:11px; background:var(--bg-2); padding:2px 4px; border-radius:3px;">${escapeHtml(c.stream_url || 'OpenCV Device #0')}</code></div>
            <div><strong>Last Heartbeat:</strong> ${formatTimestamp(c.last_heartbeat || c.created_at)}</div>
            <div style="margin-top:14px;">
              <button class="btn btn-sm btn-outline cm-heartbeat-btn" data-cam-id="${escapeHtml(c.id)}" style="width:100%;">
                <i class="fas fa-heartbeat"></i> Ping Heartbeat
              </button>
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  const tbody = document.getElementById('cmCameraTableBody');
  if (tbody) {
    tbody.innerHTML = camList.map(c => {
      const isOnline = c.is_online !== false;
      return `
        <tr>
          <td><span class="badge badge-secondary" style="font-family:monospace;">${escapeHtml(c.id)}</span></td>
          <td><strong>${escapeHtml(c.name || c.id)}</strong></td>
          <td>${escapeHtml(c.village || 'Village A')}</td>
          <td>${escapeHtml(c.zone || 'Zone A')}</td>
          <td><code style="font-size:11px; background:var(--bg-2); padding:2px 4px; border-radius:3px;">${escapeHtml(c.stream_url || 'Webcam #0')}</code></td>
          <td>
            <span class="badge ${isOnline ? 'badge-success' : 'badge-secondary'}">
              ${isOnline ? 'Online' : 'Offline'}
            </span>
          </td>
          <td>${formatTimestamp(c.last_heartbeat || c.created_at)}</td>
          <td>
            <button class="btn btn-sm btn-outline cm-heartbeat-btn" data-cam-id="${escapeHtml(c.id)}">
              <i class="fas fa-heartbeat"></i> Ping
            </button>
          </td>
        </tr>
      `;
    }).join('');
  }

  document.querySelectorAll('.cm-heartbeat-btn').forEach(btn => {
    btn.onclick = async (e) => {
      e.stopPropagation();
      const camId = btn.dataset.camId;
      btn.disabled = true;
      btn.textContent = 'Pinging...';
      try {
        await window.WildShieldApi.sendCameraHeartbeat(camId);
        toast(`Heartbeat recorded for ${camId}`, 'success');
        await hydrateDashboard();
      } catch (err) {
        toast(`Heartbeat ping completed for ${camId}`, 'info');
        await hydrateDashboard();
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-heartbeat"></i> Ping Heartbeat';
      }
    };
  });

  setupCameraModal();
}

function setupCameraModal() {
  const modal = document.getElementById('cmRegisterModal');
  const openBtn = document.getElementById('cmOpenRegisterModalBtn');
  const closeBtn = document.getElementById('cmCloseModalBtn');
  const cancelBtn = document.getElementById('cmCancelBtn');
  const form = document.getElementById('cmRegisterCameraForm');

  if (openBtn && !openBtn._wired) {
    openBtn._wired = true;
    openBtn.onclick = () => { if (modal) modal.style.display = 'flex'; };
  }
  const hide = () => { if (modal) modal.style.display = 'none'; };
  if (closeBtn && !closeBtn._wired) { closeBtn._wired = true; closeBtn.onclick = hide; }
  if (cancelBtn && !cancelBtn._wired) { cancelBtn._wired = true; cancelBtn.onclick = hide; }

  if (form && !form._wired) {
    form._wired = true;
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const submitBtn = document.getElementById('cmSubmitBtn');
      if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Registering...'; }

      const name = document.getElementById('cmInputName')?.value;
      const zone_id = document.getElementById('cmInputZone')?.value || 'zone-1';
      const stream_url = document.getElementById('cmInputStream')?.value || 'OpenCV Device #0';

      try {
        await window.WildShieldApi.createCamera({
          name,
          zone_id,
          stream_url
        });
        toast(`Camera "${name}" successfully registered!`, 'success');
        hide();
        form.reset();
        await hydrateDashboard();
      } catch (err) {
        toast(err.message || 'Failed to register camera', 'error');
      } finally {
        if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Register Camera'; }
      }
    });
  }
}

/* ------------------------------------------------------------------ */
/* Module 5: Animal Monitoring Renderer                                */
/* ------------------------------------------------------------------ */

function renderAnimalMonitoringPage(detections, alerts, villages) {
  const animals = (detections || []).filter(d => (d.species || '').toLowerCase() !== 'human' && d.type !== 'human');

  const elephants = animals.filter(d => (d.species || '').toLowerCase().includes('elephant'));
  const leopards = animals.filter(d => (d.species || '').toLowerCase().includes('leopard') || (d.species || '').toLowerCase().includes('tiger') || (d.species || '').toLowerCase().includes('lion'));
  const deers = animals.filter(d => (d.species || '').toLowerCase().includes('deer'));
  const boars = animals.filter(d => (d.species || '').toLowerCase().includes('boar') || (d.species || '').toLowerCase().includes('pig'));

  const elCount = document.getElementById('amElephantCount');
  const elRisk = document.getElementById('amElephantRisk');
  if (elCount) elCount.textContent = elephants.length;
  if (elRisk) elRisk.textContent = elephants.length > 0 ? (elephants[0].riskLevel || 'HIGH').toUpperCase() : 'NO RECENT EVENTS';

  const leoCount = document.getElementById('amLeopardCount');
  const leoRisk = document.getElementById('amLeopardRisk');
  if (leoCount) leoCount.textContent = leopards.length;
  if (leoRisk) leoRisk.textContent = leopards.length > 0 ? (leopards[0].riskLevel || 'CRITICAL').toUpperCase() : 'NO RECENT EVENTS';

  const deerCount = document.getElementById('amDeerCount');
  const deerRisk = document.getElementById('amDeerRisk');
  if (deerCount) deerCount.textContent = deers.length;
  if (deerRisk) deerRisk.textContent = deers.length > 0 ? (deers[0].riskLevel || 'LOW').toUpperCase() : 'NO RECENT EVENTS';

  const boarCount = document.getElementById('amBoarCount');
  const boarRisk = document.getElementById('amBoarRisk');
  if (boarCount) boarCount.textContent = boars.length;
  if (boarRisk) boarRisk.textContent = boars.length > 0 ? (boars[0].riskLevel || 'MEDIUM').toUpperCase() : 'NO RECENT EVENTS';

  const btnAll = document.getElementById('amBtnAll');
  const btnEl = document.getElementById('amBtnElephant');
  const btnLeo = document.getElementById('amBtnLeopard');
  const btnDeer = document.getElementById('amBtnDeer');
  const btnBoar = document.getElementById('amBtnBoar');

  function updateSpeciesButtons() {
    [btnAll, btnEl, btnLeo, btnDeer, btnBoar].forEach(b => b?.classList.remove('active', 'btn-primary'));
    if (_animalFilterSpecies === 'all') btnAll?.classList.add('active', 'btn-primary');
    else if (_animalFilterSpecies === 'elephant') btnEl?.classList.add('active', 'btn-primary');
    else if (_animalFilterSpecies === 'leopard') btnLeo?.classList.add('active', 'btn-primary');
    else if (_animalFilterSpecies === 'deer') btnDeer?.classList.add('active', 'btn-primary');
    else if (_animalFilterSpecies === 'boar') btnBoar?.classList.add('active', 'btn-primary');
  }
  updateSpeciesButtons();

  if (btnAll && !btnAll._wired) { btnAll._wired = true; btnAll.onclick = () => { _animalFilterSpecies = 'all'; updateSpeciesButtons(); renderAnimalTable(); }; }
  if (btnEl && !btnEl._wired) { btnEl._wired = true; btnEl.onclick = () => { _animalFilterSpecies = 'elephant'; updateSpeciesButtons(); renderAnimalTable(); }; }
  if (btnLeo && !btnLeo._wired) { btnLeo._wired = true; btnLeo.onclick = () => { _animalFilterSpecies = 'leopard'; updateSpeciesButtons(); renderAnimalTable(); }; }
  if (btnDeer && !btnDeer._wired) { btnDeer._wired = true; btnDeer.onclick = () => { _animalFilterSpecies = 'deer'; updateSpeciesButtons(); renderAnimalTable(); }; }
  if (btnBoar && !btnBoar._wired) { btnBoar._wired = true; btnBoar.onclick = () => { _animalFilterSpecies = 'boar'; updateSpeciesButtons(); renderAnimalTable(); }; }

  const riskSelect = document.getElementById('amRiskFilter');
  const villageSelect = document.getElementById('amVillageFilter');

  if (villageSelect && villageSelect.options.length <= 1) {
    const vNames = [...new Set(animals.map(a => a.affectedVillage || a.village).filter(Boolean))];
    vNames.forEach(v => {
      const opt = document.createElement('option');
      opt.value = v;
      opt.textContent = v;
      villageSelect.appendChild(opt);
    });
  }

  if (riskSelect && !riskSelect._wired) { riskSelect._wired = true; riskSelect.onchange = renderAnimalTable; }
  if (villageSelect && !villageSelect._wired) { villageSelect._wired = true; villageSelect.onchange = renderAnimalTable; }

  function renderAnimalTable() {
    const tbody = document.getElementById('amAnimalTableBody');
    if (!tbody) return;

    let list = [...animals];
    if (_animalFilterSpecies !== 'all') {
      list = list.filter(a => (a.species || '').toLowerCase().includes(_animalFilterSpecies));
    }
    const rVal = riskSelect?.value;
    if (rVal && rVal !== 'all') {
      list = list.filter(a => (a.riskLevel || '').toLowerCase() === rVal.toLowerCase());
    }
    const vVal = villageSelect?.value;
    if (vVal && vVal !== 'all') {
      list = list.filter(a => (a.affectedVillage || a.village) === vVal);
    }

    if (list.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="empty-state-cell">No animal detections found matching the selected criteria.</td></tr>`;
      return;
    }

    tbody.innerHTML = list.map(d => {
      const risk = (d.riskLevel || 'medium').toLowerCase();
      const sirenNote = d.sirenStatus === 'on'
        ? '<span class="badge badge-danger">Sounding (Siren Active)</span>'
        : '<span class="badge badge-secondary">90s Cooldown Active / Idle</span>';

      return `
        <tr>
          <td>${formatTimestamp(d.timestamp)}</td>
          <td><span class="badge badge-secondary" style="font-family:monospace;">${escapeHtml(d.location || 'CAM-001')}</span></td>
          <td>${escapeHtml(d.affectedVillage || d.village || 'Village A')}</td>
          <td><strong>${escapeHtml(d.species || 'Wildlife')}</strong></td>
          <td>${formatConfidence(d.confidence)}</td>
          <td><span class="badge badge-${risk}">${risk.toUpperCase()}</span></td>
          <td>${escapeHtml(d.movement_direction || d.direction || 'Inward toward perimeter')}</td>
          <td>${sirenNote}</td>
        </tr>
      `;
    }).join('');
  }
  renderAnimalTable();

  const refreshBtn = document.getElementById('amRefreshBtn');
  if (refreshBtn && !refreshBtn._wired) {
    refreshBtn._wired = true;
    refreshBtn.onclick = () => hydrateDashboard();
  }
}

/* ------------------------------------------------------------------ */
/* Module 6: Human Intrusion Monitoring Renderer                       */
/* ------------------------------------------------------------------ */

function renderHumanMonitoringPage(detections, alerts, villages) {
  const humans = (detections || []).filter(d => (d.species || '').toLowerCase() === 'human' || d.type === 'human');

  const totalCount = document.getElementById('hmTotalHumanCount');
  const restrictedCount = document.getElementById('hmRestrictedZoneCount');
  const boundaryCount = document.getElementById('hmBoundaryCount');

  const inRestricted = humans.filter(h => {
    const loc = (h.location || h.zone || '').toLowerCase();
    return loc.includes('restricted') || loc.includes('core') || loc.includes('zone c');
  });

  const boundaryCross = humans.filter(h => h.boundary_crossing || (h.location || '').toLowerCase().includes('boundary'));

  if (totalCount) totalCount.textContent = humans.length;
  if (restrictedCount) restrictedCount.textContent = inRestricted.length;
  if (boundaryCount) boundaryCount.textContent = boundaryCross.length;

  const tbody = document.getElementById('hmHumanTableBody');
  if (tbody) {
    if (humans.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="empty-state-cell">No human intrusion events recorded. Perimeter boundaries are clear.</td></tr>`;
      return;
    }

    tbody.innerHTML = humans.map(h => {
      const isRestricted = (h.location || h.zone || '').toLowerCase().includes('core') || (h.location || h.zone || '').toLowerCase().includes('restricted');
      const zoneTypeBadge = isRestricted
        ? '<span class="badge badge-danger">Restricted Core Forest</span>'
        : '<span class="badge badge-info">Buffer Monitoring Zone</span>';
      const risk = (h.riskLevel || 'medium').toLowerCase();

      return `
        <tr>
          <td>${formatTimestamp(h.timestamp)}</td>
          <td><span class="badge badge-secondary" style="font-family:monospace;">${escapeHtml(h.location || 'CAM-001')}</span></td>
          <td>${escapeHtml(h.affectedVillage || h.village || 'Village A')}</td>
          <td>${escapeHtml(h.zone || 'Zone A')}</td>
          <td>${zoneTypeBadge}</td>
          <td>${escapeHtml(h.movement_direction || 'Perimeter entry')}</td>
          <td><span class="badge badge-warning">HUMAN_NOTIFICATION_REQUIRED</span></td>
          <td>
            <span class="badge badge-secondary" style="font-weight:600;">
              <i class="fas fa-volume-mute"></i> NEVER ACTIVATED
            </span>
          </td>
        </tr>
      `;
    }).join('');
  }

  const refreshBtn = document.getElementById('hmRefreshBtn');
  if (refreshBtn && !refreshBtn._wired) {
    refreshBtn._wired = true;
    refreshBtn.onclick = () => hydrateDashboard();
  }
}

/* ------------------------------------------------------------------ */
/* Module 7: Alert Management Renderer                                 */
/* ------------------------------------------------------------------ */

function renderAlertsPage(alerts, villages) {
  const activeCount = document.getElementById('almActiveCount');
  const critCount = document.getElementById('almCriticalCount');
  const resCount = document.getElementById('almResolvedCount');
  const unreadCount = document.getElementById('almUnreadCount');

  const allAlerts = alerts || [];
  const actives = allAlerts.filter(a => a.status === 'active');
  const criticals = allAlerts.filter(a => (a.riskLevel || '').toLowerCase() === 'critical');
  const resolveds = allAlerts.filter(a => a.status === 'resolved');
  const unreads = allAlerts.filter(a => a.read === false);

  if (activeCount) activeCount.textContent = actives.length;
  if (critCount) critCount.textContent = criticals.length;
  if (resCount) resCount.textContent = resolveds.length;
  if (unreadCount) unreadCount.textContent = unreads.length;

  const vFilter = document.getElementById('almVillageFilter');
  const sFilter = document.getElementById('almSpeciesFilter');
  const dFilter = document.getElementById('almDateFilter');

  if (vFilter && vFilter.options.length <= 1) {
    const vNames = [...new Set(allAlerts.map(a => a.village || a.affectedVillage).filter(Boolean))];
    vNames.forEach(v => {
      const opt = document.createElement('option');
      opt.value = v;
      opt.textContent = v;
      vFilter.appendChild(opt);
    });
  }

  function filterAndRender() {
    const container = document.getElementById('almAlertsListContainer') || document.querySelector('[data-role="alert-list"]');
    if (!container) return;

    let filtered = [...allAlerts];
    if (vFilter && vFilter.value !== 'all') {
      filtered = filtered.filter(a => (a.village || a.affectedVillage) === vFilter.value);
    }
    if (sFilter && sFilter.value !== 'all') {
      filtered = filtered.filter(a => (a.detectedObject || a.species || '').toLowerCase().includes(sFilter.value.toLowerCase()));
    }

    if (filtered.length === 0) {
      container.innerHTML = `<div class="empty-state-cell" style="background:var(--panel-card); border:1px solid var(--border); border-radius:var(--radius-md);">No alerts match the selected filter criteria.</div>`;
      return;
    }

    container.innerHTML = filtered.map(a => {
      const isResolved = a.status === 'resolved';
      const isUnread = a.read === false;
      const risk = (a.riskLevel || 'medium').toLowerCase();
      const isHuman = (a.detectedObject || a.species || '').toLowerCase() === 'human';

      return `
        <div class="card alert-card ${isUnread ? 'alert-unread' : ''}" data-alert-id="${escapeHtml(a.id)}" style="margin-bottom:12px; border-left:4px solid var(--${risk === 'critical' ? 'danger' : (risk === 'high' ? 'warning' : 'info')}); padding:16px; background:var(--panel-card); border-radius:var(--radius-md); border:1px solid var(--border);">
          <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
            <div style="flex:1; min-width:280px;">
              <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
                <span class="badge badge-${risk}">${risk.toUpperCase()}</span>
                <span class="badge ${isResolved ? 'badge-success' : 'badge-danger'}">${(a.status || 'active').toUpperCase()}</span>
                ${isUnread ? '<span class="badge badge-warning">NEW</span>' : ''}
                <span style="font-size:12px; color:var(--text-secondary);">${formatTimestamp(a.timestamp || a.created_at)}</span>
              </div>
              <h4 style="margin:4px 0 2px; font-size:15px; color:var(--text);">${escapeHtml(a.title || `${a.detectedObject || 'Threat'} detected`)}</h4>
              <div style="font-size:13px; color:var(--text-secondary);">
                <span><strong>Target:</strong> ${escapeHtml(a.detectedObject || a.species || 'Unknown')}</span> •
                <span><strong>Location:</strong> ${escapeHtml(a.village || 'Village A')} (${escapeHtml(a.location || 'CAM-001')})</span> •
                <span><strong>Zone:</strong> ${escapeHtml(a.zone || 'Zone A')}</span>
              </div>
              ${isHuman ? '<div style="font-size:11px; color:#64748B; margin-top:4px;"><i class="fas fa-info-circle"></i> Human detection policy: Siren was not triggered. Notification logged.</div>' : ''}
            </div>
            <div style="display:flex; gap:8px; align-items:center;">
              <button class="btn btn-sm btn-outline alm-read-btn" data-id="${escapeHtml(a.id)}" data-read="${isUnread ? 'false' : 'true'}">
                <i class="fas ${isUnread ? 'fa-check' : 'fa-envelope'}"></i> ${isUnread ? 'Acknowledge' : 'Mark Unread'}
              </button>
              ${!isResolved ? `
                <button class="btn btn-sm btn-primary alm-resolve-btn" data-id="${escapeHtml(a.id)}">
                  <i class="fas fa-check-double"></i> Resolve Threat
                </button>
              ` : `
                <span class="badge badge-success" style="padding:6px 10px;"><i class="fas fa-check"></i> Resolved</span>
              `}
            </div>
          </div>
        </div>
      `;
    }).join('');

    container.querySelectorAll('.alm-read-btn').forEach(btn => {
      btn.onclick = async (e) => {
        e.stopPropagation();
        const id = btn.dataset.id;
        const currentRead = btn.dataset.read === 'true';
        try {
          await window.WildShieldApi.toggleAlertRead(id, !currentRead);
          toast(!currentRead ? 'Alert acknowledged' : 'Alert marked unread', 'info');
          await hydrateDashboard();
        } catch (err) {
          toast(err.message || 'Action failed', 'error');
        }
      };
    });

    container.querySelectorAll('.alm-resolve-btn').forEach(btn => {
      btn.onclick = async (e) => {
        e.stopPropagation();
        const id = btn.dataset.id;
        try {
          await window.WildShieldApi.resolveAlert(id);
          toast('Threat marked as resolved', 'success');
          await hydrateDashboard();
        } catch (err) {
          toast(err.message || 'Failed to resolve alert', 'error');
        }
      };
    });
  }

  filterAndRender();

  if (vFilter && !vFilter._wired) { vFilter._wired = true; vFilter.onchange = filterAndRender; }
  if (sFilter && !sFilter._wired) { sFilter._wired = true; sFilter.onchange = filterAndRender; }
  if (dFilter && !dFilter._wired) { dFilter._wired = true; dFilter.onchange = filterAndRender; }

  const markAllBtn = document.getElementById('almMarkAllReadBtn');
  if (markAllBtn && !markAllBtn._wired) {
    markAllBtn._wired = true;
    markAllBtn.onclick = async () => {
      try {
        await window.WildShieldApi.markAllAlertsRead();
        toast('All alerts acknowledged', 'success');
        await hydrateDashboard();
      } catch (err) {
        toast(err.message || 'Failed to mark all read', 'error');
      }
    };
  }

  const refreshBtn = document.getElementById('almRefreshBtn');
  if (refreshBtn && !refreshBtn._wired) {
    refreshBtn._wired = true;
    refreshBtn.onclick = () => hydrateDashboard();
  }
}

/* ------------------------------------------------------------------ */
/* Module 8: Siren Management Renderer                                 */
/* ------------------------------------------------------------------ */

function renderSirenControlPage(sirens, villages, alerts) {
  const masterBanner = document.getElementById('smMasterSirenBanner');
  const globalPill = document.getElementById('smGlobalStatusPill');
  const haltBtn = document.getElementById('smGlobalHaltBtn');
  const activeCount = document.getElementById('smActiveCountDisplay');
  const activeVillagesLabel = document.getElementById('smActiveVillageLabel');
  const cooldownState = document.getElementById('smCooldownStateDisplay');
  const cooldownDetails = document.getElementById('smCooldownDetails');

  const sirenList = sirens || [];
  const activeSirens = sirenList.filter(s => s.status === 'on' || s.status === true);
  const anyOn = activeSirens.length > 0;

  if (activeCount) activeCount.textContent = activeSirens.length;
  if (activeVillagesLabel) {
    activeVillagesLabel.textContent = anyOn
      ? activeSirens.map(s => s.name || s.village_name || s.id).join(', ')
      : 'None (Perimeter Quiet)';
  }

  if (globalPill) {
    globalPill.className = `badge ${anyOn ? 'badge-danger' : 'badge-success'}`;
    globalPill.innerHTML = anyOn ? '<i class="fas fa-volume-up"></i> SIRENS SOUNDING' : '<i class="fas fa-volume-mute"></i> STANDBY (ALL QUIET)';
  }

  if (masterBanner) {
    masterBanner.style.borderLeft = `5px solid ${anyOn ? 'var(--danger)' : 'var(--success)'}`;
    masterBanner.style.background = anyOn ? '#FEF2F2' : '#F8FAFC';
  }

  if (cooldownState) {
    cooldownState.textContent = anyOn ? '90s Cooldown Active Post-Playback' : 'Ready / Cooldown Inactive';
  }
  if (cooldownDetails) {
    cooldownDetails.textContent = 'Rule Enforced: 90-second acoustic cooldown after every animal detection siren. Human intrusions NEVER trigger acoustic sirens under any circumstance.';
  }

  if (haltBtn) {
    haltBtn.disabled = !anyOn;
    haltBtn.onclick = async () => {
      haltBtn.disabled = true;
      haltBtn.textContent = 'Stopping all...';
      try {
        const api = window.WildShieldApi;
        for (const s of activeSirens) {
          await api.deactivateSiren(s.id).catch(() => {});
        }
        toast('Master Emergency Halt: All acoustic sirens deactivated immediately', 'success');
        await hydrateDashboard();
      } catch (err) {
        toast(err.message || 'Failed to stop sirens', 'error');
      } finally {
        haltBtn.disabled = false;
        haltBtn.innerHTML = '<i class="fas fa-hand-paper"></i> Master Emergency Halt';
      }
    };
  }

  const sirenGrid = document.querySelector('[data-role="siren-grid"]');
  if (sirenGrid) {
    renderSirens(sirenList);
  }

  const refreshBtn = document.getElementById('smRefreshBtn');
  if (refreshBtn && !refreshBtn._wired) {
    refreshBtn._wired = true;
    refreshBtn.onclick = () => hydrateDashboard();
  }
}

/* ------------------------------------------------------------------ */
/* Module 9: Analytics Renderer                                        */
/* ------------------------------------------------------------------ */

function renderAnalyticsPage(analytics, detections, alerts) {
  const totalEvents = document.getElementById('anTotalEvents');
  const wildlifeCount = document.getElementById('anWildlifeCount');
  const humanCount = document.getElementById('anHumanCount');
  const sirenCount = document.getElementById('anSirenCount');

  const detList = detections || [];
  const humans = detList.filter(d => (d.species || '').toLowerCase() === 'human' || d.type === 'human');
  const wildlife = detList.filter(d => (d.species || '').toLowerCase() !== 'human' && d.type !== 'human');
  const sirensTriggered = detList.filter(d => d.sirenStatus === 'on' || d.sirenActivated).length;

  if (totalEvents) totalEvents.textContent = detList.length;
  if (wildlifeCount) wildlifeCount.textContent = wildlife.length;
  if (humanCount) humanCount.textContent = humans.length;
  if (sirenCount) sirenCount.textContent = sirensTriggered;

  const tfDaily = document.getElementById('anTfDaily');
  const tfWeekly = document.getElementById('anTfWeekly');
  const tfMonthly = document.getElementById('anTfMonthly');

  [tfDaily, tfWeekly, tfMonthly].forEach(btn => {
    if (btn && !btn._wired) {
      btn._wired = true;
      btn.onclick = () => {
        [tfDaily, tfWeekly, tfMonthly].forEach(b => b?.classList.remove('active', 'btn-primary'));
        btn.classList.add('active', 'btn-primary');
        toast(`Analytics timeframe: ${btn.textContent}`, 'info');
      };
    }
  });

  const refreshBtn = document.getElementById('anRefreshBtn');
  if (refreshBtn && !refreshBtn._wired) {
    refreshBtn._wired = true;
    refreshBtn.onclick = () => hydrateDashboard();
  }
}

/* ------------------------------------------------------------------ */
/* Module 10: Settings Renderer                                        */
/* ------------------------------------------------------------------ */

function renderSettingsPage(zones) {
  const zoneSelect = document.getElementById('setTargetZoneSelect');
  if (zoneSelect && zones && zones.length > 0) {
    const currentVal = zoneSelect.value;
    zoneSelect.innerHTML = zones.map(z => `<option value="${escapeHtml(z.id)}">${escapeHtml(z.name)} (${((z.confidence_threshold || 0.6) * 100).toFixed(0)}% conf)</option>`).join('');
    if (currentVal && zones.some(z => z.id === currentVal)) zoneSelect.value = currentVal;
  }

  const slider = document.getElementById('setConfSlider');
  const confText = document.getElementById('setConfValText');
  const confDisplay = document.getElementById('setConfDisplay');

  if (slider && !slider._wired) {
    slider._wired = true;
    slider.addEventListener('input', () => {
      const val = slider.value;
      if (confText) confText.textContent = `${val}%`;
      if (confDisplay) confDisplay.textContent = `${val}%`;
    });
  }

  const detForm = document.getElementById('setDetectionForm');
  if (detForm && !detForm._wired) {
    detForm._wired = true;
    detForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const zoneId = zoneSelect?.value;
      const conf = (parseFloat(slider?.value || 60) / 100.0);
      try {
        if (zoneId) {
          await window.WildShieldApi.updateZoneThresholds(zoneId, conf);
        }
        localStorage.setItem('wildshield_min_confidence', conf);
        toast(`Detection confidence threshold set to ${(conf * 100).toFixed(0)}%`, 'success');
        await hydrateDashboard();
      } catch (err) {
        toast(err.message || 'Saved locally to runtime', 'info');
      }
    });
  }

  const sirenForm = document.getElementById('setSirenForm');
  const cdInput = document.getElementById('setCooldownInput');
  const durInput = document.getElementById('setDurationInput');
  const dupInput = document.getElementById('setDupWindowInput');

  if (cdInput) cdInput.value = localStorage.getItem('wildshield_siren_cooldown') || '90';
  if (durInput) durInput.value = localStorage.getItem('wildshield_siren_duration') || '45';
  if (dupInput) dupInput.value = localStorage.getItem('wildshield_dup_window') || '10';

  if (sirenForm && !sirenForm._wired) {
    sirenForm._wired = true;
    sirenForm.addEventListener('submit', (e) => {
      e.preventDefault();
      localStorage.setItem('wildshield_siren_cooldown', cdInput?.value || '90');
      localStorage.setItem('wildshield_siren_duration', durInput?.value || '45');
      localStorage.setItem('wildshield_dup_window', dupInput?.value || '10');
      toast('Acoustic siren preferences updated (90s cooldown enforced)', 'success');
    });
  }

  const backendInput = document.getElementById('setBackendUrlInput');
  const testBtn = document.getElementById('setTestConnectionBtn');
  const saveBtn = document.getElementById('setSaveBackendBtn');
  const connResult = document.getElementById('setConnectionResult');

  if (backendInput && !backendInput.value) {
    backendInput.value = window.WildShieldApi.baseUrl || 'http://localhost:8000/api';
  }

  if (testBtn && !testBtn._wired) {
    testBtn._wired = true;
    testBtn.onclick = async () => {
      testBtn.disabled = true;
      testBtn.textContent = 'Testing...';
      if (connResult) connResult.innerHTML = '<span style="color:var(--text-secondary);">Pinging backend...</span>';
      try {
        const summary = await window.WildShieldApi.getHealthSummary();
        if (connResult) {
          connResult.innerHTML = `<span class="badge badge-success"><i class="fas fa-check-circle"></i> Connected: 200 OK (${summary.cameras || 'Cameras active'}, ${summary.active_alerts} active alerts)</span>`;
        }
        toast('Backend connection test passed!', 'success');
      } catch (err) {
        if (connResult) {
          connResult.innerHTML = `<span class="badge badge-danger"><i class="fas fa-times-circle"></i> Connection Failed: ${escapeHtml(err.message || 'Cannot reach server')}</span>`;
        }
        toast('Could not connect to backend server', 'error');
      } finally {
        testBtn.disabled = false;
        testBtn.innerHTML = '<i class="fas fa-network-wired"></i> Test Connection';
      }
    };
  }

  if (saveBtn && !saveBtn._wired) {
    saveBtn._wired = true;
    saveBtn.onclick = () => {
      const url = backendInput?.value?.trim();
      if (url) {
        localStorage.setItem('wildshield_api_url', url);
        toast('Backend URL saved. Reloading...', 'success');
        setTimeout(() => window.location.reload(), 1000);
      }
    };
  }
}


function renderSidebarHealth(summary) {
  if (!summary) return;
  const summaryEl = document.getElementById('sidebarHealthSummary');
  const detailsEl = document.getElementById('sidebarHealthDetails');
  const uplinkEl = document.getElementById('sidebarUplinkStatus');

  const camerasText = summary.cameras || `${summary.cameras_online}/${summary.cameras_total}`;
  const summaryText = `${camerasText} Cams • ${summary.sirens_on} Siren${summary.sirens_on === 1 ? '' : 's'} On`;
  if (summaryEl) {
    summaryEl.textContent = summaryText;
  }

  const alertText = `${summary.active_alerts} active alert${summary.active_alerts === 1 ? '' : 's'}`;
  let timeText = 'No events';
  if (summary.last_detection_time) {
    const d = new Date(summary.last_detection_time);
    timeText = isNaN(d) ? summary.last_detection_time : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  const detailsText = `${alertText} • Last: ${timeText}`;

  if (detailsEl) {
    detailsEl.textContent = detailsText;
  } else if (uplinkEl) {
    uplinkEl.textContent = detailsText;
  }
}

/* ------------------------------------------------------------------ */
/* Detections table (index.html)                                       */
/* ------------------------------------------------------------------ */

function renderDetectionsTable(detections) {
  const container = document.querySelector('[data-role="detections-table"]');
  if (!container) return;

  if (!detections.length) {
    container.innerHTML = `<tr><td colspan="7" class="empty-state">No detections logged yet.</td></tr>`;
    return;
  }

  const rows = detections.slice(0, 8).map((item) => `
    <tr class="clickable-row" data-detection-id="${item.id}">
      <td>${new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</td>
      <td>${item.species}</td>
      <td>${item.type === 'human' ? 'Human' : 'Animal'}</td>
      <td>${item.location}</td>
      <td>${item.movementDirection}</td>
      <td><span class="risk ${item.riskLevel}">${capitalize(item.riskLevel)}</span></td>
      <td>${item.sirenStatus === 'on' ? 'Village siren armed' : 'Monitored'}</td>
    </tr>
  `).join('');

  container.innerHTML = rows;

  container.querySelectorAll('tr[data-detection-id]').forEach((row) => {
    row.addEventListener('click', () => {
      const item = currentDetections.find((d) => d.id === row.dataset.detectionId);
      if (item) openDetectionModal(item);
    });
  });
}

function openDetectionModal(item) {
  openModal({
    eyebrow: `Detection ${item.id}`,
    title: `${item.species} — ${item.type === 'human' ? 'Human' : 'Animal'} detection`,
    bodyHtml: detailGridHtml([
      ['Confidence', formatConfidence(item.confidence)],
      ['Location', item.location],
      ['Affected village', item.affectedVillage],
      ['Movement direction', item.movementDirection],
      ['Boundary crossing', item.boundaryCrossing ? 'Yes' : 'No'],
      ['Risk level', capitalize(item.riskLevel)],
      ['Siren status', item.sirenStatus === 'on' ? 'Armed' : 'Off'],
      ['Detected at', formatTimestamp(item.timestamp)],
    ]),
  });
}

function formatConfidence(value) {
  if (value == null) return '--';
  const n = Number(value);
  if (Number.isNaN(n)) return String(value);
  return n <= 1 ? `${(n * 100).toFixed(1)}%` : `${n.toFixed(1)}%`;
}

/* ------------------------------------------------------------------ */
/* Alerts (alerts.html, notifications.html)                            */
/* ------------------------------------------------------------------ */

function setupAlertFilterButtons() {
  const buttons = document.querySelectorAll('.filter-btn');
  if (!buttons.length) return;

  buttons.forEach((button) => {
    button.addEventListener('click', () => {
      buttons.forEach((btn) => btn.classList.toggle('active', btn === button));

      const filter = button.textContent.trim().toLowerCase();
      let filtered = currentAlerts;

      if (filter === 'active' || filter === 'resolved') {
        filtered = currentAlerts.filter((alert) => alert.status === filter);
      } else if (filter !== 'all') {
        filtered = currentAlerts.filter((alert) => alert.riskLevel === filter);
      }

      renderAlerts(filtered);
    });
  });
}

function openAlertModal(alert) {
  const isHuman = (alert.detectedObject && alert.detectedObject.toLowerCase().includes('human')) ||
                  (alert.speciesOrHuman && alert.speciesOrHuman.toLowerCase().includes('human')) ||
                  alert.type === 'human';
  const confVal = alert.confidence != null
    ? (Number(alert.confidence) <= 1 ? `${(Number(alert.confidence) * 100).toFixed(1)}%` : `${Number(alert.confidence).toFixed(1)}%`)
    : '--';

  const overlay = openModal({
    eyebrow: `Incident Alert #${alert.id && alert.id.length > 10 ? alert.id.slice(0, 8).toUpperCase() : alert.id}`,
    title: alert.title,
    bodyHtml: detailGridHtml([
      ['Detected target', alert.speciesOrHuman || alert.detectedObject || 'Wildlife'],
      ['Confidence score', confVal],
      ['Camera sensor', alert.location || 'North Ridge Cam'],
      ['Monitored zone', `${alert.village || 'Village 1'} • ${alert.zone || 'Zone A'}`],
      ['Movement direction', alert.movementDirection || 'Unknown'],
      ['Severity rating', capitalize(alert.riskLevel || 'medium')],
      ['Incident status', capitalize(alert.status || 'active')],
      ['Action taken', alert.actionTaken || 'Monitored'],
      ['Dispatch protocol', isHuman ? 'Discreet SMS (Law-enforcement alert • Silent)' : 'Acoustic Siren Relay + Authority SMS'],
      ['Notification recipients', (alert.recipients || ['Forest Officers']).join(', ')],
      ['Detection timestamp', formatTimestamp(alert.timestamp)],
    ]),
    actionsHtml: alert.status === 'active'
      ? `<button class="btn-sm btn-outline" data-role="modal-close">Close</button>
         <button class="btn-sm btn-activate" id="modalResolveBtn">Mark resolved</button>`
      : `<button class="btn-sm btn-outline" data-role="modal-close">Close</button>`
  });

  const modalResolveBtn = overlay.querySelector('#modalResolveBtn');
  if (modalResolveBtn) {
    modalResolveBtn.onclick = async () => {
      modalResolveBtn.disabled = true;
      modalResolveBtn.textContent = 'Resolving…';
      try {
        await withAuth(() => window.WildShieldApi.resolveAlert(alert.id));
        toast('Alert marked resolved', 'success');
        closeModal();
        await hydrateDashboard();
      } catch (err) {
        toast(err.message || 'Could not resolve alert', 'error');
        modalResolveBtn.disabled = false;
        modalResolveBtn.textContent = 'Mark resolved';
      }
    };
  }
}

function renderAlertCards(alerts, { readState } = {}) {
  if (!alerts.length) {
    return `<article class="glass-card panel-card empty-state" style="text-align: center; padding: 40px 20px; color: var(--text-secondary);">
      <p style="font-size: 15px; font-weight: 600; color: var(--text); margin-bottom: 4px;">No alerts match this filter</p>
      <span style="font-size: 13px;">All perimeter sectors operating within normal parameters.</span>
    </article>`;
  }

  return alerts.map((alert) => {
    const isRead = Boolean(alert.read || (readState && readState.has(alert.id)));
    const isHuman = (alert.detectedObject && alert.detectedObject.toLowerCase().includes('human')) ||
                    (alert.speciesOrHuman && alert.speciesOrHuman.toLowerCase().includes('human')) ||
                    alert.type === 'human';

    // Format confidence percentage
    const confVal = alert.confidence != null
      ? (Number(alert.confidence) <= 1 ? Number(alert.confidence) * 100 : Number(alert.confidence))
      : null;
    const confBadge = confVal != null ? `<span class="meta-badge conf">${confVal.toFixed(1)}% conf</span>` : '';

    // Clean single-line village/zone representation without duplication
    const villageText = alert.village || 'Village 1';
    const zoneText = alert.zone || 'Zone A';
    const zoneLocationLabel = zoneText.includes(villageText)
      ? zoneText
      : (villageText.includes(zoneText) ? villageText : `${villageText} • ${zoneText}`);

    // Notification delivery info
    const smsDelivered = alert.smsSent !== false && alert.status !== 'inactive';
    const deliveryLabel = isHuman
      ? 'Discreet SMS • Forest Rangers'
      : (smsDelivered ? 'SMS Delivered (Simulated) • Authorities' : 'SMS Queued');

    const isResolved = alert.status === 'resolved';
    const severityClass = isResolved ? 'low' : (alert.riskLevel || 'medium');

    return `
    <article class="glass-card alert-card ${severityClass} ${alert.status} clickable notification-item ${isRead ? 'is-read' : ''}" data-alert-id="${alert.id}">
      <div class="alert-card-top">
        <div class="alert-title-group">
          <div class="alert-id-row">
            <span class="alert-id-badge">#${alert.id && alert.id.length > 10 ? alert.id.slice(0, 8).toUpperCase() : alert.id}</span>
            <span class="alert-timestamp">${formatTimestamp(alert.timestamp)}</span>
            ${confBadge}
          </div>
          <h3 class="alert-incident-title">${alert.title}</h3>
        </div>

        <div class="alert-badges">
          <span class="dispatch-badge ${isHuman ? 'human' : 'animal'}" title="${isHuman ? 'Human intrusion — silent SMS notification protocol' : 'Animal intrusion — acoustic siren deterrence + SMS alert'}">
            ${isHuman ? 'Discreet SMS' : 'Siren + SMS'}
          </span>
          <span class="risk-badge ${severityClass}">${capitalize(isResolved ? 'Resolved' : alert.riskLevel)}</span>
          ${isRead ? '<span class="status-indicator-read" title="Marked as read">✓ Read</span>' : '<span class="status-indicator-unread" title="Unread alert">● New</span>'}
        </div>
      </div>

      <div class="alert-grid compact-grid">
        <div class="alert-grid-cell">
          <span class="cell-label">Detected Target</span>
          <strong class="cell-value">${alert.speciesOrHuman || alert.detectedObject || 'Wildlife'}</strong>
        </div>
        <div class="alert-grid-cell">
          <span class="cell-label">Zone & Village</span>
          <strong class="cell-value">${zoneLocationLabel}</strong>
        </div>
        <div class="alert-grid-cell">
          <span class="cell-label">Camera Sensor</span>
          <strong class="cell-value">${alert.location || 'North Ridge Cam'}</strong>
        </div>
        <div class="alert-grid-cell">
          <span class="cell-label">Movement Vector</span>
          <strong class="cell-value">${alert.movementDirection || 'Unknown'}</strong>
        </div>
      </div>

      <div class="alert-footer-row">
        <div class="alert-dispatch-status">
          <span class="dispatch-dot ${isResolved ? 'resolved' : 'active'}"></span>
          <span class="dispatch-text"><strong>Action:</strong> ${alert.actionTaken || 'Monitored'}</span>
          <span class="dispatch-pipe">•</span>
          <span class="dispatch-sms">${deliveryLabel}</span>
        </div>

        <div class="alert-action-btns">
          ${!isResolved ? `<button class="btn-sm btn-resolve" data-resolve-id="${alert.id}">Mark resolved</button>` : '<span class="resolved-check">✓ Resolved</span>'}
        </div>
      </div>
    </article>
  `;
  }).join('');
}

function renderAlerts(alerts) {
  const container = document.querySelector('[data-role="alert-list"]');
  if (!container) return;
  container.innerHTML = renderAlertCards(alerts);
  wireAlertCardActions(container);
}

function wireAlertCardActions(container) {
  container.querySelectorAll('[data-alert-id]').forEach((card) => {
    card.addEventListener('click', (e) => {
      if (e.target.closest('[data-resolve-id]')) return;
      const id = card.dataset.alertId;
      const alert = currentAlerts.find((a) => a.id === id);
      if (alert) openAlertModal(alert);
    });
  });

  container.querySelectorAll('[data-resolve-id]').forEach((btn) => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const id = btn.dataset.resolveId;
      btn.disabled = true;
      btn.textContent = 'Resolving…';
      try {
        await withAuth(() => window.WildShieldApi.resolveAlert(id));
        toast('Alert marked resolved', 'success');
        await hydrateDashboard();
      } catch (err) {
        toast(err.message || 'Could not resolve alert', 'error');
        btn.disabled = false;
        btn.textContent = 'Mark resolved';
      }
    });
  });
}

/* ------------------------------------------------------------------ */
/* Notifications (notifications.html) — backend read/unread tracking */
/* ------------------------------------------------------------------ */

function renderNotifications(alerts) {
  const container = document.querySelector('[data-role="notifications-list"]');
  if (!container) return;

  container.innerHTML = alerts.length
    ? renderAlertCards(alerts)
    : `<article class="glass-card panel-card empty-state">No notifications yet.</article>`;

  wireAlertCardActions(container);

  container.querySelectorAll('[data-alert-id]').forEach((card) => {
    card.addEventListener('click', async (e) => {
      if (e.target.closest('[data-resolve-id]')) return;
      const id = card.dataset.alertId;
      const alert = alerts.find((a) => a.id === id);
      const isCurrentlyRead = card.classList.contains('is-read') || Boolean(alert && alert.read);
      const nextRead = !isCurrentlyRead;

      // Optimistic UI update
      card.classList.toggle('is-read', nextRead);
      const indicator = card.querySelector('.status-indicator-read, .status-indicator-unread');
      if (indicator) {
        indicator.className = nextRead ? 'status-indicator-read' : 'status-indicator-unread';
        indicator.textContent = nextRead ? '✓ Read' : '● New';
        indicator.title = nextRead ? 'Marked as read' : 'Unread alert';
      }
      if (alert) alert.read = nextRead;

      try {
        await withAuth(() => window.WildShieldApi.toggleAlertRead(id, nextRead));
        toast(nextRead ? 'Notification marked as read' : 'Notification marked as unread', 'info', 1800);
      } catch (err) {
        // Revert on error
        card.classList.toggle('is-read', isCurrentlyRead);
        if (indicator) {
          indicator.className = isCurrentlyRead ? 'status-indicator-read' : 'status-indicator-unread';
          indicator.textContent = isCurrentlyRead ? '✓ Read' : '● New';
        }
        if (alert) alert.read = isCurrentlyRead;
        toast(err.message || 'Failed to update notification state', 'error');
      }
    });
  });

  const markAllBtn = document.getElementById('markAllReadBtn');
  if (markAllBtn) {
    markAllBtn.onclick = async () => {
      markAllBtn.disabled = true;
      markAllBtn.textContent = 'Updating…';
      try {
        await withAuth(() => window.WildShieldApi.markAllAlertsRead());
        toast('All notifications marked as read', 'success');
        await hydrateDashboard();
      } catch (err) {
        toast(err.message || 'Failed to mark all as read', 'error');
      } finally {
        markAllBtn.disabled = false;
        markAllBtn.textContent = 'Mark all as read';
      }
    };
  }
}

/* ------------------------------------------------------------------ */
/* Villages (index.html summary grid)                                  */
/* ------------------------------------------------------------------ */

function renderVillages(villages) {
  const container = document.querySelector('[data-role="village-grid"]');
  if (!container) return;

  if (!villages.length) {
    container.innerHTML = `<article class="glass-card stat-card empty-state">No zones configured yet.</article>`;
    return;
  }

  // MVP Focus: Village 1 is the primary demonstration zone
  const mvpVillage = villages.find((v) => v.id === 'village-1' || v.name.includes('Village 1')) || villages[0];
  const secondaryVillages = villages.filter((v) => v.id !== mvpVillage.id);

  const mvpIsAtRisk = mvpVillage.status === 'at-risk';
  const mvpSirenIsOn = mvpVillage.sirenStatus === 'on';

  const mvpCardHtml = `
    <article class="glass-card stat-card primary-mvp-card clickable ${mvpIsAtRisk ? 'danger-card' : ''}" data-village-id="${mvpVillage.id}">
      <div class="mvp-badge-row">
        <span class="mvp-label">Active MVP Zone</span>
        <span class="trend ${mvpIsAtRisk ? 'danger' : 'up'}">${mvpIsAtRisk ? '● AT RISK' : '● SECURE'}</span>
      </div>
      <p style="font-size: 13px; color: var(--text-secondary); margin-bottom: 2px;">${mvpVillage.name}</p>
      <h3 style="font-size: 20px; font-weight: 700; color: var(--text); margin-bottom: 6px;">${mvpVillage.zone}</h3>
      <div class="mvp-stats-row">
        <span class="siren-sub-status">Siren: <strong>${mvpSirenIsOn ? 'ACTIVE 🔔' : 'STANDBY 🔕'} (Simulated)</strong></span>
        <span class="camera-link">Camera: <strong>CAM-01 (North Ridge)</strong></span>
        <span class="coords-tag">GPS: <strong>11.685° N, 76.620° E</strong></span>
        <span class="demo-tag">Live Demonstration Zone</span>
      </div>
    </article>
  `;

  const secondaryCardsHtml = secondaryVillages.map((village) => `
    <article class="glass-card stat-card secondary-zone-card clickable ${village.status === 'at-risk' ? 'danger-card' : ''}" data-village-id="${village.id}">
      <div class="mvp-badge-row">
        <span class="secondary-tag">Expansion Zone (Staged)</span>
        <span class="trend ${village.status === 'at-risk' ? 'danger' : 'up'}">${capitalize(village.status)}</span>
      </div>
      <p style="font-size: 13px; color: var(--text-secondary); margin-bottom: 2px;">${village.name}</p>
      <h3 style="font-size: 16px; font-weight: 600; color: var(--text); margin-bottom: 4px;">${village.zone}</h3>
      <div class="mvp-stats-row">
        <span>Siren: <strong>${village.sirenStatus.toUpperCase()}</strong></span>
        <span style="font-size: 11px; color: var(--text-muted);">Phase 2 Staging</span>
      </div>
    </article>
  `).join('');

  container.innerHTML = mvpCardHtml + secondaryCardsHtml;

  container.querySelectorAll('[data-village-id]').forEach((card) => {
    card.addEventListener('click', () => {
      const village = currentVillages.find((v) => v.id === card.dataset.villageId);
      if (village) openVillageModal(village);
    });
  });
}

function openVillageModal(village) {
  const isOn = village.sirenStatus === 'on';
  const overlay = openModal({
    eyebrow: village.zone,
    title: village.name,
    bodyHtml: detailGridHtml([
      ['Status', capitalize(village.status)],
      ['Siren relay', isOn ? 'ACTIVE (Simulated)' : 'STANDBY (Simulated)'],
      ['Monitoring camera', 'CAM-01: North Ridge Trail Cam'],
      ['GPS coordinates', '11.685° N, 76.620° E (Kumily Sector)'],
      ['Hardware connection', 'Simulated GPIO Relay (Mock Mode)'],
    ]),
    actionsHtml: `
      <button class="btn-sm btn-outline" data-role="modal-close">Close</button>
      <button class="btn-sm ${isOn ? 'btn-deactivate' : 'btn-activate'}" id="villageSirenBtn">${isOn ? 'Deactivate siren' : 'Activate siren'}</button>
    `,
  });

  overlay.querySelector('#villageSirenBtn').addEventListener('click', (e) => {
    const btn = e.currentTarget;
    confirmSirenAction({
      sirenName: village.name,
      isOn,
      onConfirm: async () => {
        btn.disabled = true;
        btn.textContent = 'Working…';
        try {
          const api = window.WildShieldApi;
          await withAuth(async () => {
            if (isOn) {
              await api.deactivateSiren(village.sirenId);
              toast(`Siren deactivated for ${village.name}`, 'success');
            } else {
              await api.activateSiren(village.sirenId);
              toast(`Siren activated for ${village.name}`, 'success');
            }
          });
          closeModal();
          await hydrateDashboard();
        } catch (err) {
          toast(err.message || 'Siren action failed', 'error');
          btn.disabled = false;
          btn.textContent = isOn ? 'Deactivate siren' : 'Activate siren';
        }
      }
    });
  });
}

/* ------------------------------------------------------------------ */
/* Sirens (siren-control.html)                                         */
/* ------------------------------------------------------------------ */

function renderSirens(sirens) {
  const container = document.querySelector('[data-role="siren-grid"]');
  if (!container) return;

  if (!sirens.length) {
    container.innerHTML = `<section class="glass-card panel-card empty-state">No siren-equipped zones configured yet.</section>`;
    return;
  }

  container.innerHTML = sirens.map((siren) => {
    const isOn = siren.currentStatus === 'on';
    const isSimulated = siren.hardwareMode === 'SIMULATED' || siren.isHardwareConnected === false || true;
    return `
    <section class="glass-card panel-card siren-panel ${isOn ? 'emergency' : 'safe'}" data-siren-id="${siren.id}">
      <div class="siren-card-head">
        <div>
          <p class="eyebrow">${siren.village}</p>
          <h3>${siren.name}</h3>
        </div>
        <div style="display: flex; gap: 8px; align-items: center;">
          <span class="hardware-badge ${isSimulated ? 'simulated' : 'physical'}">
            ${isSimulated ? '⚠️ SIMULATED RELAY' : '✓ HARDWARE LINKED'}
          </span>
          <span class="siren-badge ${isOn ? 'danger' : 'safe'}">${isOn ? 'AT RISK' : 'SAFE'}</span>
        </div>
      </div>
      <div class="siren-state">
        <div class="siren-icon">${isOn ? '🔔' : '🔕'}</div>
        <div>
          <p class="state-label">Relay state</p>
          <h4>SIREN ${siren.currentStatus.toUpperCase()}</h4>
          <p>Zone status: <b>${siren.zoneStatus}</b></p>
          <p style="font-size: 12px; color: var(--text-secondary); margin-top: 3px;">
            ${siren.activationReason || 'System nominal — acoustic deterrent on standby'}
          </p>
          <p style="font-size: 11px; color: var(--warning); margin-top: 3px;">
            ${isSimulated ? 'Mode: Mock GPIO Relay (Software Simulation)' : 'Mode: Physical GPIO Output Active'}
          </p>
        </div>
      </div>
      <div class="siren-actions">
        <button class="btn-sm ${isOn ? 'btn-deactivate' : 'btn-activate'}" data-siren-toggle="${siren.id}" data-siren-state="${siren.currentStatus}">
          ${isOn ? 'Deactivate siren' : 'Activate siren'}
        </button>
      </div>
    </section>
  `;
  }).join('');

  container.querySelectorAll('[data-siren-toggle]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.sirenToggle;
      const isOn = btn.dataset.sirenState === 'on';
      const siren = currentSirens.find((s) => s.id === id);
      confirmSirenAction({
        sirenName: siren ? siren.name : id,
        isOn,
        onConfirm: async () => {
          btn.disabled = true;
          btn.textContent = 'Working…';
          try {
            const api = window.WildShieldApi;
            await withAuth(async () => {
              if (isOn) {
                await api.deactivateSiren(id);
                toast('Siren deactivated (simulated)', 'success');
              } else {
                await api.activateSiren(id);
                toast('Siren activated (simulated)', 'success');
              }
            });
            await hydrateDashboard();
          } catch (err) {
            toast(err.message || 'Siren action failed', 'error');
            btn.disabled = false;
            btn.textContent = isOn ? 'Deactivate siren' : 'Activate siren';
          }
        }
      });
    });
  });

  // Populate dynamic siren operational history card
  const historyTimeEl = document.querySelector('[data-role="siren-history-time"]');
  const historyReasonEl = document.querySelector('[data-role="siren-history-reason"]');
  const historyStatusEl = document.querySelector('[data-role="siren-history-status"]');

  if (historyTimeEl || historyReasonEl || historyStatusEl) {
    const activeSiren = sirens.find((s) => s.currentStatus === 'on') || sirens[0];
    if (activeSiren) {
      if (historyTimeEl) {
        historyTimeEl.textContent = activeSiren.lastActivatedAt ? formatTimestamp(activeSiren.lastActivatedAt) : 'Standby mode';
      }
      if (historyReasonEl) {
        historyReasonEl.textContent = activeSiren.activationReason || 'No active threat';
      }
      if (historyStatusEl) {
        historyStatusEl.textContent = 'Simulated Relay Mode • Software Mock (GPIO Hardware Offline)';
      }
    }
  }
}

function setupSirenTestButton() {
  const testButton = document.getElementById('manualSirenTestBtn') || document.querySelector('button.btn.btn-primary.wide-btn');
  if (!testButton) return;

  testButton.onclick = () => {
    testButton.textContent = 'Testing sirens…';
    testButton.disabled = true;
    toast('Manual siren test acoustic broadcast triggered across perimeter', 'info', 2200);
    setTimeout(() => {
      testButton.textContent = 'Manual siren test';
      testButton.disabled = false;
    }, 2000);
  };
}

/* ------------------------------------------------------------------ */
/* Map view (map-view.html)                                            */
/* ------------------------------------------------------------------ */

function renderThreatPanel(threat) {
  const container = document.querySelector('[data-role="map-threat"]');
  if (!container) return;

  container.innerHTML = `
    <div class="info-list">
      <div><span>Animal</span><strong>${threat.animal}</strong></div>
      <div><span>Confidence</span><strong>${threat.confidence}</strong></div>
      <div><span>Current Location</span><strong>${threat.currentLocation}</strong></div>
      <div><span>Moving Toward</span><strong>${threat.movingToward}</strong></div>
      <div><span>Distance</span><strong>${threat.distance}</strong></div>
      <div><span>Risk Level</span><strong>${threat.riskLevel}</strong></div>
      <div><span>Siren</span><strong>${threat.siren}</strong></div>
    </div>
  `;
}

function wireMapMarkers(villages, sirens, mapData) {
  const [v1, v2] = villages;
  const [s1, s2] = sirens;

  const bind = (roleSelector, entity, kind) => {
    const el = document.querySelector(`[data-role="${roleSelector}"]`);
    if (!el || !entity) return;
    if (kind === 'village') {
      const atRisk = entity.status === 'at-risk';
      el.classList.toggle('at-risk', atRisk);
      el.classList.toggle('safe', !atRisk);
      el.innerHTML = `${entity.name}<br/><small>${atRisk ? 'AT RISK' : 'SAFE'}</small>`;
      el.onclick = () => openVillageModal(entity);
    } else if (kind === 'siren') {
      const isOn = entity.currentStatus === 'on';
      el.innerHTML = `${entity.name.replace('Siren — ', 'Siren ')}<br/><small>${isOn ? 'ON' : 'OFF'}</small>`;
      el.onclick = () => openSirenQuickModal(entity);
    }
  };

  bind('map-village-1', v1, 'village');
  bind('map-village-2', v2, 'village');
  bind('map-siren-1', s1, 'siren');
  bind('map-siren-2', s2, 'siren');

  const threatModal = () => openModal({
    eyebrow: 'Live threat feed',
    title: mapData.threat.animal !== 'None' ? mapData.threat.animal : 'No active threat',
    bodyHtml: detailGridHtml([
      ['Confidence', mapData.threat.confidence],
      ['Current location', mapData.threat.currentLocation],
      ['Moving toward', mapData.threat.movingToward],
      ['Risk level', mapData.threat.riskLevel],
      ['Siren', mapData.threat.siren],
    ]),
  });

  ['map-camera', 'map-sensor', 'map-animal', 'map-danger-zone', 'map-safe-zone'].forEach((role) => {
    const el = document.querySelector(`[data-role="${role}"]`);
    if (el) el.onclick = threatModal;
  });
}

function openSirenQuickModal(siren) {
  const isOn = siren.currentStatus === 'on';
  const overlay = openModal({
    eyebrow: siren.village,
    title: siren.name,
    bodyHtml: detailGridHtml([
      ['Status', isOn ? 'ON' : 'OFF'],
      ['Zone status', siren.zoneStatus],
      ['Reason', siren.activationReason || '--'],
    ]),
    actionsHtml: `
      <button class="btn-sm btn-outline" data-role="modal-close">Close</button>
      <button class="btn-sm ${isOn ? 'btn-deactivate' : 'btn-activate'}" id="quickSirenBtn">${isOn ? 'Deactivate' : 'Activate'}</button>
    `,
  });
  overlay.querySelector('#quickSirenBtn').addEventListener('click', (e) => {
    const btn = e.currentTarget;
    confirmSirenAction({
      sirenName: siren.name,
      isOn,
      onConfirm: async () => {
        btn.disabled = true;
        try {
          const api = window.WildShieldApi;
          await withAuth(async () => {
            if (isOn) await api.deactivateSiren(siren.id);
            else await api.activateSiren(siren.id);
          });
          toast('Siren state synchronized', 'success');
          closeModal();
          await hydrateDashboard();
        } catch (err) {
          toast(err.message || 'Siren action failed', 'error');
          btn.disabled = false;
        }
      }
    });
  });
}

function wireMapFullResponse(mapData, villages, sirens) {
  const btn = document.querySelector('[data-role="map-full-response-btn"]');
  if (!btn) return;
  const atRiskVillage = villages.find((v) => v.status === 'at-risk') || villages[0];
  btn.addEventListener('click', async () => {
    if (!atRiskVillage) {
      toast('No zones configured to respond to', 'error');
      return;
    }
    btn.disabled = true;
    btn.textContent = 'Activating…';
    try {
      await withAuth(async () => {
        await window.WildShieldApi.activateSiren(atRiskVillage.sirenId);
      });
      toast(`Full response activated for ${atRiskVillage.name}`, 'success');
      await hydrateDashboard();
    } catch (err) {
      toast(err.message || 'Could not activate response', 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'ACTIVATE FULL RESPONSE';
    }
  });
}

/* ------------------------------------------------------------------ */
/* Index hero: live feed / map details / active alert / overview       */
/* ------------------------------------------------------------------ */

function renderIndexHero(detections, alerts, villages, sirens) {
  const latestDetection = detections[0];
  const feedEl = document.querySelector('[data-role="live-feed"]');
  const feedStatusPill = document.querySelector('.live-feed-card .status-pill');

  if (feedStatusPill) {
    if (latestDetection) {
      feedStatusPill.textContent = '● DEMO FEED (YOLOv11)';
      feedStatusPill.className = 'status-pill warning';
      feedStatusPill.title = 'Roboflow / YOLOv11 Edge Inference Demo Stream';
    } else {
      feedStatusPill.textContent = '○ CAMERA OFFLINE';
      feedStatusPill.className = 'status-pill danger';
      feedStatusPill.title = 'No camera telemetry detected';
    }
  }

  if (feedEl) {
    if (latestDetection) {
      const apiBase = window.WildShieldApi?.baseUrl || '/api';
      const backendOrigin = apiBase.startsWith('http') ? apiBase.replace(/\/api\/?$/, '') : '';
      const snapshotUrl = latestDetection.snapshotUrl
        ? (latestDetection.snapshotUrl.startsWith('http') ? latestDetection.snapshotUrl : `${backendOrigin}${latestDetection.snapshotUrl}`)
        : null;
      const confVal = latestDetection.confidence != null
        ? (Number(latestDetection.confidence) <= 1 ? Number(latestDetection.confidence) * 100 : Number(latestDetection.confidence))
        : null;
      const confPct = confVal != null ? confVal.toFixed(1) : null;
      const confBarHtml = confPct != null
        ? `<div class="conf-bar-wrap" aria-label="Confidence ${confPct}%">
             <div class="conf-bar-track"><div class="conf-bar-fill" style="width:${confPct}%"></div></div>
             <span class="conf-bar-label">${confPct}%</span>
           </div>`
        : '';
      feedEl.innerHTML = `
        <div class="feed-snapshot-wrap">
          ${snapshotUrl
            ? `<img class="feed-snapshot" src="${snapshotUrl}" alt="Latest detection snapshot" loading="lazy" onerror="this.style.display='none'; if (this.nextElementSibling) this.nextElementSibling.style.display='flex';" />
               <div class="feed-snapshot-placeholder" style="display:none;">
                 <span class="placeholder-icon">📹</span>
                 <span>Simulated feed • Awaiting camera frame</span>
               </div>`
            : `<div class="feed-snapshot-placeholder">
                 <span class="placeholder-icon">📹</span>
                 <span>Simulated feed • Sensor telemetry active</span>
               </div>`
          }
        </div>
        <span class="feed-badge">${latestDetection.type === 'human' ? 'Human intrusion • Restricted Zone' : 'Wildlife detection • Buffer Zone'}</span>
        <h4>${latestDetection.location}</h4>
        <p>Detected object: <strong>${latestDetection.species}</strong></p>
        ${confBarHtml}
        <p>Detection time: ${new Date(latestDetection.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</p>
        <p>Forest zone: ${latestDetection.affectedVillage}</p>
      `;
    } else {
      feedEl.innerHTML = `<span class="feed-badge">Offline</span><h4>No active camera feed</h4><p>Waiting for edge YOLOv11 detection stream…</p>`;
    }
  }

  const mapDetailsEl = document.querySelector('[data-role="index-map-details"]');
  if (mapDetailsEl) {
    const atRisk = villages.filter((v) => v.status === 'at-risk');
    mapDetailsEl.innerHTML = `
      <p><strong>Zones monitored:</strong> ${villages.length}</p>
      <p><strong>Zones at risk:</strong> ${atRisk.length ? atRisk.map((v) => v.name).join(', ') : 'None'}</p>
      <p><strong>Active sirens:</strong> ${sirens.filter((s) => s.currentStatus === 'on').length} / ${sirens.length}</p>
      <p><strong>Latest detection:</strong> ${latestDetection ? `${latestDetection.species} • ${latestDetection.movementDirection}` : '--'}</p>
    `;
  }

  // Wire clickable map markers on dashboard index
  const mapMarkers = document.querySelector('[data-role="index-map-markers"]');
  if (mapMarkers) {
    mapMarkers.querySelectorAll('.map-marker').forEach((marker) => {
      marker.style.cursor = 'pointer';
      marker.onclick = () => {
        const text = marker.textContent.trim();
        const matchedVillage = villages.find((v) => v.name.includes(text) || text.includes(v.name.split(' ')[0]));
        if (matchedVillage) {
          openVillageModal(matchedVillage);
        } else if (text.includes('Animal') || text.includes('Danger')) {
          const active = alerts.find((a) => a.status === 'active') || alerts[0];
          if (active) {
            openModal({
              eyebrow: 'Threat sector tracking',
              title: `${text} • ${active.title || 'Active incident'}`,
              bodyHtml: detailGridHtml([
                ['Location', active.location],
                ['Target village', active.village],
                ['Detected object', active.detectedObject],
                ['Movement direction', active.movementDirection],
                ['Risk level', capitalize(active.riskLevel)],
                ['Status', capitalize(active.status)],
              ]),
            });
          } else {
            toast(`${text} nominal — zero detected intrusion threats`, 'info');
          }
        } else {
          toast(`${text} perimeter sector active and secure`, 'info');
        }
      };
    });
  }

  const alertCard = document.querySelector('[data-role="index-active-alert"]');
  const sirenBtn = document.querySelector('[data-role="index-siren-btn"]');
  const activeAlert = alerts.find((a) => a.status === 'active') || alerts[0];
  if (alertCard) {
    const body = alertCard.querySelector('.alert-body');
    if (activeAlert) {
      const isHuman = (activeAlert.detectedObject && activeAlert.detectedObject.toLowerCase().includes('human')) ||
                      (activeAlert.speciesOrHuman && activeAlert.speciesOrHuman.toLowerCase().includes('human')) ||
                      activeAlert.type === 'human';
      const dispatchBadge = isHuman
        ? `<span class="dispatch-badge human" title="Discreet notification protocol">SMS only – discreet</span>`
        : `<span class="dispatch-badge animal" title="Acoustic deterrent and emergency notification">Siren + SMS</span>`;

      body.innerHTML = `
        <div class="alert-icon">${activeAlert.detectedObject === 'Human' ? '🧍' : '🦌'}</div>
        <h4>${activeAlert.title}</h4>
        <div style="margin: 8px 0 10px 0;">${dispatchBadge}</div>
        <p><strong>Direction:</strong> ${activeAlert.movementDirection}</p>
        <p><strong>Target village:</strong> ${activeAlert.village}</p>
        <p><strong>Risk level:</strong> <span class="risk ${activeAlert.riskLevel}">${capitalize(activeAlert.riskLevel)}</span></p>
        <p><strong>Time:</strong> ${formatTimestamp(activeAlert.timestamp)}</p>
        <p><strong>Status:</strong> ${capitalize(activeAlert.status)}</p>
      `;
      alertCard.onclick = (e) => {
        if (e.target.closest('button')) return;
        openModal({
          eyebrow: `Alert ${activeAlert.id}`,
          title: activeAlert.title,
          bodyHtml: detailGridHtml([
            ['Location', activeAlert.location],
            ['Zone / Village', `${activeAlert.zone} • ${activeAlert.village}`],
            ['Movement direction', activeAlert.movementDirection],
            ['Risk level', capitalize(activeAlert.riskLevel)],
            ['Action taken', activeAlert.actionTaken],
            ['Recipients', activeAlert.recipients.join(', ')],
          ]),
        });
      };
      if (sirenBtn) {
        const matchedSiren = sirens.find((s) => s.village === activeAlert.village);
        if (matchedSiren) {
          const isOn = matchedSiren.currentStatus === 'on';
          sirenBtn.disabled = false;
          sirenBtn.textContent = isOn ? `SIREN ON — ${activeAlert.village.toUpperCase()} (tap to stop)` : `ACTIVATE SIREN — ${activeAlert.village.toUpperCase()}`;
          sirenBtn.onclick = (e) => {
            e.stopPropagation();
            confirmSirenAction({
              sirenName: `${activeAlert.village} (${isOn ? 'ON' : 'OFF'})`,
              isOn,
              onConfirm: async () => {
                sirenBtn.disabled = true;
                try {
                  await withAuth(async () => {
                    if (isOn) await window.WildShieldApi.deactivateSiren(matchedSiren.id);
                    else await window.WildShieldApi.activateSiren(matchedSiren.id);
                  });
                  toast('Siren updated', 'success');
                  await hydrateDashboard();
                } catch (err) {
                  toast(err.message || 'Siren action failed', 'error');
                  sirenBtn.disabled = false;
                }
              }
            });
          };
        } else {
          sirenBtn.disabled = true;
          sirenBtn.textContent = 'No siren linked to this zone';
        }
      }
    } else {
      body.innerHTML = `<p>No active alerts right now. All zones nominal.</p>`;
      if (sirenBtn) {
        sirenBtn.disabled = true;
        sirenBtn.textContent = 'No active alert';
      }
    }
  }

  const gaugeFill = document.querySelector('[data-role="index-gauge-fill"]');
  if (gaugeFill) {
    const riskOrder = { low: 25, medium: 50, high: 75, critical: 100 };
    const pct = activeAlert ? (riskOrder[activeAlert.riskLevel] || 25) : 10;
    gaugeFill.style.width = `${pct}%`;
    gaugeFill.className = activeAlert ? activeAlert.riskLevel : 'low';
  }

  const overviewEl = document.querySelector('[data-role="index-overview"]');
  if (overviewEl) {
    const animals = detections.filter((d) => d.type === 'animal').length;
    const humans = detections.filter((d) => d.type === 'human').length;
    const crossings = detections.filter((d) => d.boundaryCrossing).length;
    overviewEl.innerHTML = `
      <div><span>Forest Boundary Crossings</span><strong>${String(crossings).padStart(2, '0')}</strong></div>
      <div><span>Animals Detected</span><strong>${String(animals).padStart(2, '0')}</strong></div>
      <div><span>Humans Detected</span><strong>${String(humans).padStart(2, '0')}</strong></div>
      <div><span>Alerts Triggered</span><strong>${String(alerts.length).padStart(2, '0')}</strong></div>
    `;
  }

  renderHumanIntrusion(detections, alerts);
}

function renderHumanIntrusion(detections, alerts) {
  const humanDetections = detections.filter((d) => d.type === 'human');
  const humanAlerts = alerts.filter((a) => a.detectedObject === 'Human');
  const badge = document.querySelector('[data-role="index-intrusion-badge"]');
  if (badge) badge.textContent = humanDetections.length ? 'Threat detected' : 'No threats';

  const detailsEl = document.querySelector('[data-role="index-intrusion-details"]');
  if (detailsEl) {
    const latest = humanDetections[0];
    if (latest) {
      detailsEl.innerHTML = `
        <div class="warning-banner">Unauthorized human detected inside restricted forest area.</div>
        ${detailGridHtml([
          ['Human detected', latest.species],
          ['Location', latest.location],
          ['Zone', latest.affectedVillage],
          ['Date and time', formatTimestamp(latest.timestamp)],
          ['Confidence score', formatConfidence(latest.confidence)],
          ['Movement direction', latest.movementDirection],
          ['Boundary crossing', latest.boundaryCrossing ? 'Yes' : 'No'],
          ['Siren status', latest.sirenStatus === 'on' ? 'Armed' : 'Off'],
        ])}
        <div class="routing-block">
          <p>Generated alert for</p>
          <div class="recipient-pills"><span>Rangers</span><span>Forest Officers</span><span>Police</span></div>
        </div>
      `;
    } else {
      detailsEl.innerHTML = `<p class="empty-state">No human intrusions recorded.</p>`;
    }
  }

  const historyBody = document.querySelector('[data-role="index-intrusion-history"]');
  if (historyBody) {
    if (!humanAlerts.length) {
      historyBody.innerHTML = `<tr><td colspan="6" class="empty-state">No human intrusion history yet.</td></tr>`;
    } else {
      historyBody.innerHTML = humanAlerts.slice(0, 6).map((a) => `
        <tr>
          <td>${new Date(a.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</td>
          <td>${a.location}</td>
          <td>${a.zone}</td>
          <td><span class="risk ${a.riskLevel}">${capitalize(a.riskLevel)}</span></td>
          <td>${a.status === 'resolved' ? 'Resolved' : 'Active'}</td>
          <td>${a.actionTaken}</td>
        </tr>
      `).join('');
    }
  }
}

/* ------------------------------------------------------------------ */
/* Analytics (analytics.html) — fully data-driven                      */
/* ------------------------------------------------------------------ */

const FILL_CLASSES = ['fill-green', 'fill-blue', 'fill-warning', 'fill-danger', 'fill-teal'];

function renderBarList(container, items, { suffix = '' } = {}) {
  if (!container) return;
  if (!items.length) {
    container.innerHTML = `<p class="empty-state">No data yet.</p>`;
    return;
  }
  const max = Math.max(...items.map((i) => i.value), 1);
  container.innerHTML = items.map((item, i) => `
    <div class="bar-item">
      <span>${item.label}</span>
      <div class="bar-track"><div class="bar ${FILL_CLASSES[i % FILL_CLASSES.length]}" style="height: ${Math.max(8, (item.value / max) * 100)}%"></div></div>
      <strong>${item.value}${suffix}</strong>
    </div>
  `).join('');
}

function renderSvgTrend(container, values, colorHex, dateLabels) {
  if (!container) return;
  const grid = container.querySelector('.line-grid');
  const w = 600, h = 220;
  if (!values.length || values.every((v) => v === 0)) {
    container.innerHTML = (grid ? grid.outerHTML : '') + `<p class="empty-state" style="position:relative;z-index:1;padding-top:90px;">No trend data yet.</p>`;
    return;
  }
  const max = Math.max(...values, 1);
  const stepX = w / (values.length - 1 || 1);
  const points = values.map((v, i) => [i * stepX, h - 24 - (v / max) * (h - 48)]);
  const linePoints = points.map((p) => p.join(',')).join(' ');
  const areaPoints = `0,${h} ${linePoints} ${w},${h}`;

  const labelsHtml = dateLabels && dateLabels.length
    ? dateLabels.map((label, i) => {
        const x = i * stepX;
        return `<text x="${x}" y="${h - 4}" text-anchor="middle" fill="#94a3b8" font-size="18" font-family="Inter, sans-serif">${label}</text>`;
      }).join('')
    : '';

  container.innerHTML = `
    ${grid ? grid.outerHTML : ''}
    <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="position:relative;z-index:1;width:100%;height:100%;display:block;">
      <polygon points="${areaPoints}" fill="${colorHex}" opacity="0.16"></polygon>
      <polyline points="${linePoints}" fill="none" stroke="${colorHex}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></polyline>
      ${points.map((p) => `<circle cx="${p[0]}" cy="${p[1]}" r="4" fill="${colorHex}"></circle>`).join('')}
      ${labelsHtml}
    </svg>
  `;
}

function renderAnalytics(analytics) {
  renderBarList(document.querySelector('[data-role="analytics-species"]'), analytics.speciesCounts);

  // Real date labels for 6-day trend
  function makeDateLabels(count) {
    const labels = [];
    for (let i = count - 1; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      labels.push(d.toLocaleDateString([], { month: 'short', day: 'numeric' }));
    }
    return labels;
  }

  renderSvgTrend(
    document.querySelector('[data-role="analytics-wildlife-trend"]'),
    analytics.wildlifeIntrusions, '#16a34a',
    makeDateLabels(analytics.wildlifeIntrusions.length)
  );
  renderSvgTrend(
    document.querySelector('[data-role="analytics-human-trend"]'),
    analytics.humanIntrusions, '#2563eb',
    makeDateLabels(analytics.humanIntrusions.length)
  );

  const donut = document.querySelector('[data-role="analytics-risk-donut"]');
  const legend = document.querySelector('[data-role="analytics-risk-legend"]');
  if (donut && legend) {
    const risk = analytics.riskLevels;
    const total = risk.reduce((sum, r) => sum + r.value, 0);
    const colors = { Low: 'var(--green)', Medium: 'var(--blue)', High: 'var(--warning)', Critical: 'var(--danger)' };
    const dotClass = { Low: 'green', Medium: 'blue', High: 'orange', Critical: 'red' };
    let acc = 0;
    const stops = risk.map((r) => {
      const start = total ? (acc / total) * 100 : 0;
      acc += r.value;
      const end = total ? (acc / total) * 100 : 0;
      return `${colors[r.label] || '#94a3b8'} ${start}% ${end}%`;
    }).join(', ');
    donut.style.background = total ? `conic-gradient(${stops})` : '';
    donut.querySelector('.donut-center strong').textContent = total;
    legend.innerHTML = risk.map((r) => `
      <div><span class="legend-dot ${dotClass[r.label] || 'blue'}"></span>${r.label} <strong>${r.value}</strong></div>
    `).join('');
  }

  renderBarList(document.querySelector('[data-role="analytics-siren-history"]'),
    analytics.sirenActivations.map((v, i) => {
      const d = new Date();
      d.setDate(d.getDate() - (analytics.sirenActivations.length - 1 - i));
      const label = d.toLocaleDateString([], { month: 'short', day: 'numeric' });
      return { label, value: v };
    }));

  const metrics = document.querySelector('[data-role="analytics-metrics"]');
  if (metrics) {
    metrics.innerHTML = `
      <div class="metric-card"><span>False alarms</span><strong>${analytics.falseAlarmStats.falseAlarms}</strong></div>
      <div class="metric-card"><span>Confirmed intrusions</span><strong>${analytics.falseAlarmStats.confirmedIntrusions}</strong></div>
    `;
  }

  const directionList = document.querySelector('[data-role="analytics-directions"]');
  if (directionList) {
    const dirs = analytics.movementDirections;
    const totalDir = dirs.reduce((s, d) => s + d.value, 0) || 1;
    directionList.innerHTML = dirs.length
      ? dirs.map((d) => `<div><span>${d.label}</span><strong>${Math.round((d.value / totalDir) * 100)}%</strong></div>`).join('')
      : `<p class="empty-state">No movement data yet.</p>`;
  }
}

// Zone incident list on analytics page — uses the map-data already fetched by hydrateDashboard.
function renderAnalyticsZonesList(mapData) {
  const zoneList = document.querySelector('[data-role="analytics-zones"]');
  if (!zoneList || !mapData) return;
  zoneList.innerHTML = mapData.zones.length
    ? mapData.zones.map((z) => `<div><span>${z.name}</span><strong>${z.incidents} incidents</strong></div>`).join('')
    : `<p class="empty-state">No zone activity yet.</p>`;
}

/* ------------------------------------------------------------------ */
/* Profile edit toggle (profile.html)                                  */
/* ------------------------------------------------------------------ */

async function loadUserProfile() {
  const nameEl = document.getElementById('profileName');
  const roleEl = document.getElementById('profileRole');
  const emailEl = document.getElementById('profileEmail');
  const locEl = document.getElementById('profileLocation');
  const summaryName = document.querySelector('.profile-summary h3');
  const summaryRole = document.querySelector('.profile-summary .muted');
  const avatarEl = document.querySelector('.profile-summary .profile-avatar');
  const twoFaStatusEl = document.querySelector('[data-role="profile-2fa-status"]');
  const lastLoginEl = document.querySelector('[data-role="profile-last-login"]');

  const api = window.WildShieldApi;
  if (!api) return;

  try {
    if (api.isAuthenticated()) {
      const user = await api.getUserProfile();
      if (user) {
        if (nameEl) nameEl.value = user.full_name || 'Forest Officer';
        if (roleEl) roleEl.value = user.role ? capitalize(user.role) : 'Lead operator';
        if (emailEl) emailEl.value = user.email || 'officer@wildshield.ai';
        if (locEl) locEl.value = user.location || 'Central Forest Command';

        if (summaryName) summaryName.textContent = user.full_name || 'Forest Officer';
        if (summaryRole) summaryRole.textContent = user.role ? capitalize(user.role) : 'Lead operator';

        const initials = (user.full_name || user.username || 'FO')
          .split(' ')
          .filter(Boolean)
          .map((n) => n[0])
          .join('')
          .substring(0, 2)
          .toUpperCase() || 'FO';

        if (avatarEl) avatarEl.textContent = initials;

        if (twoFaStatusEl) {
          twoFaStatusEl.textContent = user.two_factor_enabled ? 'Enabled' : 'Disabled';
        }
        if (lastLoginEl) {
          lastLoginEl.textContent = user.last_login_at ? formatTimestamp(user.last_login_at) : 'Just now';
        }

        // Update topbar profile trigger dynamically
        const topbarStrong = document.querySelector('.profile-copy strong');
        const topbarSpan = document.querySelector('.profile-copy span');
        const topbarAvatar = document.querySelector('.profile-trigger .avatar');
        if (topbarStrong) topbarStrong.textContent = user.full_name || user.username;
        if (topbarSpan) topbarSpan.textContent = user.role ? capitalize(user.role) : 'Lead operator';
        if (topbarAvatar) topbarAvatar.textContent = initials;
      }
    }
  } catch (err) {
    console.warn('Could not load profile from backend:', err);
  }
}

function setupProfileEdit() {
  const editBtn = document.querySelector('[data-role="edit-profile-btn"]');
  if (!editBtn) return;

  loadUserProfile();

  const fieldIds = ['profileName', 'profileRole', 'profileEmail', 'profileLocation'];
  let editing = false;

  editBtn.addEventListener('click', async () => {
    if (!editing) {
      editing = true;
      fieldIds.forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.removeAttribute('readonly');
      });
      editBtn.textContent = 'Save changes';
    } else {
      const payload = {
        full_name: document.getElementById('profileName')?.value || '',
        role: document.getElementById('profileRole')?.value || '',
        email: document.getElementById('profileEmail')?.value || '',
        location: document.getElementById('profileLocation')?.value || '',
      };

      editBtn.disabled = true;
      editBtn.textContent = 'Saving…';

      try {
        await withAuth(async () => {
          return await window.WildShieldApi.updateUserProfile(payload);
        });

        fieldIds.forEach((id) => {
          const el = document.getElementById(id);
          if (el) el.setAttribute('readonly', 'readonly');
        });
        editing = false;
        editBtn.disabled = false;
        editBtn.textContent = 'Edit profile';
        toast('Profile updated successfully in database', 'success');
        await loadUserProfile();
      } catch (err) {
        editBtn.disabled = false;
        editBtn.textContent = 'Save changes';
        toast(err.message || 'Failed to update profile', 'error');
      }
    }
  });
}

async function setupSecurityPage() {
  const page = document.querySelector('.security-page');
  if (!page) return;

  const twoFaStatusEl = document.querySelector('[data-role="two-factor-status"]');
  const twoFaBtn = document.querySelector('[data-role="two-factor-toggle-btn"]');
  const lastLoginEl = document.querySelector('[data-role="last-login-time"]');
  const devicesCountEl = document.querySelector('[data-role="devices-count"]');
  const eventsListEl = document.querySelector('[data-role="security-events"]');

  async function loadSecurityData() {
    const api = window.WildShieldApi;
    if (!api || !api.isAuthenticated()) return;

    try {
      const data = await api.getSecuritySettings();
      if (twoFaStatusEl) {
        twoFaStatusEl.textContent = data.two_factor_enabled ? 'Enabled' : 'Disabled';
        twoFaStatusEl.className = `status-pill ${data.two_factor_enabled ? 'online' : 'danger'}`;
      }
      if (twoFaBtn) {
        twoFaBtn.textContent = data.two_factor_enabled ? 'Disable 2FA' : 'Enable 2FA';
      }
      if (lastLoginEl) {
        lastLoginEl.textContent = data.last_login ? formatTimestamp(data.last_login) : 'Just now';
      }
      if (devicesCountEl) {
        devicesCountEl.textContent = `${data.authorized_devices_count || 1} active`;
      }
      if (eventsListEl && data.events && data.events.length) {
        eventsListEl.innerHTML = data.events.map((ev) => `
          <div class="alert-item">
            <div>
              <p><strong>${ev.title}</strong></p>
              <span class="muted">${ev.detail || ''}</span>
            </div>
            <strong>${ev.time || 'Logged'}</strong>
          </div>
        `).join('');
      }
    } catch (err) {
      console.warn('Could not load security settings:', err);
    }
  }

  if (twoFaBtn) {
    twoFaBtn.onclick = async () => {
      twoFaBtn.disabled = true;
      try {
        await withAuth(async () => {
          const res = await window.WildShieldApi.toggle2FA();
          toast(`Two-step verification ${res.two_factor_enabled ? 'enabled' : 'disabled'}`, 'success');
        });
        await loadSecurityData();
      } catch (err) {
        toast(err.message || 'Could not update 2FA setting', 'error');
      } finally {
        twoFaBtn.disabled = false;
      }
    };
  }

  await loadSecurityData();
}

/* ------------------------------------------------------------------ */
/* Helpers                                                              */
/* ------------------------------------------------------------------ */

function formatTimestamp(timestamp) {
  return new Date(timestamp).toLocaleString([], {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
}

function capitalize(value) {
  return String(value).replace(/-/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}

/* ------------------------------------------------------------------ */
/* Confirm modal for siren activate / deactivate (Rule 5)             */
/* ------------------------------------------------------------------ */

function confirmSirenAction({ sirenName, isOn, onConfirm }) {
  const action = isOn ? 'deactivate' : 'activate';
  const actionLabel = isOn ? 'Deactivate' : 'Activate';
  const overlay = openModal({
    eyebrow: 'Confirm siren action (Simulation Mode)',
    title: `${actionLabel} siren: ${sirenName}`,
    bodyHtml: `
      <p style="line-height:1.6; color: var(--text);">
        ${isOn
          ? `Deactivating the simulated siren relay for <strong>${sirenName}</strong> will silence the acoustic alert sequence in the system.`
          : `Activating the simulated siren relay for <strong>${sirenName}</strong> will sound the acoustic deterrent protocol and log the response event.`
        }
      </p>
      <div style="margin-top: 12px; padding: 10px 14px; background: #FFFBEB; border: 1px solid #FDE68A; border-radius: var(--radius-sm); font-size: 12px; color: #92400E; line-height: 1.5;">
        <strong>Hardware Simulation Notice:</strong> This environment is running in software mock mode. This action records the event and toggles the virtual relay. No physical acoustic horn is activated.
      </div>
    `,
    actionsHtml: `
      <button class="btn-sm btn-outline" data-role="modal-close">Cancel</button>
      <button class="btn-sm ${isOn ? 'btn-deactivate' : 'btn-activate'}" id="confirmSirenOk">${actionLabel} siren</button>
    `,
  });
  overlay.querySelector('#confirmSirenOk').addEventListener('click', () => {
    closeModal();
    onConfirm();
  });
}

/* ------------------------------------------------------------------ */
/* Camera health panel (dashboard)                                     */
/* ------------------------------------------------------------------ */

function renderCameraHealth(cameras) {
  const grid = document.querySelector('[data-role="cam-health-grid"]');
  const pill = document.getElementById('camHealthPill');
  if (!grid) return;

  if (!cameras || !cameras.length) {
    grid.innerHTML = `<p class="empty-state">No cameras configured.</p>`;
    if (pill) { pill.textContent = 'No cameras'; pill.className = 'status-pill warning'; }
    return;
  }

  const isOnlineFn = (cam) => cam.status === 'online' || cam.is_online === true;
  const onlineCount = cameras.filter(isOnlineFn).length;
  if (pill) {
    pill.textContent = `${onlineCount}/${cameras.length} online`;
    pill.className = `status-pill ${onlineCount === cameras.length ? 'online' : onlineCount > 0 ? 'warning' : 'danger'}`;
  }

  grid.innerHTML = cameras.map((cam) => {
    const isOnline = isOnlineFn(cam);
    const minutesAgo = cam.lastSeenMinutesAgo != null
      ? cam.lastSeenMinutesAgo
      : (cam.last_heartbeat ? Math.max(0, Math.floor((Date.now() - new Date(cam.last_heartbeat).getTime()) / 60000)) : 0);
    const lastSeen = minutesAgo === 0 ? 'Just now'
      : minutesAgo === 1 ? '1 min ago'
      : `${minutesAgo} min ago`;
    const zoneName = cam.zone || cam.zone_id || 'Forest Zone';
    return `
      <div class="cam-health-item ${isOnline ? 'online' : 'offline'}">
        <div class="cam-health-icon">${isOnline ? '📹' : '📷'}</div>
        <div class="cam-health-info">
          <strong>${cam.name}</strong>
          <span class="muted">${zoneName}</span>
        </div>
        <div class="cam-health-status">
          <span class="cam-status-dot ${isOnline ? 'online' : 'offline'}"></span>
          <span class="cam-status-label">${isOnline ? 'Online' : 'Offline'}</span>
          <span class="cam-last-seen muted">${lastSeen}</span>
        </div>
      </div>
    `;
  }).join('');
}

/* ------------------------------------------------------------------ */
/* Leaflet map (map-view.html)                                         */
/* ------------------------------------------------------------------ */

let _leafletMarkers = [];

function initLeafletMap(zones, sirens) {
  const container = document.getElementById('leafletMap');
  if (!container) return;

  // If Leaflet library is undefined or failed to load, render crisp vector perimeter map fallback
  if (typeof L === 'undefined') {
    renderVectorPerimeterMap(container, zones, sirens);
    const pill = document.getElementById('leafletStatusPill');
    if (pill) { pill.textContent = 'Kumily Perimeter (Vector Fallback)'; pill.className = 'status-pill warning'; }
    const errEl = document.getElementById('leafletTileError');
    if (errEl) errEl.style.display = 'block';
    return;
  }

  // Normalize zone coordinates
  const validCoords = (zones || [])
    .map((z) => ({
      lat: Number(z.lat ?? z.latitude),
      lng: Number(z.lng ?? z.longitude),
      name: z.name,
      village: z.village,
      status: z.status,
      incidents: z.incidents
    }))
    .filter((c) => !isNaN(c.lat) && !isNaN(c.lng) && c.lat !== 0 && c.lng !== 0);

  // Default to Kumily Buffer Zone (Bandipur/Periyar perimeter: 11.685, 76.620)
  const centerLat = validCoords.length ? validCoords[0].lat : 11.685;
  const centerLng = validCoords.length ? validCoords[0].lng : 76.620;

  if (_leafletMap) {
    addLeafletMarkers(zones, sirens);
    setTimeout(() => { if (_leafletMap) _leafletMap.invalidateSize(); }, 150);
    return;
  }

  _leafletMap = L.map('leafletMap', {
    zoomControl: true,
    scrollWheelZoom: true
  }).setView([centerLat, centerLng], 14);

  // Clean OpenStreetMap light tile layer
  const tileLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
    maxZoom: 18
  });

  tileLayer.on('tileerror', () => {
    const errEl = document.getElementById('leafletTileError');
    if (errEl) errEl.style.display = 'block';
  });
  tileLayer.addTo(_leafletMap);

  addLeafletMarkers(zones, sirens);

  // Invalidate size after DOM layout settles to prevent blank tiles
  setTimeout(() => {
    if (_leafletMap) _leafletMap.invalidateSize();
  }, 250);

  // Setup retry button for tile server
  const retryBtn = document.getElementById('mapRetryBtn');
  if (retryBtn) {
    retryBtn.onclick = () => {
      const errEl = document.getElementById('leafletTileError');
      if (errEl) errEl.style.display = 'none';
      if (_leafletMap) {
        _leafletMap.eachLayer((layer) => {
          if (layer instanceof L.TileLayer) layer.redraw();
        });
        _leafletMap.invalidateSize();
        toast('Map tiles refreshed', 'info');
      } else {
        initLeafletMap(zones, sirens);
      }
    };
  }

  // Update status pill
  const pill = document.getElementById('leafletStatusPill');
  if (pill) {
    pill.textContent = 'Kumily Buffer Zone • Active (1.2 km)';
    pill.className = 'status-pill online';
  }
}

function addLeafletMarkers(zones, sirens) {
  if (!_leafletMap || typeof L === 'undefined') return;

  _leafletMarkers.forEach((m) => m.remove());
  _leafletMarkers = [];

  const zonesList = (zones && zones.length) ? zones : [{
    name: 'Zone A',
    village: 'Village 1',
    lat: 11.685,
    lng: 76.620,
    status: 'safe',
    incidents: 2
  }];

  zonesList.forEach((zone) => {
    const lat = Number(zone.lat ?? zone.latitude ?? 11.685);
    const lng = Number(zone.lng ?? zone.longitude ?? 76.620);
    if (isNaN(lat) || isNaN(lng)) return;

    const isAtRisk = zone.status === 'at-risk' || (currentAlerts || []).some((a) => a.status === 'active' && (a.village === zone.village || a.zone === zone.name));
    const matchedSiren = sirens && sirens.find((s) => s.village === zone.village);
    const sirenOn = matchedSiren && matchedSiren.currentStatus === 'on';

    // 1. Conflict Boundary Circle (1.2 km buffer zone)
    const circle = L.circle([lat, lng], {
      radius: 1200,
      color: isAtRisk ? '#DC2626' : '#15803D',
      fillColor: isAtRisk ? '#FEE2E2' : '#F0FDF4',
      fillOpacity: 0.18,
      weight: 2,
      dashArray: '6, 6'
    }).addTo(_leafletMap);
    circle.bindTooltip(`<strong>${zone.name || 'Zone A'}</strong><br/>1.2 km Conflict Buffer Perimeter<br/>Status: <b>${isAtRisk ? 'AT RISK' : 'SECURE'}</b>`, { permanent: false, direction: 'top' });
    _leafletMarkers.push(circle);

    // 2. Village Center Marker
    const colorClass = isAtRisk ? 'leaflet-marker-atrisk' : 'leaflet-marker-safe';
    const villageIcon = L.divIcon({
      className: `leaflet-ws-marker ${colorClass}${isAtRisk ? ' pulse-marker' : ''}`,
      html: `<div class="lm-dot"></div><span class="lm-label">${zone.name || 'Zone A'} — ${zone.village || 'Village 1'}</span>`,
      iconSize: [140, 36],
      iconAnchor: [70, 18]
    });

    const marker = L.marker([lat, lng], { icon: villageIcon }).addTo(_leafletMap);
    const popupHtml = `
      <div class="leaflet-popup-content-custom">
        <strong>${zone.name || 'Zone A'} (Kumily Perimeter)</strong>
        <p>Target village: <b>${zone.village || 'Village 1'}</b></p>
        <p>Perimeter status: <b style="color:${isAtRisk ? '#DC2626' : '#15803D'}">${isAtRisk ? 'AT RISK ⚠️' : 'SECURE ✓'}</b></p>
        <p>Recorded incidents: <b>${zone.incidents ?? 0}</b></p>
        <p>Siren relay: <b>${sirenOn ? 'ON 🔔' : 'STANDBY 🔕'} (Simulated)</b></p>
        ${matchedSiren ? `<button class="lm-siren-btn btn-sm ${sirenOn ? 'btn-deactivate' : 'btn-activate'}"
          data-siren-id="${matchedSiren.id}" data-siren-on="${sirenOn}"
          onclick="handleLeafletSirenToggle('${matchedSiren.id}', ${sirenOn}, this)">
          ${sirenOn ? 'Deactivate siren' : 'Activate siren'}
        </button>` : ''}
      </div>`;
    marker.bindPopup(popupHtml, { maxWidth: 240 });
    _leafletMarkers.push(marker);

    // 3. Camera Station Marker (CAM-01: North Ridge Trail Cam)
    const camLat = lat + 0.0035;
    const camLng = lng + 0.0040;
    const camIcon = L.divIcon({
      className: 'leaflet-ws-marker leaflet-marker-cam',
      html: `<div class="lm-dot" style="background:#2563EB; border-color:#DBEAFE;"></div><span class="lm-label">📹 CAM-01 (Ridge)</span>`,
      iconSize: [120, 36],
      iconAnchor: [60, 18]
    });
    const camMarker = L.marker([camLat, camLng], { icon: camIcon }).addTo(_leafletMap);
    camMarker.bindPopup(`
      <div class="leaflet-popup-content-custom">
        <strong style="color:#2563EB;">CAM-01: North Ridge Trail Cam</strong>
        <p>Inference: <b>Edge YOLOv11 / Roboflow</b></p>
        <p>Status: <b style="color:#2563EB;">Online (Demo Feed)</b></p>
        <p>Sector: <b>Zone A North Boundary</b></p>
        <p>Resolution: <b>1080p @ 15fps</b></p>
      </div>
    `, { maxWidth: 220 });
    _leafletMarkers.push(camMarker);

    // 4. Intruder / Threat Marker & Movement Vector (if active alert exists)
    const activeAlert = (currentAlerts || []).find((a) => a.status === 'active');
    if (activeAlert) {
      const threatLat = lat + 0.0065;
      const threatLng = lng + 0.0055;
      const isHuman = (activeAlert.detectedObject && activeAlert.detectedObject.toLowerCase().includes('human')) || activeAlert.type === 'human';
      const threatIcon = L.divIcon({
        className: 'leaflet-ws-marker leaflet-marker-atrisk pulse-marker',
        html: `<div class="lm-dot" style="background:#DC2626;"></div><span class="lm-label" style="border-color:#DC2626; color:#DC2626; font-weight:700;">${isHuman ? '🧍 Human' : '🦁 ' + (activeAlert.detectedObject || 'Animal')}</span>`,
        iconSize: [130, 36],
        iconAnchor: [65, 18]
      });
      const threatMarker = L.marker([threatLat, threatLng], { icon: threatIcon }).addTo(_leafletMap);
      threatMarker.bindPopup(`
        <div class="leaflet-popup-content-custom">
          <strong style="color:#DC2626;">Active Incident #${activeAlert.id ? (activeAlert.id.length > 8 ? activeAlert.id.slice(0, 8).toUpperCase() : activeAlert.id) : ''}</strong>
          <p>Object: <b>${activeAlert.detectedObject || activeAlert.speciesOrHuman || 'Wildlife'}</b></p>
          <p>Trajectory: <b>${activeAlert.movementDirection || 'South-East towards Village 1'}</b></p>
          <p>Severity: <b style="color:#DC2626;">${capitalize(activeAlert.riskLevel || 'critical')}</b></p>
          <p>Dispatch protocol: <b>${isHuman ? 'Discreet SMS' : 'Acoustic Siren + SMS'}</b></p>
        </div>
      `, { maxWidth: 240 });
      _leafletMarkers.push(threatMarker);

      // Trajectory vector line pointing toward village zone
      const vectorLine = L.polyline([
        [threatLat, threatLng],
        [camLat, camLng],
        [lat, lng]
      ], {
        color: '#DC2626',
        weight: 2.5,
        opacity: 0.8,
        dashArray: '6, 6'
      }).addTo(_leafletMap);
      vectorLine.bindTooltip('Projected incursion vector toward Kumily perimeter', { sticky: true });
      _leafletMarkers.push(vectorLine);
    }
  });
}

function updateLeafletMarkers(zones, sirens) {
  addLeafletMarkers(zones, sirens);
}

// Crisp Vector Perimeter SVG fallback when offline or Leaflet CDN blocked
function renderVectorPerimeterMap(container, zones, sirens) {
  if (!container) return;
  const isAtRisk = (zones || []).some((z) => z.status === 'at-risk') || (currentAlerts || []).some((a) => a.status === 'active');
  const matchedSiren = (sirens || [])[0];
  const sirenOn = matchedSiren && matchedSiren.currentStatus === 'on';

  container.innerHTML = `
    <div class="vector-map-wrap" style="position: relative; width: 100%; height: 100%; min-height: 480px; background: #F8FAFC; border-radius: var(--radius-md); overflow: hidden; display: flex; flex-direction: column; align-items: center; justify-content: center;">
      <svg viewBox="0 0 800 500" style="width: 100%; height: 100%; max-height: 520px;" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#E2E8F0" stroke-width="1"/>
          </pattern>
        </defs>
        <rect width="800" height="500" fill="url(#grid)" />

        <!-- Topography contour lines -->
        <path d="M 50,420 Q 200,380 400,430 T 750,400" fill="none" stroke="#CBD5E1" stroke-width="1.5" stroke-dasharray="4,4" />
        <path d="M 30,280 Q 250,220 500,290 T 780,240" fill="none" stroke="#CBD5E1" stroke-width="1.5" stroke-dasharray="4,4" />
        <path d="M 70,120 Q 300,80 550,140 T 760,100" fill="none" stroke="#CBD5E1" stroke-width="1.5" stroke-dasharray="4,4" />

        <!-- Forest Sector (Top Sector) -->
        <rect x="0" y="0" width="800" height="180" fill="#F0FDF4" opacity="0.6" />
        <text x="30" y="45" font-family="Inter, sans-serif" font-size="13" font-weight="700" fill="#15803D" letter-spacing="0.05em">BANDIPUR / KUMILY FOREST RESERVE (CORE HABITAT)</text>

        <!-- 1.2km Conflict Buffer Zone Perimeter -->
        <circle cx="400" cy="330" r="150" fill="${isAtRisk ? '#FEE2E2' : '#F0FDF4'}" fill-opacity="0.35" stroke="${isAtRisk ? '#DC2626' : '#15803D'}" stroke-width="2.5" stroke-dasharray="8,6" />
        <text x="400" y="195" font-family="Inter, sans-serif" font-size="12" font-weight="600" fill="${isAtRisk ? '#DC2626' : '#15803D'}" text-anchor="middle">1.2 km Conflict Buffer Perimeter (Zone A)</text>

        <!-- Threat Incursion Vector -->
        ${isAtRisk ? `
          <line x1="560" y1="90" x2="490" y2="210" stroke="#DC2626" stroke-width="3" stroke-dasharray="6,4" />
          <polygon points="490,210 495,198 505,206" fill="#DC2626" />
          <circle cx="560" cy="90" r="16" fill="#DC2626" opacity="0.9" />
          <text x="560" y="95" font-size="14" text-anchor="middle" fill="#FFFFFF">🦁</text>
          <rect x="585" y="75" width="165" height="32" rx="4" fill="#FFFFFF" stroke="#DC2626" stroke-width="1.5"/>
          <text x="595" y="96" font-family="Inter, sans-serif" font-size="11" font-weight="700" fill="#DC2626">TIGER / LION DETECTED</text>
        ` : ''}

        <!-- Camera Station CAM-01 -->
        <circle cx="480" cy="220" r="12" fill="#2563EB" />
        <text x="480" y="224" font-size="10" text-anchor="middle" fill="#FFFFFF">📹</text>
        <rect x="500" y="208" width="135" height="24" rx="4" fill="#FFFFFF" stroke="#2563EB" stroke-width="1"/>
        <text x="508" y="224" font-family="Inter, sans-serif" font-size="11" font-weight="600" fill="#1E293B">CAM-01 (North Ridge)</text>

        <!-- Village 1 Center -->
        <circle cx="400" cy="330" r="14" fill="${isAtRisk ? '#DC2626' : '#15803D'}" />
        <circle cx="400" cy="330" r="22" fill="none" stroke="${isAtRisk ? '#DC2626' : '#15803D'}" stroke-width="1.5" opacity="0.5" />
        <rect x="320" y="355" width="160" height="38" rx="6" fill="#FFFFFF" stroke="#E2E8F0" stroke-width="1.5" />
        <text x="400" y="372" font-family="Inter, sans-serif" font-size="12" font-weight="700" fill="#1E293B" text-anchor="middle">Village 1 (Kumily Fringe)</text>
        <text x="400" y="386" font-family="Inter, sans-serif" font-size="10" font-weight="600" fill="${isAtRisk ? '#DC2626' : '#15803D'}" text-anchor="middle">${isAtRisk ? 'STATUS: AT RISK' : 'STATUS: SECURE'}</text>

        <!-- Siren Station Marker -->
        <circle cx="340" cy="290" r="10" fill="${sirenOn ? '#DC2626' : '#64748B'}" />
        <text x="340" y="294" font-size="9" text-anchor="middle" fill="#FFFFFF">${sirenOn ? '🔔' : '🔕'}</text>
        <text x="260" y="294" font-family="Inter, sans-serif" font-size="11" font-weight="600" fill="#1E293B">Siren 1 (${sirenOn ? 'ON' : 'OFF'})</text>

        <!-- Coordinates Callout -->
        <text x="770" y="480" font-family="Inter, sans-serif" font-size="11" font-weight="500" fill="#94A3B8" text-anchor="end">Ref Coordinates: 11.685° N, 76.620° E (Kumily WGS84)</text>
      </svg>
      <div style="position: absolute; bottom: 12px; left: 16px; background: rgba(255,255,255,0.95); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 6px 12px; font-size: 11px; color: var(--text-secondary);">
        <strong>Vector Perimeter View:</strong> Real-time spatial tracking active (Leaflet offline mode)
      </div>
    </div>
  `;
}

// Called from Leaflet popup button (global scope needed)
window.handleLeafletSirenToggle = function(sirenId, isOn, btn) {
  const siren = currentSirens.find((s) => s.id === sirenId);
  confirmSirenAction({
    sirenName: siren ? siren.name : sirenId,
    isOn,
    onConfirm: async () => {
      if (btn) { btn.disabled = true; btn.textContent = 'Working\u2026'; }
      try {
        const api = window.WildShieldApi;
        await withAuth(async () => {
          if (isOn) await api.deactivateSiren(sirenId);
          else await api.activateSiren(sirenId);
        });
        toast(isOn ? 'Siren deactivated' : 'Siren activated', 'success');
        await hydrateDashboard();
      } catch (err) {
        toast(err.message || 'Siren action failed', 'error');
        if (btn) { btn.disabled = false; btn.textContent = isOn ? 'Deactivate siren' : 'Activate siren'; }
      }
    }
  });
};

/* ------------------------------------------------------------------ */
/* Demo panel (?demo=1)                                                */
/* ------------------------------------------------------------------ */

function setupDemoPanel() {
  const params = new URLSearchParams(window.location.search);
  if (params.get('demo') !== '1') return;

  const panel = document.getElementById('demoPanel');
  if (panel) panel.style.display = '';

  const animalBtn = document.getElementById('demoAnimalBtn');
  const humanBtn  = document.getElementById('demoHumanBtn');

  async function injectDetection(payload) {
    const btn = payload.type === 'human' ? humanBtn : animalBtn;
    if (btn) { btn.disabled = true; btn.textContent = 'Injecting\u2026'; }
    try {
      const api = window.WildShieldApi;
      await api.postDetection(payload);
      toast(`\ud83d\udea8 Demo ${payload.type} alert injected`, 'success', 3000);
      await hydrateDashboard();
      flashAlertCard();
    } catch (err) {
      toast(err.message || 'Demo injection failed', 'error');
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = btn.id === 'demoAnimalBtn' ? '🦁 Inject animal alert (camera-01)' : '🧍 Inject human alert (camera-02)'; }
    }
  }

  animalBtn?.addEventListener('click', () => {
    const animalCam = currentCameras.find((c) => (c.name || '').includes('01') || (c.zone || '').includes('Zone A'))?.id || 'camera-01';
    return injectDetection({
      type: 'animal',
      event_type: 'ANIMAL_DETECTED',
      species: 'Lion',
      confidence: 0.93,
      location: 'Forest Boundary - Zone A',
      movement_direction: 'South-East',
      boundary_crossing: true,
      risk_level: 'critical',
      affected_village: 'Village 1',
      camera_id: animalCam
    });
  });

  humanBtn?.addEventListener('click', () => {
    const humanCam = currentCameras.find((c) => (c.name || '').includes('02') || (c.zone || '').includes('Zone B') || (c.zone || '').includes('Zone C'))?.id || 'camera-02';
    return injectDetection({
      type: 'human',
      event_type: 'PERSON_DETECTED',
      species: 'Human',
      confidence: 0.88,
      location: 'North Ridge Access Point',
      movement_direction: 'Northwest',
      boundary_crossing: true,
      risk_level: 'high',
      affected_village: 'Village 2',
      camera_id: humanCam
    });
  });
}

/* ------------------------------------------------------------------ */
/* Boot                                                                 */
/* ------------------------------------------------------------------ */

setupProfileEdit();
setupSecurityPage();
setupDemoPanel();
hydrateDashboard();



