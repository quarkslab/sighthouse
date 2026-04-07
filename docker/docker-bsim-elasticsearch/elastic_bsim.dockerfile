ARG BASE_URL

FROM ${BASE_URL}/ghidraheadless:1.0.3 as ghidraheadless_layer
FROM docker.elastic.co/elasticsearch/elasticsearch:8.8.1

ARG ELASTIC_USERNAME
ARG ELASTIC_PASSWORD


USER 0
RUN chown 1000 /usr/share/elasticsearch/data
VOLUME /usr/share/elasticsearch/data

RUN usermod -l user elasticsearch
USER 1000

COPY --from=ghidraheadless_layer /ghidra/Extensions/Ghidra/ghidra_11.4.1_PUBLIC_20250731_BSimElasticPlugin.zip /tmp/BSimElasticPlugin.zip
RUN unzip /tmp/BSimElasticPlugin.zip
RUN /usr/share/elasticsearch/bin/elasticsearch-plugin install "file:///usr/share/elasticsearch/BSimElasticPlugin/data/lsh.zip"
RUN bin/elasticsearch-users useradd ${ELASTIC_USERNAME} -p ${ELASTIC_PASSWORD} -r superuser
