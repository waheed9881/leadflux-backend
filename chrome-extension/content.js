/**
 * LinkedIn Scrape Data - LinkedIn Content Script
 */

(function () {
  'use strict';

  // Check if extension context is still valid
  function isExtensionContextValid() {
    try {
      if (!chrome || !chrome.runtime) return false;
      return !!chrome.runtime.id;
    } catch (error) {
      return false;
    }
  }

  // Get current API URL
  async function getApiUrl() {
    return new Promise((resolve) => {
      if (!isExtensionContextValid()) {
        resolve('http://localhost:8002');
        return;
      }
      try {
        chrome.storage.sync.get(['apiUrl'], (result) => {
          resolve(result.apiUrl || 'http://localhost:8002');
        });
      } catch (error) {
        resolve('http://localhost:8002');
      }
    });
  }

  function isProfilePage() {
    return window.location.pathname.match(/^\/in\/[^\/]+/);
  }

  function isSearchPage() {
    return window.location.pathname.includes('/search/') ||
      window.location.search.includes('keywords=') ||
      !!document.querySelector('.reusable-search__result-container, .entity-result');
  }

  // Extract name from profile
  function extractName() {
    const selectors = [
      'h1.text-heading-xlarge',
      '.pv-text-details__left-panel h1',
      'h1[class*="text-heading"]',
      '.top-card-layout__title',
      'main h1'
    ];
    for (const s of selectors) {
      const el = document.querySelector(s);
      if (el && el.textContent.trim()) {
        const full = el.textContent.trim();
        const parts = full.split(' ').filter(p => p);
        return { first: parts[0] || '', last: parts.slice(1).join(' ') || '', full };
      }
    }
    return null;
  }

  function extractCompany() {
    const selectors = [
      '[data-field="experience_company_logo"] ~ div .t-14.t-black.t-bold span',
      '.pv-entity__secondary-title',
      '.pv-text-details__right-panel .inline-block',
      '.top-card-link-has-icon span'
    ];
    for (const s of selectors) {
      const el = document.querySelector(s);
      if (el && el.textContent.trim()) return el.textContent.trim();
    }
    return null;
  }

  function extractHeadline() {
    const el = document.querySelector('.text-body-medium.break-words, .pv-text-details__left-panel .text-body-medium');
    return el ? el.textContent.trim() : '';
  }

  // Extract profile from a search result card
  function extractProfileFromCard(card) {
    try {
      // Find the name link
      const link = card.querySelector('a[href*="/in/"]');
      if (!link) return null;

      let fullName = link.textContent.trim();
      // If name is empty (e.g. icon link), try finding a nearby span or heading
      if (!fullName) {
        const nameEl = card.querySelector('.entity-result__title-text, h3, h4');
        if (nameEl) fullName = nameEl.textContent.trim();
      }

      // Clean up "LinkedIn Member" or empty names
      if (!fullName || fullName.includes('LinkedIn Member') || fullName.length < 2) return null;

      let url = link.href.split('?')[0];
      if (!url.startsWith('http')) url = window.location.origin + url;

      // Validate URL pattern
      if (!url.match(/\/in\/[^\/]+\/?/)) return null;

      const headlineEl = card.querySelector('.entity-result__primary-subtitle, .base-search-card__subtitle, [class*="subtitle"]');
      const companyEl = card.querySelector('.entity-result__secondary-subtitle, .base-search-card__metadata, [class*="secondary"]');
      const locationEl = card.querySelector('.entity-result__tertiary-subtitle, [class*="location"]');

      const nameParts = fullName.split(' ').filter(p => p);
      return {
        full_name: fullName,
        first_name: nameParts[0] || '',
        last_name: nameParts.slice(1).join(' ') || '',
        headline: headlineEl ? headlineEl.textContent.trim() : '',
        company_name: companyEl ? companyEl.textContent.trim() : '',
        location: locationEl ? locationEl.textContent.trim() : '',
        linkedin_url: url,
        element: card
      };
    } catch (e) {
      return null;
    }
  }

  // Get all profile cards
  function getAllProfileCards() {
    const selectors = [
      'li.reusable-search__result-container',
      '.entity-result',
      '.search-result',
      '.reusable-search__result-container'
    ];

    let cards = [];
    for (const s of selectors) {
      const found = document.querySelectorAll(s);
      if (found.length > 0) {
        cards = Array.from(found);
        break;
      }
    }

    // Fallback: find any /in/ link and get its closest container
    if (cards.length === 0) {
      const links = document.querySelectorAll('a[href*="/in/"]');
      const seen = new Set();
      links.forEach(l => {
        const container = l.closest('li, div[class*="result"], .base-card');
        if (container && !seen.has(container)) {
          cards.push(container);
          seen.add(container);
        }
      });
    }

    return cards.map(c => extractProfileFromCard(c)).filter(p => p);
  }

  // UI Components
  function showNotification(msg, type = 'info') {
    const el = document.createElement('div');
    el.style.cssText = `
      position: fixed; bottom: 20px; left: 20px; z-index: 1000000;
      padding: 12px 20px; border-radius: 8px; color: white;
      font-family: sans-serif; font-size: 14px; box-shadow: 0 4px 12px rgba(0,0,0,0.2);
      background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6'};
      transition: all 0.3s;
    `;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => {
      el.style.opacity = '0';
      el.style.transform = 'translateY(10px)';
      setTimeout(() => el.remove(), 300);
    }, 3000);
  }

  function createScraperButton() {
    if (document.getElementById('linkedin-scrape-btn')) return;
    const btn = document.createElement('button');
    btn.id = 'linkedin-scrape-btn';
    btn.innerHTML = '🔍 Scrape Data';
    btn.style.cssText = `
      position: fixed; bottom: 20px; right: 20px; z-index: 999999;
      padding: 12px 20px; background: #06b6d4; color: white;
      border: none; border-radius: 8px; font-weight: 600; cursor: pointer;
      box-shadow: 0 4px 12px rgba(6, 182, 212, 0.4);
    `;
    btn.onclick = () => {
      const panel = document.getElementById('linkedin-scrape-panel');
      if (panel) panel.remove();
      else injectPanel();
    };
    document.body.appendChild(btn);
  }

  function injectPanel() {
    const panel = document.createElement('div');
    panel.id = 'linkedin-scrape-panel';
    panel.style.cssText = `
      position: fixed; top: 20px; right: 20px; width: 360px; max-height: 85vh;
      background: #1e293b; border: 1px solid #334155; border-radius: 12px;
      z-index: 999998; display: flex; flex-direction: column; color: white;
      font-family: sans-serif; box-shadow: 0 20px 50px rgba(0,0,0,0.4);
    `;

    panel.innerHTML = `
      <div style="padding: 16px; border-bottom: 1px solid #334155; display: flex; justify-content: space-between; align-items: center;">
        <h3 style="margin: 0; font-size: 16px; color: #38bdf8;">LinkedIn Scrape Data</h3>
        <button onclick="this.closest('#linkedin-scrape-panel').remove()" style="background: none; border: none; color: #94a3b8; cursor: pointer; font-size: 20px;">×</button>
      </div>
      <div style="padding: 16px; overflow-y: auto; flex: 1;">
        <div id="scrape-status" style="margin-bottom: 12px; font-size: 14px; padding: 8px; background: #0f172a; border-radius: 6px; text-align: center;">
          Scanning page...
        </div>
        <div id="profile-list" style="margin-bottom: 16px; max-height: 250px; overflow-y: auto; border: 1px solid #334155; border-radius: 8px; background: #0f172a;">
        </div>
        <div style="display: flex; gap: 8px; margin-bottom: 12px;">
          <button id="btn-refresh" style="flex: 1; padding: 8px; background: #334155; border: none; border-radius: 6px; color: white; cursor: pointer; font-size: 12px;">🔄 Refresh</button>
          <button id="btn-select-all" style="flex: 1; padding: 8px; background: #334155; border: none; border-radius: 6px; color: white; cursor: pointer; font-size: 12px;">✅ All</button>
          <button id="btn-select-none" style="flex: 1; padding: 8px; background: #334155; border: none; border-radius: 6px; color: white; cursor: pointer; font-size: 12px;">❌ None</button>
        </div>
        <div style="margin-bottom: 16px;">
          <label style="display: flex; align-items: center; gap: 8px; font-size: 13px; cursor: pointer;">
            <input type="checkbox" id="chk-auto-email" checked>
            <span>Auto-find emails</span>
          </label>
        </div>
        <button id="btn-start-scrape" style="width: 100%; padding: 12px; background: #06b6d4; color: white; border: none; border-radius: 8px; font-weight: 600; cursor: pointer;">Scrape Selected</button>
      </div>
      <div id="results-area" style="padding: 16px; border-top: 1px solid #334155; display: none; background: #0f172a;">
        <h4 style="margin: 0 0 10px 0; font-size: 14px;">Results</h4>
        <div id="results-list" style="max-height: 150px; overflow-y: auto; font-size: 12px; margin-bottom: 10px;"></div>
        <button id="btn-export" style="width: 100%; padding: 8px; background: #10b981; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600;">Export CSV</button>
      </div>
    `;

    document.body.appendChild(panel);
    updateProfileList(panel);

    panel.querySelector('#btn-refresh').onclick = () => updateProfileList(panel);
    panel.querySelector('#btn-select-all').onclick = () => panel.querySelectorAll('.prof-cb').forEach(cb => cb.checked = true);
    panel.querySelector('#btn-select-none').onclick = () => panel.querySelectorAll('.prof-cb').forEach(cb => cb.checked = false);

    panel.querySelector('#btn-start-scrape').onclick = async () => {
      const selected = Array.from(panel.querySelectorAll('.prof-cb:checked')).map(cb => JSON.parse(cb.dataset.profile));
      if (selected.length === 0) {
        showNotification('Please select at least one profile', 'error');
        return;
      }

      const btn = panel.querySelector('#btn-start-scrape');
      btn.disabled = true;
      btn.textContent = 'Processing...';

      const results = [];
      const apiUrl = await getApiUrl();
      const autoEmail = panel.querySelector('#chk-auto-email').checked;

      for (const p of selected) {
        try {
          const res = await fetch(`${apiUrl}/api/leads/linkedin-capture`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...p, auto_find_email: autoEmail })
          });
          const data = await res.json();
          results.push({ ...p, ...data, success: true });
        } catch (e) {
          results.push({ ...p, success: false, error: e.message });
        }
        updateResultsUI(panel, results);
      }

      btn.disabled = false;
      btn.textContent = 'Scrape Selected';
      showNotification(`Finished scraping ${results.length} profiles`, 'success');
    };
  }

  function updateProfileList(panel) {
    const listEl = panel.querySelector('#profile-list');
    const statusEl = panel.querySelector('#scrape-status');

    // If on individual profile page, just add that one
    let profiles = [];
    if (isProfilePage()) {
      const name = extractName();
      if (name) {
        profiles = [{
          full_name: name.full,
          first_name: name.first,
          last_name: name.last,
          headline: extractHeadline(),
          company_name: extractCompany(),
          linkedin_url: window.location.href.split('?')[0],
          location: ''
        }];
      }
    } else {
      profiles = getAllProfileCards();
    }

    statusEl.textContent = `${profiles.length} profiles detected`;
    statusEl.style.color = profiles.length > 0 ? '#38bdf8' : '#94a3b8';

    if (profiles.length === 0) {
      listEl.innerHTML = '<div style="padding: 20px; text-align: center; color: #94a3b8; font-size: 13px;">No profiles found.<br>Try scrolling down or refreshing.</div>';
    } else {
      listEl.innerHTML = profiles.map((p, i) => `
        <label style="display: flex; align-items: flex-start; gap: 10px; padding: 10px; border-bottom: 1px solid #334155; cursor: pointer; hover: background: #1e293b;">
          <input type="checkbox" class="prof-cb" data-index="${i}" data-profile='${JSON.stringify(p).replace(/'/g, "&apos;")}' checked style="margin-top: 3px;">
          <div style="flex: 1; overflow: hidden;">
            <div style="font-size: 13px; font-weight: 600; color: #f1f5f9; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${p.full_name}</div>
            <div style="font-size: 11px; color: #94a3b8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${p.headline || 'No headline'}</div>
          </div>
        </label>
      `).join('');
    }
  }

  function updateResultsUI(panel, results) {
    const area = panel.querySelector('#results-area');
    const list = panel.querySelector('#results-list');
    area.style.display = 'block';

    list.innerHTML = results.map(r => `
      <div style="padding: 4px 0; border-bottom: 1px solid #334155; display: flex; justify-content: space-between;">
        <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;">${r.full_name}</span>
        <span style="color: ${r.success ? '#10b981' : '#ef4444'}; font-weight: bold; margin-left: 8px;">
          ${r.success ? (r.email_status?.email ? '📧' : '✅') : '❌'}
        </span>
      </div>
    `).join('');

    panel.querySelector('#btn-export').onclick = () => {
      const headers = ['Name', 'Email', 'Headline', 'Company', 'LinkedIn URL'];
      const rows = results.map(r => [
        r.full_name,
        r.email_status?.email || '',
        r.headline,
        r.company_name,
        r.linkedin_url
      ].map(v => `"${(v || '').replace(/"/g, '""')}"`).join(','));

      const csv = [headers.join(','), ...rows].join('\n');
      const blob = new Blob([csv], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `linkedin_leads_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
    };
  }

  // Initialize
  function init() {
    createScraperButton();
  }

  init();

  // Handle LinkedIn SPA navigation
  let lastUrl = location.href;
  setInterval(() => {
    if (location.href !== lastUrl) {
      lastUrl = location.href;
      init();
    }
  }, 2000);

})();
