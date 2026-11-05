// The library Agent: a right-hand conversation for the landing and a top-level topic page. A paper's Agent lives in
// reader.js, with the paper's own paragraphs and citations behind it.
(() => {
  'use strict';
  const bootEl = document.getElementById('boot');
  if (!bootEl || document.getElementById('paper-data')) return;
  const BOOT = JSON.parse(bootEl.textContent || '{}');
  const landing = document.getElementById('landing');
  const topicRoot = document.getElementById('topic');
  if (!landing && !topicRoot) return;

  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* private window */ } },
  };
  const gist = (key) => {
    try { return localStorage.getItem(key); } catch { return null; }
  };
  const I18N = window.DR_I18N;
  const readLang = gist('pf-ui-lang') || (I18N ? I18N.guess(BOOT.langs || I18N.NATIVE) : 'en');
  const ui = (() => {
    try { return I18N ? I18N.uiFor(readLang) : readLang; } catch { return readLang; }
  })();
  const zh = String(ui).startsWith('zh');
  const T = {
    agent: 'Agent',
    library: zh ? '文献库' : 'Library',
    topic: zh ? '专题' : 'Topic',
    libraryScope: (n) => zh ? `整个文献库 · ${n} 篇` : `Entire library · ${n} papers`,
    topicScope: (name, n) => zh ? `${name} · ${n} 篇` : `${name} · ${n} papers`,
    open: zh ? '打开 Agent' : 'Open Agent',
    close: zh ? '关闭' : 'Close',
    clear: zh ? '清空对话' : 'Clear conversation',
    placeholder: zh ? '问问文献库，或让它帮你分类整理…' : 'Ask about the library, or how to organize it…',
    placeholderTopic: zh ? '问问这个专题，或让它帮你整理…' : 'Ask about this topic, or how to organize it…',
    send: zh ? '发送' : 'Send',
    thinking: zh ? '正在梳理文献库…' : 'Reading the library…',
    startersLib: zh
      ? ['我的文献库现在是怎么组织的？', '这些论文里有哪些正在形成的主题？', '帮我设计一个更清楚的文件夹结构', '哪些论文看起来放错了文件夹？']
      : ['How is my library organized?', 'Which themes are emerging across these papers?', 'Suggest a cleaner folder structure', 'Which papers look misplaced?'],
    startersTopic: zh
      ? ['用几句话概括这个专题', '这些论文之间有什么共同主题？', '这个专题应该怎么组织？', '哪些论文不太属于这个专题？']
      : ['Summarize this topic in a few sentences', 'What themes connect these papers?', 'How should this topic be organized?', 'Which papers seem out of place?'],
    starts: zh ? '可以这样问' : 'Try asking',
    empty: zh ? 'Agent 能读到你的论文标题、文件夹和收录位置，也能提出整理方案，等你确认后才执行。' : 'The Agent can see paper titles, folders and where each paper sits. Changes wait for your confirmation.',
    proposed: zh ? '建议的整理' : 'Proposed changes',
    apply: zh ? '执行这些修改' : 'Apply changes',
    dismiss: zh ? '不用了' : 'Dismiss',
    applied: (n) => zh ? `已执行 ${n} 项修改` : `Applied ${n} changes`,
    dismissed: zh ? '已忽略这次建议' : 'Suggestions dismissed',
    failed: zh ? '没有得到回答' : 'No answer',
    applyFailed: zh ? '修改没有执行：' : 'Changes were not applied: ',
    newFolder: zh ? '新建文件夹' : 'New folder',
    movePapers: zh ? '移动论文' : 'Move papers',
    renamePaper: zh ? '重命名论文' : 'Rename paper',
    renameFolder: zh ? '重命名文件夹' : 'Rename folder',
    into: zh ? '到' : 'to',
    topLevel: zh ? '顶层' : 'top level',
    papersN: (n) => zh ? `${n} 篇` : `${n} papers`,
    papers: zh ? '论文' : 'Papers',
    direct: zh ? '直接收录' : 'Directly in this topic',
    folderEmpty: zh ? '这个文件夹里还没有论文' : 'No papers in this folder yet',
    noPapers: zh ? '这个专题里还没有论文。把论文拖进文件夹后，再来和 Agent 讨论。' : 'No papers in this topic yet. Add some, then come back and talk it through.',
    allPapers: zh ? '全部论文' : 'All papers',
    back: zh ? '文献库' : 'Library',
    reading: zh ? '正在读取…' : 'Reading…',
  };

  let papers = Array.isArray(BOOT.papers) ? BOOT.papers : [];
  let folders = BOOT.folders && Array.isArray(BOOT.folders.folders)
    ? { folders: BOOT.folders.folders, of: { ...(BOOT.folders.of || {}) } }
    : { folders: [], of: {} };
  const topic = BOOT.topic || null;
  const scope = topic ? 'topic' : 'library';
  const folderId = topic ? topic.id : '';
  const KEY = `textfold.agent:${scope}:${folderId || 'all'}`;

  function under(id) {
    const out = new Set([id]);
    for (let more = true; more;) {
      more = false;
      for (const f of folders.folders) if (out.has(f.parent) && !out.has(f.id)) { out.add(f.id); more = true; }
    }
    return out;
  }
  function kids(id) { return folders.folders.filter((f) => (f.parent || null) === id); }
  function paperLabel(p) { return p.name || p.title || p.id; }
  function scopedPapers() {
    if (!topic) return papers;
    const inside = under(topic.id);
    return papers.filter((p) => inside.has(folders.of[p.id]));
  }
  function scopeText() {
    return topic ? T.topicScope(topic.name, scopedPapers().length) : T.libraryScope(papers.length);
  }

  // ── the topic page ──────────────────────────────────────────────
  function renderTopic() {
    if (!topicRoot || !topic) return;
    const title = document.getElementById('tp-title'), sub = document.getElementById('tp-sub');
    const content = document.getElementById('tp-content');
    if (title) title.textContent = topic.name;
    if (sub) sub.textContent = T.papersN(scopedPapers().length);
    document.title = `${topic.name} · TextFold`;
    for (const el of topicRoot.querySelectorAll('[data-tp="library"]')) el.textContent = T.back;
    for (const el of topicRoot.querySelectorAll('[data-tp="topic"]')) el.textContent = T.topic;
    if (!content) return;
    const inside = under(topic.id);
    const direct = papers.filter((p) => folders.of[p.id] === topic.id);
    const tree = [];
    const walk = (id, depth) => {
      for (const f of kids(id)) {
        tree.push({ f, depth });
        walk(f.id, depth + 1);
      }
    };
    walk(topic.id, 0);
    const paperCard = (p) => {
      const lang = p.langs && p.langs.includes(readLang) ? readLang : (p.langs && p.langs[0]) || 'en';
      const authors = (p.authors || []).slice(0, 3).join(', ');
      const langs = (p.langs || []).map((l) => `<span>${esc(l.toUpperCase())}</span>`).join('');
      return `<a class="tp-paper" href="/p/${encodeURIComponent(p.id)}?lang=${encodeURIComponent(lang)}">
        <span class="tp-paper-main"><span class="tp-paper-title">${esc(paperLabel(p))}</span>
        ${authors ? `<span class="tp-paper-authors">${esc(authors)}</span>` : ''}</span>
        <span class="tp-paper-meta"><span class="tp-paper-id">${esc(p.id)}</span><span class="tp-langs">${langs}</span></span>
        <span class="tp-arrow" aria-hidden="true">→</span></a>`;
    };
    if (!papers.length) {
      content.innerHTML = `<div class="tp-empty">${esc(T.noPapers)}</div>`;
      return;
    }
    let html = '';
    const hasGroups = tree.length > 0;
    if (direct.length) {
      html += `<section class="tp-group"><div class="tp-group-head"><h2>${esc(hasGroups ? T.direct : T.allPapers)}</h2><span>${direct.length}</span></div>
        <div class="tp-papers">${direct.map(paperCard).join('')}</div></section>`;
    }
    for (const { f, depth } of tree) {
      const ps = papers.filter((p) => folders.of[p.id] === f.id);
      if (!ps.length) continue;
      html += `<section class="tp-group" style="--d:${depth}">
        <div class="tp-group-head"><h2>${esc(f.name)}</h2><span>${ps.length}</span></div>
        <div class="tp-papers">${ps.map(paperCard).join('')}</div></section>`;
    }
    content.innerHTML = html || `<div class="tp-empty">${esc(T.noPapers)}</div>`;
  }

  // ── the drawer ──────────────────────────────────────────────────
  let history = [];
  try {
    const saved = JSON.parse(store.get(KEY) || '[]');
    if (Array.isArray(saved)) history = saved.slice(-20);
  } catch { /* private window, or an old shape */ }
  const drawer = document.createElement('aside');
  drawer.className = 'agent-drawer';
  drawer.hidden = true;
  drawer.setAttribute('aria-label', T.agent);
  drawer.innerHTML = `<header class="ag-head">
      <div class="ag-heading"><span class="agent-orbit" aria-hidden="true"><i></i></span><b>${T.agent}</b></div>
      <div class="ag-head-acts"><button type="button" class="ag-clear" title="${esc(T.clear)}" aria-label="${esc(T.clear)}">
        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 5.5h12M8 5.5V4h4v1.5M6.5 5.5l.7 10h5.6l.7-10" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button><button type="button" class="ag-x" aria-label="${esc(T.close)}" title="${esc(T.close)}">
        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M6 6l8 8M14 6l-8 8" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>
      </button></div>
    </header>
    <div class="ag-context"><span class="ag-scope-chip"><span class="agent-orbit small" aria-hidden="true"><i></i></span><span class="ag-scope-text"></span></span></div>
    <div class="ag-body" role="log" aria-live="polite"></div>
    <form class="ag-compose"><textarea class="ag-input" rows="1" maxlength="4000" placeholder="${esc(topic ? T.placeholderTopic : T.placeholder)}" aria-label="${esc(topic ? T.placeholderTopic : T.placeholder)}"></textarea>
      <button type="submit" class="ag-send" aria-label="${esc(T.send)}" title="${esc(T.send)}"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3.2 10h13M11 4.8l5.2 5.2-5.2 5.2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></button></form>`;
  document.body.append(drawer);
  const body = drawer.querySelector('.ag-body');
  const field = drawer.querySelector('.ag-input');
  const scopeEl = drawer.querySelector('.ag-scope-text');
  let busy = false;

  function trigger() {
    if (landing) {
      const top = document.querySelector('.ui-top');
      if (!top) return null;
      let b = top.querySelector('.agent-open');
      if (!b) {
        b = document.createElement('button');
        b.type = 'button';
        b.className = 'agent-open';
        b.setAttribute('aria-expanded', 'false');
        b.innerHTML = `<span class="agent-orbit" aria-hidden="true"><i></i></span><span>${T.agent}</span>`;
        top.prepend(b);
      }
      return b;
    }
    return document.getElementById('agent-open');
  }
  const openButton = trigger();

  function md(text) {
    let s = esc(text).replace(/\r\n?/g, '\n');
    s = s.replace(/```([\s\S]*?)```/g, (_, code) => `<pre><code>${code.replace(/\n$/, '')}</code></pre>`);
    s = s.replace(/`([^`\n]+)`/g, '<code>$1</code>');
    s = s.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/\[([^\]\n]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    const lines = s.split('\n'), out = [];
    let list = null;
    const close = () => { if (list) { out.push(`</${list}>`); list = null; } };
    for (const line of lines) {
      const bullet = /^\s*[-*]\s+(.*)$/.exec(line), num = /^\s*\d+[.)]\s+(.*)$/.exec(line);
      if (bullet || num) {
        const kind = bullet ? 'ul' : 'ol';
        if (list !== kind) { close(); out.push(`<${kind}>`); list = kind; }
        out.push(`<li>${(bullet || num)[1]}</li>`);
      } else if (!line.trim()) {
        close(); out.push('');
      } else if (/^#{1,3}\s+/.test(line)) {
        close();
        const m = /^(#{1,3})\s+(.*)$/.exec(line);
        out.push(`<h4>${m[2]}</h4>`);
      } else {
        close(); out.push(`<p>${line}</p>`);
      }
    }
    close();
    return out.join('');
  }

  function actionLine(a) {
    const names = (a.papers || []).map((p) => `<b>${esc(p.title)}</b>`).join(zh ? '、' : ', ');
    if (a.op === 'new_folder') {
      const where = a.parent ? `${T.into} <b>${esc(a.parent.name)}</b>` : T.topLevel;
      return `<span class="ag-act-kind">${T.newFolder}</span><span><b>${esc(a.name)}</b> · ${where}${names ? ` · ${names}` : ''}</span>`;
    }
    if (a.op === 'move_papers') {
      const where = a.folder ? `<b>${esc(a.folder.name)}</b>` : T.topLevel;
      return `<span class="ag-act-kind">${T.movePapers}</span><span>${names} → ${where}</span>`;
    }
    if (a.op === 'rename_paper') {
      return `<span class="ag-act-kind">${T.renamePaper}</span><span><b>${esc(a.paper.title)}</b> → <b>${esc(a.name)}</b></span>`;
    }
    return `<span class="ag-act-kind">${T.renameFolder}</span><span><b>${esc(a.folder.name)}</b> → <b>${esc(a.name)}</b></span>`;
  }

  function save() { store.set(KEY, JSON.stringify(history.slice(-20))); }

  function render() {
    scopeEl.textContent = scopeText();
    if (!history.length) {
      const starters = topic ? T.startersTopic : T.startersLib;
      body.innerHTML = `<div class="ag-empty"><p>${esc(T.empty)}</p><div class="ag-starters"><span>${esc(T.starts)}</span>${starters.map((q) =>
        `<button type="button" class="ag-start" data-q="${esc(q)}">${esc(q)}</button>`).join('')}</div></div>`;
      return;
    }
    body.innerHTML = history.map((t, i) => `<div class="ag-turn${t.pending ? ' pending' : ''}" data-i="${i}">
      <div class="ag-q">${esc(t.q)}</div>
      <div class="ag-a">${t.pending ? `<span class="ag-thinking"><i></i><i></i><i></i>${esc(T.thinking)}</span>`
        : t.error ? `<div class="ag-error">${esc(t.error)}</div>` : md(t.a || '')}</div>
      ${!t.pending && t.actions && t.actions.length ? `<div class="ag-actions">
        <div class="ag-actions-head">${esc(T.proposed)}</div>
        ${t.actions.map((a) => `<div class="ag-action">${actionLine(a)}</div>`).join('')}
        ${t.applied ? `<div class="ag-applied">${esc(T.applied(t.applied))}</div>`
          : t.dismissed ? `<div class="ag-dismissed">${esc(T.dismissed)}</div>`
          : `<div class="ag-actions-foot"><button type="button" class="ag-apply" data-i="${i}">${esc(T.apply)}</button>
             <button type="button" class="ag-dismiss" data-i="${i}">${esc(T.dismiss)}</button></div>`}
      </div>` : ''}
    </div>`).join('');
    body.scrollTop = body.scrollHeight;
  }

  function open() {
    drawer.hidden = false;
    openButton?.setAttribute('aria-expanded', 'true');
    document.documentElement.classList.add('agent-open-panel');
    render();
    requestAnimationFrame(() => field.focus());
  }
  function close() {
    drawer.hidden = true;
    openButton?.setAttribute('aria-expanded', 'false');
    document.documentElement.classList.remove('agent-open-panel');
  }
  function toggle() { if (drawer.hidden) open(); else close(); }
  openButton?.addEventListener('click', toggle);
  drawer.querySelector('.ag-x').addEventListener('click', close);
  drawer.querySelector('.ag-clear').addEventListener('click', () => {
    if (busy || !history.length) return;
    history = [];
    save();
    render();
  });
  addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' || drawer.hidden) return;
    if (document.querySelector('dialog[open]')) return;
    close();
  });

  body.addEventListener('click', (e) => {
    const start = e.target.closest('.ag-start');
    if (start) { field.value = start.dataset.q || ''; send(); return; }
    const apply = e.target.closest('.ag-apply');
    if (apply) { applyActions(+apply.dataset.i); return; }
    const dismiss = e.target.closest('.ag-dismiss');
    if (dismiss) {
      const t = history[+dismiss.dataset.i];
      if (t) { t.actions = []; t.dismissed = true; save(); render(); }
    }
  });

  async function api(path, body) {
    const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || r.statusText);
    return d;
  }

  async function send() {
    const q = field.value.trim();
    if (!q || busy) return;
    field.value = '';
    resize();
    busy = true;
    const turn = { q, a: '', pending: true };
    history.push(turn);
    save();
    render();
    try {
      const earlier = history.filter((t) => t !== turn && t.a && !t.pending).slice(-6).map((t) => ({ q: t.q, a: t.a }));
      const d = await api('/api/agent', { scope, folder: folderId, question: q, ui, history: earlier });
      turn.a = d.answer || '';
      turn.actions = Array.isArray(d.actions) ? d.actions : [];
      turn.pending = false;
    } catch (err) {
      turn.error = String(err.message || err).slice(0, 500);
      turn.pending = false;
    } finally {
      busy = false;
      save();
      render();
      field.focus();
    }
  }

  async function applyActions(i) {
    const t = history[i];
    if (!t || !t.actions || busy) return;
    busy = true;
    const count = t.actions.length;
    try {
      const d = await api('/api/agent/apply', { actions: t.actions });
      papers = d.papers || papers;
      folders = d.folders || folders;
      t.applied = count;
      t.actions = [];
      save();
      render();
      renderTopic();
      dispatchEvent(new CustomEvent('tf-library', { detail: { papers, folders } }));
    } catch (err) {
      t.error = T.applyFailed + String(err.message || err).slice(0, 400);
      save();
      render();
    } finally {
      busy = false;
    }
  }

  function resize() {
    field.style.height = 'auto';
    field.style.height = `${Math.min(160, field.scrollHeight)}px`;
  }
  field.addEventListener('input', resize);
  field.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' || e.shiftKey || e.isComposing) return;
    e.preventDefault();
    send();
  });
  drawer.querySelector('.ag-compose').addEventListener('submit', (e) => { e.preventDefault(); send(); });

  renderTopic();
  render();
  addEventListener('tf-library', (e) => {
    if (e.detail?.papers) papers = e.detail.papers;
    if (e.detail?.folders) folders = e.detail.folders;
    renderTopic();
    if (!drawer.hidden) { scopeEl.textContent = scopeText(); }
  });
  window.TFAgent = { open, close, toggle, render: () => { renderTopic(); if (!drawer.hidden) render(); } };
})();
