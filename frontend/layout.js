/**
 * WildShield AI — Shared Layout Injector
 * Injects unified sidebar navigation and topbar command chrome across all pages.
 * Handles active link state dynamically based on window.location.pathname.
 */
(function () {
  const currentPath = window.location.pathname.split('/').filter(Boolean).pop() || 'index.html';

  const pages = {
    'index.html': { title: 'WildShield AI Command Center', subtitle: 'AI-Powered Early Warning System for Human–Wildlife Conflict Zones' },
    'map-view.html': { title: 'Map View', subtitle: 'Live wildlife intrusion & perimeter monitoring' },
    'alerts.html': { title: 'Alerts', subtitle: 'Real-time incident management & dispatch' },
    'siren-control.html': { title: 'Siren Control', subtitle: 'Intelligent zone-specific acoustic deterrence' },
    'analytics.html': { title: 'Analytics', subtitle: 'Operational insights, intrusion trends & detection statistics' },
    'notifications.html': { title: 'Notifications', subtitle: 'Live event stream and security audit notifications' },
    'profile.html': { title: 'Operator Profile', subtitle: 'Manage operator credentials and regional access' },
    'security.html': { title: 'Security Settings', subtitle: 'Authentication security, authorized devices & audit log' }
  };

  const navItems = [
    {
      href: 'index.html',
      icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/></svg>',
      label: 'Dashboard'
    },
    {
      href: 'map-view.html',
      icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/><line x1="8" y1="2" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="22"/></svg>',
      label: 'Map View'
    },
    {
      href: 'alerts.html',
      icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
      label: 'Alerts'
    },
    {
      href: 'siren-control.html',
      icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>',
      label: 'Siren Control'
    },
    {
      href: 'analytics.html',
      icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>',
      label: 'Analytics'
    }
  ];

  const secondaryNavItems = [
    {
      href: 'profile.html',
      icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>',
      label: 'Operator Profile'
    },
    {
      href: 'security.html',
      icon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>',
      label: 'Security Settings'
    }
  ];

  function buildSidebar() {
    const navHtml = navItems
      .map((item) => {
        const isActive = item.href === currentPath || (currentPath === 'index.html' && item.href === 'index.html');
        return `
          <a href="${item.href}" class="nav-item ${isActive ? 'active' : ''}">
            <span class="nav-icon" aria-hidden="true">${item.icon}</span>
            <span class="nav-label">${item.label}</span>
          </a>
        `;
      })
      .join('');

    const secondaryNavHtml = secondaryNavItems
      .map((item) => {
        const isActive = item.href === currentPath;
        return `
          <a href="${item.href}" class="nav-item secondary ${isActive ? 'active' : ''}">
            <span class="nav-icon" aria-hidden="true">${item.icon}</span>
            <span class="nav-label">${item.label}</span>
          </a>
        `;
      })
      .join('');

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
          <div class="nav-group-label">OPERATIONS</div>
          ${navHtml}

          <div class="nav-group-label" style="margin-top: 16px;">ADMINISTRATION</div>
          ${secondaryNavHtml}
        </nav>

        <div class="sidebar-footer">
          <div class="status-card" id="sidebarStatusCard">
            <div class="status-card-header">
              <span class="status-card-dot"></span>
              <p>System Health</p>
            </div>
            <strong id="sidebarHealthSummary">Loading health…</strong>
            <span id="sidebarHealthDetails">Connecting to sensor network…</span>
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
