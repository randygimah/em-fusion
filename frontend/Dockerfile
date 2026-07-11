# ======================= 
#  Build the React app     
# ======================= 

FROM node:24-alpine AS build

# Enable corepack so the pnpm version pinned in package.json is used
RUN corepack enable

# Set working dir
WORKDIR /app

# Copy dependency manifests
COPY package.json pnpm-lock.yaml ./

# Install project dependencies
RUN pnpm install --frozen-lockfile

# Copy the rest of the application source code
COPY . .

# Build the static assets
RUN pnpm run build

# ==========================================
#  Serve Static Files with Nginx
# ==========================================
FROM nginx:1.25-alpine

# Copy the compiled React assets from the build stage to Nginx web root
COPY --from=build /app/dist /usr/share/nginx/html

# Copy a custom Nginx configuration to handle React routing properly
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 80 for web traffic
EXPOSE 80

# Start Nginx in the foreground
CMD ["nginx", "-g", "daemon off;"]