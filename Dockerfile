FROM node:22-slim AS node-stage

FROM python:3.12-slim

WORKDIR /app

# Copy Node.js binary from official image (no apt needed)
COPY --from=node-stage /usr/local/bin/node /usr/local/bin/node
COPY --from=node-stage /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=node-stage /usr/local/include/node /usr/local/include/node
COPY --from=node-stage /usr/local/share/doc/node /usr/local/share/doc/node
RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && \
    ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npx

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .

RUN python - <<'PY'
from pathlib import Path
path = Path("/app/start.sh")
path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
PY
RUN chmod +x /app/start.sh && mkdir -p var/logs var/cache var/run

ENV PORT=18765
ENV PYTHONUNBUFFERED=1

EXPOSE 18765

CMD ["sh", "/app/start.sh"]
