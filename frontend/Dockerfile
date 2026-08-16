FROM node:22-alpine

WORKDIR /app

# package.json primero para que instalar dependencias quede cacheado.
COPY package.json ./
RUN npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev"]
