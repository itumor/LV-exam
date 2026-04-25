FROM nginx:1.27-alpine

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY latvian-a2-exam-app /usr/share/nginx/html/latvian-a2-exam-app
COPY codex /usr/share/nginx/html/codex

EXPOSE 80
