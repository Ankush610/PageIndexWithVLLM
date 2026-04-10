// ═══════════════════════════════════════════════════════════
// PageIndex UI — app.js  (Projects refactor)
// ═══════════════════════════════════════════════════════════

// ── State ─────────────────────────────────────────────────────────────────────
const API = '';
let docs           = [];        // all documents (all projects)
let projects       = [];        // list of project name strings
let activeDocIds   = [];        // docs selected for chat
let currentProject = null;      // null = grid view; string = inside a project
let detailSelected = new Set(); // checkboxes inside project detail view
let isQuerying     = false;
let isIndexing     = false;

// For pending move operation
let _movePendingDocIds = [];     // doc IDs waiting to be moved

// (no double-click timing needed — single click opens project)

// ══════════════════════════════════════════════════════════════════════════════
// PROCESSING OVERLAY  (unchanged from original)
// ══════════════════════════════════════════════════════════════════════════════
const OV_STEPS_BASE = [
  { key: 'upload',       icon: '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 9V3M7 3L4 6M7 3l3 3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 10v1a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1v-1" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>', label: 'Uploading to server' },
  { key: 'read',         icon: '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 2h7l3 3v8a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M9 2v3h3" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M4 7h6M4 9.5h4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>', label: 'Reading pages & counting tokens' },
  { key: 'toc_find',     icon: '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="6" cy="6" r="4" stroke="currentColor" stroke-width="1.4"/><path d="M9.5 9.5L13 13" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>', label: 'Scanning for Table of Contents' },
  { key: 'toc_grp',      icon: '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><rect x="1" y="1" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.4"/><rect x="8" y="1" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.4"/><rect x="1" y="8" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.4"/><rect x="8" y="8" width="5" height="5" rx="1" stroke="currentColor" stroke-width="1.4"/></svg>', label: 'Grouping content into sections' },
  { key: 'toc_gen',      icon: '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="2.5" r="1.5" stroke="currentColor" stroke-width="1.4"/><circle cx="3" cy="10" r="1.5" stroke="currentColor" stroke-width="1.4"/><circle cx="11" cy="10" r="1.5" stroke="currentColor" stroke-width="1.4"/><path d="M7 4v3M7 7l-3 2M7 7l4 2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>', label: 'Generating hierarchical structure' },
  { key: 'toc_conv',     icon: '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 4h8M3 7h6M3 10h4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><path d="M10 8l2 2-2 2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>', label: 'Resolving physical page numbers' },
  { key: 'toc_ver',      icon: '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="5.5" stroke="currentColor" stroke-width="1.4"/><path d="M4.5 7l2 2 3-3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>', label: 'Verifying index accuracy' },
  { key: 'toc_chk',      icon: '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="6" cy="6" r="4" stroke="currentColor" stroke-width="1.4"/><path d="M9.5 9.5L13 13" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><path d="M4.5 6l1.5 1.5 2-2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>', label: 'Checking section start positions' },
  { key: 'page_extract', icon: '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><rect x="2" y="1" width="10" height="12" rx="1" stroke="currentColor" stroke-width="1.4"/><path d="M4 4h6M4 7h6M4 10h3" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>', label: 'DYNAMIC' },
  { key: 'done',         icon: '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="5.5" stroke="currentColor" stroke-width="1.4"/><path d="M4 7l2.5 2.5 3.5-4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>', label: 'Indexing complete' },
];
let OV_STEPS = OV_STEPS_BASE;
let _sels = {};

function ovShow(fname, idx, total, settings) {
  OV_STEPS = OV_STEPS_BASE.map(s => {
    if (s.key === 'page_extract') {
      return (settings && settings.use_llm_parser)
        ? { ...s, icon: '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="6" r="2.5" stroke="currentColor" stroke-width="1.4"/><path d="M1 6s2-4 6-4 6 4 6 4-2 4-6 4-6-4-6-4Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>', label: 'Extracting pages with LLM Vision' }
        : { ...s, icon: '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 2h7l3 3v8a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M9 2v3h3" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M4 7h6M4 9.5h4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>', label: 'Extracting pages with PDF Parser' };
    }
    return s;
  });
  document.getElementById('ov-filename').textContent = fname;
  const multi = document.getElementById('ov-multi');
  if (total > 1) { multi.style.display = 'flex'; document.getElementById('ov-multi-text').textContent = `File ${idx + 1} of ${total}`; }
  else { multi.style.display = 'none'; }
  const container = document.getElementById('ov-steps');
  container.innerHTML = ''; _sels = {};
  OV_STEPS.forEach(s => {
    const el = document.createElement('div');
    el.className = 'proc-step'; el.id = 'ps-' + s.key;
    el.innerHTML = `<div class="proc-step-icon">${s.icon}</div><div class="proc-step-body"><div class="proc-step-label">${s.label}</div><div class="proc-step-sub" id="pss-${s.key}"></div></div>`;
    container.appendChild(el); _sels[s.key] = el;
  });
  document.getElementById('proc-overlay').classList.add('visible');
  document.getElementById('sidebar').classList.add('locked');
  const banner = document.getElementById('proc-banner');
  banner.style.display = 'flex';
  document.getElementById('proc-banner-text').textContent = 'Indexing: ' + fname;
  isIndexing = true;
}

function ovHide() {
  document.getElementById('proc-overlay').classList.remove('visible');
  document.getElementById('sidebar').classList.remove('locked');
  document.getElementById('proc-banner').style.display = 'none';
  isIndexing = false;
  const btn = document.getElementById('cancel-index-btn');
  if (btn) { btn.disabled = false; btn.textContent = 'Cancel'; btn.style.opacity = ''; btn.style.cursor = 'pointer'; }
  const note = document.getElementById('cancel-pending-note');
  if (note) note.style.display = 'none';
}

function _stepActivate(key, sub) {
  Object.values(_sels).forEach(el => { if (el.classList.contains('s-active')) { el.classList.remove('s-active'); el.classList.add('s-done'); } });
  const el = _sels[key]; if (!el) return;
  el.classList.add('s-active');
  if (sub) document.getElementById('pss-' + key).textContent = sub;
  el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
function _stepDone(key, sub) { const el = _sels[key]; if (!el) return; el.classList.remove('s-active'); el.classList.add('s-done'); if (sub) document.getElementById('pss-' + key).textContent = sub; }
function _stepError(key, msg) { const el = _sels[key]; if (!el) return; el.classList.remove('s-active'); el.classList.add('s-error'); if (msg) document.getElementById('pss-' + key).textContent = msg; }
function _activeKey() { for (const [k, el] of Object.entries(_sels)) { if (el.classList.contains('s-active')) return k; } return 'upload'; }

// ══════════════════════════════════════════════════════════════════════════════
// PROJECTS API
// ══════════════════════════════════════════════════════════════════════════════
async function loadProjects() {
  try {
    const r = await fetch(API + '/projects');
    if (r.ok) projects = (await r.json()).projects || ['default'];
  } catch (e) { projects = ['default']; }
  _syncProjectDropdown();
}

function _syncProjectDropdown() {
  const sel = document.getElementById('project-select');
  if (!sel) return;
  const cur = sel.value;
  sel.innerHTML = projects.map(p => `<option value="${esc(p)}">${esc(p)}</option>`).join('');
  if (projects.includes(cur)) sel.value = cur;
}

async function createProject(name) {
  const r = await fetch(API + '/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }) });
  if (!r.ok) { const e = await r.json(); throw new Error(e.detail || 'Failed to create project'); }
  await loadProjects();
  await loadDocs();
  renderProjectGrid();
}

async function renameProject(oldName, newName) {
  const r = await fetch(API + '/projects/' + encodeURIComponent(oldName), { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ new_name: newName }) });
  if (!r.ok) { const e = await r.json(); throw new Error(e.detail || 'Failed to rename'); }
  // If we're inside the renamed project, update currentProject
  if (currentProject === oldName) currentProject = newName;
  await loadProjects();
  await loadDocs();
}

