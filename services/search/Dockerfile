FROM node:24.16.0-alpine3.22 AS build

WORKDIR /srv/services/search

COPY services/search/package.json services/search/package-lock.json services/search/.npmrc ./
RUN npm ci

COPY services/search/tsconfig.json services/search/tsconfig.build.json ./
COPY services/search/src ./src
RUN npm run build

FROM node:24.16.0-alpine3.22 AS dependencies

WORKDIR /srv/services/search

COPY services/search/package.json services/search/package-lock.json services/search/.npmrc ./
RUN npm ci --omit=dev

FROM node:24.16.0-alpine3.22

ENV NODE_ENV=production

# Mirrors the repository layout so `contracts/` resolves at the same relative
# path from the compiled code as it does from the sources.
WORKDIR /srv/services/search

COPY contracts /srv/contracts
COPY --from=dependencies /srv/services/search/node_modules ./node_modules
COPY --from=build /srv/services/search/dist ./dist
COPY services/search/package.json ./

USER node

EXPOSE 8082

ENTRYPOINT ["node", "dist/main.js"]
