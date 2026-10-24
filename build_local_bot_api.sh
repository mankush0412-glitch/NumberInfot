#!/usr/bin/env bash
set -euo pipefail

apt-get update
apt-get install -y make git zlib1g-dev libssl-dev gperf cmake g++

cd /usr/local/src
if [ ! -d telegram-bot-api ]; then
  git clone --recursive https://github.com/tdlib/telegram-bot-api.git
else
  cd telegram-bot-api
  git pull
  git submodule update --init --recursive
  cd ..
fi

cd telegram-bot-api
rm -rf build
mkdir build
cd build
cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local ..
cmake --build . --target install -j"$(nproc)"

mkdir -p /var/lib/telegram-bot-api/temp
echo "✅ telegram-bot-api installed at /usr/local/bin/telegram-bot-api"
