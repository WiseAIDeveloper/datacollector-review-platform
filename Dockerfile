FROM python:3.10.10-slim
WORKDIR /app
COPY app/ /app/app/
COPY web/ /app/web/
ENV PYTHONDONTWRITEBYTECODE=1
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)" || exit 1
CMD ["python", "-u", "-m", "app"]
