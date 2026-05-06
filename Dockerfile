FROM python:3.13-alpine

WORKDIR /app

RUN mkdir -p /app/data/.multica /app/data/uploads

COPY server.py /app/server.py
COPY billing.py /app/billing.py
COPY exam_bank.py /app/exam_bank.py
COPY latvian-a2-exam-app /app/latvian-a2-exam-app
COPY codex /app/codex
COPY latvian-listening-library/web /app/latvian-listening-library/web
COPY latvian-listening-library/data /app/latvian-listening-library/data

ENV PORT=80
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.getenv('PORT', '80'), timeout=3).read(1)"

CMD ["python", "server.py"]
