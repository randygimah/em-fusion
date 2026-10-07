# ======================= 
#  Build the React app     
# ======================= 

# Dependencies only. The `frontend-dev` service (ops-006) starts from here and
# mounts the working tree over /app, so it must not depend on that tree
# type-checking -- a tree mid-edit often does not, and `build` runs `tsc -b`.
FROM node:24-alpine AS deps

# Enable corepack so the pnpm version pinned in package.json is used
RUN corepack enable

# Set working dir
WORKDIR /app

# Copy dependency manifests
COPY package.json pnpm-lock.yaml ./

# Install project dependencies
RUN pnpm install --frozen-lockfile

FROM deps AS build

# Copy the rest of the application source code
COPY . .

# Build the static assets
RUN pnpm run build

# ==========================================
#  Serve Static Files with Nginx
# ==========================================

FROM nginxinc/nginx-unprivileged:1.25-alpine

# Copy the compiled React assets from the build stage to Nginx web root
COPY --from=build /app/dist /usr/share/nginx/html

# Copy a custom Nginx configuration to handle React routing properly
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose the unprivileged port nginx.conf listens on
EXPOSE 8080

# Start Nginx in the foreground
CMD ["nginx", "-g", "daemon off;"]