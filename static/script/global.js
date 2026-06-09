document.addEventListener("DOMContentLoaded", () => {
  const root = document.documentElement;
  const menuToggle = document.querySelector(".menu-toggle");
  const siteMenu = document.querySelector("#site-menu");
  const themeBtn = document.querySelector(".theme-toggle");
  const dropdowns = document.querySelectorAll(".dropdown");

  function updateProgressBar() {
    const progress = document.getElementById("progress");
    if (!progress) return;

    const scrollTop = window.scrollY || document.documentElement.scrollTop;
    const docHeight = document.documentElement.scrollHeight - window.innerHeight;
    const progressValue = docHeight > 0 ? (scrollTop / docHeight) * 100 : 0;
    progress.style.width = progressValue + "%";
  }

  function initFadeIn() {
    const els = document.querySelectorAll(".fade-in");
    if (!els.length) return;

    if (!("IntersectionObserver" in window)) {
      els.forEach((el) => el.classList.add("in", "is-visible"));
      return;
    }

    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("in", "is-visible");
        }
      });
    }, { threshold: 0.12 });

    els.forEach((el) => io.observe(el));
  }

  function syncThemeButtonUI() {
    if (!themeBtn) return;
    const current = root.getAttribute("data-theme") || "light";
    themeBtn.textContent = current === "dark" ? "🌙" : "☀️";
    themeBtn.setAttribute(
      "aria-label",
      current === "dark" ? "Увімкнути світлу тему" : "Увімкнути темну тему"
    );
  }

  function initTheme() {
    const systemTheme = window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";

    if (!root.getAttribute("data-theme")) {
      root.setAttribute("data-theme", systemTheme);
    }

    syncThemeButtonUI();

    if (themeBtn) {
      themeBtn.addEventListener("click", () => {
        const current = root.getAttribute("data-theme") === "dark" ? "dark" : "light";
        const next = current === "dark" ? "light" : "dark";
        root.setAttribute("data-theme", next);
        syncThemeButtonUI();
      });
    }
  }

  function closeAllDropdowns(except = null) {
    dropdowns.forEach((dropdown) => {
      if (dropdown === except) return;
      dropdown.classList.remove("is-open");

      const button = dropdown.querySelector(".dropbtn");
      if (button) {
        button.setAttribute("aria-expanded", "false");
      }
    });
  }

  function initDropdowns() {
    if (!dropdowns.length) return;

    dropdowns.forEach((dropdown) => {
      const button = dropdown.querySelector(".dropbtn");
      if (!button) return;

      button.addEventListener("click", (event) => {
        if (window.innerWidth > 920) return;

        event.preventDefault();
        event.stopPropagation();

        const willOpen = !dropdown.classList.contains("is-open");
        closeAllDropdowns(dropdown);
        dropdown.classList.toggle("is-open", willOpen);
        button.setAttribute("aria-expanded", willOpen ? "true" : "false");
      });
    });
  }

  function initMobileMenu() {
    if (!menuToggle || !siteMenu) return;

    menuToggle.addEventListener("click", () => {
      const isOpen = siteMenu.classList.toggle("is-open");
      menuToggle.classList.toggle("is-open", isOpen);
      menuToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
      menuToggle.setAttribute("aria-label", isOpen ? "Закрити меню" : "Відкрити меню");

      if (!isOpen) {
        closeAllDropdowns();
      }
    });
  }

  function initOutsideClick() {
    document.addEventListener("click", (event) => {
      if (!event.target.closest(".dropdown")) {
        closeAllDropdowns();
      }

      const nav = document.querySelector(".nav");
      if (
        window.innerWidth <= 920 &&
        siteMenu &&
        siteMenu.classList.contains("is-open") &&
        nav &&
        !nav.contains(event.target)
      ) {
        siteMenu.classList.remove("is-open");
        menuToggle?.classList.remove("is-open");
        menuToggle?.setAttribute("aria-expanded", "false");
        menuToggle?.setAttribute("aria-label", "Відкрити меню");
      }
    });
  }

  function initEscapeClose() {
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeAllDropdowns();

        if (window.innerWidth <= 920 && siteMenu?.classList.contains("is-open")) {
          siteMenu.classList.remove("is-open");
          menuToggle?.classList.remove("is-open");
          menuToggle?.setAttribute("aria-expanded", "false");
          menuToggle?.setAttribute("aria-label", "Відкрити меню");
          menuToggle?.focus();
        }
      }
    });
  }

  function initMenuLinkClose() {
    document.querySelectorAll('#site-menu a[href]').forEach((link) => {
      link.addEventListener("click", () => {
        closeAllDropdowns();

        if (window.innerWidth <= 920 && siteMenu?.classList.contains("is-open")) {
          siteMenu.classList.remove("is-open");
          menuToggle?.classList.remove("is-open");
          menuToggle?.setAttribute("aria-expanded", "false");
          menuToggle?.setAttribute("aria-label", "Відкрити меню");
        }
      });
    });
  }

  function initSegmentCards() {
    const segCards = document.querySelectorAll(".segment-card");
    const segDetails = document.querySelectorAll(".segment-details");
    if (!segCards.length || !segDetails.length) return;

    segCards.forEach((card) => {
      card.addEventListener("click", () => {
        const targetId = card.getAttribute("data-target");
        if (!targetId) return;

        const next = document.getElementById(targetId);
        if (!next || next.classList.contains("active")) return;

        segCards.forEach((c) => c.classList.remove("active"));
        card.classList.add("active");

        segDetails.forEach((d) => d.classList.remove("active"));
        next.classList.add("active");
      });
    });
  }

  function initParallaxHero() {
    const hero = document.querySelector(".hero-inner");
    if (!hero) return;

    const onScroll = () => {
      const rect = hero.getBoundingClientRect();
      const vh = window.innerHeight || document.documentElement.clientHeight;
      const center = (rect.top + rect.height / 2 - vh / 2) / vh;
      const shift = Math.max(-0.5, Math.min(0.5, center));
      hero.style.transform = `translateY(${shift * -12}px)`;
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  function initDataHrefButtons() {
    const navButtons = document.querySelectorAll("[data-href]");
    if (!navButtons.length) return;

    navButtons.forEach((button) => {
      button.addEventListener("click", () => {
        const href = button.getAttribute("data-href");
        if (!href) return;
        window.location.href = href;
      });
    });
  }

  updateProgressBar();
  window.addEventListener("scroll", updateProgressBar, { passive: true });

  initFadeIn();
  initTheme();
  initDropdowns();
  initMobileMenu();
  initOutsideClick();
  initEscapeClose();
  initMenuLinkClose();
  initSegmentCards();
  initParallaxHero();
  initDataHrefButtons();
});