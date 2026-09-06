document.addEventListener('DOMContentLoaded', function () {
  const container = document.getElementById('gallery-photos');
  if (!container) return;

  let dragSrcEl = null;

  function handleDragStart(e) {
    dragSrcEl = this;
    e.dataTransfer.effectAllowed = 'move';
    try { e.dataTransfer.setData('text/plain', this.dataset.id); } catch (ex) {}
    this.classList.add('dragging');
    // set custom drag image (ghost)
    try {
      const img = this.querySelector('img');
      if (img) {
        const ghost = img.cloneNode(true);
        ghost.classList.add('drag-ghost');
        ghost.style.width = '220px';
        ghost.style.opacity = '0.95';
        ghost.style.position = 'absolute';
        ghost.style.top = '-1000px';
        document.body.appendChild(ghost);
        e.dataTransfer.setDragImage(ghost, 110, 55);
        setTimeout(() => document.body.removeChild(ghost), 300);
      }
    } catch (ex) {}
    // ensure placeholder exists while dragging
    ensurePlaceholder();
  }

  function handleDragOver(e) {
    if (e.preventDefault) e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    return false;
  }

  function handleDragEnter() {
    this.classList.add('over');
    const ph = getPlaceholder();
    if (ph && this.parentNode === container) {
      container.insertBefore(ph, this);
    }
  }

  function handleDragLeave() {
    this.classList.remove('over');
    const ph = getPlaceholder();
    if (ph && ph.parentNode === container) {
      container.removeChild(ph);
    }
  }

  function handleDrop(e) {
    if (e.stopPropagation) e.stopPropagation();
    if (dragSrcEl !== this) {
      // swap nodes
      const src = dragSrcEl;
      const tgt = this;
      const parent = container;
      parent.insertBefore(src, tgt);
    }
    return false;
  }

  function handleDragEnd() {
    const items = container.querySelectorAll('.gallery-card');
    items.forEach(function (it) {
      it.classList.remove('over');
      it.classList.remove('dragging');
    });
    // remove placeholder and send order to server
    const ph = getPlaceholder();
    if (ph && ph.parentNode === container) container.removeChild(ph);
    saveOrder();
  }

  // Touch support: long-press to start drag, then move
  let touchSrc = null;
  let touchTimer = null;
  function onTouchStart(e) {
    const card = this;
    touchTimer = setTimeout(() => {
      touchSrc = card;
      card.classList.add('dragging');
      ensurePlaceholder();
    }, 220);
  }
  function onTouchMove(e) {
    if (!touchSrc) return;
    const touch = e.touches[0];
    const el = document.elementFromPoint(touch.clientX, touch.clientY);
    if (!el) return;
    const card = el.closest('.gallery-card');
    if (card && card !== touchSrc) {
      container.insertBefore(touchSrc, card);
    }
    e.preventDefault();
  }
  function onTouchEnd(e) {
    clearTimeout(touchTimer);
    if (!touchSrc) return;
    touchSrc.classList.remove('dragging');
    touchSrc = null;
    const ph = getPlaceholder();
    if (ph && ph.parentNode === container) container.removeChild(ph);
    saveOrder();
  }

  function saveOrder() {
    const items = Array.from(container.querySelectorAll('.gallery-card'));
    const ids = items.map(i => i.dataset.id).filter(Boolean);
    if (!ids.length) return;
    // find a csrf token from the page
    const tokenInput = document.querySelector('input[name="csrf_token"]');
    const csrf = tokenInput ? tokenInput.value : '';
    const body = new URLSearchParams();
    body.append('csrf_token', csrf);
    body.append('action', 'reorder');
    body.append('order', ids.join(','));
    // include service scope if present
    const svcSel = document.querySelector('select[name="service_id"]');
    if (svcSel) body.append('service_id', svcSel.value);
    fetch(window.location.pathname, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
      credentials: 'same-origin'
    }).then(resp => {
      if (!resp.ok) console.warn('Failed to save gallery order');
      showSavedToast();
      return resp.text();
    }).catch(err => console.error(err));
  }

  function ensurePlaceholder() {
    if (!getPlaceholder()) {
      const ph = document.createElement('div');
      ph.className = 'gallery-placeholder gallery-card col-md-3 mb-3';
      ph.innerHTML = '<div class="card"><div style="height:160px;display:flex;align-items:center;justify-content:center;background:#eef;">Drop here</div></div>';
      container.appendChild(ph);
    }
  }

  function getPlaceholder() {
    return container.querySelector('.gallery-placeholder');
  }

  function showSavedToast() {
    let t = document.getElementById('admin-gallery-toast');
    if (!t) {
      t = document.createElement('div');
      t.id = 'admin-gallery-toast';
      t.className = 'admin-gallery-toast';
      t.innerText = 'Order saved';
      document.body.appendChild(t);
    }
    t.classList.add('visible');
    setTimeout(() => t.classList.remove('visible'), 1600);
  }

  const cards = container.querySelectorAll('.gallery-card');
  cards.forEach(function (card) {
    card.addEventListener('dragstart', handleDragStart, false);
    card.addEventListener('dragenter', handleDragEnter, false);
    card.addEventListener('dragover', handleDragOver, false);
    card.addEventListener('dragleave', handleDragLeave, false);
    card.addEventListener('drop', handleDrop, false);
    card.addEventListener('dragend', handleDragEnd, false);
    // make only the handle start touch/drag for better UX
    const handle = card.querySelector('.drag-handle');
    if (handle) {
      handle.style.touchAction = 'none';
      handle.addEventListener('touchstart', function (ev) { onTouchStart.call(card, ev); }, {passive:false});
      handle.addEventListener('touchmove', function (ev) { onTouchMove.call(card, ev); }, {passive:false});
      handle.addEventListener('touchend', function (ev) { onTouchEnd.call(card, ev); }, {passive:false});
      // also allow mouse drag when starting from handle by forwarding events
      handle.addEventListener('mousedown', function () { try { card.draggable = true; } catch(e){} });
      handle.addEventListener('mouseup', function () { try { card.draggable = true; } catch(e){} });
    }
    // keyboard accessibility: focusable and keyboard reordering
    card.addEventListener('keydown', function (ev) {
      handleKeyDown.call(card, ev);
    });
  });

  function handleKeyDown(e) {
    const el = this;
    const grabbed = el.getAttribute('aria-grabbed') === 'true';
    if (e.key === ' ' || e.key === 'Spacebar') {
      e.preventDefault();
      // toggle grab
      if (!grabbed) {
        el.setAttribute('aria-grabbed', 'true');
        el.classList.add('dragging');
        ensurePlaceholder();
      } else {
        el.setAttribute('aria-grabbed', 'false');
        el.classList.remove('dragging');
        const ph = getPlaceholder(); if (ph && ph.parentNode === container) container.removeChild(ph);
        saveOrder();
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const prev = el.previousElementSibling;
      if (prev && prev.classList && prev.classList.contains('gallery-card')) {
        container.insertBefore(el, prev);
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      const next = el.nextElementSibling;
      if (next && next.classList && next.classList.contains('gallery-card')) {
        container.insertBefore(next, el);
      }
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (grabbed) {
        el.setAttribute('aria-grabbed', 'false');
        el.classList.remove('dragging');
        const ph = getPlaceholder(); if (ph && ph.parentNode === container) container.removeChild(ph);
        saveOrder();
      }
    } else if (e.key === 'Escape') {
      if (grabbed) {
        el.setAttribute('aria-grabbed', 'false');
        el.classList.remove('dragging');
        const ph = getPlaceholder(); if (ph && ph.parentNode === container) container.removeChild(ph);
      }
    }
  }
});
