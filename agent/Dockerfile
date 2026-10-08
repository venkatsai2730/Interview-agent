FROM node:20-slim

WORKDIR /app/agent

COPY agent/package.json agent/package-lock.json ./
RUN npm ci

COPY agent/ ./

# Compile TypeScript using project tsconfig
RUN npx tsc

EXPOSE 3001

CMD ["node", "dist/agent.js"]
