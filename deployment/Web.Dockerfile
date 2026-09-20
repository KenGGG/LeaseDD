FROM node:24-alpine AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend ./
RUN npm run build
FROM caddy:2.10-alpine
COPY --from=build /app/dist /srv
COPY deployment/Caddyfile /etc/caddy/Caddyfile
