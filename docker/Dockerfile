FROM eclipse-temurin:21-jre
ARG JENA_VERSION=5.5.0
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /jena /fuseki \
    && curl -fsSL https://repo1.maven.org/maven2/org/apache/jena/apache-jena/${JENA_VERSION}/apache-jena-${JENA_VERSION}.tar.gz | tar xz -C /jena --strip-components=1 \
    && curl -fsSL https://repo1.maven.org/maven2/org/apache/jena/apache-jena-fuseki/${JENA_VERSION}/apache-jena-fuseki-${JENA_VERSION}.tar.gz | tar xz -C /fuseki --strip-components=1
ENV JVM_ARGS="-Xmx4g"
EXPOSE 3030
CMD ["/fuseki/fuseki-server", "--tdb2", "--loc=/data/tdb", "--port=3030", "/football"]
