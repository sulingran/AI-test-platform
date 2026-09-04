FROM python:3.12-slim-bookworm

ARG APT_MIRROR=deb.debian.org

RUN sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        default-jre-headless \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        libzbar0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Browser automation and report generation are part of the existing backend dependency set.
RUN playwright install --with-deps chromium

COPY manage.py .
COPY backend/ backend/
COPY apps/ apps/
COPY docs/tester.md docs/tester.md
COPY docs/tester_pro.md docs/tester_pro.md
COPY docs/prompts/ docs/prompts/
COPY templates/ templates/

RUN mkdir -p static_files media logs

COPY backend/entrypoint.sh /entrypoint.sh
COPY backend/scheduler-loop.sh /scheduler-loop.sh
RUN chmod +x /entrypoint.sh /scheduler-loop.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "backend.asgi:application"]
