odoo.define("tanatech_website.brand", [], function (require) {
  ("use strict");

  $(document).ready(function () {
    const swiper_client = new Swiper(".swiper_client", {
      direction: "horizontal",
      loop: true,
      loopAdditionalSlides: 7, // nombre total de logos
      spaceBetween: 20,
      speed: 2000,   
      autoplay: {
        delay: 3000,
        disableOnInteraction: false,
      },
      navigation: {
        nextEl: ".navigation-swip .fa-arrow-right",
        prevEl: ".navigation-swip .fa-arrow-left",
      },
      breakpoints: {
        300: { slidesPerView: 1.5 },
        600: { slidesPerView: 2.5 },
        900: { slidesPerView: 3 },
        1200: { slidesPerView: 5 },
      },
    });
  });
});