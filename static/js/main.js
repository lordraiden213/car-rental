// Function to initialize the mobile menu
function initMenu() {
    const menuBtn = document.getElementById("menu-btn");
    const navLinks = document.getElementById("nav-links");
    const menuBtnIcon = menuBtn.querySelector("i");
  
    if (menuBtn && navLinks && menuBtnIcon) {
      menuBtn.addEventListener("click", (e) => {
        navLinks.classList.toggle("open");
  
        const isOpen = navLinks.classList.contains("open");
        menuBtnIcon.setAttribute("class", isOpen ? "ri-close-line" : "ri-menu-line");
      });
  
      navLinks.addEventListener("click", (e) => {
        navLinks.classList.remove("open");
        menuBtnIcon.setAttribute("class", "ri-menu-line");
      });
    }
  }
  
  
  // Function to initialize ScrollReveal animations
  function initScrollReveal() {
    const scrollRevealOption = {
      distance: "50px",
      origin: "bottom",
      duration: 1000,
    };
  
    ScrollReveal().reveal(".header__image img", {
      ...scrollRevealOption,
      origin: "right",
    });
    ScrollReveal().reveal(".header__content h2", {
      ...scrollRevealOption,
      delay: 500,
    });
    ScrollReveal().reveal(".header__content h1", {
      ...scrollRevealOption,
      delay: 1000,
    });
    ScrollReveal().reveal(".header__content .section__description", {
      ...scrollRevealOption,
      delay: 1500,
    });
  
    ScrollReveal().reveal(".header__form form", {
      ...scrollRevealOption,
      delay: 2000,
    });
  
    ScrollReveal().reveal(".about__card", {
      ...scrollRevealOption,
      interval: 500,
    });
  
    ScrollReveal().reveal(".choose__image img", {
      ...scrollRevealOption,
      origin: "left",
    });
    ScrollReveal().reveal(".choose__content .section__header", {
      ...scrollRevealOption,
      delay: 500,
    });
    ScrollReveal().reveal(".choose__content .section__description", {
      ...scrollRevealOption,
      delay: 1000,
    });
    ScrollReveal().reveal(".choose__card", {
      duration: 1000,
      delay: 1500,
      interval: 500,
    });
  
    ScrollReveal().reveal(".subscribe__image img", {
      ...scrollRevealOption,
      origin: "right",
    });
    ScrollReveal().reveal(".subscribe__content .section__header", {
      ...scrollRevealOption,
      delay: 500,
    });
    ScrollReveal().reveal(".subscribe__content .section__description", {
      ...scrollRevealOption,
      delay: 1000,
    });
    ScrollReveal().reveal(".subscribe__content form", {
      ...scrollRevealOption,
      delay: 1500,
    });
  }
  
  // Function to initialize the deals tabs
  function initDealsTabs() {
    const tabs = document.querySelector(".deals__tabs");
  
    if (tabs) {
      tabs.addEventListener("click", (e) => {
        const tabContents = document.querySelectorAll(
          ".deals__container .tab__content"
        );
        Array.from(tabs.children).forEach((item) => {
          if (item.dataset.id === e.target.dataset.id) {
            item.classList.add("active");
          } else {
            item.classList.remove("active");
          }
        });
        tabContents.forEach((item) => {
          if (item.id === e.target.dataset.id) {
            item.classList.add("active");
          } else {
            item.classList.remove("active");
          }
        });
      });
    }
  }
  
  // Function to initialize the Swiper carousel
  function initSwiper() {
    const swiper = new Swiper(".swiper", {
      slidesPerView: 3,
      spaceBetween: 20,
      loop: true,
    });
  }
  
  // Function to initialize all scripts
  function initScripts() {
    initMenu();
    initScrollReveal();
    initDealsTabs();
    initSwiper();
  }
  
  // Wait for the DOM to load before initializing scripts
  document.addEventListener("DOMContentLoaded", initScripts);
  
  // Reinitialize scripts after dynamically loading sections
  function loadSection(file, elementId) {
    fetch(file)
      .then((response) => response.text())
      .then((data) => {
        document.getElementById(elementId).innerHTML = data;
        initScripts(); // Reinitialize scripts after loading new content
      })
      .catch((error) => console.error("Error loading section:", error));
  }

  document.addEventListener("DOMContentLoaded", function () {
    const buttons = document.querySelectorAll(".deals__tabs .btn");
    const tabs = document.querySelectorAll(".tab__content");

    buttons.forEach(button => {
        button.addEventListener("click", function () {
            // Remove active class from all buttons
            buttons.forEach(btn => btn.classList.remove("active"));
            // Add active class to the clicked button
            this.classList.add("active");

            // Hide all tab contents
            tabs.forEach(tab => tab.classList.remove("active"));

            // Get the corresponding tab and show it
            const tabId = this.getAttribute("data-id");
            document.getElementById(tabId).classList.add("active");
        });
    });
});
  
  // Load sections dynamically
  //loadSection("sections/header.html", "header");
  //loadSection("sections/about.html", "about");
  //loadSection("sections/deals.html", "deals");
  //loadSection("sections/choose.html", "choose");
  //loadSection("sections/testimonials.html", "testimonials");
  //loadSection("sections/footer.html", "footer");