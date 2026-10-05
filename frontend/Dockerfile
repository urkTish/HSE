# Production image for `docker compose up` (service `frontend`, port 3000).
FROM node:22-alpine AS build
WORKDIR /app
# Rewrites to the API are resolved at build time; inside compose the backend is `backend:8000`.
ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=$BACKEND_URL NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build && npm prune --omit=dev

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=build /app ./
EXPOSE 3000
CMD ["npm", "run", "start"]
