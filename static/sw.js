if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/static/sw.js")
    .then((reg) => {
        console.log("SW Registered");

        // FORCE reload after SW activates (important for install prompt)
        if (reg.active) {
            console.log("SW already active");
        } else {
            reg.addEventListener("updatefound", () => {
                console.log("SW installing...");
            });
        }
    })
    .catch(err => console.log("SW failed", err));
}