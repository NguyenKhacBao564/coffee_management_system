FROM node:20.19.4-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM node:20.19.4-alpine
WORKDIR /app
ENV NODE_ENV=production
ENV VITE_API_PROXY_TARGET=http://api:8000
COPY --from=build /app/package.json /app/package-lock.json ./
RUN npm ci --omit=dev
COPY --from=build /app/dist ./dist
COPY --from=build /app/vite.preview.config.js ./
EXPOSE 4173
CMD ["npm", "run", "preview"]
