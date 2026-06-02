(function () {
  if (!window.gsap) return;

  const mm = gsap.matchMedia();

  mm.add("(prefers-reduced-motion: no-preference)", function () {
    gsap.defaults({ duration: 0.55, ease: "power3.out" });

    // Page intro timeline
    const tl = gsap.timeline();
    tl.from(".hero-headline", { autoAlpha: 0, y: 18, duration: 0.5 })
      .from(".hero-sub", { autoAlpha: 0, y: 10, duration: 0.4 }, "-=0.2")
      .from(".hero-meta", { autoAlpha: 0, y: 10, duration: 0.4 }, "-=0.25")
      .from(".stat", { autoAlpha: 0, y: 14, scale: 0.98, stagger: 0.06, duration: 0.45 }, "-=0.15")
      .from(".coverage-card", { autoAlpha: 0, y: 10, stagger: 0.045, duration: 0.4 }, "-=0.2")
      .from(".primary-controls", { autoAlpha: 0, y: 8, duration: 0.4 }, "-=0.15")
      .from(".advanced-panel", { autoAlpha: 0, y: 8, duration: 0.4 }, "-=0.3");

    // Daily Brief is display:none until data arrives, so animate it only after render.
    document.addEventListener("aiRadar:briefRendered", function () {
      const brief = document.querySelector(".daily-brief");
      const cards = document.querySelectorAll(".story-card");
      if (brief) {
        gsap.fromTo(brief, { autoAlpha: 0, y: 16 }, { autoAlpha: 1, y: 0, duration: 0.45, clearProps: "transform" });
      }
      if (!cards.length) return;
      gsap.from(cards, { autoAlpha: 0, y: 16, scale: 0.98, stagger: 0.06, duration: 0.5, clearProps: "transform" });
    });

    // List: animate first 30 visible cards on render/mode switch
    document.addEventListener("aiRadar:listRendered", function () {
      const cards = Array.from(document.querySelectorAll(".news-card")).slice(0, 30);
      if (!cards.length) return;
      gsap.from(cards, { autoAlpha: 0, y: 12, stagger: 0.03, duration: 0.4, clearProps: "transform" });
    });

    // Section scroll reveal via IntersectionObserver
    const revealEls = document.querySelectorAll(".waytoagi-wrap, .list-wrap");
    if (revealEls.length && window.IntersectionObserver) {
      gsap.set(revealEls, { autoAlpha: 0, y: 20 });
      const observer = new IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            gsap.to(entry.target, { autoAlpha: 1, y: 0, duration: 0.55, clearProps: "transform" });
            observer.unobserve(entry.target);
          }
        });
      }, { threshold: 0.08 });
      revealEls.forEach(function (el) { observer.observe(el); });
    }
  });
}());