async function deleteProject(name) {
  const r = await fetch(API + '/projects/' + encodeURIComponent(name), { method: 'DELETE' });
  if (!r.ok) { const e = await r.json(); throw new Error(e.detail || 'Failed to delete project'); }
  await loadProjects();
  await loadDocs();
}

async function moveDoc(docId, targetProject) {
  const r = await fetch(API + '/document/' + docId + '/move', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ project: targetProject }) });
  if (!r.ok) { const e = await r.json(); throw new Error(e.detail || 'Failed to move document'); }
  await loadDocs();
}

// ══════════════════════════════════════════════════════════════════════════════
// PROJECT GRID (top-level view)
// ══════════════════════════════════════════════════════════════════════════════
function renderProjectGrid() {
  const grid = document.getElementById('project-grid');
  if (!grid) return;

  // Build per-project doc counts
  const counts = {};
  projects.forEach(p => { counts[p] = 0; });
  docs.forEach(d => { const p = d.project || 'default'; if (counts[p] !== undefined) counts[p]++; else counts[p] = 1; });

  if (!projects.length) {
    grid.innerHTML = `<div style="color:var(--text-dim);font-size:13px;padding:20px 0;">No projects yet.</div>`;
    return;
  }

  grid.innerHTML = projects.map(p => {
    const count = counts[p] || 0;
    const isDefault = p === 'default';
    return `<div class="project-card" data-project="${esc(p)}"
      onclick="_handleProjectClick(event, '${esc(p)}')"
      title="Click to open project">
      <div class="project-card-icon">
        <svg width="26" height="26" viewBox="0 0 22 22" fill="none">
          <path d="M2 5a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
        </svg>
      </div>
      <div class="project-card-body">
        <div class="project-card-name">${esc(p)}</div>
        ${isDefault ? '<div style="font-size:10px;color:var(--text-dim);font-family:var(--font-mono);">default project</div>' : ''}
        <div class="project-card-meta">${count} document${count !== 1 ? 's' : ''}</div>
      </div>
      <div class="project-card-footer">
        <svg width="10" height="10" viewBox="0 0 12 12" fill="none"><path d="M5 2l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        Open
      </div>
    </div>`;
  }).join('');

  updateLibCount();
  updateActiveDocsStrip();
}

function _handleProjectClick(e, projectName) {
  openProjectDetail(projectName);
}

function openProjectDetail(projectName) {
  currentProject = projectName;
  detailSelected.clear();
  document.getElementById('view-projects-grid').style.display = 'none';
  const detail = document.getElementById('view-project-detail');
  detail.style.display = 'flex';
  detail.style.flexDirection = 'column';
  document.getElementById('detail-project-name').textContent = projectName;
  document.getElementById('detail-title').textContent = projectName;
  // Hide rename button for default project
  document.getElementById('btn-rename-project').style.display = projectName === 'default' ? 'none' : 'flex';
  document.getElementById('btn-delete-project').style.display = projectName === 'default' ? 'none' : 'flex';
  renderDetailDocs();
}

function exitProject() {
  currentProject = null;
  detailSelected.clear();
  document.getElementById('view-project-detail').style.display = 'none';
  document.getElementById('view-projects-grid').style.display = 'flex';
  document.getElementById('view-projects-grid').style.flexDirection = 'column';
  renderProjectGrid();
}

function renderDetailDocs() {
  const list = document.getElementById('detail-doc-list');
  const projectDocs = docs.filter(d => (d.project || 'default') === currentProject);

  if (!projectDocs.length) {
    list.innerHTML = `<div style="color:var(--text-dim);font-size:13px;padding:20px 0;">No documents in this project. Go to Indexing to upload one and save it here.</div>`;
    _updateDetailToolbar();
    return;
  }

  const activeSet = new Set(activeDocIds);
  list.innerHTML = projectDocs.map(d => {
    const pages = d.total_pages || d.page_count || '?';
    const isSel = detailSelected.has(d.doc_id);
    const isActive = activeSet.has(d.doc_id);
    return `<div class="detail-doc-row ${isSel ? 'detail-sel' : ''} ${isActive ? 'detail-active' : ''}" onclick="toggleDetailSelect('${d.doc_id}')">
      <div class="detail-check-wrap">
        <div class="detail-checkbox ${isSel ? 'checked' : ''}">
          ${isSel ? '<svg width="9" height="9" viewBox="0 0 10 10" fill="none"><path d="M1.5 5l3 3 4-4.5" stroke="white" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>' : ''}
        </div>
      </div>
      <div class="detail-doc-icon">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M3 2h7l4 4v9a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M10 2v4h4" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M5 8h6M5 11h4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>
      </div>
      <div class="detail-doc-body">
        <div class="detail-doc-name">${esc(d.doc_name)}</div>
        <div class="detail-doc-meta">
          <span class="doc-meta-badge">${pages} pages</span>
          ${isActive ? '<span class="doc-meta-badge" style="color:var(--green);border-color:var(--green);background:var(--green-bg);">active</span>' : ''}
        </div>
      </div>
      <div class="detail-doc-actions">
        <button class="detail-action-btn" onclick="event.stopPropagation();toggleChatSelect('${d.doc_id}')" title="${isActive ? 'Remove from chat' : 'Add to chat'}">
          ${isActive
            ? '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M1 11L11 1M1 1l10 10" stroke="var(--green)" stroke-width="1.5" stroke-linecap="round"/></svg>'
            : '<svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M2 6h8M6 2v8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>'}
        </button>
        <button class="detail-action-btn" onclick="event.stopPropagation();deleteDoc('${d.doc_id}')" title="Delete document">
          <svg width="12" height="12" viewBox="0 0 14 14" fill="none"><path d="M2 3.5h10M5.5 3.5V2.5h3v1M3.5 3.5l.7 8h5.6l.7-8" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
      </div>
    </div>`;
  }).join('');

  _updateDetailToolbar();
}

