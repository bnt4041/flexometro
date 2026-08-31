# Dos etapas: `desarrollo` (lo de siempre, con recarga en caliente) y
# `produccion` (build estático servido por nginx).
#
# Hasta ahora producción corría `npm run dev`, y eso trae tres problemas que
# no se ven hasta que molestan: el JavaScript va sin minificar (arranque
# lento), el código fuente queda expuesto en los sourcemaps, y el service
# worker no se registra —está desactivado en desarrollo a propósito, o
# taparía la recarga en caliente—, así que la aplicación no se puede instalar
# en el móvil.

FROM node:22-alpine AS base
WORKDIR /app
# package.json primero para que instalar dependencias quede cacheado.
COPY package.json ./
RUN npm install
COPY . .

# --- Desarrollo -----------------------------------------------------------
FROM base AS desarrollo
EXPOSE 5173
CMD ["npm", "run", "dev"]

# --- Producción -----------------------------------------------------------
FROM base AS construir
# Las VITE_* se incrustan en el bundle al compilar, no se leen en tiempo de
# ejecución: tienen que estar aquí, no en el contenedor final.
ARG VITE_KEYCLOAK_URL
ARG VITE_KEYCLOAK_REALM
ARG VITE_KEYCLOAK_CLIENT_ID
ARG VITE_AUTH_BACKEND
ARG VITE_APP_VERSION
RUN npm run build

FROM nginx:alpine AS produccion
COPY --from=construir /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
