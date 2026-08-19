FROM node:20-bookworm-slim AS build

WORKDIR /app

COPY frontend/package*.json ./frontend/
WORKDIR /app/frontend
RUN npm ci

COPY frontend/ .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine

COPY --from=build /app/frontend/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
	CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/"]

CMD ["nginx", "-g", "daemon off;"]
