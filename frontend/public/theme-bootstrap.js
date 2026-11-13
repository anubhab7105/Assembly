(() => {
  let theme = null;

  try {
    const saved = window.localStorage.getItem("assembly:theme");
    if (saved === "light" || saved === "dark") theme = saved;
  } catch {
    // Browser storage is optional; use the system preference below.
  }

  if (!theme) {
    try {
      theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    } catch {
      theme = "light";
    }
  }

  document.documentElement.classList.toggle("dark", theme === "dark");
})();