function toggleDetailSelect(docId) {
  if (detailSelected.has(docId)) detailSelected.delete(docId);
  else detailSelected.add(docId);
  renderDetailDocs();
}

function toggleChatSelect(docId) {
  const idx = activeDocIds.indexOf(docId);
  if (idx !== -1) {
    activeDocIds.splice(idx, 1);
  } else {

    activeDocIds.push(docId);
  }
  _updateActiveDocHeader();
  renderDetailDocs();
}

function clearDetailSelection() {
  detailSelected.clear();
  renderDetailDocs();
}

function activateSelectedDocs() {
  for (const docId of detailSelected) {
    if (!activeDocIds.includes(docId)) {
      activeDocIds.push(docId);
    }
  }
  _updateActiveDocHeader();
  renderDetailDocs();
}

function deactivateSelectedDocs() {
  for (const docId of detailSelected) {
    activeDocIds = activeDocIds.filter(id => id !== docId);
  }
  _updateActiveDocHeader();
  renderDetailDocs();
}

function _updateDetailToolbar() {
  const toolbar = document.getElementById('detail-toolbar');
  const count = detailSelected.size;
  toolbar.style.display = count > 0 ? 'flex' : 'none';
  document.getElementById('detail-sel-count').textContent = `${count} selected`;
  // Detail subtitle
  const projectDocs = docs.filter(d => (d.project || 'default') === currentProject);
  const activeInProject = projectDocs.filter(d => activeDocIds.includes(d.doc_id)).length;
  document.getElementById('detail-subtitle').textContent =
    activeInProject > 0
      ? `${activeInProject} doc${activeInProject !== 1 ? 's' : ''} active for chat`
      : 'Select docs to add to chat session';
}

async function deleteSelectedDetail() {
  if (!detailSelected.size) return;
  const n = detailSelected.size;
  if (!confirm(`Delete ${n} document${n !== 1 ? 's' : ''}? This cannot be undone.`)) return;
  for (const docId of [...detailSelected]) {
    const r = await fetch(API + '/document/' + docId, { method: 'DELETE' });
    if (r.ok) {
      docs = docs.filter(d => d.doc_id !== docId);
      activeDocIds = activeDocIds.filter(id => id !== docId);
      detailSelected.delete(docId);
    }
  }
  _updateActiveDocHeader();
  updateLibCount();
  renderDetailDocs();
}

function moveSelectedDocs() {
  if (!detailSelected.size) return;
  _movePendingDocIds = [...detailSelected];
  openMoveModal(_movePendingDocIds);
}

// ══════════════════════════════════════════════════════════════════════════════
// PROJECT MODALS
// ══════════════════════════════════════════════════════════════════════════════
function openCreateModal() {
  const modal = document.getElementById('create-modal');
  modal.style.display = 'flex';
  document.getElementById('create-input').value = '';
  setTimeout(() => document.getElementById('create-input').focus(), 50);
}
function closeCreateModal() { document.getElementById('create-modal').style.display = 'none'; }
async function confirmCreate() {
  const name = document.getElementById('create-input').value.trim();
  if (!name) return;
  try {
    await createProject(name);
    closeCreateModal();
    renderProjectGrid();
  } catch (e) { alert(e.message); }
}

let _renamingProject = null;
function openRenameModal() {
  _renamingProject = currentProject;
  const modal = document.getElementById('rename-modal');
  modal.style.display = 'flex';
  const inp = document.getElementById('rename-input');
  inp.value = _renamingProject;
  setTimeout(() => { inp.focus(); inp.select(); }, 50);
}
function closeRenameModal() { document.getElementById('rename-modal').style.display = 'none'; }
async function confirmRename() {
  const newName = document.getElementById('rename-input').value.trim();
  if (!newName || newName === _renamingProject) { closeRenameModal(); return; }
  try {
    await renameProject(_renamingProject, newName);
    closeRenameModal();
    // Update the detail view labels
    document.getElementById('detail-project-name').textContent = currentProject;
    document.getElementById('detail-title').textContent = currentProject;
  } catch (e) { alert(e.message); }
}

async function deleteCurrentProject() {
  if (!currentProject || currentProject === 'default') return;
  const count = docs.filter(d => (d.project || 'default') === currentProject).length;
  const msg = count > 0
    ? `Delete project "${currentProject}" and its ${count} document${count !== 1 ? 's' : ''}? This cannot be undone.`
    : `Delete project "${currentProject}"?`;
  if (!confirm(msg)) return;
  try {
    await deleteProject(currentProject);
    // Remove deleted doc IDs from activeDocIds
    const deletedIds = new Set(docs.filter(d => (d.project || 'default') === currentProject).map(d => d.doc_id));
    activeDocIds = activeDocIds.filter(id => !deletedIds.has(id));
    _updateActiveDocHeader();
    exitProject();
  } catch (e) { alert(e.message); }
}

// Move modal
function openMoveModal(docIds) {
  const modal = document.getElementById('move-modal');
  const n = docIds.length;
  document.getElementById('move-modal-subtitle').textContent =
    `Move ${n} document${n !== 1 ? 's' : ''} to:`;
  const listEl = document.getElementById('move-modal-list');
  listEl.innerHTML = projects
    .filter(p => p !== currentProject)
    .map(p => `<button onclick="confirmMove('${esc(p)}')"
      style="width:100%;text-align:left;padding:10px 14px;background:var(--card-bg);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:13px;cursor:pointer;font-family:var(--font-main);display:flex;align-items:center;gap:8px;transition:all .15s;"
      onmouseover="this.style.borderColor='var(--accent)';this.style.color='var(--accent)'"
      onmouseout="this.style.borderColor='var(--border)';this.style.color='var(--text)'">
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M1 3a1 1 0 0 1 1-1h3l1.5 1.5H12a1 1 0 0 1 1 1V11a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V3Z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>
      ${esc(p)}
    </button>`).join('');
  modal.style.display = 'flex';
}
function closeMoveModal() {
  document.getElementById('move-modal').style.display = 'none';
  // Do NOT clear _movePendingDocIds here — confirmMove still needs it
}
async function confirmMove(targetProject) {
  closeMoveModal();
  console.log('[move] starting move of', _movePendingDocIds, '→', targetProject);
  const results = await Promise.all(_movePendingDocIds.map(async docId => {
    try {
      const res = await fetch(API + '/document/' + docId + '/move', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project: targetProject })
      });
      const body = await res.json();
      console.log('[move] doc', docId, '→', targetProject, '| status', res.status, body);
      return { docId, ok: res.ok, body };
    } catch (e) {
      console.error('[move] fetch error for', docId, e);
      return { docId, ok: false, error: e.message };
    }
  }));
  console.log('[move] all results:', results);
  _movePendingDocIds = [];
  detailSelected.clear();
  await loadDocs();
  console.log('[move] docs after reload:', docs.map(d => ({ id: d.doc_id, name: d.doc_name, project: d.project })));
  renderDetailDocs();
  renderProjectGrid();
}

