document.addEventListener("DOMContentLoaded", () => {
    const savedTheme = localStorage.getItem("theme") || "dark";
    if (savedTheme === "light") {
        document.documentElement.setAttribute("data-theme", "light");
    } else {
        document.documentElement.removeAttribute("data-theme");
    }

    document.querySelectorAll(".toggle-btn").forEach((btn) => {
        btn.addEventListener("click", (event) => {
            event.preventDefault();
            const currentTheme = document.documentElement.getAttribute("data-theme");
            if (currentTheme === "light") {
                document.documentElement.removeAttribute("data-theme");
                localStorage.setItem("theme", "dark");
            } else {
                document.documentElement.setAttribute("data-theme", "light");
                localStorage.setItem("theme", "light");
            }
        });
    });
});
