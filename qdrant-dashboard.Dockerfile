FROM nginx:alpine
COPY nginx-qdrant-readonly.conf /etc/nginx/conf.d/default.conf 