// ══════════════════════════════════════════════════════════════════════════════
// STAGED UPLOAD  (unchanged)
// ══════════════════════════════════════════════════════════════════════════════
let _pendingFiles = [];
let _cancelRequested = false;

function cancelIndexing() {
  if (_cancelRequested) return;
  _cancelRequested = true;
  fetch(API + '/cancel_indexing', { method: 'POST' }).catch(() => {});
  document.getElementById('proc-banner-text').textContent = 'Finishing current document… indexing will stop after this one';
  const btn = document.getElementById('cancel-index-btn');
  if (btn) { btn.disabled = true; btn.textContent = 'Cancellation pending…'; btn.style.opacity = '0.5'; btn.style.cursor = 'not-allowed'; }
  const note = document.getElementById('cancel-pending-note');
  if (note) note.style.display = 'block';
}

function onFilesSelected(event) {
  const files = Array.from(event.target.files || []);
  event.target.value = '';
  if (!files.length) return;
  _pendingFiles = [..._pendingFiles, ...files];
  _renderStagedFiles();
}

function _renderStagedFiles() {
  const area = document.getElementById('staged-files');
  const list = document.getElementById('staged-list');
  if (!_pendingFiles.length) { area.style.display = 'none'; return; }
  area.style.display = 'block';
  list.innerHTML = _pendingFiles.map((f, i) =>
    `<div style="display:flex;align-items:center;gap:8px;padding:6px 10px;background:var(--card-bg);border:1px solid var(--border);border-radius:6px;font-size:12px;font-family:var(--font-mono);">
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:flex;align-items:center;gap:6px;"><svg width="13" height="13" viewBox="0 0 14 14" fill="none"><path d="M2 2h7l3 3v8a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M9 2v3h3" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>${f.name}</span>
      <span style="color:var(--text-muted);flex-shrink:0;">${(f.size/1024/1024).toFixed(1)} MB</span>
      <span onclick="_removeStaged(${i})" style="cursor:pointer;color:var(--text-dim);padding:0 4px;display:flex;align-items:center;" title="Remove"><svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M1 1l8 8M9 1L1 9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg></span>
    </div>`
  ).join('');
}

function _removeStaged(idx) { _pendingFiles.splice(idx, 1); _renderStagedFiles(); }

async function startIndexing() {
  if (!_pendingFiles.length) return;
  const files = [..._pendingFiles];
  _pendingFiles = [];
  _renderStagedFiles();
  await _processFiles(files);
}

async function _processFiles(files) {
  _cancelRequested = false;
  const settings = getIndexingSettings();
  const beforeIds = new Set(docs.map(d => d.doc_id));

  for (let i = 0; i < files.length; i++) {
    if (_cancelRequested) {
      const remaining = files.slice(i);
      _pendingFiles = remaining;
      _renderStagedFiles();
      appendSystemMsg(`Indexing cancelled. ${remaining.length} file(s) restored to queue.`);
      break;
    }
    const file = files[i];
    ovShow(file.name, i, files.length, settings);
    _stepActivate('upload', 'Sending file…');
    try {
      const fd = new FormData();
      fd.append('files', file);
      fd.append('settings', JSON.stringify(settings));
      const uploadPromise = fetch(API + '/upload', { method: 'POST', body: fd });
      uploadPromise.then(() => { _stepDone('upload', 'File received'); _stepActivate('read', 'Waiting for indexing to start…'); }).catch(() => {});
      const [response] = await Promise.all([uploadPromise, _pollUntilDone(beforeIds, file.name, uploadPromise)]);
      const data = await response.json().catch(() => ({ results: [] }));
      const res  = (data.results || []).find(r => r.doc_name === file.name);
      if (res?.success) {
        Object.keys(_sels).forEach(k => { if (k !== 'page_extract' && k !== 'done' && _sels[k].classList.contains('s-active')) _stepDone(k); });
        _stepActivate('page_extract', settings.use_llm_parser ? 'Reading pages with vision model…' : 'Parsing PDF text…');
        _stepDone('page_extract', settings.use_llm_parser ? 'Vision extraction complete' : 'PDF text extracted');
        _stepActivate('done');
        _stepDone('done', `${res.total_nodes} nodes · ${res.total_pages} pages indexed`);
        await loadDocs();
        renderProjectGrid();
        if (currentProject) renderDetailDocs();
        appendSystemMsg(`Indexed **${res.doc_name}** → project **${settings.project}** — ${res.total_nodes} nodes across ${res.total_pages} pages.`);
      } else {
        const errMsg = res?.error || 'Unknown error';
        const isTo = errMsg.toLowerCase().includes('timeout') || errMsg.toLowerCase().includes('timed out');
        const isScanned = errMsg.toLowerCase().includes('processing failed');
        const displayMsg = isTo
          ? 'LLM timeout — try again or check LLM server'
          : isScanned
            ? 'Processing failed — likely a scanned PDF with no text. Enable LLM Vision Parser in Indexing Settings and retry.'
            : errMsg;
        _stepError(_activeKey(), displayMsg);
        await loadDocs();
        appendSystemMsg(`Failed: **${file.name}**: ${displayMsg}`);
      }
    } catch (e) {
      _stepError(_activeKey(), e.message);
      await loadDocs();
      appendSystemMsg(`Upload error: **${file.name}**: ${e.message}`);
    }
    if (i < files.length - 1 && !_cancelRequested) await _waitForServerIdle();
  }
  ovHide();
  await loadDocs();
  renderProjectGrid();
  if (currentProject) renderDetailDocs();
}

async function _waitForServerIdle() {
  const maxWait = 10_000; const iv = 600; let elapsed = 0;
  while (elapsed < maxWait) {
    await sleep(iv); elapsed += iv;
    try { const r = await fetch(API + '/queue_status'); if (r.ok) { const s = await r.json(); if (!s.index_busy) return; } } catch (_) {}
  }
}

