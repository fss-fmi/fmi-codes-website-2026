# Stage 1: build the React app
FROM node:22-alpine AS builder

WORKDIR /app

# Install from the committed lockfile. A fresh resolve of package.json crashes
# npm 10 (see ONBOARDING.md), so never fall back to a lockfile-less install.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# Stage 2: serve with nginx
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# H4: Grant the nginx user write access to the dirs it needs at runtime,
# then drop root.  nginx:alpine ships with a 'nginx' user (UID 101) for exactly
# this.  Reference the user by its numeric UID so Kubernetes' runAsNonRoot can
# verify the user is non-root at admission (it cannot verify a username alone).
RUN chown -R nginx:nginx /usr/share/nginx/html \
    && chown -R nginx:nginx /var/cache/nginx \
    && chown -R nginx:nginx /var/log/nginx \
    && touch /var/run/nginx.pid \
    && chown nginx:nginx /var/run/nginx.pid

USER 101

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
