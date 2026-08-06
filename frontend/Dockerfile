FROM node:22-alpine AS builder
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime
COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
USER 101
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/"]