async function _pollUntilDone(beforeIds, fname, uploadPromise) {
  const max = 320_000; const iv = 1800; let elapsed = 0;
  let wasQueued = false, reachedPageIndex = false, reachedPageExtract = false;
  let uploadDone = false, uploadSucceeded = null;
  if (uploadPromise) {
    uploadPromise.then(async r => {
      try { const clone = r.clone(); const data = await clone.json(); const res = (data.results || []).find(x => x.doc_name === fname); uploadSucceeded = res ? res.success : false; } catch (_) { uploadSucceeded = false; }
      uploadDone = true;
    }).catch(() => { uploadDone = true; uploadSucceeded = false; });
  }
  while (elapsed < max) {
    if (_cancelRequested) return null;
    if (uploadDone && uploadSucceeded === false) return null;
    await sleep(iv); elapsed += iv;
    try {
      const pr = await fetch(API + '/indexing_phase'); if (!pr.ok) continue;
      const ps = await pr.json(); const phase = ps.phase; const file = ps.file;
      if (phase === 'pageindex' && file !== fname) { if (!wasQueued) { wasQueued = true; document.getElementById('proc-banner-text').textContent = `Queued — waiting for current indexing job to finish…`; } continue; }
      if (wasQueued && (file === fname || phase === 'idle')) { wasQueued = false; document.getElementById('proc-banner-text').textContent = 'Indexing: ' + fname; }
      if (phase === 'pageindex' && file === fname && !reachedPageIndex) { reachedPageIndex = true; _stepDone('read', 'Reading document…'); _stepActivate('toc_find', 'Building document structure…'); }
      if (phase === 'page_extract' && file === fname && !reachedPageExtract) { reachedPageExtract = true; ['read','toc_find','toc_grp','toc_gen','toc_conv','toc_ver','toc_chk'].forEach(k => { if (_sels[k] && !_sels[k].classList.contains('s-done')) _stepDone(k, k === 'toc_find' ? 'Structure built' : ''); }); _stepActivate('page_extract'); }
    } catch (_) {}
  }
  return null;
}

function handleDrop(e) {
  e.preventDefault();
  document.getElementById('upload-zone').classList.remove('drag-over');
  const files = Array.from(e.dataTransfer.files).filter(f => f.name.toLowerCase().endsWith('.pdf'));
  if (!files.length) return;
  _pendingFiles = [..._pendingFiles, ...files];
  _renderStagedFiles();
}

// ══════════════════════════════════════════════════════════════════════════════
// INDEXING SETTINGS
// ══════════════════════════════════════════════════════════════════════════════
function toggleIxSettings() {
  document.getElementById('ix-settings-body').classList.toggle('hidden');
  document.getElementById('ix-chevron').classList.toggle('open');
}

function getIndexingSettings() {
  const summaryOn = document.getElementById('summary-toggle').checked;
  const projectSel = document.getElementById('project-select');
  return {
    toc_check_page_num:     parseInt(document.getElementById('toc-slider').value),
    max_page_num_each_node: parseInt(document.getElementById('node-slider').value),
    if_add_node_summary:    summaryOn ? 'yes' : 'no',
    if_add_doc_description: (summaryOn && document.getElementById('doc-description-toggle').checked) ? 'yes' : 'no',
    use_llm_parser:         document.getElementById('use-llm-parser-toggle').checked,
    project:                projectSel ? projectSel.value : 'default',
  };
}

// ══════════════════════════════════════════════════════════════════════════════
// DOCUMENTS (backend data layer)
// ══════════════════════════════════════════════════════════════════════════════
async function loadDocs() {
  try {
    const r = await fetch(API + '/documents');
    if (r.ok) docs = (await r.json()).documents || [];
  } catch (e) { docs = []; }
  updateLibCount();
}

function updateLibCount() {
  const total = docs.length;
  document.getElementById('lib-count').textContent = total + ' doc' + (total !== 1 ? 's' : '');
  const sbTotal = document.getElementById('sb-total-docs');
  const sbSel   = document.getElementById('sb-selected');
  if (sbTotal) sbTotal.textContent = total;
  if (sbSel)   sbSel.textContent   = activeDocIds.length;
}

function updateActiveDocsStrip() {
  // active-docs-strip removed from UI; no-op kept for compatibility
}

function removeActiveDoc(docId) {
  activeDocIds = activeDocIds.filter(id => id !== docId);
  _updateActiveDocHeader();
  updateActiveDocsStrip();
  updateLibCount();
}

async function deleteDoc(docId) {
  if (isIndexing || !confirm('Remove this document?')) return;
  const r = await fetch(API + '/document/' + docId, { method: 'DELETE' });
  if (r.ok) {
    docs = docs.filter(d => d.doc_id !== docId);
    activeDocIds = activeDocIds.filter(id => id !== docId);
    detailSelected.delete(docId);
    _updateActiveDocHeader();
    updateLibCount();
    if (currentProject) renderDetailDocs();
    renderProjectGrid();
  }
}

// ══════════════════════════════════════════════════════════════════════════════
// NAVIGATION
// ══════════════════════════════════════════════════════════════════════════════
function _setActiveNav(id) {
  ['btn-chat','btn-docs','btn-indexing'].forEach(b => {
    document.getElementById(b).classList.toggle('active', b === id);
  });
}

function showChat() {
  if (isIndexing) return;
  document.getElementById('view-chat').classList.remove('hidden');
  document.getElementById('view-docs').classList.add('hidden');
  document.getElementById('view-indexing').classList.add('hidden');
  _setActiveNav('btn-chat');
}

async function showDocs() {
  if (isIndexing) return;
  document.getElementById('view-docs').classList.remove('hidden');
  document.getElementById('view-chat').classList.add('hidden');
  document.getElementById('view-indexing').classList.add('hidden');
  _setActiveNav('btn-docs');
  await loadProjects();
  await loadDocs();
  // Always start at project grid when switching to docs view
  if (currentProject) {
    // Stay in detail if we were already there
    renderDetailDocs();
  } else {
    document.getElementById('view-project-detail').style.display = 'none';
    document.getElementById('view-projects-grid').style.display = 'flex';
    document.getElementById('view-projects-grid').style.flexDirection = 'column';
    renderProjectGrid();
  }
}

async function showIndexing() {
  if (isIndexing) return;
  document.getElementById('view-indexing').classList.remove('hidden');
  document.getElementById('view-chat').classList.add('hidden');
  document.getElementById('view-docs').classList.add('hidden');
  _setActiveNav('btn-indexing');
  await loadProjects();
  _syncProjectDropdown();
}

// ══════════════════════════════════════════════════════════════════════════════
// CHAT
// ══════════════════════════════════════════════════════════════════════════════
function clearChat() {
  const msgs = document.getElementById('messages');
  msgs.innerHTML = '';
  const es = document.createElement('div'); es.id = 'empty-state';
  es.innerHTML = `<div class="empty-icon"><svg width="48" height="48" viewBox="0 0 48 48" fill="none"><circle cx="24" cy="8" r="4" stroke="currentColor" stroke-width="2"/><circle cx="10" cy="30" r="4" stroke="currentColor" stroke-width="2"/><circle cx="38" cy="30" r="4" stroke="currentColor" stroke-width="2"/><circle cx="24" cy="42" r="4" stroke="currentColor" stroke-width="2"/><path d="M24 12v8M24 20l-10 6M24 20l14 6M10 34v4M38 34v4" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></div>
    <div class="empty-title">Reasoning over structure</div>
    <div class="empty-sub">Select documents and ask questions. PageIndex builds a hierarchical tree and uses LLM reasoning to navigate — no embeddings, no similarity search.</div>
    <div class="suggestion-chips">
      <div class="chip" onclick="useChip(this)">What are the main findings?</div>
      <div class="chip" onclick="useChip(this)">Summarize the methodology</div>
      <div class="chip" onclick="useChip(this)">What models are used?</div>
      <div class="chip" onclick="useChip(this)">List the key conclusions</div>
    </div>`;
  msgs.appendChild(es);
}

