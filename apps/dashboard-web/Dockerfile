## Stage 0: Build Stage ##
FROM node:20-alpine AS builder

# Accept build argument for app name
ARG APP_NAME=dashboard-web

WORKDIR /app

# Configure npm to accept self-signed certificates
RUN npm config set strict-ssl false

# Copy packages directory first (for workspace dependencies)
COPY packages/ /packages/

# Build the packages first
WORKDIR /packages/farmiq-api-client
RUN for i in 1 2 3 4 5; do \
      npm ci --include=dev && break; \
      if [ "$i" -eq 5 ]; then exit 1; fi; \
      sleep $((i * 5)); \
    done && (test -x ./node_modules/.bin/tsc || npm install --include=dev typescript@^5) && npm run build

WORKDIR /packages/contracts
RUN for i in 1 2 3 4 5; do \
      npm install && break; \
      if [ "$i" -eq 5 ]; then exit 1; fi; \
      sleep $((i * 5)); \
    done && npm run build

# Go back to app directory
WORKDIR /app

# Copy app package.json and install dependencies
COPY apps/${APP_NAME}/package.json ./
RUN npm cache clean --force && \
    for i in 1 2 3 4 5; do \
      npm install && break; \
      if [ "$i" -eq 5 ]; then exit 1; fi; \
      sleep $((i * 5)); \
    done

# Copy app source code (excluding node_modules)
COPY apps/${APP_NAME}/src ./src
COPY apps/${APP_NAME}/public ./public
COPY apps/${APP_NAME}/index.html ./index.html
COPY apps/${APP_NAME}/vite.config.ts ./vite.config.ts
COPY apps/${APP_NAME}/tsconfig.json ./tsconfig.json
COPY apps/${APP_NAME}/tsconfig.node.json ./tsconfig.node.json

# Build with commit ID
ARG VITE_COMMIT_ID
ENV VITE_COMMIT_ID=$VITE_COMMIT_ID
ENV NODE_OPTIONS="--max-old-space-size=4096"

# Use npx to run vite build
RUN npx vite build

## Stage 1: Development Stage ##
FROM node:20-alpine AS development

# Accept build argument for app name
ARG APP_NAME=dashboard-web

WORKDIR /app

# Configure npm to accept self-signed certificates
RUN npm config set strict-ssl false

# Copy packages directory first (for workspace dependencies)
COPY packages/ /packages/

# Build the packages first
WORKDIR /packages/farmiq-api-client
RUN for i in 1 2 3 4 5; do \
      npm ci --include=dev && break; \
      if [ "$i" -eq 5 ]; then exit 1; fi; \
      sleep $((i * 5)); \
    done && (test -x ./node_modules/.bin/tsc || npm install --include=dev typescript@^5) && npm run build

WORKDIR /packages/contracts
RUN for i in 1 2 3 4 5; do \
      npm install && break; \
      if [ "$i" -eq 5 ]; then exit 1; fi; \
      sleep $((i * 5)); \
    done && npm run build

# Go back to app directory
WORKDIR /app

# Copy app package.json and install dependencies
COPY apps/${APP_NAME}/package.json ./
RUN npm cache clean --force && \
    for i in 1 2 3 4 5; do \
      npm install && break; \
      if [ "$i" -eq 5 ]; then exit 1; fi; \
      sleep $((i * 5)); \
    done

# Copy app source code (excluding node_modules)
COPY apps/${APP_NAME}/src ./src
COPY apps/${APP_NAME}/public ./public
COPY apps/${APP_NAME}/index.html ./index.html
COPY apps/${APP_NAME}/vite.config.ts ./vite.config.ts
COPY apps/${APP_NAME}/tsconfig.json ./tsconfig.json
COPY apps/${APP_NAME}/tsconfig.node.json ./tsconfig.node.json

# Create entrypoint script inline
RUN mkdir -p /usr/local/bin && \
    echo '#!/bin/sh' > /usr/local/bin/docker-entrypoint.sh && \
    echo 'set -e' >> /usr/local/bin/docker-entrypoint.sh && \
    echo 'echo "[Entrypoint] Starting entrypoint script..."' >> /usr/local/bin/docker-entrypoint.sh && \
    echo 'if [ -f "/app/package.json" ]; then' >> /usr/local/bin/docker-entrypoint.sh && \
    echo '  echo "[Entrypoint] package.json found, checking dependencies..."' >> /usr/local/bin/docker-entrypoint.sh && \
    echo '  MISSING_DEPS=false' >> /usr/local/bin/docker-entrypoint.sh && \
    echo '  if [ ! -d "/app/node_modules/lucide-react" ]; then MISSING_DEPS=true; fi' >> /usr/local/bin/docker-entrypoint.sh && \
    echo '  if [ ! -d "/app/node_modules/@tanstack/react-query" ]; then MISSING_DEPS=true; fi' >> /usr/local/bin/docker-entrypoint.sh && \
    echo '  if [ ! -d "/app/node_modules/i18next-browser-languagedetector" ]; then MISSING_DEPS=true; fi' >> /usr/local/bin/docker-entrypoint.sh && \
    echo '  if [ ! -d "/app/node_modules" ] || [ ! "$(ls -A /app/node_modules 2>/dev/null)" ] || [ "$MISSING_DEPS" = "true" ]; then' >> /usr/local/bin/docker-entrypoint.sh && \
    echo '    echo "[Entrypoint] Installing/updating dependencies..."' >> /usr/local/bin/docker-entrypoint.sh && \
    echo '    npm cache clean --force && npm install' >> /usr/local/bin/docker-entrypoint.sh && \
    echo '    echo "[Entrypoint] Dependencies installed successfully"' >> /usr/local/bin/docker-entrypoint.sh && \
    echo '  fi' >> /usr/local/bin/docker-entrypoint.sh && \
    echo 'fi' >> /usr/local/bin/docker-entrypoint.sh && \
    echo 'echo "[Entrypoint] Executing command: $@"' >> /usr/local/bin/docker-entrypoint.sh && \
    echo 'exec "$@"' >> /usr/local/bin/docker-entrypoint.sh && \
    chmod +x /usr/local/bin/docker-entrypoint.sh

# Set environment for development
ENV NODE_ENV=development
ENV NODE_OPTIONS="--max-old-space-size=256"

# Expose port
EXPOSE 5173

# Use entrypoint to check and install dependencies
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Start development server
CMD ["npm", "run", "dev"]

## Stage 2: Production Stage ##
FROM nginx:1.27.4-alpine

# Accept build argument for app name
ARG APP_NAME=dashboard-web

# Install curl for health check
RUN apk add --no-cache curl

# Create non-root user if not exists
RUN adduser -D -H -u 101 -s /sbin/nologin nginx || true

# Copy build files and set ownership
COPY --from=builder --chown=nginx:nginx /app/build /usr/share/nginx/html

# Copy and set ownership of nginx configuration
COPY --chown=nginx:nginx apps/${APP_NAME}/nginx.conf /etc/nginx/nginx.conf

# Remove source maps for security
RUN find /usr/share/nginx/html -type f -name "*.map" -exec rm -f {} \;

# Set up permissions
RUN chmod 1777 /tmp && \
    chown -R nginx:nginx /var/cache/nginx /var/run /var/log/nginx && \
    touch /var/run/nginx.pid && \
    chown nginx:nginx /var/run/nginx.pid

# Switch to non-root user
USER nginx

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/ || exit 1

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
