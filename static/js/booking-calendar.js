(function() {
  function setValue(id, value) {
    var el = document.getElementById(id);
    if (el) {
      el.value = value;
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }

  document.addEventListener('click', function(e) {
    var nextBtn = e.target.closest('#select-next-slot');
    if (nextBtn) {
      var nextDate = nextBtn.getAttribute('data-date');
      var nextTime = nextBtn.getAttribute('data-time');
      var nextTech = nextBtn.getAttribute('data-tech-id');
      if (nextDate) setValue('date', nextDate);
      if (nextTime) setValue('time', nextTime);
      if (nextTech !== null) setValue('technician_id', nextTech);
      var match = document.querySelector('.slot-button[data-date="' + nextDate + '"][data-time="' + nextTime + '"][data-tech-id="' + nextTech + '"]');
      if (match) {
        document.querySelectorAll('.slot-button').forEach(function(b) {
          b.classList.remove('selected');
        });
        match.classList.add('selected');
      }
      var formPanel = document.querySelector('.form-panel');
      if (formPanel) formPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
    var btn = e.target.closest('.slot-button');
    if (!btn) return;
    var date = btn.getAttribute('data-date');
    var time = btn.getAttribute('data-time');
    var techId = btn.getAttribute('data-tech-id');
    if (date) setValue('date', date);
    if (time) setValue('time', time);
    if (techId) setValue('technician_id', techId);
    document.querySelectorAll('.slot-button').forEach(function(b) {
      b.classList.remove('selected');
    });
    btn.classList.add('selected');
    var form = document.querySelector('.form-panel');
    if (form) form.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
})();
