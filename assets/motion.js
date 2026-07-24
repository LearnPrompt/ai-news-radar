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
          delay: Math.min(index * 28, 240),
          easing: "cubic-bezier(.2,.8,.2,1)",
        },
      );
    });
  }

  document.addEventListener("aiRadar:listRendered", () => {
    animateTransform(document.querySelectorAll(".timeline-item, .news-card"), 9, 300);
  });

  const sections = document.querySelectorAll(".waytoagi-wrap, .list-wrap");
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
