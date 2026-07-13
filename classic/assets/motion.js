(function () {
  if (!window.gsap) return;

  const mm = gsap.matchMedia();

  mm.add("(prefers-reduced-motion: no-preference)", function () {
    gsap.defaults({ duration: 0.55, ease: "power3.out" });

    // Stats and section tabs are data-driven. Wait until app.js has rendered
    // them so GSAP never tries to animate missing targets on first load.
    document.addEventListener("aiRadar:ready", function () {
      const tl = gsap.timeline();
      const addFrom = function (selector, vars, position) {
        if (document.querySelector(selector)) tl.from(selector, vars, position);
      };
      addFrom(".hero-headline", { autoAlpha: 0, y: 18, duration: 0.5 });
      addFrom(".hero-sub", { autoAlpha: 0, y: 10, duration: 0.4 }, "-=0.2");
      addFrom(".hero-meta", { autoAlpha: 0, y: 10, duration: 0.4 }, "-=0.25");
      addFrom(".stat", { autoAlpha: 0, y: 14, scale: 0.98, stagger: 0.06, duration: 0.45 }, "-=0.15");
      addFrom(".section-tab", { autoAlpha: 0, y: 10, stagger: 0.045, duration: 0.4 }, "-=0.2");
      addFrom(".section-summary", { autoAlpha: 0, y: 8, duration: 0.35 }, "-=0.25");
      addFrom(".primary-controls", { autoAlpha: 0, y: 8, duration: 0.4 }, "-=0.15");
      addFrom(".advanced-panel", { autoAlpha: 0, y: 8, duration: 0.4 }, "-=0.3");
    }, { once: true });

    // Top stories render after data loads; keep legacy selectors for old data views.
    document.addEventListener("aiRadar:briefRendered", function () {
      const brief = document.querySelector(".bole-picks-wrap");
      const cards = Array.from(document.querySelectorAll(".top-story-card, .story-row, .bole-row")).slice(0, 24);
      if (brief) {
        gsap.fromTo(brief, { y: 12 }, { y: 0, duration: 0.35, clearProps: "transform" });
      }
      if (!cards.length) return;
      gsap.killTweensOf(cards);
      gsap.set(cards, { clearProps: "transform" });
      gsap.from(cards, { autoAlpha: 0, stagger: 0.035, duration: 0.28, clearProps: "opacity,visibility" });
    });

    // List: animate first 30 visible cards on render/mode switch
    document.addEventListener("aiRadar:listRendered", function () {
      const cards = Array.from(document.querySelectorAll(".intel-card, .news-card")).slice(0, 30);
      if (!cards.length) return;
      gsap.from(cards, { autoAlpha: 0, y: 12, stagger: 0.03, duration: 0.4, clearProps: "transform,opacity,visibility" });
    });

    // Section scroll reveal via IntersectionObserver. Keep sections visible:
    // hiding whole content blocks can leave blank viewports after responsive
    // reflow or rapid mobile scrolling.
    const revealEls = document.querySelectorAll(".bole-picks-wrap, .waytoagi-wrap, .list-wrap");
    if (revealEls.length && window.IntersectionObserver) {
      gsap.set(revealEls, { y: 14 });
      const observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            gsap.to(entry.target, { y: 0, duration: 0.45, clearProps: "transform" });
            observer.unobserve(entry.target);
          }
        });
      }, { threshold: 0.08 });
      revealEls.forEach(function (el) { observer.observe(el); });
    }
  });
}());
