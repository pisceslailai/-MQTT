FROM node:22-alpine AS build
WORKDIR /app
ARG VITE_API_BASE=""
ARG VITE_SHOW_CONFIG_UI="true"
ENV VITE_API_BASE=$VITE_API_BASE
ENV VITE_SHOW_CONFIG_UI=$VITE_SHOW_CONFIG_UI
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
