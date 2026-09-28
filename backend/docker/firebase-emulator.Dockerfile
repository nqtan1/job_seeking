# The Firebase Emulator Suite needs a JRE even to run the Auth emulator alone,
# and there is no official lightweight image for it.
FROM node:20-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends default-jre-headless curl \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g firebase-tools@13

WORKDIR /emulator
COPY firebase.json .firebaserc ./

EXPOSE 9099 4000

CMD ["firebase", "emulators:start", "--only", "auth"]
