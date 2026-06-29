ARG BASE_URL

FROM ${BASE_URL}/ghidraheadless:1.0.5

USER 0
RUN apt-get -y update && apt-get install --no-install-recommends -y libsqlite3-0 \
                                            curl \
                                            libfreetype6 \
                                            fontconfig \
                                            fonts-dejavu \
                                            python3-dev \
                                            python3-venv \
                                            python3-pip \
                                            make \
                                            cmake \
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
                                            libc6-dev-arm64-cross \
                                            gcc-arm-linux-gnueabi \
                                            libc6-dev-armhf-cross \
                                            libc6-dev-armel-cross \
                                            gcc-mips-linux-gnu \
                                            libc6-dev-mips32-mips64-cross \
                                            gcc-mipsel-linux-gnu \
                                            libc6-dev-mips64-mipsel-cross \
                                            && apt-get clean \
                                            && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives /tmp/* /var/tmp/*

# Use ghidra user
USER user
