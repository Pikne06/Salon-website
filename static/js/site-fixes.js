// Toggle and close the nav menu to prevent overlays blocking inputs
(function(){
  function getMenus() {
    return Array.prototype.slice.call(document.querySelectorAll('.nav-menu'));
  }

  function setExpanded(menu, expanded) {
    var btn = menu.querySelector('.nav-menu-trigger');
    if (btn) btn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
  }

  function closeMenu(menu) {
    if (!menu) return;
    menu.classList.remove('open');
    setExpanded(menu, false);
  }

  function closeAll() {
    getMenus().forEach(closeMenu);
  }

  function openMenu(menu) {
    if (!menu) return;
    menu.classList.add('open');
    setExpanded(menu, true);
  }

  document.addEventListener('click', function(e){
    var trigger = e.target.closest('.nav-menu-trigger');
    if (trigger) {
      var menu = trigger.closest('.nav-menu');
      if (!menu) return;
      e.preventDefault();
      var wasOpen = menu.classList.contains('open');
      closeAll();
      if (!wasOpen) openMenu(menu);
      return;
    }

    if (e.target.closest('.nav-menu-panel a')) {
      closeAll();
      return;
    }

    if (!e.target.closest('.nav-menu')) {
      closeAll();
    }
  });

  window.addEventListener('scroll', function(){ closeAll(); }, {passive:true});

  document.addEventListener('focusin', function(e){
    var t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'SELECT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) {
      closeAll();
    }
  });

  document.addEventListener('keydown', function(e){
    if (e.key === 'Escape') closeAll();
  });
})();