function _updateActiveDocHeader() {
  const nameEl = document.getElementById('active-doc-name');
  if (!activeDocIds.length) {
    nameEl.textContent = 'No document selected';
  } else if (activeDocIds.length === 1) {
    const d = docs.find(x => x.doc_id === activeDocIds[0]);
    nameEl.textContent = d ? d.doc_name : 'Unknown';
  } else {
    nameEl.textContent = activeDocIds.length + ' docs active';
  }
  document.getElementById('no-doc-warning').classList.toggle('hidden', activeDocIds.length > 0);
  updateActiveDocsStrip();
  updateLibCount();
}

// ══════════════════════════════════════════════════════════════════════════════
// QUERY  (unchanged)
// ══════════════════════════════════════════════════════════════════════════════
function useChip(el) { document.getElementById('query-input').value = el.textContent; sendQuery(); }
function handleKey(e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendQuery(); } }
function autoResize(el) { el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 120) + 'px'; }

async function sendQuery() {
  const input = document.getElementById('query-input');
  const query = input.value.trim();
  if (!query || isQuerying || isIndexing) return;
  if (!activeDocIds.length) { document.getElementById('no-doc-warning').classList.remove('hidden'); return; }
  const es = document.getElementById('empty-state');
  if (es) es.style.display = 'none';
  isQuerying = true;
  document.getElementById('send-btn').disabled = true;
  input.value = ''; input.style.height = 'auto';
  appendUserMsg(query);
  const loadingEl = appendLoadingMsg();
  // Build the actual query — prepend page context prefix if chips are present
  const _ctxPrefix  = _buildPageCtxPrefix();
  const _queryDocIds = _getQueryDocIds();
  const _fullQuery  = _ctxPrefix ? _ctxPrefix + query : query;
  try {
    const qr = await fetch(API + '/queue_status');
    if (qr.ok) { const qs = await qr.json(); if (qs.query_busy) { const dots = loadingEl.querySelector('.loading-dots'); if (dots) dots.insertAdjacentHTML('afterend', '<div style="font-size:11px;color:var(--text-dim);margin-top:4px;">Queued — waiting for previous query…</div>'); } }
  } catch (_) {}
  try {
    const r = await fetch(API + '/query', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query: _fullQuery, doc_id: _queryDocIds[0], doc_ids: _queryDocIds }) });
    if (!r.ok) { const err = await r.json(); throw new Error(err.detail || 'Query failed'); }
    const data = await r.json();
    loadingEl.remove();
    appendAIResponse(query, data);
  } catch (e) { loadingEl.remove(); appendSystemMsg(`Error: ${e.message}`); }
  isQuerying = false;
  document.getElementById('send-btn').disabled = false;
  input.focus();
}

// ══════════════════════════════════════════════════════════════════════════════
// MESSAGE RENDERERS  (unchanged)
// ══════════════════════════════════════════════════════════════════════════════
function appendUserMsg(text) {
  const msgs = document.getElementById('messages');
  const w = document.createElement('div'); w.className = 'msg-wrapper msg-user';
  w.innerHTML = `<div class="bubble">${esc(text)}</div>`;
  msgs.appendChild(w); msgs.scrollTop = msgs.scrollHeight;
}
function appendLoadingMsg() {
  const msgs = document.getElementById('messages');
  const w = document.createElement('div'); w.className = 'msg-wrapper msg-ai';
  w.innerHTML = `<div class="ai-avatar">✦</div><div class="msg-ai-content"><div class="loading-dots"><span></span><span></span><span></span></div></div>`;
  msgs.appendChild(w); msgs.scrollTop = msgs.scrollHeight;
  return w;
}
function appendAIResponse(query, data) {
  const msgs = document.getElementById('messages');
  const w = document.createElement('div'); w.className = 'msg-wrapper msg-ai';
  const uid = 'r' + Date.now();
  const traversal = data.traversal || [];
  let answer = (data.answer || '').trim();
  if (answer.startsWith('{') && answer.includes('"answer"')) {
    try { const parsed = JSON.parse(answer); if (parsed.answer && parsed.answer !== 'null') answer = parsed.answer; }
    catch (_) { const m = answer.match(/"answer"\s*:\s*"([\s\S]*?)(?:"\s*\}?\s*$|"\s*,)/); if (m) answer = m[1].replace(/\\n/g, '\n').replace(/\\"/g, '"'); }
  }
  const PHASE = { get_document: 'plan', get_document_structure: 'navigate', get_page_content: 'read', answer: 'answer' };
  const LABEL = { get_document: () => 'Fetched document metadata', get_document_structure: () => 'Loaded document structure (tree)', get_page_content: s => `Read pages ${(s.args || {}).pages || '?'}`, answer: () => 'Composed final answer' };
  const stepsHtml = traversal.map(step => {
    const phase = PHASE[step.tool] || 'navigate';
    const label = (LABEL[step.tool] || (() => step.tool))(step);
    const preview = step.result_preview ? `<div style="margin-top:3px;color:var(--text-dim);font-size:10px;font-family:var(--font-mono);white-space:pre-wrap;word-break:break-all;">${esc(step.result_preview.slice(0, 180))}…</div>` : '';
    return `<div class="traversal-step"><span class="phase-badge phase-${phase}">${phase}</span><div style="color:var(--text-muted);">${esc(label)}${preview}</div></div>`;
  }).join('');
  const ctxItems = (data.context || []).filter(c => c.relevant && c.passages?.length);
  const ctxHtml = ctxItems.map(item => `<div class="context-card"><div class="context-card-header"><span class="source-ref"><svg width="12" height="12" viewBox="0 0 14 14" fill="none" style="vertical-align:middle;margin-right:3px"><path d="M2 2h7l3 3v8a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M9 2v3h3" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>${esc(item.section_title || 'Section')} · p.${item.page_number || '?'}</span></div><div class="context-passages">${item.passages.map(p => `<div style="margin-bottom:4px;">— ${esc(p)}</div>`).join('')}</div></div>`).join('');
  const readSteps = traversal.filter(s => s.tool === 'get_page_content');
  const docLabel  = activeDocIds.length > 1 ? activeDocIds.length + ' docs' : esc(data.doc_name || '');
  const srcTags = readSteps.length ? `<div style="margin-bottom:10px;display:flex;flex-wrap:wrap;gap:4px;">${readSteps.map(s => { const did = (s.args || {}).doc_id || activeDocIds[0] || ''; const pages = (s.args || {}).pages || '?'; const firstPage = parseInt(String(pages).split(/[-,]/)[0]) || 1; return `<span class="source-ref source-ref-btn" onclick="openPdfPanel('${did}',${firstPage})" title="View in PDF"><svg width="12" height="12" viewBox="0 0 14 14" fill="none" style="vertical-align:middle;margin-right:3px"><path d="M2 2h7l3 3v8a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M9 2v3h3" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M4 7h6M4 9.5h4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>Pages&nbsp;${pages} — ${docLabel}</span>`; }).join('')}</div>` : '';
  w.innerHTML = `<div class="ai-avatar">✦</div><div class="msg-ai-content">
    ${traversal.length ? `<div class="thinking-block"><div class="thinking-header" onclick="toggleBlock('${uid}-t','${uid}-tc')"><span><svg width="11" height="11" viewBox="0 0 11 11" fill="none" style="vertical-align:middle;margin-right:3px"><path d="M6.5 1L2 6.5h4L4 10l5.5-5.5H6L6.5 1Z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></svg>Thought for ${traversal.length} step${traversal.length !== 1 ? 's' : ''}</span><span style="margin-left:auto;" id="${uid}-tc"><svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M2 3.5l3 3 3-3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></span></div><div class="thinking-content" id="${uid}-t">${stepsHtml}</div></div>` : ''}
    ${ctxItems.length ? `<div class="tool-block"><div class="tool-header" onclick="toggleToolBlock('${uid}-ctx')"><span class="tool-title">get_page_content <svg width="10" height="10" viewBox="0 0 10 10" fill="none" style="vertical-align:middle"><path d="M1.5 5l3 3 4-4.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></span><div class="tool-status"></div><span class="tool-chevron" id="chev-${uid}-ctx"><svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M2 3.5l3 3 3-3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></span></div><div class="tool-body" id="${uid}-ctx"><div style="margin-bottom:10px;color:var(--text-dim);">Retrieved <strong style="color:var(--text)">${ctxItems.length}</strong> section(s)</div>${ctxHtml}</div></div>` : ''}
    ${srcTags}<div class="answer-block" id="${uid}-ans"></div></div>`;
  msgs.appendChild(w);
  const ansEl = w.querySelector(`#${uid}-ans`);
  if (ansEl && answer) ansEl.innerHTML = marked.parse(answer);
  msgs.scrollTop = msgs.scrollHeight;
}
function appendSystemMsg(md) {
  const msgs = document.getElementById('messages');
  const w = document.createElement('div'); w.className = 'msg-wrapper msg-ai';
  w.innerHTML = `<div class="ai-avatar">✦</div><div class="msg-ai-content"><div class="answer-block">${marked.parse(md)}</div></div>`;
  msgs.appendChild(w); msgs.scrollTop = msgs.scrollHeight;
}
function toggleBlock(cid, chid) {
  const el = document.getElementById(cid); const ch = document.getElementById(chid);
  el.classList.toggle('open'); ch.innerHTML = el.classList.contains('open')
    ? '<svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M2 6.5l3-3 3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    : '<svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M2 3.5l3 3 3-3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
}
function toggleToolBlock(id) { const el = document.getElementById(id); const ch = document.getElementById('chev-' + id); el.classList.toggle('open'); if (ch) ch.classList.toggle('open'); }

