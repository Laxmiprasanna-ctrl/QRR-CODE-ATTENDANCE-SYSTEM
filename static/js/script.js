// script.js - Global utilities

// Auto-dismiss flash messages after 4 seconds
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".flash-container .alert").forEach(el => {
    setTimeout(() => {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(el);
      bsAlert.close();
    }, 4000);
  });
});
