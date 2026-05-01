FROM python:3.13-alpine

WORKDIR /app

COPY server.py /app/server.py
COPY latvian-a2-exam-app /app/latvian-a2-exam-app
COPY codex /app/codex

ENV PORT=80
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/latvian-a2-exam-app/' % os.getenv('PORT', '80'), timeout=3).read(1)"

CMD ["python", "server.py"]
