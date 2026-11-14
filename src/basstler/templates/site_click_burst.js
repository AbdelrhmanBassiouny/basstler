(function () {
  "use strict";
  var root = document.documentElement;
  var stillness = window.matchMedia("(prefers-reduced-motion: reduce)");

  function between(low, high) {
    return low + Math.random() * (high - low);
  }

  function throwParticle(x, y, reach) {
    var particle = document.createElement("span");
    var angle = between(0, 2 * Math.PI);
    var distance = between(0.35, 1) * reach;
    particle.className = "burst-particle";
    particle.style.setProperty("--burst-x", x + "px");
    particle.style.setProperty("--burst-y", y + "px");
    particle.style.setProperty("--burst-dx", Math.cos(angle) * distance + "px");
    particle.style.setProperty("--burst-dy", Math.sin(angle) * distance + "px");
    particle.style.setProperty("--burst-spin", between(-320, 320) + "deg");
    particle.style.setProperty("--burst-scale", between(0.6, 1.25));
    particle.addEventListener("animationend", function () { particle.remove(); });
    document.body.appendChild(particle);
  }

  document.addEventListener("pointerdown", function (event) {
    var style = window.getComputedStyle(root);
    var count = parseInt(style.getPropertyValue("--burst-count"), 10) || 0;
    if (stillness.matches || !event.target.closest("button, select")) {
      return;
    }
    for (var thrown = 0; thrown < count; thrown += 1) {
      throwParticle(event.clientX, event.clientY, parseFloat(style.getPropertyValue("--burst-reach")));
    }
  });
})();
