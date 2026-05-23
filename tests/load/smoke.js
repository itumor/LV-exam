// k6 load smoke test for lvcodex
//
// Targets the lightest read-only endpoints to verify the app can serve
// 50 concurrent virtual users for 60 seconds without elevated p95
// latency or 5xx errors. Wired into ci-release.yml by T-006.
//
// Run locally against the dev server:
//   k6 run -e BASE_URL=http://localhost:4173 tests/load/smoke.js
//
// Run against a Fly preview from CI:
//   k6 run -e BASE_URL=https://lvcodex-pr-<N>.fly.dev tests/load/smoke.js

import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '15s', target: 25 }, // ramp up
    { duration: '30s', target: 50 }, // hold
    { duration: '15s', target: 0 },  // ramp down
  ],
  thresholds: {
    http_req_failed: ['rate<0.01'],      // < 1% requests fail
    http_req_duration: ['p(95)<1500'],   // 95% under 1.5s
    'http_req_duration{endpoint:healthz}': ['p(99)<500'],
  },
};

const BASE = __ENV.BASE_URL || 'http://localhost:4173';

const READ_ONLY_ROUTES = [
  { path: '/healthz', tag: 'healthz' },
  { path: '/latvian-a2-exam-app/', tag: 'index' },
  { path: '/api/exams/catalog', tag: 'catalog' },
  { path: '/api/practice-feed', tag: 'feed' },
];

export default function () {
  for (const route of READ_ONLY_ROUTES) {
    const res = http.get(`${BASE}${route.path}`, {
      tags: { endpoint: route.tag },
    });
    check(res, {
      [`${route.tag}: status is 2xx`]: (r) => r.status >= 200 && r.status < 300,
    });
  }
  sleep(1);
}
