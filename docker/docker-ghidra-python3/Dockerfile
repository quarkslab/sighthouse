ARG BASE_URL

FROM ${BASE_URL}/ghidraheadless:1.0.0

USER 0
RUN apt-get -y update && apt-get install --no-install-recommends -y libsqlite3-0 \
                                            curl \
                                            libfreetype6 \
                                            fontconfig \
                                            fonts-dejavu \
                                            python3-dev \
                                            python3-pip \
                                            make \
                                            autotools-dev \ 
                                            autoconf \
                                            build-essential \
                                            libc6-dev-i386 \
                                            gawk \
                                            bison \
                                            flex \
                                            git \
                                            bc \
                                            pahole \
                                            libelf-dev \
                                            elfutils \
                                            libssl-dev \
                                            gcc-aarch64-linux-gnu \
                                            gcc-arm-linux-gnueabi \
                                            gcc-mips-linux-gnu \
                                            gcc-mipsel-linux-gnu \
                                            && apt-get clean \
                                            && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives /tmp/* /var/tmp/*

# Use ghidra user
USER user