// ══════════════════════════════════════════════════════════════════════════════
// UTILITIES
// ══════════════════════════════════════════════════════════════════════════════
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
function esc(str) { return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

// Settings dependency wiring
(function wireSettingsDeps() {
  const summaryToggle  = document.getElementById('summary-toggle');
  const docDescToggle  = document.getElementById('doc-description-toggle');
  const docDescRow     = docDescToggle && docDescToggle.closest('.ix-row');
  function syncDocDesc() {
    if (!docDescToggle) return;
    const enabled = summaryToggle && summaryToggle.checked;
    docDescToggle.disabled = !enabled;
    if (docDescRow) docDescRow.style.opacity = enabled ? '1' : '0.45';
    if (!enabled) docDescToggle.checked = false;
  }
  if (summaryToggle) summaryToggle.addEventListener('change', syncDocDesc);
  syncDocDesc();
})();

// ══════════════════════════════════════════════════════════════════════════════
// INIT
// ══════════════════════════════════════════════════════════════════════════════
(async () => {
  await loadProjects();
  await loadDocs();
  renderProjectGrid();
})();

// ---------------------------------------------------------------------------
// PDF side panel
// ---------------------------------------------------------------------------
let _pdfPanelDocId = null;
let _pdfPanelPage  = null;
let _pdfPanelTotal = null;
let _pdfPanelName  = null;
let _pdfZoom       = 100;  // percent

function openPdfPanel(docId, page) {
  _pdfPanelDocId = docId;
  _pdfZoom = 100;
  const panel    = document.getElementById('pdf-panel');
  const resizer  = document.getElementById('pdf-resizer');
  if (!panel) return;
  panel.classList.add('open');
  if (resizer) resizer.style.display = '';
  _loadPdfPage(docId, page);
}

function closePdfPanel() {
  const panel   = document.getElementById('pdf-panel');
  const resizer = document.getElementById('pdf-resizer');
  if (panel)   panel.classList.remove('open');
  if (resizer) resizer.style.display = 'none';
  // Reset any manual width so CSS transition takes over cleanly
  if (panel)   panel.style.width = '';
  if (panel)   panel.style.minWidth = '';
}

// ---------------------------------------------------------------------------
// Resizer drag logic
// ---------------------------------------------------------------------------
(function _initResizer() {
  document.addEventListener('DOMContentLoaded', () => {
    const resizer = document.getElementById('pdf-resizer');
    const panel   = document.getElementById('pdf-panel');
    if (!resizer || !panel) return;

    const MIN_PANEL = 300;
    const MAX_PANEL = window.innerWidth * 0.75;
    let _resizing = false;

    resizer.addEventListener('mousedown', e => {
      _resizing = true;
      resizer.classList.add('dragging');
      document.body.style.cursor    = 'col-resize';
      document.body.style.userSelect = 'none';
      e.preventDefault();
    });

    document.addEventListener('mousemove', e => {
      if (!_resizing) return;
      // Distance from right edge of window
      const newWidth = Math.max(MIN_PANEL, Math.min(window.innerWidth - e.clientX, MAX_PANEL));
      panel.style.width    = newWidth + 'px';
      panel.style.minWidth = newWidth + 'px';
      // Disable CSS transition while dragging for snappy feel
      panel.style.transition = 'none';
    });

    document.addEventListener('mouseup', () => {
      if (!_resizing) return;
      _resizing = false;
      resizer.classList.remove('dragging');
      document.body.style.cursor     = '';
      document.body.style.userSelect = '';
      panel.style.transition = '';
    });
  });
})();

function _loadPdfPage(docId, page) {
  const img       = document.getElementById('pdf-panel-img');
  const label     = document.getElementById('pdf-panel-label');
  const pageLabel = document.getElementById('pdf-page-label');
  const err       = document.getElementById('pdf-panel-err');
  if (!img) return;
  img.style.opacity = '0.3';
  if (err) err.style.display = 'none';
  img.onload  = () => { img.style.opacity = '1'; _applyZoom(); };
  img.onerror = () => {
    img.style.opacity = '0';
    if (err) { err.style.display = 'block'; err.textContent = `Could not load page ${page}.`; }
  };
  img.src = `/pdf/${encodeURIComponent(docId)}/page/${page}?t=${Date.now()}`;

  // Resolve doc name + total from active docs list
  const docEntry = docs.find(d => d.doc_id === docId);
  _pdfPanelName  = docEntry ? docEntry.doc_name : docId;
  _pdfPanelTotal = docEntry ? (docEntry.page_count || null) : null;

  if (label) label.textContent = _pdfPanelName;
  if (pageLabel) pageLabel.textContent = `p. ${page}${_pdfPanelTotal ? ' / ' + _pdfPanelTotal : ''}`;
  _pdfPanelPage = page;
  _updatePdfNav();
  _updateZoomLabel();
}

function _applyZoom() {
  const img  = document.getElementById('pdf-panel-img');
  const body = document.querySelector('.pdf-panel-body');
  if (!img) return;
  img.style.width = _pdfZoom + '%';
  if (body) body.classList.toggle('zoomable', _pdfZoom > 100);
}

// Drag-to-pan: hold click and move mouse to scroll the panel body
(function _initPdfPan() {
  let _dragging = false, _startX = 0, _startY = 0, _scrollLeft = 0, _scrollTop = 0;

  document.addEventListener('DOMContentLoaded', () => {
    const body = document.querySelector('.pdf-panel-body');
    if (!body) return;

    body.addEventListener('mousedown', e => {
      // Only pan when zoomed beyond 100% or image wider than container
      const img = document.getElementById('pdf-panel-img');
      if (!img || _pdfZoom <= 100) return;
      _dragging = true;
      _startX = e.clientX;
      _startY = e.clientY;
      _scrollLeft = body.scrollLeft;
      _scrollTop  = body.scrollTop;
      body.style.cursor = 'grabbing';
      body.style.userSelect = 'none';
      e.preventDefault();
    });

    document.addEventListener('mousemove', e => {
      if (!_dragging) return;
      const body = document.querySelector('.pdf-panel-body');
      if (!body) return;
      body.scrollLeft = _scrollLeft - (e.clientX - _startX);
      body.scrollTop  = _scrollTop  - (e.clientY - _startY);
    });

    document.addEventListener('mouseup', () => {
      if (!_dragging) return;
      _dragging = false;
      const body = document.querySelector('.pdf-panel-body');
      if (body) { body.style.cursor = ''; body.style.userSelect = ''; }
    });
  });
})();

function _updateZoomLabel() {
  const zl = document.getElementById('pdf-zoom-label');
  if (zl) zl.textContent = _pdfZoom + '%';
}

function _updatePdfNav() {
  const prev = document.getElementById('pdf-nav-prev');
  const next = document.getElementById('pdf-nav-next');
  if (prev) prev.disabled = (_pdfPanelPage || 1) <= 1;
  if (next) next.disabled = _pdfPanelTotal ? (_pdfPanelPage || 1) >= _pdfPanelTotal : false;
}

function pdfNavPrev() {
  if (_pdfPanelDocId && _pdfPanelPage > 1) _loadPdfPage(_pdfPanelDocId, _pdfPanelPage - 1);
}
function pdfNavNext() {
  if (_pdfPanelDocId && (!_pdfPanelTotal || _pdfPanelPage < _pdfPanelTotal))
    _loadPdfPage(_pdfPanelDocId, _pdfPanelPage + 1);
}

function pdfZoomIn()  { _pdfZoom = Math.min(_pdfZoom + 25, 300); _applyZoom(); _updateZoomLabel(); }
function pdfZoomOut() { _pdfZoom = Math.max(_pdfZoom - 25,  50); _applyZoom(); _updateZoomLabel(); }

// ---------------------------------------------------------------------------
// Add Page to Chat — chips inside the input bar, persists across messages
// ---------------------------------------------------------------------------

// _pageCtxItems: array of { chipId, docId, page, docName }
const _pageCtxItems = [];

function pdfAddToChat() {
  if (!_pdfPanelDocId || !_pdfPanelPage) return;
  const docId   = _pdfPanelDocId;
  const page    = _pdfPanelPage;
  const docName = _pdfPanelName || _pdfPanelDocId;

  // Prevent duplicate of same doc+page
  if (_pageCtxItems.find(x => x.docId === docId && x.page === page)) return;

  const chipId = 'chip-' + Date.now();
  _pageCtxItems.push({ chipId, docId, page, docName });
  _renderPageChips();
  document.getElementById('query-input')?.focus();
}

function _renderPageChips() {
  const stack = document.getElementById('page-ctx-stack');
  if (!stack) return;
  stack.innerHTML = _pageCtxItems.map(({ chipId, page, docName }) => `
    <span class="page-chip" id="${chipId}">
      <svg width="11" height="11" viewBox="0 0 14 14" fill="none" style="flex-shrink:0">
        <path d="M2 2h7l3 3v8a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>
        <path d="M9 2v3h3" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>
      </svg>
      <span class="page-chip-label">p.${page} — ${esc(docName)}</span>
      <button class="page-chip-remove" onclick="_removePageChip('${chipId}')" title="Remove">×</button>
    </span>`).join('');
  // Update placeholder hint
  const input = document.getElementById('query-input');
  if (input) {
    input.placeholder = _pageCtxItems.length
      ? `Ask about ${_pageCtxItems.length === 1 ? 'this page' : 'these pages'}…`
      : 'Ask a question about your document…';
  }
}

function _removePageChip(chipId) {
  const idx = _pageCtxItems.findIndex(x => x.chipId === chipId);
  if (idx !== -1) _pageCtxItems.splice(idx, 1);
  _renderPageChips();
}

// Called by sendQuery — returns page-focused prefix or null
function _buildPageCtxPrefix() {
  if (!_pageCtxItems.length) return null;
  // Group by doc
  const byDoc = {};
  for (const { docId, page, docName } of _pageCtxItems) {
    if (!byDoc[docId]) byDoc[docId] = { docName, pages: [] };
    byDoc[docId].pages.push(page);
  }
  const parts = Object.values(byDoc).map(({ docName, pages }) =>
    `page${pages.length > 1 ? 's' : ''} ${pages.sort((a,b)=>a-b).join(', ')} of "${docName}"`
  );
  return `[Focus only on ${parts.join(' and ')}] `;
}

// Returns the doc_ids to query — if chips present, use only those docs
function _getQueryDocIds() {
  if (_pageCtxItems.length) {
    const ids = [...new Set(_pageCtxItems.map(x => x.docId))];
    return ids;
  }
  return activeDocIds;
}

