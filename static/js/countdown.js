document.addEventListener("DOMContentLoaded", () => {
  const nodes = document.querySelectorAll("[data-countdown]");
  if (!nodes.length) {
    return;
  }

  nodes.forEach((node) => {
    const endValue = node.getAttribute("data-countdown");
    if (!endValue) {
      return;
    }

    const endTime = new Date(endValue);
    if (Number.isNaN(endTime.getTime())) {
      return;
    }

    let timer = null;
    const update = () => {
      const now = new Date();
      const diff = endTime.getTime() - now.getTime();
      if (diff <= 0) {
        node.textContent = "Offer ended";
        if (timer) {
          clearInterval(timer);
        }
        return;
      }

      const totalSeconds = Math.floor(diff / 1000);
      const days = Math.floor(totalSeconds / 86400);
      const hours = Math.floor((totalSeconds % 86400) / 3600);
      const minutes = Math.floor((totalSeconds % 3600) / 60);
      const seconds = totalSeconds % 60;
      const pad = (value) => String(value).padStart(2, "0");

      node.textContent = `${days}d ${pad(hours)}h ${pad(minutes)}m ${pad(seconds)}s`;
    };

    update();
    timer = setInterval(update, 1000);
  });
});
