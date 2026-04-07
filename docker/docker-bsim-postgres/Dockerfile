ARG BASE_URL

FROM ${BASE_URL}/ghidraheadless:1.0.3

USER 0

RUN apt-get update && apt-get install -y \
  gcc \
  build-essential \
  autoconf \
  bison \
  flex \
  libreadline-dev \
  zlib1g-dev make \
  libssl-dev curl \
  --no-install-recommends \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives /tmp/* /var/tmp/* 

# pg_ctl command from Postgres can not be run as root
USER user

WORKDIR /ghidra/Ghidra/Features/BSim/support
RUN ./make-postgres.sh && mkdir /home/user/ghidra-data

COPY create_bsim_database.sh .
COPY pg_is_ready.sh .

RUN ./create_bsim_database.sh

COPY entrypoint.sh /entrypoint.sh

CMD ["tail", "-f", "/dev/null"]
