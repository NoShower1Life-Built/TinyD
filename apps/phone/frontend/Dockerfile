FROM node:22-alpine AS build
WORKDIR /app
ARG VITE_PHONE_API=http://localhost:8080
ENV VITE_PHONE_API=$VITE_PHONE_API
COPY package.json tsconfig.json vite.config.ts ./
RUN npm install
COPY index.html .
COPY src ./src
RUN npm run build

FROM nginx:1.29-alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
