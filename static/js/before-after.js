(function() {
  function initSlider(wrapper) {
    var range = wrapper.querySelector('.before-after__range');
    if (!range) return;
    function update() {
      wrapper.style.setProperty('--position', range.value + '%');
    }
    range.addEventListener('input', update);
    update();
  }

  document.addEventListener('DOMContentLoaded', function() {
    var sliders = document.querySelectorAll('.before-after');
    for (var i = 0; i < sliders.length; i += 1) {
      initSlider(sliders[i]);
    }
  });
})();
