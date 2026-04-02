FROM node:22-alpine

WORKDIR /app

# Install deps first (cache layer)
COPY package*.json ./
RUN npm install

# Copy source
COPY . .

EXPOSE 5173

# Vite dev server — proxies /api to backend
CMD ["npx", "vite", "--host", "0.0.0.0", "--port", "5173"]
