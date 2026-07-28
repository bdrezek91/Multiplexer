# Build produkcyjny (Etap 10) - dwuetapowy: Node buduje statyczny bundle, Nginx go serwuje +
# reverse-proxuje /api/ do backendu (patrz nginx.conf). Do dev uzywaj `npm run dev` bezposrednio
# (patrz README.md) - ten Dockerfile jest tylko do wdrozenia produkcyjnego.
FROM node:22-alpine AS build
WORKDIR /app

# playwright to devDependency uzywana tylko do jednorazowych, recznych skryptow weryfikacyjnych
# (patrz docs/RAPORT_ETAP_8.md) - w obrazie produkcyjnym niepotrzebna, a jej postinstall probowalby
# pobierac binaria przegladarek, spowalniajac/psujac build.
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
