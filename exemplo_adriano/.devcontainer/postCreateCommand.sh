# Instala o CfitsIO (fpack e funpack) e as dependencias python
sudo apt-get update && sudo apt-get install -y libcfitsio-bin --no-install-recommends \
&& sudo rm -rf /var/lib/apt/lists/* \
&& sudo apt-get purge -y \
&& pip install --upgrade pip && pip install --user -r requirements.txt


# Exemplo de Instalação de pacotes: https://www.ianlewis.org/en/creating-smaller-docker-images
# # for redis-sentinel see: http://redis.io/topics/sentinel
# ENV REDIS_VERSION 3.0.5
# ENV REDIS_DOWNLOAD_URL http://download.redis.io/releases/redis-3.0.5.tar.gz
# ENV REDIS_DOWNLOAD_SHA1 ad3ee178c42bfcfd310c72bbddffbbe35db9b4a6
# RUN buildDeps='gcc libc6-dev make' \
#     && set -x \
#     && apt-get update && apt-get install -y $buildDeps --no-install-recommends \
#     && rm -rf /var/lib/apt/lists/* \
#     && mkdir -p /usr/src/redis \
#     && curl -sSL "$REDIS_DOWNLOAD_URL" -o redis.tar.gz \
#     && echo "$REDIS_DOWNLOAD_SHA1 *redis.tar.gz" | sha1sum -c - \
#     && tar -xzf redis.tar.gz -C /usr/src/redis --strip-components=1 \
#     && rm redis.tar.gz \
#     && make -C /usr/src/redis \
#     && make -C /usr/src/redis install \
#     && rm -r /usr/src/redis \
#     && apt-get purge -y --auto-remove $buildDeps
