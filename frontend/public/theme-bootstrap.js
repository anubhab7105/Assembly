(() => {
  const pathname = window.location.pathname;
  if (pathname === "/" || pathname === "/science") {
    document.documentElement.classList.add("dark");
    return;
  }

  let theme = "dark";
  try {
    const saved = window.localStorage.getItem("assembly:theme");
    if (saved === "light" || saved === "dark") theme = saved;
  } catch {
    // Default to dark
  }

  document.documentElement.classList.toggle("dark", theme === "dark");
})();
