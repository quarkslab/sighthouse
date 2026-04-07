#FROM openjdk:21-jdk-slim
FROM eclipse-temurin:21-jdk-noble

LABEL version="1.0.3"
LABEL name="ghidraheadless"

ENV VERSION 11.4.1_PUBLIC
ENV DL https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_11.4.1_build/ghidra_11.4.1_PUBLIC_20250731.zip
ENV GHIDRA_SHA 59b657c39c2113d65e591c1087b77d85f6f7a11e97f2f4a0c9e7188510d07ea0

USER 0
RUN apt-get update && apt-get install -y wget unzip --no-install-recommends \
    && wget --progress=bar:force -O /tmp/ghidra.zip ${DL} \
    && echo "$GHIDRA_SHA /tmp/ghidra.zip" | sha256sum -c - \
    && unzip /tmp/ghidra.zip \
    && mv ghidra_${VERSION} /ghidra \
    && chmod +x /ghidra/ghidraRun \
    && echo "===> Clean up unnecessary files..." \
    && apt-get purge -y --auto-remove wget unzip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives /tmp/* /var/tmp/* /ghidra/docs /ghidra/Extensions/Eclipse /ghidra/licenses

# Remove ubuntu user
RUN userdel ubuntu
# Create a ghidra user
RUN useradd --create-home -u 1000 -m user && chown -R user:user /ghidra
USER user

WORKDIR /work

COPY entrypoint.sh /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
