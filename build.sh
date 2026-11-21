#!/bin/bash
set -e
cd "$(dirname "$0")"
NM=${NM:-/workspace/whale-nm/node_modules}
[ -x "$NM/.bin/esbuild" ] || NM=./node_modules
NODE_PATH=$NM $NM/.bin/esbuild src/main.tsx --bundle --minify --format=iife --target=es2019 --jsx=automatic --define:process.env.NODE_ENV='"production"' --outfile=app.js --log-level=warning
V=$(cat app.js | md5sum | cut -c1-10)
sed -i -E "s/app\.js\?v=[a-z0-9]+/app.js?v=$V/" index.html
echo "built app.js v=$V ($(wc -c < app.js) bytes)"
