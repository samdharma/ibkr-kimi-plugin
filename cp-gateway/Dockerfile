FROM eclipse-temurin:17-jre

WORKDIR /opt/cp-gateway

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl unzip \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSLO https://download2.interactivebrokers.com/portal/clientportal.gw.zip \
    && unzip clientportal.gw.zip \
    && rm clientportal.gw.zip

WORKDIR /opt/cp-gateway/clientportal.gw

EXPOSE 5000

CMD ["bin/run.sh", "root/conf.yaml"]
