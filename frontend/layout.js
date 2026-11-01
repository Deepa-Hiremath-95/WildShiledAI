/**
 * WildShield AI — Shared Layout Injector
 * Injects unified sidebar navigation and topbar command chrome across all pages.
 * Handles active link state dynamically based on window.location.pathname.
 */
(function () {
  let rawPath = window.location.pathname.split('/').filter(Boolean).pop() || 'index.html';
  if (!rawPath.endsWith('.html') && !rawPath.includes('.')) {
    rawPath += '.html';
  }
  const currentPath = rawPath;

  const pages = {
    'index.html': { title: 'WildShield AI Command Center', subtitle: 'Executive overview, active wildlife alerts & camera telemetry' },
    'live-monitoring.html': { title: 'Live Surveillance Monitoring', subtitle: 'Real-time camera feed, YOLOv11 bounding boxes & instant telemetry' },
    'villages.html': { title: 'Village Management', subtitle: 'Configurable demonstration villages, zones & emergency contacts' },
    'cameras.html': { title: 'Camera Network', subtitle: 'Edge camera nodes, heartbeat telemetry & monitoring zones' },
    'animal-monitoring.html': { title: 'Animal Intrusion Monitoring', subtitle: 'Species-specific detection tracking (Elephant, Leopard, Deer, Wild Boar)' },
    'human-monitoring.html': { title: 'Human Intrusion Monitoring', subtitle: 'Restricted-zone human tracking — Acoustic siren strictly disabled' },
    'alerts.html': { title: 'Incident & Alert Management', subtitle: 'Real-time threat triage, operator acknowledgement & incident resolution' },
    'analytics.html': { title: 'Analytics & Trends', subtitle: 'Detection frequency, species distribution, risk heatmaps & false-alarm audits' },
    'siren-control.html': { title: 'Siren & Acoustic Management', subtitle: 'Village-specific acoustic patterns, 90s cooldown monitor & emergency stop' },
    'settings.html': { title: 'System Settings', subtitle: 'Inference thresholds, cooldown parameters & notification routing' },
    'map-view.html': { title: 'Geospatial Map View', subtitle: 'GIS perimeter mapping, conflict buffer zones & intrusion vectors' },
    'profile.html': { title: 'Operator Profile', subtitle: 'Lead operator credentials and regional access' },
    'security.html': { title: 'Security Settings', subtitle: 'Authentication security, authorized devices & audit log' },
    'notifications.html': { title: 'System Notifications', subtitle: 'Live event stream and security audit notifications' }
  };

  const navSections = [
    {
      label: 'OPERATIONS',
      items: [
        {
          href: 'index.html',
          icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/></svg>',
          label: 'Overview'
        },
        {
          href: 'live-monitoring.html',
          icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg>',
          label: 'Live Monitoring'
        },
        {
          href: 'map-view.html',
          icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/><line x1="8" y1="2" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="22"/></svg>',
          label: 'Perimeter Map'
        }
      ]
    },
    {
      label: 'DETECTION & THREATS',
      items: [
        {
          href: 'animal-monitoring.html',
          icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>',
          label: 'Animal Monitoring'
        },
        {
          href: 'human-monitoring.html',
          icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
          label: 'Human Intrusion'
        },
        {
          href: 'alerts.html',
          icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
          label: 'Alert Management'
        },
        {
          href: 'siren-control.html',
          icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>',
          label: 'Siren Management'
        }
      ]
    },
    {
      label: 'INFRASTRUCTURE & DATA',
      items: [
        {
          href: 'villages.html',
          icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>',
          label: 'Villages & Zones'
        },
        {
          href: 'cameras.html',
          icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"/><line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/></svg>',
          label: 'Camera Network'
        },
        {
          href: 'analytics.html',
          icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>',
          label: 'Analytics'
        }
      ]
    },
    {
      label: 'SYSTEM',
      items: [
        {
          href: 'settings.html',
          icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
          label: 'System Settings'
        },
        {
          href: 'profile.html',
          icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
          label: 'Operator Profile'
        },
        {
          href: 'security.html',
          icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>',
          label: 'Security & 2FA'
        }
      ]
    }
  ];

  function buildSidebar() {
    let sectionsHtml = '';
    for (const section of navSections) {
      sectionsHtml += `<div class="nav-group-label">${section.label}</div>`;
      for (const item of section.items) {
        const isActive = item.href === currentPath || (currentPath === 'index.html' && item.href === 'index.html');
        sectionsHtml += `
          <a href="${item.href}" class="nav-item ${isActive ? 'active' : ''}">
            <span class="nav-icon" aria-hidden="true">${item.icon}</span>
            <span class="nav-label">${item.label}</span>
          </a>
        `;
      }
    }

    return `
      <aside class="sidebar" id="sidebar" aria-label="Main Navigation">
        <div class="sidebar-top">
          <div class="brand compact-brand">
            <div class="brand-mark" aria-label="WildShield AI logo">
              <svg width="36" height="36" viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-hidden="true">
                <rect width="36" height="36" rx="8" fill="#F0FDF4"/>
                <path d="M18 7L9 11V17C9 23 12.8 28.5 18 30C23.2 28.5 27 23 27 17V11L18 7Z" fill="#15803D" stroke="#15803D" stroke-width="1.2" stroke-linejoin="round"/>
                <path d="M14 18L17 21L22 15" stroke="#FFFFFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </div>
            <div class="brand-text">
              <h1>WildShield AI</h1>
              <p>Predict • Protect • Respond</p>
            </div>
          </div>
          <button class="icon-btn sidebar-toggle" id="sidebarToggle" aria-label="Toggle navigation">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
          </button>
        </div>

        <nav class="sidebar-nav" aria-label="Primary Navigation">
          ${sectionsHtml}
        </nav>

        <div class="sidebar-footer">
          <div class="status-card" id="sidebarStatusCard">
            <div class="status-card-header">
              <span class="status-card-dot"></span>
              <p>System Health</p>
            </div>
            <strong id="sidebarHealthSummary">Loading health…</strong>
            <span id="sidebarHealthDetails">Connecting to backend…</span>
          </div>
        </div>
      </aside>
      <div class="sidebar-backdrop" id="sidebarBackdrop"></div>
    `;
  }

  function buildTopbar() {
    const meta = pages[currentPath] || {
      title: 'WildShield AI Command Center',
      subtitle: 'Predict. Protect. Respond.'
    };

    return `
      <header class="topbar">
        <div class="topbar-left">
          <button class="icon-btn mobile-toggle" id="mobileToggle" aria-label="Open navigation">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
          </button>
          <div class="topbar-title">
            <h2>${meta.title}</h2>
            <p>${meta.subtitle}</p>
          </div>
        </div>

        <div class="topbar-right">
          <span class="ws-pill offline" id="wsStatusPill" title="WebSocket connection status">● OFFLINE</span>
          <div class="date-pill" id="currentDateTime">--</div>
          <div class="profile-menu">
            <button class="profile-trigger" id="profileTrigger" aria-expanded="false" aria-label="Operator user menu">
              <div class="avatar" aria-hidden="true">FO</div>
              <div class="profile-copy">
                <strong>Forest Officer</strong>
                <span>Lead operator</span>
              </div>
              <svg class="chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9"/></svg>
            </button>
            <div class="profile-dropdown" id="profileDropdown" role="menu">
              <a href="profile.html" role="menuitem">Profile</a>
              <a href="security.html" role="menuitem">Security</a>
              <a href="#" id="authActionLink" role="menuitem">Sign out</a>
            </div>
          </div>
        </div>
      </header>
    `;
  }

  function injectLayout() {
    if (document.getElementById('sidebar')) return;
    const shell = document.querySelector('.app-shell');
    if (!shell) return;
    const mainPanel = shell.querySelector('.main-panel');
    if (!mainPanel) return;

    // Inject sidebar and backdrop into app-shell before main-panel
    const tempContainer = document.createElement('div');
    tempContainer.innerHTML = buildSidebar();
    while (tempContainer.firstChild) {
      shell.insertBefore(tempContainer.firstChild, mainPanel);
    }

    // Inject topbar into main-panel before main
    const tempTopbar = document.createElement('div');
    tempTopbar.innerHTML = buildTopbar().trim();
    const topbarEl = tempTopbar.firstElementChild;
    mainPanel.insertBefore(topbarEl, mainPanel.firstElementChild);
  }

  if (document.querySelector('.app-shell')) {
    injectLayout();
  } else {
    document.addEventListener('DOMContentLoaded', injectLayout);
  }
})();
