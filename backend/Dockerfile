# syntax=docker/dockerfile:1
# Image API J&C untuk staging dan produksi (DIG-216). Cara build dan menjalankan:
# docs/DEPLOYMENT.md.

FROM python:3.11-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /src
COPY pyproject.toml constraints.txt ./
COPY app ./app
# Pasang dependency dengan versi persis dari constraints.txt. Paket aplikasinya sendiri dilepas
# lagi, karena kode dijalankan langsung dari /app di image akhir.
RUN pip install -c constraints.txt . \
    && pip uninstall -y digital-twin-puti-api


FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    APP_ENV=production
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin jc
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

# Berjalan sebagai user biasa; kode dan dependency milik root sehingga tidak bisa diubah proses API.
USER jc
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --start-interval=2s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)"]

# Satu worker: batas login gagal (app/modules/auth/rate_limit.py) dihitung per proses.
# Alamat IP klien dibaca dari X-Forwarded-For hanya bila request datang dari alamat di
# FORWARDED_ALLOW_IPS (bawaan uvicorn 127.0.0.1); di compose diisi subnet jaringan internal.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
