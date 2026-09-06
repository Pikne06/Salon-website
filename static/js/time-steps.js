(function() {
  function parseSteps(raw) {
    if (!raw) return [0, 15, 30];
    return raw
      .split(',')
      .map(function(part) { return parseInt(part.trim(), 10); })
      .filter(function(val) { return !isNaN(val); });
  }

  function pad2(value) {
    return value < 10 ? '0' + value : String(value);
  }

  function parseTime(raw) {
    if (!raw) return null;
    var parts = raw.split(':');
    if (parts.length < 2) return null;
    var hour = parseInt(parts[0], 10);
    var minute = parseInt(parts[1], 10);
    if (isNaN(hour) || isNaN(minute)) return null;
    return { hour: hour, minute: minute };
  }

  function buildOption(value, label) {
    var option = document.createElement('option');
    option.value = value;
    option.textContent = label;
    return option;
  }

  function upgradeTimeInput(input) {
    if (input.dataset.timeSelectBound === '1') return;
    input.dataset.timeSelectBound = '1';

    var steps = parseSteps(input.getAttribute('data-minute-steps'));
    var required = !!input.required;
    var minTime = parseTime(input.getAttribute('min'));
    var maxTime = parseTime(input.getAttribute('max'));
    var minHour = minTime ? minTime.hour : 0;
    var maxHour = maxTime ? maxTime.hour : 23;

    var hourSelect = document.createElement('select');
    var minuteSelect = document.createElement('select');
    hourSelect.className = 'time-select time-select-hour';
    minuteSelect.className = 'time-select time-select-minute';

    if (required) {
      hourSelect.appendChild(buildOption('', 'HH'));
    }
    for (var h = minHour; h <= maxHour; h += 1) {
      hourSelect.appendChild(buildOption(pad2(h), pad2(h)));
    }

    function rebuildMinuteOptions() {
      var currentHour = hourSelect.value;
      var prevValue = minuteSelect.value;
      minuteSelect.innerHTML = '';
      if (required) {
        minuteSelect.appendChild(buildOption('', 'MM'));
      }
      if (!currentHour) {
        return;
      }
      var hourNum = parseInt(currentHour, 10);
      var allowed = steps.slice();
      if (minTime && hourNum === minTime.hour) {
        allowed = allowed.filter(function(val) { return val >= minTime.minute; });
      }
      if (maxTime && hourNum === maxTime.hour) {
        allowed = allowed.filter(function(val) { return val <= maxTime.minute; });
      }
      if (!allowed.length) {
        allowed = steps.slice();
      }
      allowed.forEach(function(val) {
        minuteSelect.appendChild(buildOption(pad2(val), pad2(val)));
      });
      if (prevValue && Array.prototype.some.call(minuteSelect.options, function(opt) { return opt.value === prevValue; })) {
        minuteSelect.value = prevValue;
      } else if (!required && allowed.length) {
        minuteSelect.value = pad2(allowed[0]);
      }
    }

    var syncing = false;
    function syncInputFromSelects() {
      if (syncing) return;
      syncing = true;
      if (!hourSelect.value || !minuteSelect.value) {
        input.value = '';
      } else {
        input.value = hourSelect.value + ':' + minuteSelect.value;
      }
      input.dispatchEvent(new Event('change', { bubbles: true }));
      syncing = false;
    }

    function syncSelectsFromInput() {
      if (syncing) return;
      var parsed = parseTime(input.value);
      if (!parsed) {
        if (required) {
          hourSelect.value = '';
          minuteSelect.value = '';
        }
        return;
      }
      syncing = true;
      hourSelect.value = pad2(parsed.hour);
      rebuildMinuteOptions();
      minuteSelect.value = pad2(parsed.minute);
      syncing = false;
    }

    rebuildMinuteOptions();

    hourSelect.addEventListener('change', function() {
      rebuildMinuteOptions();
      syncInputFromSelects();
    });
    minuteSelect.addEventListener('change', syncInputFromSelects);
    input.addEventListener('change', syncSelectsFromInput);

    var wrapper = document.createElement('div');
    wrapper.className = 'time-selects';
    wrapper.appendChild(hourSelect);
    var separator = document.createElement('span');
    separator.className = 'time-select-separator';
    separator.textContent = ':';
    wrapper.appendChild(separator);
    wrapper.appendChild(minuteSelect);

    var label = document.querySelector('label[for="' + input.id + '"]');
    if (label) {
      hourSelect.id = input.id + '_hour';
      label.setAttribute('for', hourSelect.id);
    }

    input.required = false;
    input.classList.add('time-input-hidden');
    input.insertAdjacentElement('afterend', wrapper);

    syncSelectsFromInput();
  }

  document.addEventListener('DOMContentLoaded', function() {
    var inputs = document.querySelectorAll('input[type="time"][data-minute-steps]');
    for (var i = 0; i < inputs.length; i += 1) {
      upgradeTimeInput(inputs[i]);
    }
  });
})();
