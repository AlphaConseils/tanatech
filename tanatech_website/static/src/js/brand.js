// Attendre que le DOM soit complètement chargé
document.addEventListener("DOMContentLoaded", function () {
  const track = document.getElementById("carouselTrack");
  const prevBtn = document.getElementById("prevBtn");
  const nextBtn = document.getElementById("nextBtn");
  const indicators = document.querySelectorAll(".indicator");

  // Vérifier que tous les éléments existent
  if (!track || !prevBtn || !nextBtn || !indicators.length) {
    console.error("Un ou plusieurs éléments du carousel sont manquants");
    console.log("track:", track, "prevBtn:", prevBtn, "nextBtn:", nextBtn);
    return;
  }

  console.log("Carousel initialisé avec succès");

  let currentIndex = 0;
  const itemWidth = 180; // Approximate width including gap

  function updateCarousel(index) {
    currentIndex = index;
    track.scrollLeft = index * itemWidth;

    indicators.forEach((indicator, i) => {
      indicator.classList.toggle("active", i === index);
    });
  }

  prevBtn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    console.log("Bouton précédent cliqué");
    const newIndex = Math.max(0, currentIndex - 1);
    updateCarousel(newIndex);
  });

  nextBtn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    console.log("Bouton suivant cliqué");
    const maxIndex = indicators.length - 1;
    const newIndex = Math.min(maxIndex, currentIndex + 1);
    updateCarousel(newIndex);
  });

  indicators.forEach((indicator, index) => {
    indicator.addEventListener("click", () => {
      console.log("Indicateur cliqué:", index);
      updateCarousel(index);
    });
  });

  // Auto-scroll detection
  track.addEventListener("scroll", () => {
    const scrollPosition = track.scrollLeft;
    const newIndex = Math.round(scrollPosition / itemWidth);

    if (newIndex !== currentIndex) {
      currentIndex = newIndex;
      indicators.forEach((indicator, i) => {
        indicator.classList.toggle("active", i === currentIndex);
      });
    }
  });
});
