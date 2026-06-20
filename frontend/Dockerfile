FROM node:20-alpine

WORKDIR /app

# Copy package files first for layer caching
COPY package.json package-lock.json* ./

RUN npm install

COPY . .

RUN npm run build

RUN addgroup -g 10001 appgroup && \
    adduser -u 10001 -G appgroup -h /app -s /bin/sh -D appuser && \
    chown -R appuser:appgroup /app

USER appuser

EXPOSE 3000

CMD ["npm", "run", "start"]
