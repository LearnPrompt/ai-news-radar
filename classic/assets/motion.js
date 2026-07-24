(() => {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  function animateTransform(elements, distance = 12, duration = 360) {
    Array.from(elements).forEach((element, index) => {
      if (typeof element.animate !== "function") return;
      element.getAnimations().forEach((animation) => animation.cancel());
      element.animate(
        [
          { transform: `translateY(${distance}px)` },
          { transform: "translateY(0)" },
        ],
        {
          duration,
          delay: Math.min(index * 30, 240),
          easing: "cubic-bezier(.2,.8,.2,1)",
        },
      );
    });
  }

  document.addEventListener("aiRadar:ready", () => {
    // The identity header stays stationary so the view switch never jumps.
    animateTransform(document.querySelectorAll(".stat, .section-tab"), 9, 320);
    animateTransform(
      document.querySelectorAll(".section-summary, .primary-controls, .advanced-panel"),
      7,
      300,
    );
  }, { once: true });

  document.addEventListener("aiRadar:briefRendered", () => {
    animateTransform(
      document.querySelectorAll(".top-story-card, .story-row, .bole-row"),
      9,
      280,
    );
  });

  document.addEventListener("aiRadar:listRendered", () => {
    animateTransform(
      Array.from(document.querySelectorAll(".intel-card, .news-card")).slice(0, 30),
      9,
      300,
    );
  });

  const sections = document.querySelectorAll(".bole-picks-wrap, .waytoagi-wrap, .list-wrap");
  if (!sections.length || !window.IntersectionObserver) return;
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      animateTransform([entry.target], 12, 340);
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.08 });
  sections.forEach((section) => observer.observe(section));
})();
