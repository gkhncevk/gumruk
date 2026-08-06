# Stage 1: frontend'i build et
FROM node:20-alpine AS frontend-build
WORKDIR /repo/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: backend'i calistir, build edilmis frontend'i statik sun
FROM node:20-alpine
WORKDIR /repo/backend
COPY backend/package.json backend/package-lock.json ./
RUN npm install --omit=dev
COPY backend/server.js ./
COPY --from=frontend-build /repo/frontend/dist /repo/frontend/dist

EXPOSE 3000
CMD ["node", "server.js"]
