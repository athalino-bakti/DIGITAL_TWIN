# syntax=docker/dockerfile:1
# Build produksi frontend J&C, disajikan nginx tanpa root (DIG-216). docs/DEPLOYMENT.md.

FROM node:22.12-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY . .
# API dipanggil lewat origin yang sama (/api/v1), diteruskan nginx ke container API.
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build


FROM nginxinc/nginx-unprivileged:1.29-alpine
# Alamat API di jaringan internal; diisikan ke template nginx saat container mulai.
ENV API_UPSTREAM=api:8000
# Header HSTS; kosong sampai situs dilayani lewat HTTPS (DIG-206).
ENV STRICT_TRANSPORT_SECURITY=""
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 8080
