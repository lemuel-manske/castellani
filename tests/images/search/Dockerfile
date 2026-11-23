FROM node:24.16.0-alpine

WORKDIR /app

COPY services/search/package.json ./
COPY services/search/node_modules ./node_modules
COPY services/search/dist ./dist

USER node

EXPOSE 8082

CMD ["node", "dist/main.js"]
