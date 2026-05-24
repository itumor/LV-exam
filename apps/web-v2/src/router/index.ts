import { createRouter, createWebHistory } from "vue-router";
import HomeView from "../views/HomeView.vue";
import ReadinessView from "../views/ReadinessView.vue";
import AttemptsView from "../views/AttemptsView.vue";
import TutorDashboardView from "../views/TutorDashboardView.vue";
import LeaderboardsView from "../views/LeaderboardsView.vue";

// The SPA is mounted under `/v2/` by the Python server (see core.py T-036
// static handler). vue-router's history base must match so deep links such as
// `/v2/readiness` resolve correctly when the browser refreshes.
export const router = createRouter({
  history: createWebHistory("/v2/"),
  routes: [
    { path: "/", name: "home", component: HomeView },
    { path: "/readiness", name: "readiness", component: ReadinessView },
    { path: "/attempts", name: "attempts", component: AttemptsView },
    // T-042 tutor dashboard — gated server-side on the tutor-plan org
    // membership; the link surfaces in the nav for every user but
    // calling the API as a non-tutor returns 403.
    { path: "/tutor", name: "tutor", component: TutorDashboardView },
    // T-052 leaderboards (weekly / friends / by-city) — server-side
    // privacy filter strips PII; the view renders only display_name + XP.
    { path: "/leaderboards", name: "leaderboards", component: LeaderboardsView },
    { path: "/:pathMatch(.*)*", redirect: { name: "home" } },
  ],
});

export default router;
