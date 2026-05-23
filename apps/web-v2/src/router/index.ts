import { createRouter, createWebHistory } from "vue-router";
import HomeView from "../views/HomeView.vue";
import ReadinessView from "../views/ReadinessView.vue";
import AttemptsView from "../views/AttemptsView.vue";

// The SPA is mounted under `/v2/` by the Python server (see core.py T-036
// static handler). vue-router's history base must match so deep links such as
// `/v2/readiness` resolve correctly when the browser refreshes.
export const router = createRouter({
  history: createWebHistory("/v2/"),
  routes: [
    { path: "/", name: "home", component: HomeView },
    { path: "/readiness", name: "readiness", component: ReadinessView },
    { path: "/attempts", name: "attempts", component: AttemptsView },
    { path: "/:pathMatch(.*)*", redirect: { name: "home" } },
  ],
});

export default router;
