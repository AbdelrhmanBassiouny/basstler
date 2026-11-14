(function () {
  "use strict";
  var choices = {{ appearance.viewer_choices | tojson }};
  var root = document.documentElement;

  function storedValue(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (error) {
      return null;
    }
  }

  function keep(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (error) {
      // Without storage the pick lasts until the page is left.
    }
  }

  choices.forEach(function (choice) {
    var stored = storedValue(choice.storage_key);
    var known = choice.options.some(function (option) { return option.value === stored; });
    if (known) {
      root.setAttribute(choice.attribute, stored);
    }
  });

  document.addEventListener("DOMContentLoaded", function () {
    choices.forEach(function (choice) {
      var menu = document.querySelector('select[name="' + choice.attribute + '"]');
      if (!menu) {
        return;
      }
      menu.value = root.getAttribute(choice.attribute);
      menu.addEventListener("change", function () {
        root.setAttribute(choice.attribute, menu.value);
        keep(choice.storage_key, menu.value);
      });
    });
  });
})();
