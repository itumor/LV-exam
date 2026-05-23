import { createApp } from "vue";
import App from "./App.vue";
import { router } from "./router";
import { loadTenant } from "./composables/useTenant";
import "./styles.css";

// T-044: resolve the per-tenant theme (logo + colours + support contact)
// before mounting the app so the document already has the right brand
// palette on first paint. ``loadTenant`` swallows network failures and
// falls back to the bundled defaults so a backend outage cannot block
// the SPA from booting.
loadTenant().finally(() => {
  const app = createApp(App);
  app.use(router);
  app.mount("#app");
});
