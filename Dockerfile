# Builder
FROM node:10-slim as builder

RUN apt-get update \
 && apt-get install -y git python build-essential libicu-dev

RUN git clone https://github.com/matrix-org/freebindfree.git \
 && cd freebindfree \
 && make

COPY ./package.json ./package.json
RUN npm install

# App
FROM node:10-slim

RUN apt-get update \
 && apt-get install -y sipcalc iproute2 openssl --no-install-recommends \
 && mkdir app

# python is to run the test bootstrap script, maybe rewrite it in JS to avoid?
RUN apt-get install -y python3 python3-requests

# Clean up install stuff
RUN rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /node_modules /app/node_modules
COPY --from=builder /freebindfree/libfreebindfree.so /app/libfreebindfree.so

COPY app.js /app/
COPY lib /app/lib
COPY docker /app/docker
COPY config /app/config
COPY scripts /app/scripts

ENV LD_PRELOAD /app/libfreebindfree.so

ENTRYPOINT ["/app/docker/start.sh"]
