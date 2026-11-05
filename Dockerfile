FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    TEXTFOLD_DATA=/data TEXTFOLD_HOME=/config TEXTFOLD_AUTH=1 TEXTFOLD_WEB=1
WORKDIR /app
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY textfold ./textfold
RUN pip install --no-cache-dir . \
    && groupadd --gid 10001 textfold \
    && useradd --uid 10001 --gid textfold --no-create-home textfold \
    && mkdir -p /data /config \
    && chown textfold:textfold /data /config
USER textfold
EXPOSE 3017
CMD ["python", "-m", "textfold", "serve", "--web", "--auth", "--host", "0.0.0.0", "--port", "3017"]
