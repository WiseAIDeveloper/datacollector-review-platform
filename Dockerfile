FROM python:3.10.10-slim
WORKDIR /app
COPY server.py settings.py capture_data.py ingestion.py delete_capture.py edit_capture.py quality_reviews.py /app/
COPY index.html coverage.html ingestion.html search.html quality.html capture_review.js image_zoom.js terminal.css frozen_panes.css /app/
ENV PYTHONDONTWRITEBYTECODE=1
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)" || exit 1
CMD ["python", "-u", "/app/server.py"]
