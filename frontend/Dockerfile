# Build de producción del frontend (Vue 3 + Vite) servido por nginx.
#
# VITE_API_URL es variable de BUILD (Vite la inyecta al compilar, no en runtime):
# - same-domain (recomendado, cero CORS): dejarla vacía → paths relativos; Traefik
#   enruta /api/v1 al backend y el resto a este contenedor.
# - subdominio propio: pasar la URL del backend como build arg en Dokploy.
#
# Dokploy: build type "Dockerfile", root `frontend/`, puerto del contenedor 80.

FROM node:20-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
